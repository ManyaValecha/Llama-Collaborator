"""FastAPI entry point for Llama-Collaborator."""
import os
import secrets
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from llama_collaborator import provider
from llama_collaborator.adaptive import for_turn, label
from llama_collaborator.agents import collaborate
from llama_collaborator.changes import apply as apply_change, propose as propose_change, workspace_file
from llama_collaborator.memory import MemoryStore
from llama_collaborator.router import route_task
from llama_collaborator.verification import runner_available, syntax_check, syntax_check_local

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(Path(__file__).resolve().parent / ".env")
memory = MemoryStore(os.getenv("LLAMA_MEMORY_DB", str(ROOT / "backend" / "data" / "llama-collaborator.sqlite3")))
WORKSPACE = Path(os.getenv("LLAMA_WORKSPACE_ROOT", str(ROOT))).expanduser().resolve()
approvals: dict[str, float] = {}
app = FastAPI(title="Llama-Collaborator", version="0.2.0")


class Turn(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    project_id: str = Field(default="demo-project", min_length=1, max_length=100)
    user_id: str = Field(default="local-user", min_length=1, max_length=100)
    conversation_id: str = Field(default="local-session", min_length=1, max_length=100)
    image_data: str | None = Field(default=None, max_length=7_000_000)
    files_context: list[dict[str, str]] = Field(default_factory=list, max_length=8)


class MemoryInput(BaseModel):
    project_id: str = Field(default="demo-project", min_length=1, max_length=100)
    kind: str = Field(default="decision", min_length=1, max_length=40)
    content: str = Field(min_length=1, max_length=4000)
    source: str = Field(default="manual", max_length=40)
    source_ref: str = Field(default="", max_length=300)
    governs: str = Field(default="", max_length=1000)
    decision: str = Field(default="", max_length=4000)
    rejected: str = Field(default="", max_length=1000)
    reason: str = Field(default="", max_length=2000)
    future_implication: str = Field(default="", max_length=2000)
    confidence: int = Field(default=3, ge=1, le=5)
    status: str = Field(default="active", pattern="^(active|superseded|overridden|proposed)$")
    supersedes: str = Field(default="", max_length=40)
    depends: str = Field(default="", max_length=500)
    blocks: str = Field(default="", max_length=500)
    security_relevance: str = Field(default="unknown", pattern="^(unknown|low|medium|high|critical)$")
    review_after: str = Field(default="", max_length=10)


class ComfortInput(BaseModel):
    user_id: str = Field(default="local-user", min_length=1, max_length=100)
    comfort: int = Field(ge=1, le=5)


class FeedbackInput(BaseModel):
    user_id: str = Field(default="local-user", min_length=1, max_length=100)
    project_id: str = Field(default="demo-project", min_length=1, max_length=100)
    conversation_id: str = Field(min_length=1, max_length=100)
    rating: str = Field(pattern="^(too_complex|too_simple|helpful)$")


class VerificationApproval(BaseModel):
    approval_id: str = Field(min_length=20, max_length=100)


class CodeFile(BaseModel):
    path: str = Field(min_length=1, max_length=300)
    content: str = Field(max_length=40000)


class ChangeProposal(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    files: list[CodeFile] = Field(min_length=1, max_length=5)


class ChangeApproval(BaseModel):
    approval_id: str = Field(min_length=20, max_length=100)


@app.get("/api/health")
def health():
    base = os.getenv("MODEL_API_BASE", "https://api.meta.ai/v1")
    provider_name = "OpenRouter" if "openrouter.ai" in base else "Meta Model API"
    return {"status": "ok", "provider_configured": provider.configured(),
            "provider_mode": "model" if provider.configured() else "offline", "provider_name": provider_name,
            "model": provider.model_name(), "workspace": str(WORKSPACE),
            "verification_runner": runner_available()}


@app.post("/api/turn")
def turn(payload: Turn):
    if payload.image_data and not payload.image_data.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="Image must be a base64 data:image URL.")
    context = payload.text
    for item in payload.files_context:
        name = item.get("name", "attached file")[:200]
        content = item.get("content", "")[:12000]
        context += f"\n\nAttached source file: {name}\n```\n{content}\n```"
    memories = memory.search(payload.project_id, payload.text + " " + " ".join(x.get("content", "")[:500] for x in payload.files_context))
    route = route_task(payload.text, bool(payload.image_data), bool(payload.files_context), bool(memories))
    saved_comfort = memory.get_comfort(payload.user_id)
    comfort, adaptation_reason = for_turn(payload.text, saved_comfort)
    history = memory.get_history(payload.conversation_id)
    memory.save_message(payload.conversation_id, payload.project_id, payload.user_id, "user", payload.text)
    agents = collaborate(context, route, memories, comfort, payload.image_data, history)
    final_text = next((a["output"] for a in reversed(agents) if a["agent"] == "coach"), agents[-1]["output"] if agents else "No specialist was assigned.")
    memory.save_message(payload.conversation_id, payload.project_id, payload.user_id, "assistant", final_text)
    return {
        "route": {"intent": route.intent, "complexity": route.complexity, "agents": list(route.agents), "signals": list(route.signals)},
        "memory": memories, "comfort": comfort, "saved_comfort": saved_comfort,
        "adaptation": {"level": label(comfort), "reason": adaptation_reason}, "agents_result": agents,
        "conversation_id": payload.conversation_id,
        "verification": {"status": "not_run", "evidence": []},
        "note": "No code was executed or changed by this request.",
    }


@app.post("/api/demo/prepare")
def prepare_demo():
    """Return a clearly marked, local fixture and seed its decision for a guided run."""
    project_id = "demo-project"
    source_ref = "guided-demo-token-claims"
    existing = next((item for item in memory.list_memories(project_id) if item.get("source_ref") == source_ref), None)
    if existing is None:
        decision = "Reject tokens that omit required subject or expiry claims; consider a token expired when current time reaches its expiry."
        memory.remember(
            project_id, "security-invariant", decision,
            source="guided-demo", source_ref=source_ref, governs="examples/demo_token_claims.py",
            decision=decision, reason="Missing claims and an inclusive expiry boundary can admit malformed or expired tokens.",
            future_implication="Validate required claims explicitly and reject at now >= exp.", confidence=5,
            status="active", security_relevance="high",
        )
    fixture = ROOT / "examples" / "demo_token_claims.py"
    return {
        "project_id": project_id,
        "task": "Debug this token-claims code and its traceback risks. Reject missing subject/expiry claims and treat now >= exp as expired. Explain the fix like I am new to backend development.",
        "file": {"path": "examples/demo_token_claims.py", "content": fixture.read_text(encoding="utf-8")},
        "note": "Demo fixture: contains intentional defects; no code is changed by loading it.",
    }


@app.post("/api/memory")
def add_memory(payload: MemoryInput):
    data = payload.model_dump()
    project_id = data.pop("project_id")
    kind = data.pop("kind")
    content = data.pop("content")
    if not data["decision"]:
        data["decision"] = content
    try:
        return memory.remember(project_id, kind, content, **data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/memory/{project_id}")
def get_memory(project_id: str, q: str = ""):
    return {"items": memory.search(project_id, q, limit=20) if q else memory.list_memories(project_id)}


@app.get("/api/memory/{project_id}/health")
def memory_health(project_id: str):
    return memory.validate_memories(project_id)


@app.post("/api/profile/comfort")
def set_comfort(payload: ComfortInput):
    memory.set_comfort(payload.user_id, payload.comfort)
    return {"user_id": payload.user_id, "comfort": payload.comfort}


@app.get("/api/profile/comfort")
def get_comfort(user_id: str = "local-user"):
    comfort = memory.get_comfort(user_id)
    return {"user_id": user_id, "comfort": comfort, "level": label(comfort)}


@app.post("/api/feedback")
def feedback(payload: FeedbackInput):
    comfort = memory.record_feedback(payload.user_id, payload.project_id, payload.conversation_id, payload.rating)
    return {"comfort": comfort, "level": label(comfort), "saved": True}


@app.get("/api/conversations")
def conversations(user_id: str = "local-user"):
    return {"items": memory.list_conversations(user_id)}


@app.get("/api/conversations/{conversation_id}")
def conversation(conversation_id: str):
    return {"id": conversation_id, "messages": memory.get_history(conversation_id, limit=100)}


@app.get("/api/workspace/files")
def workspace_files(q: str = ""):
    blocked = {".git", ".venv", "venv", "node_modules", "__pycache__", ".env", "data", "outputs"}
    allowed = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".html", ".css", ".toml", ".yaml", ".yml"}
    paths = []
    for path in WORKSPACE.rglob("*"):
        if len(paths) >= 500:
            break
        relative = path.relative_to(WORKSPACE)
        if any(part in blocked or part.startswith(".") for part in relative.parts) or not path.is_file() or path.suffix.lower() not in allowed:
            continue
        if q and q.lower() not in relative.as_posix().lower():
            continue
        paths.append(relative.as_posix())
    return {"root": str(WORKSPACE), "files": paths}


@app.get("/api/workspace/file")
def workspace_file_content(path: str):
    try:
        target = workspace_file(WORKSPACE, path)
        content = target.read_text(encoding="utf-8")
    except (ValueError, UnicodeDecodeError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if len(content) > 40000:
        raise HTTPException(status_code=413, detail="File exceeds the 40 KB context limit.")
    return {"path": path, "content": content}


@app.post("/api/changes/propose")
def changes_propose(payload: ChangeProposal):
    try:
        return propose_change(WORKSPACE, payload.text, [item.model_dump() for item in payload.files])
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/changes/apply")
def changes_apply(payload: ChangeApproval):
    try:
        return apply_change(payload.approval_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/verification/preview")
def verification_preview():
    approval_id = secrets.token_urlsafe(24)
    approvals[approval_id] = time.time() + 300
    isolated = runner_available()
    description = ("Parse Python source in a network-disabled Docker container with the workspace mounted read-only."
                   if isolated else "Parse Python source on this host without importing or executing it. This syntax check is not sandbox-isolated.")
    return {"available": True, "approval_id": approval_id, "expires_in_seconds": 300,
            "command": "python-syntax", "isolated": isolated, "description": description}


@app.post("/api/verification/run")
def verification_run(payload: VerificationApproval):
    expiry = approvals.pop(payload.approval_id, None)
    if not expiry or expiry < time.time():
        raise HTTPException(status_code=403, detail="Approval missing, expired, or already used. Preview the action again.")
    return syntax_check(WORKSPACE) if runner_available() else syntax_check_local(WORKSPACE)


@app.get("/api")
def home():
    return FileResponse(ROOT / "index.html")


@app.get("/")
def root():
    return FileResponse(ROOT / "index.html")


@app.get("/{asset_path:path}")
def assets(asset_path: str):
    candidate = (ROOT / asset_path).resolve()
    if ROOT not in candidate.parents or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(candidate)
