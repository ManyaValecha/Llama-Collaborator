"""SQLite-backed project memory and lightweight learner profile."""
import sqlite3
import re
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any


class MemoryStore:
    def __init__(self, location: str):
        self.path = Path(location)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY, project TEXT NOT NULL, kind TEXT NOT NULL,
                content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source TEXT NOT NULL DEFAULT 'manual', source_ref TEXT NOT NULL DEFAULT '',
                governs TEXT NOT NULL DEFAULT '', decision TEXT NOT NULL DEFAULT '',
                rejected TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '',
                future_implication TEXT NOT NULL DEFAULT '', confidence INTEGER NOT NULL DEFAULT 3,
                status TEXT NOT NULL DEFAULT 'active', supersedes TEXT NOT NULL DEFAULT '',
                depends TEXT NOT NULL DEFAULT '', blocks TEXT NOT NULL DEFAULT '',
                security_relevance TEXT NOT NULL DEFAULT 'unknown', review_after TEXT NOT NULL DEFAULT ''
              );
              CREATE TABLE IF NOT EXISTS profiles (
                user_id TEXT PRIMARY KEY, comfort INTEGER NOT NULL DEFAULT 2,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
              );
              CREATE TABLE IF NOT EXISTS learning_feedback (
                id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, project TEXT NOT NULL,
                conversation_id TEXT NOT NULL, rating TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
              );
              CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY, project TEXT NOT NULL, user_id TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
              );
              CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY, conversation_id TEXT NOT NULL, role TEXT NOT NULL,
                content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(conversation_id) REFERENCES conversations(id)
              );
            """)
            existing = {row[1] for row in db.execute("PRAGMA table_info(memories)")}
            additions = {
                "source": "TEXT NOT NULL DEFAULT 'manual'", "source_ref": "TEXT NOT NULL DEFAULT ''",
                "governs": "TEXT NOT NULL DEFAULT ''", "decision": "TEXT NOT NULL DEFAULT ''",
                "rejected": "TEXT NOT NULL DEFAULT ''", "reason": "TEXT NOT NULL DEFAULT ''",
                "future_implication": "TEXT NOT NULL DEFAULT ''", "confidence": "INTEGER NOT NULL DEFAULT 3",
                "status": "TEXT NOT NULL DEFAULT 'active'", "supersedes": "TEXT NOT NULL DEFAULT ''",
                "depends": "TEXT NOT NULL DEFAULT ''", "blocks": "TEXT NOT NULL DEFAULT ''",
                "security_relevance": "TEXT NOT NULL DEFAULT 'unknown'", "review_after": "TEXT NOT NULL DEFAULT ''",
            }
            for column, declaration in additions.items():
                if column not in existing:
                    db.execute(f"ALTER TABLE memories ADD COLUMN {column} {declaration}")

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def search(self, project: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        words = [w.strip(".,!?():;\"'").lower() for w in query.split()]
        words = [w for w in words if len(w) > 3][:8]
        if not words:
            return []
        where = " OR ".join("lower(content || ' ' || decision || ' ' || governs) LIKE ?" for _ in words)
        with self._db() as db:
            rows = db.execute(
                f"SELECT id, kind, content, created_at, decision, reason, future_implication, governs, status, source, source_ref, confidence FROM memories WHERE project=? AND status='active' AND ({where}) ORDER BY id DESC LIMIT ?",
                [project, *(f"%{word}%" for word in words), limit],
            ).fetchall()
        return [dict(row) for row in rows]

    def remember(self, project: str, kind: str, content: str, **fields: Any) -> dict[str, Any]:
        columns = ("source", "source_ref", "governs", "decision", "rejected", "reason", "future_implication", "confidence", "status", "supersedes", "depends", "blocks", "security_relevance", "review_after")
        values = [fields.get(column, 3 if column == "confidence" else "active" if column == "status" else "unknown" if column == "security_relevance" else "") for column in columns]
        with self._db() as db:
            supersedes = fields.get("supersedes", "").strip()
            if supersedes:
                match = re.fullmatch(r"MEM-(\d{6})", supersedes)
                if not match:
                    raise ValueError("supersedes must reference an ID such as MEM-000014")
                old = db.execute("SELECT id,status FROM memories WHERE project=? AND id=?", (project, int(match.group(1)))).fetchone()
                if not old:
                    raise ValueError(f"Superseded decision {supersedes} does not exist in this project")
                if old["status"] not in {"active", "proposed"}:
                    raise ValueError(f"Decision {supersedes} is already {old['status']}")
                if fields.get("status", "active") == "active":
                    db.execute("UPDATE memories SET status='superseded' WHERE project=? AND id=?", (project, old["id"]))
            marks = ",".join("?" for _ in range(3 + len(columns)))
            cursor = db.execute(f"INSERT INTO memories(project,kind,content,{','.join(columns)}) VALUES({marks})", (project, kind, content, *values))
            row = db.execute("SELECT * FROM memories WHERE id=?", (cursor.lastrowid,)).fetchone()
        return dict(row)

    def list_memories(self, project: str) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute("SELECT * FROM memories WHERE project=? ORDER BY id DESC", (project,)).fetchall()
        return [dict(row) for row in rows]

    def validate_memories(self, project: str) -> dict[str, Any]:
        rows = self.list_memories(project)
        by_id = {f"MEM-{r['id']:06d}": r for r in rows}
        errors: list[str] = []
        warnings: list[str] = []
        graph: dict[str, list[str]] = {}
        for key, row in by_id.items():
            if not row['content'].strip() and not row['decision'].strip(): errors.append(f"{key}: decision content is empty")
            if row['status'] not in {"active", "superseded", "overridden", "proposed"}: errors.append(f"{key}: invalid status '{row['status']}'")
            if row['supersedes']:
                if row['supersedes'] not in by_id: errors.append(f"{key}: superseded decision {row['supersedes']} does not exist")
                elif row['status'] == 'active' and by_id[row['supersedes']]['status'] != 'superseded': warnings.append(f"{key}: active replacement does not point to a superseded decision")
            if not 1 <= row['confidence'] <= 5: errors.append(f"{key}: confidence must be 1–5")
            if row['review_after']:
                try: date.fromisoformat(row['review_after'])
                except ValueError: errors.append(f"{key}: review_after must be an ISO date")
                else:
                    if date.fromisoformat(row['review_after']) < date.today() and row['status'] == 'active': warnings.append(f"{key}: review date has passed")
            refs = [x.strip() for x in row['depends'].split(',') if x.strip()]
            graph[key] = refs
            for ref in refs:
                if ref not in by_id: errors.append(f"{key}: dependency {ref} does not exist")
                elif by_id[ref]['status'] == 'superseded' and row['status'] == 'active': warnings.append(f"{key}: active memory depends on superseded {ref}")
            for ref in [x.strip() for x in row['blocks'].split(',') if x.strip()]:
                if ref not in by_id: errors.append(f"{key}: blocked memory {ref} does not exist")
        visiting: set[str] = set(); visited: set[str] = set()
        def visit(node: str):
            if node in visiting: errors.append(f"dependency cycle includes {node}"); return
            if node in visited: return
            visiting.add(node)
            for nxt in graph.get(node, []):
                if nxt in graph: visit(nxt)
            visiting.remove(node); visited.add(node)
        for key in graph: visit(key)
        return {"count": len(rows), "errors": list(dict.fromkeys(errors)), "warnings": list(dict.fromkeys(warnings)), "healthy": not errors, "items": rows}

    def get_comfort(self, user_id: str) -> int:
        with self._db() as db:
            row = db.execute("SELECT comfort FROM profiles WHERE user_id=?", (user_id,)).fetchone()
        return int(row[0]) if row else 3

    def set_comfort(self, user_id: str, comfort: int) -> None:
        with self._db() as db:
            db.execute("INSERT INTO profiles(user_id,comfort) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET comfort=excluded.comfort, updated_at=CURRENT_TIMESTAMP", (user_id, comfort))

    def record_feedback(self, user_id: str, project: str, conversation_id: str, rating: str) -> int:
        delta = {"too_complex": -1, "too_simple": 1, "helpful": 0}[rating]
        with self._db() as db:
            db.execute("INSERT INTO learning_feedback(user_id,project,conversation_id,rating) VALUES(?,?,?,?)", (user_id, project, conversation_id, rating))
            current = db.execute("SELECT comfort FROM profiles WHERE user_id=?", (user_id,)).fetchone()
            comfort = int(current[0]) if current else 3
            comfort = max(1, min(5, comfort + delta))
            db.execute("INSERT INTO profiles(user_id,comfort) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET comfort=excluded.comfort, updated_at=CURRENT_TIMESTAMP", (user_id, comfort))
        return comfort

    def save_message(self, conversation_id: str, project: str, user_id: str, role: str, content: str) -> None:
        with self._db() as db:
            db.execute("INSERT INTO conversations(id,project,user_id) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET updated_at=CURRENT_TIMESTAMP", (conversation_id, project, user_id))
            db.execute("INSERT INTO messages(conversation_id,role,content) VALUES(?,?,?)", (conversation_id, role, content))

    def get_history(self, conversation_id: str, limit: int = 12) -> list[dict[str, str]]:
        with self._db() as db:
            rows = db.execute("SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?", (conversation_id, limit)).fetchall()
        return [dict(row) for row in reversed(rows)]

    def list_conversations(self, user_id: str) -> list[dict[str, str]]:
        with self._db() as db:
            rows = db.execute("SELECT c.id,c.project,c.updated_at,(SELECT content FROM messages m WHERE m.conversation_id=c.id ORDER BY m.id DESC LIMIT 1) AS last_message FROM conversations c WHERE c.user_id=? ORDER BY c.updated_at DESC LIMIT 30", (user_id,)).fetchall()
        return [dict(row) for row in rows]
