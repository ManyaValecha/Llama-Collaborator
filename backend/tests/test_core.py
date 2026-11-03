import sqlite3
import tempfile
import unittest
import os
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import httpx

import main
from llama_collaborator.adaptive import for_turn, guidance
from llama_collaborator.memory import MemoryStore
from llama_collaborator import provider
from llama_collaborator.agents import _offline_note, collaborate
from llama_collaborator.router import route_task
from llama_collaborator.verification import syntax_check_local


class RouterTests(unittest.TestCase):
    def test_debug_route_uses_context_and_distinct_roles(self):
        route = route_task("Debug this traceback", has_files=True, has_memory=True)
        self.assertEqual(route.intent, "debug")
        self.assertEqual(route.signals, ("source_files", "project_memory"))
        self.assertEqual(len(route.agents), len(set(route.agents)))
        self.assertIn("debugger", route.agents)
        self.assertIn("coder", route.agents)
        self.assertIn("verifier", route.agents)

    def test_research_tool_is_only_routed_for_research_intent(self):
        self.assertEqual(route_task("What is a list?").intent, "engineering_question")
        self.assertEqual(route_task("Research the latest Python docs").intent, "research")


class AdaptiveTests(unittest.TestCase):
    def test_explicit_expertise_cues_adjust_only_the_current_turn(self):
        self.assertEqual(for_turn("I'm new, explain step by step", 3)[0], 2)
        self.assertEqual(for_turn("Assume I'm experienced; skip basics", 3)[0], 4)
        self.assertEqual(for_turn("Fix this", 3)[0], 3)

    def test_guidance_changes_by_comfort_level(self):
        self.assertIn("plain language", guidance(1))
        self.assertIn("fluency", guidance(5))

    def test_offline_guidance_changes_for_greeting_debug_planning_and_research(self):
        cases = [
            ("coach", "engineering_question", "hi", "Hi!"),
            ("coach", "debug", "Debug this Python traceback", "complete traceback"),
            ("coach", "planning", "Plan this feature", "acceptance check"),
            ("coach", "research", "Research current docs", "current documentation"),
        ]
        answers = [_offline_note(role, intent, task, False, 3) for role, intent, task, expected in cases]
        for answer, (_, _, _, expected) in zip(answers, cases):
            self.assertIn(expected.lower(), answer.lower())
        self.assertEqual(len(set(answers)), len(answers))

    def test_provider_failure_is_attempted_once_then_uses_task_specific_offline_guidance(self):
        route = route_task("Debug this Python traceback")
        with patch.object(provider, "configured", return_value=True), patch.object(
            provider, "complete", side_effect=TimeoutError("provider timed out")
        ) as complete:
            results = collaborate("Debug this Python traceback", route, [], 2)
        self.assertEqual(complete.call_count, 1)
        self.assertEqual(results[0]["status"], "error")
        self.assertTrue(all(item["mode"] == "offline_fallback" for item in results[1:]))
        self.assertIn("complete traceback", results[-1]["output"].lower())


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = MemoryStore(str(Path(self.temp.name) / "memory.sqlite3"))

    def tearDown(self):
        self.temp.cleanup()

    def test_structured_decisions_and_feedback_persist(self):
        record = self.store.remember(
            "p", "decision", "Require token expiry", decision="Require exp claim",
            source="manual", governs="auth.py", confidence=5, status="active",
            security_relevance="high",
        )
        self.assertEqual(record["decision"], "Require exp claim")
        self.assertEqual(len(self.store.search("p", "expiry token")), 1)
        self.assertEqual(self.store.record_feedback("u", "p", "c", "too_complex"), 2)
        self.assertEqual(self.store.get_comfort("u"), 2)

    def test_validator_reports_dependency_cycles(self):
        self.store.remember("p", "decision", "Decision A", decision="Decision A", depends="MEM-000002")
        self.store.remember("p", "decision", "Decision B", decision="Decision B", depends="MEM-000001")
        result = self.store.validate_memories("p")
        self.assertFalse(result["healthy"])
        self.assertTrue(any("cycle" in error for error in result["errors"]))

    def test_active_replacement_supersedes_old_decision_transactionally(self):
        old = self.store.remember("p", "decision", "Use option A", decision="Use option A")
        new = self.store.remember("p", "decision", "Use option B", decision="Use option B", supersedes="MEM-000001")
        self.assertEqual(old["id"], 1)
        self.assertEqual(new["supersedes"], "MEM-000001")
        rows = self.store.list_memories("p")
        self.assertEqual(rows[1]["status"], "superseded")
        self.assertTrue(self.store.validate_memories("p")["healthy"])

    def test_invalid_supersedes_reference_does_not_insert(self):
        with self.assertRaises(ValueError):
            self.store.remember("p", "decision", "New decision", supersedes="MEM-999999")
        self.assertEqual(self.store.list_memories("p"), [])

    def test_old_memory_database_is_migrated_without_dropping_records(self):
        path = Path(self.temp.name) / "old.sqlite3"
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE memories (id INTEGER PRIMARY KEY, project TEXT NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            db.execute("INSERT INTO memories(project,kind,content) VALUES('p','decision','Existing decision')")
        store = MemoryStore(str(path))
        rows = store.list_memories("p")
        self.assertEqual(rows[0]["content"], "Existing decision")
        self.assertEqual(rows[0]["status"], "active")


class VerificationTests(unittest.TestCase):
    def test_local_syntax_check_parses_without_executing_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "valid.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
            (root / "invalid.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
            result = syntax_check_local(root)
        self.assertEqual(result["files_checked"], 2)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["isolated"])
        self.assertTrue(result["errors"])


class ProviderTests(unittest.TestCase):
    def test_openrouter_responses_payload_uses_vision_and_search_without_live_network(self):
        captured = {}

        class FakeResponses:
            def create(self, **kwargs):
                captured.update(kwargs)
                annotation = SimpleNamespace(url="https://example.test/docs", title="Docs")
                block = SimpleNamespace(annotations=[annotation])
                return SimpleNamespace(output_text="Grounded answer", output=[SimpleNamespace(content=[block])])

        class FakeOpenAI:
            def __init__(self, **kwargs):
                captured["client"] = kwargs
                self.responses = FakeResponses()

        env = {
            "MODEL_API_KEY": "test-key",
            "MODEL_API_BASE": "https://openrouter.ai/api/v1",
            "MODEL_NAME": "meta-llama/llama-4-maverick",
        }
        with patch.dict(os.environ, env, clear=False), patch.object(provider, "OpenAI", FakeOpenAI):
            result = provider.complete("Review", "Inspect this", "data:image/png;base64,AA==", web_search=True)
        self.assertEqual(captured["client"]["base_url"], env["MODEL_API_BASE"])
        self.assertLessEqual(captured["client"]["timeout"], 20)
        self.assertEqual(captured["client"]["max_retries"], 0)
        self.assertEqual(captured["model"], env["MODEL_NAME"])
        self.assertFalse(captured["store"])
        self.assertNotIn("reasoning", captured)
        self.assertEqual(captured["tools"], [{"type": "openrouter:web_search"}])
        self.assertEqual(captured["input"][0]["content"][1]["type"], "input_image")
        self.assertEqual(result["citations"][0]["url"], "https://example.test/docs")


class DemoApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_memory = main.memory
        main.memory = MemoryStore(str(Path(self.temp.name) / "api.sqlite3"))
        transport = httpx.ASGITransport(app=main.app)
        self.client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        main.memory = self.original_memory
        self.temp.cleanup()

    async def test_guided_demo_is_repeatable_and_local_until_turn_is_submitted(self):
        first = await self.client.post("/api/demo/prepare")
        second = await self.client.post("/api/demo/prepare")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["file"]["path"], "examples/demo_token_claims.py")
        self.assertEqual(second.status_code, 200)
        health = (await self.client.get("/api/memory/demo-project/health")).json()
        self.assertEqual(health["count"], 1)
        self.assertTrue(health["healthy"])

    async def test_feedback_endpoint_updates_saved_preference(self):
        response = await self.client.post("/api/feedback", json={
            "conversation_id": "conversation-1", "rating": "too_complex",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["comfort"], 2)
        self.assertEqual((await self.client.get("/api/profile/comfort")).json()["comfort"], 2)

    async def test_memory_api_saves_structured_decisions_and_supersedes_predecessor(self):
        first = await self.client.post("/api/memory", json={
            "project_id": "p", "content": "Use short token TTL", "decision": "Use short token TTL",
            "reason": "Reduce token exposure", "governs": "auth.py", "confidence": 4,
            "security_relevance": "high",
        })
        second = await self.client.post("/api/memory", json={
            "project_id": "p", "content": "Use proof-key tokens", "decision": "Use proof-key tokens",
            "supersedes": "MEM-000001", "status": "active",
        })
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        memories = (await self.client.get("/api/memory/p")).json()["items"]
        self.assertEqual(memories[1]["status"], "superseded")
        self.assertEqual(memories[0]["supersedes"], "MEM-000001")
        self.assertTrue((await self.client.get("/api/memory/p/health")).json()["healthy"])

    async def test_offline_turn_runs_the_real_router_and_all_specialists_without_provider_calls(self):
        with patch.object(provider, "configured", return_value=False):
            response = await self.client.post("/api/turn", json={
                "text": "Debug this Python traceback. I am new to backend development.",
                "project_id": "demo-project", "user_id": "local-user",
                "conversation_id": "offline-run",
                "files_context": [{"name": "sample.py", "path": "sample.py", "content": "def f(): pass"}],
            })
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["route"]["intent"], "debug")
        self.assertEqual(result["comfort"], 2)
        self.assertEqual(result["verification"]["status"], "not_run")
        self.assertEqual([item["agent"] for item in result["agents_result"]], ["architect", "debugger", "coder", "verifier", "coach"])
        self.assertTrue(all(item["mode"] == "offline" for item in result["agents_result"]))
        history = (await self.client.get("/api/conversations/offline-run")).json()["messages"]
        self.assertEqual([item["role"] for item in history], ["user", "assistant"])


if __name__ == "__main__":
    unittest.main()
