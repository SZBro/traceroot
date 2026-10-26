"""All Jev calls (TypeSafe AI, decision-only model). Jev returns probabilities, never text.

- gate():  one `choice` question over the fixed categories -> is this an easy, common error?
- score(): one `choice` question over Claude's candidates -> an independent probability per cause.

No key or any API error -> None, and the pipeline falls back to Claude-only ranking.
Request/response format taken from the installed typesafe-sdk source (Choice, SystemOneResponse).
"""
import os
import sys

from . import config

# Each category says the cause is AT the crash site; anything else is other_or_complex. That way a
# confident gate answer (which points at the crash line) is only given when the crash line is right.
CATEGORY_CRITERIA = {
    "missing_import_or_module": "A module or name is used without being imported, or a package is not "
                                "installed. Fix: add the import at the top of the file.",
    "undefined_name_or_typo": "A variable or function name is misspelled or not defined, on the crash "
                              "line itself. Fix: correct the name on that line.",
    "wrong_type": "The crash line itself uses an obviously wrong type, and the value was not created by "
                  "some other function.",
    "none_value": "The crash line uses a value that is None, and the None comes from the same line "
                  "or the line just before it.",
    "wrong_arguments": "A call passes the wrong number or names of arguments to a function, visible "
                       "directly in the call. Fix: change the call.",
    "key_or_index_error": "A missing dict key or out-of-range index whose mistake is on the crash line "
                          "itself.",
    "file_not_found": "A file path that does not exist is opened. Fix: correct the path or create the file.",
    "syntax_error": "Invalid Python syntax at the reported line.",
    "other_or_complex": "The root cause is NOT on the crash line: the bad value (None, wrong type, wrong "
                        "key, wrong bound) was created in a different function or line and passed along, "
                        "or the cause is unclear or needs deeper reasoning.",
}

GATE_INSTRUCTIONS = ("A Python program crashed. Classify the ROOT CAUSE. Pick a simple category only if the "
                     "mistake is visible on the crash line itself and a one-line fix there would solve it. "
                     "If the bad value was produced elsewhere and passed along, pick other_or_complex.")

SCORE_INSTRUCTIONS = ("A Python program crashed. Each option is a proposed root cause. Which option is the "
                      "real root cause: the change that fixes the bug where it starts, not just where it crashes?")

_client = None
_disabled_reason: str | None = None
last_usage = {"input_tokens": 0, "output_tokens": 0}


def _notice(msg: str) -> None:
    print(f"traceroot: {msg}", file=sys.stderr)


def _get_client():
    """Create the SDK client once. Returns None (with a one-line notice) when Jev can't be used."""
    global _client, _disabled_reason
    if _client is not None or _disabled_reason:
        return _client
    if not os.environ.get("TYPESAFE_API_KEY", "").strip():
        _disabled_reason = "no TYPESAFE_API_KEY; Jev disabled, ranking by Claude only"
    else:
        try:
            from typesafe_sdk import TypeSafeClient
            _client = TypeSafeClient(model=config.JEV_MODEL, timeout=config.JEV_TIMEOUT_S)
        except Exception as e:                       # bad key format, missing SDK, ...
            _disabled_reason = f"Jev unavailable ({type(e).__name__}); ranking by Claude only"
    if _disabled_reason:
        _notice(_disabled_reason)
    return _client


def _ask_choice(state: dict, instructions: str, criteria: dict[str, str]) -> dict | None:
    """One choice question -> {choice, confidence, probabilities, input_tokens} or None on any error."""
    client = _get_client()
    if client is None:
        return None
    try:
        from typesafe_sdk import Choice
        res = client.system_one(state=state, questions={"q": Choice(instructions=instructions, criteria=criteria)})
        ans = res.choices["q"]
    except Exception as e:                           # TypeSafeError subclasses, KeyError, network...
        # Never echo the request or key; the exception type and status are enough.
        _notice(f"Jev call failed ({type(e).__name__}); continuing without it")
        return None
    usage = {"input_tokens": res.usage.input_tokens or 0, "output_tokens": res.usage.output_tokens or 0}
    for k in last_usage:
        last_usage[k] += usage[k]
    return {"choice": ans.choice, "confidence": ans.confidence,
            "probabilities": dict(ans.probabilities), **usage}


def _state(error_text: str, code_slices: str) -> dict:
    # Jev's input limit is ~64k tokens; pipeline already trims, this is a second guard.
    return {"traceback": error_text[-12000:], "code": code_slices[:80000]}


def gate(error_text: str, code_slices: str) -> dict | None:
    """-> {category, probability, confidence, probabilities} or None when Jev is unavailable."""
    ans = _ask_choice(_state(error_text, code_slices), GATE_INSTRUCTIONS,
                      {c: CATEGORY_CRITERIA[c] for c in config.CATEGORIES})
    if ans is None or ans["choice"] not in config.CATEGORIES:
        return None
    probs = {k: round(float(v), 4) for k, v in ans["probabilities"].items()}
    return {"category": ans["choice"], "probability": probs.get(ans["choice"], 0.0),
            "confidence": round(float(ans["confidence"]), 4), "probabilities": probs}


def score(error_text: str, code_slices: str, candidates: list[dict]) -> list[float] | None:
    """-> one probability per candidate (same order) or None when Jev is unavailable.
    Options are keyed by candidate id (titles might collide); the title + location is the description."""
    if not candidates:
        return None
    criteria = {}
    for c in candidates:
        where = f" ({c['file']}:{c['line']})" if c.get("file") and c.get("line") else ""
        criteria[c["id"]] = f"{c['title']}{where}"
    ans = _ask_choice(_state(error_text, code_slices), SCORE_INSTRUCTIONS, criteria)
    if ans is None:
        return None
    probs = ans["probabilities"]
    if set(probs) != set(criteria):
        _notice("Jev returned unexpected options; ignoring its scores")
        return None
    return [round(float(probs[c["id"]]), 4) for c in candidates]
