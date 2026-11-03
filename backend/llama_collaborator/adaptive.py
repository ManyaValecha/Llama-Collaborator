"""Explicit, reversible adaptation based on the saved comfort setting and user cues."""

LEVELS = {
    1: ("new", "Use plain language, define jargon, explain one step at a time, and include a tiny example."),
    2: ("exploring", "Use simple explanations, define unfamiliar terms, and connect each step to the outcome."),
    3: ("building", "Explain the reasoning beside the implementation and call out important tradeoffs."),
    4: ("confident", "Be concise; focus on design tradeoffs, edge cases, and the reasoning behind choices."),
    5: ("expert", "Assume strong engineering fluency; be brief and emphasize novel risks and non-obvious details."),
}


def for_turn(text: str, saved_level: int) -> tuple[int, str]:
    value = text.lower()
    beginner = ("i'm new", "i am new", "beginner", "explain simply", "step by step", "teach me", "first time")
    advanced = ("assume i'm experienced", "assume i am experienced", "be concise", "skip basics", "expert level", "just the diff")
    if any(cue in value for cue in beginner):
        return max(1, saved_level - 1), "Your request signals that a more guided explanation will help."
    if any(cue in value for cue in advanced):
        return min(5, saved_level + 1), "Your request signals that a more concise, advanced explanation will help."
    return saved_level, "Using your saved explanation preference."


def guidance(level: int) -> str:
    return LEVELS[max(1, min(5, level))][1]


def label(level: int) -> str:
    return LEVELS[max(1, min(5, level))][0]
