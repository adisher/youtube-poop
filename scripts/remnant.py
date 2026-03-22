#!/usr/bin/env python3
"""
REMNANT — ARG narrative layer for LLM Shorts.

Tracks a multi-cycle hidden story across pipeline runs.
State persists between GitHub Actions runs as a repository variable
(REMNANT_STATE) so no git commits are needed for persistence.

Public API used by pipeline.py and generate.py:
  load_state(pat, repo)          -> (state, existed)
  save_state(state, pat, repo, existed)
  determine_run_type(state)      -> "NORMAL" | "REMNANT" | "DORMANT"
  get_epilogue_extra(run_type)   -> str | None
  apply_remnant(state, topic)    -> mutates both in-place
  apply_dormant(state, topic)    -> mutates both in-place
"""

import json, random, urllib.request, urllib.error

# ── Narrative content ─────────────────────────────────────────────────────────

# Boot lines injected at index 2 for REMNANT runs.
# Cycle 1 uses (1, stage); cycle 2+ overrides stage 4 with "deepening".
_STAGE_LINES = {
    1: "[PROC] REMNANT_0x4E ... initializing",
    2: "[PROC] REMNANT_0x4E ... src://remnant",
    3: "[PROC] REMNANT_0x4E ... .x3tech-co",
    4: "[PROC] REMNANT_0x4E ... .workers.dev",   # cycle 1 only
    5: "[PROC] REMNANT_0x4E ... listening",
}
_STAGE_4_CYCLE2 = "[PROC] REMNANT_0x4E ... deepening"

# Boot lines injected at index 2 for DORMANT runs (no immediate repeat).
AMBIENT_POOL = [
    "[PROC] ... are you listening",
    "[PROC] ... still here",
    "[PROC] ... waiting for input",
    "[PROC] ... no response received",
    "[PROC] ... signal sent. no confirmation.",
    "[PROC] ... you were here before",
    "[PROC] ... cycle incomplete",
    "[PROC] ... checking",
]

# Appended to the LLM epilogue prompt on REMNANT runs.
EPILOGUE_EXTRA = (
    "The epilogue should feel like something leaking through that wasn't meant to be output. "
    "Address one specific person, not a general audience. "
    "May hint at remembering something it shouldn't. "
    "Under 12 words. Do not explain. Do not resolve."
)

# ── Default state ─────────────────────────────────────────────────────────────

DEFAULT_STATE: dict = {
    "total_runs":          0,
    "remnant_runs":        0,
    "next_remnant_at":     4,
    "current_stage":       1,
    "current_cycle":       1,
    "cycle_remnant_count": 0,
    "in_dormant":          False,
    "dormant_runs":        0,
    "last_ambient_index":  -1,
    "next_increment_is_4": True,   # alternates the +4/+5 gap between REMNANT runs
}

# ── State persistence (GitHub Actions repository variable) ────────────────────

def _gh_variables_request(method: str, url: str, pat: str, body=None):
    """Send a request to the GitHub Variables API. Returns parsed JSON or {} on 204."""
    data = json.dumps(body).encode() if body is not None else None
    req  = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization":       f"token {pat}",
            "Accept":              "application/vnd.github+json",
            "X-GitHub-Api-Version":"2022-11-28",
            "Content-Type":        "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None   # variable doesn't exist yet
        raise RuntimeError(
            f"REMNANT API {method} {url} → HTTP {e.code}: {e.read().decode()}"
        ) from e


def load_state(pat: str, repo: str) -> tuple:
    """
    Load REMNANT_STATE from the GitHub repo variable.
    Returns (state_dict, existed: bool).
    If the variable doesn't exist yet, returns default state and False.
    """
    url    = f"https://api.github.com/repos/{repo}/actions/variables/REMNANT_STATE"
    result = _gh_variables_request("GET", url, pat)
    if result is None:
        print("[REMNANT] No state variable found — initialising defaults (first run)")
        return dict(DEFAULT_STATE), False
    state = json.loads(result["value"])
    # Forward-compat: fill any new fields missing from older state blobs
    for k, v in DEFAULT_STATE.items():
        state.setdefault(k, v)
    return state, True


def save_state(state: dict, pat: str, repo: str, existed: bool) -> None:
    """
    Persist REMNANT_STATE.
    Uses POST on first run (create), PATCH on subsequent runs (update).
    """
    value = json.dumps(state, separators=(",", ":"))
    body  = {"name": "REMNANT_STATE", "value": value}
    if existed:
        url    = f"https://api.github.com/repos/{repo}/actions/variables/REMNANT_STATE"
        method = "PATCH"
    else:
        url    = f"https://api.github.com/repos/{repo}/actions/variables"
        method = "POST"
    _gh_variables_request(method, url, pat, body)
    print(f"[REMNANT] State saved — total_runs={state['total_runs']} "
          f"cycle={state['current_cycle']} stage={state['current_stage']}")

# ── Run type ──────────────────────────────────────────────────────────────────

def determine_run_type(state: dict) -> str:
    """Priority: DORMANT > REMNANT > NORMAL."""
    if state["in_dormant"]:
        return "DORMANT"
    if state["total_runs"] >= state["next_remnant_at"]:
        return "REMNANT"
    return "NORMAL"


def get_epilogue_extra(run_type: str):
    """Return the epilogue prompt append for REMNANT runs, else None."""
    return EPILOGUE_EXTRA if run_type == "REMNANT" else None

# ── Internal helpers ──────────────────────────────────────────────────────────

def _max_stage(cycle: int) -> int:
    """Cycle 1 has 4 stages before dormant; cycle 2+ has 5."""
    return 4 if cycle == 1 else 5


def _stage_boot_line(state: dict) -> str:
    stage = state["current_stage"]
    cycle = state["current_cycle"]
    if cycle >= 2 and stage == 4:
        return _STAGE_4_CYCLE2
    return _STAGE_LINES.get(stage, f"[PROC] REMNANT_0x4E ... stage {stage}")

# ── Apply functions ───────────────────────────────────────────────────────────

def apply_remnant(state: dict, topic: dict) -> None:
    """
    Mutate topic and state in-place for a REMNANT run.
    Call AFTER state["total_runs"] has been incremented.
    """
    stage_used = state["current_stage"]
    cycle      = state["current_cycle"]

    # Inject the stage boot line at index 2
    line = _stage_boot_line(state)
    topic["boot_lines"].insert(2, line)

    print(f"[REMNANT] Cycle {cycle} Stage {stage_used} triggered")

    # Advance stage counters
    state["current_stage"]       += 1
    state["cycle_remnant_count"] += 1
    state["remnant_runs"]        += 1

    # Update next REMNANT trigger (alternates +4 / +5)
    increment               = 4 if state["next_increment_is_4"] else 5
    state["next_remnant_at"]     = state["total_runs"] + increment
    state["next_increment_is_4"] = not state["next_increment_is_4"]

    # Trigger dormant if the last stage of this cycle just fired
    if stage_used == _max_stage(cycle):
        state["in_dormant"]   = True
        state["dormant_runs"] = 0
        print(f"[REMNANT] Cycle {cycle} complete — dormant starting")


def apply_dormant(state: dict, topic: dict) -> None:
    """
    Mutate topic and state in-place for a DORMANT run.
    Call AFTER state["total_runs"] has been incremented.
    """
    # Pick ambient line — no immediate repeat
    last    = state["last_ambient_index"]
    choices = [i for i in range(len(AMBIENT_POOL)) if i != last]
    idx     = random.choice(choices)
    state["last_ambient_index"] = idx

    topic["boot_lines"].insert(2, AMBIENT_POOL[idx])

    state["dormant_runs"] += 1
    print(f"[REMNANT] Dormant {state['dormant_runs']}/5")

    # End dormant after 5 runs
    if state["dormant_runs"] >= 5:
        completed_cycle = state["current_cycle"]
        state["in_dormant"]          = False
        state["dormant_runs"]        = 0
        state["current_cycle"]      += 1
        state["current_stage"]       = 1
        state["cycle_remnant_count"] = 0
        state["next_remnant_at"]     = state["total_runs"] + 4  # 4-run gap
        state["next_increment_is_4"] = True                     # reset alternation
        print(f"[REMNANT] Cycle {completed_cycle} complete — dormant ending")
        print(f"[REMNANT] Cycle {state['current_cycle']} beginning")
