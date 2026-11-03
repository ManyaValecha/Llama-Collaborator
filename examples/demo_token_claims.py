"""Small, intentionally flawed fixture for the guided debugging demo."""


def read_token_subject(claims: dict[str, object]) -> str:
    # BUG: malformed tokens raise an unhelpful KeyError.
    return str(claims["sub"])


def is_token_expired(claims: dict[str, object], now: int) -> bool:
    # BUG: exp is optional here, and the boundary second is treated as valid.
    return int(claims.get("exp", now + 3600)) < now
