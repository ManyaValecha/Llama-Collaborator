"""Small, inspectable intent router. Model-assisted routing can be layered on later."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    intent: str
    agents: tuple[str, ...]
    complexity: str
    signals: tuple[str, ...] = ()


def route_task(text: str, has_image: bool = False, has_files: bool = False, has_memory: bool = False) -> Route:
    value = text.lower()
    agents = ["architect"]
    signals = []
    if has_image:
        signals.append("image")
    if has_files:
        signals.append("source_files")
    if has_memory:
        signals.append("project_memory")
    if any(word in value for word in ("security", "vulnerability", "review this", "audit", "threat model")):
        intent = "review"
        agents += ["debugger", "researcher", "verifier"]
        signals.append("security_or_review")
    elif any(word in value for word in ("error", "bug", "fail", "traceback", "debug", "exception")):
        intent = "debug"
        agents += ["debugger", "coder"]
    elif any(word in value for word in ("build", "implement", "write", "create", "code")):
        intent = "implementation"
        agents += ["coder"]
    elif any(word in value for word in ("docs", "documentation", "research", "latest", "reference")):
        intent = "research"
        agents += ["researcher"]
    elif any(word in value for word in ("design", "architecture", "plan", "tradeoff", "approach")):
        intent = "planning"
        agents += ["researcher"] if any(word in value for word in ("latest", "current", "compare")) else []
    else:
        intent = "engineering_question"
        agents += ["researcher"] if any(word in value for word in ("latest", "current", "documentation")) else []
    if has_image:
        agents.insert(0, "vision")
    if "verifier" not in agents:
        agents.append("verifier")
    agents.append("coach")
    complexity = "high" if len(text) > 500 or intent in {"debug", "implementation", "review"} or has_image or has_files else "normal"
    return Route(intent=intent, agents=tuple(agents), complexity=complexity, signals=tuple(signals))
