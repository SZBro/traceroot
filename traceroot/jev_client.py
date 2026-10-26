"""All Jev calls (gate + score). Step 3 placeholder: both return None ("Jev unavailable"), so the
pipeline uses Claude-only ranking. The real calls arrive in build step 4."""


def gate(error_text: str, code_slices: str) -> dict | None:
    """-> {category, probability, confidence} or None when Jev is unavailable."""
    return None


def score(error_text: str, code_slices: str, candidates: list[dict]) -> list[float] | None:
    """-> one probability per candidate (same order) or None when Jev is unavailable."""
    return None
