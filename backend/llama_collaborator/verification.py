"""Approval-gated, Docker-isolated syntax check with machine-readable evidence."""
import json
import shutil
import subprocess
import ast
from pathlib import Path


def runner_available() -> bool:
    return shutil.which("docker") is not None


def syntax_check(workspace: Path) -> dict:
    if not runner_available():
        return {"status": "unavailable", "reason": "Docker is not installed or not on PATH.", "evidence": []}
    script = """import ast, json, pathlib, sys
root = pathlib.Path('/workspace')
excluded = {'.git', '.venv', 'venv', 'node_modules', '__pycache__'}
files = [p for p in root.rglob('*.py') if not any(part in excluded for part in p.parts)]
errors = []
for path in files:
    try:
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path.relative_to(root)))
    except (SyntaxError, UnicodeDecodeError) as error:
        errors.append(f'{path.relative_to(root)}: {error}')
print(json.dumps({'files_checked': len(files), 'errors': errors}))
sys.exit(bool(errors))
"""
    command = [
        "docker", "run", "--rm", "--network=none", "--cpus=1", "--memory=256m", "--pids-limit=64",
        "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m", "-v", f"{workspace}:/workspace:ro",
        "-w", "/workspace", "python:3.12-slim", "python", "-c", script,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "reason": "The isolated syntax check exceeded 90 seconds.", "evidence": []}
    except OSError as exc:
        return {"status": "unavailable", "reason": str(exc), "evidence": []}
    evidence = [{"command": "Isolated Python syntax check (Docker, network disabled)", "exit_code": result.returncode,
                 "stdout": result.stdout[-12000:], "stderr": result.stderr[-4000:]}]
    parsed = {}
    for line in reversed(result.stdout.splitlines()):
        try:
            parsed = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    count = parsed.get("files_checked", 0)
    status = "failed" if result.returncode else "passed" if count else "skipped"
    return {"status": status, "files_checked": count,
            "errors": parsed.get("errors", []), "evidence": evidence, "isolated": True,
            "scope": "Python syntax only; application code and tests were not executed."}


def syntax_check_local(workspace: Path) -> dict:
    """Parse Python sources without importing or executing them when Docker is absent."""
    excluded = {".git", ".venv", "venv", "node_modules", "__pycache__", "data", "outputs"}
    files = [p for p in workspace.rglob("*.py") if not any(part in excluded for part in p.parts)]
    errors = []
    for path in files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path.relative_to(workspace)))
        except (SyntaxError, UnicodeDecodeError) as error:
            errors.append(f"{path.relative_to(workspace)}: {error}")
        except OSError as error:
            errors.append(f"{path.relative_to(workspace)}: could not read file ({error})")
    status = "failed" if errors else "passed" if files else "skipped"
    return {"status": status, "files_checked": len(files),
            "errors": errors, "evidence": [{"command": "Python AST parse on host (no code execution)", "exit_code": int(bool(errors)), "files_checked": len(files)}],
            "isolated": False, "scope": "Python syntax only; application code and tests were not executed."}
