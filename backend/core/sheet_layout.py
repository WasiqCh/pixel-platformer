# backend/core/sheet_layout.py
"""Single source of truth for sprite-sheet layout.

These values were previously copy-pasted into BOTH backend/api/sheets.py and
backend/api/prompts.py (the copy even carried a "Match sheets.py constants"
comment). Two copies of a magic number is how sprite-sheet numbering silently
drifts apart between the sheet builder and the prompt composer.

Import from here instead. Nothing else should redefine these.
"""

# --- Character sheets -------------------------------------------------------
# Hard cap on actions packed into one character sheet.
# Spec (AI_Production_Asset_Workflow.md 3.2) allows 2-6.
CHAR_ACTIONS_PER_SHEET = 6

# --- Environment sheets -----------------------------------------------------
# How many variations get packed into ONE environment sheet.
# Confirmed by user (2026-09-18): an environment sheet is TWO STATES OF ONE
# LOCATION (e.g. before/after, day/night) - not several boxed locations.
# Was 9; every sheet was bloated with variations nobody asked for.
ENV_VARIATIONS_PER_SHEET = 2

# Action cells offered for a character sheet.
CHAR_CELLS = [
    "wide full-body neutral stance",
    "medium front three-quarter view",
    "medium profile walking",
    "close-up face neutral",
    "close-up face determined",
    "close-up face angry or afraid",
    "signature action pose",
    "holding signature props",
    "pure silhouette",
]

# Used to pad an environment sheet up to ENV_VARIATIONS_PER_SHEET when the
# extractor only found one state for a location. These are STATES (contrasting
# conditions), not shot types, so they read coherently next to an extracted
# variation like "supernatural storm-brooding waters".
ENV_FALLBACK_STATES = [
    "calm baseline condition, clear even light",
    "altered condition - dramatic shift in light, weather or damage",
]

# Variation cells offered for an environment sheet.
ENV_CELLS = [
    "wide establishing shot, dawn light",
    "wide shot, harsh noon light",
    "wide shot, dusk or night",
    "wide shot, bad weather",
    "medium shot of the key detail",
    "close texture study",
    "populated with characters",
    "empty and still",
    "silhouette / shape study",
]


def env_cells(limit: int = None) -> list:
    """Environment variation cells, capped at `limit` (default ENV_VARIATIONS_PER_SHEET)."""
    return ENV_CELLS[: (ENV_VARIATIONS_PER_SHEET if limit is None else limit)]


def char_sheet_count(total_actions: int = None) -> int:
    """How many character sheets are needed for `total_actions` actions."""
    import math
    n = len(CHAR_CELLS) if total_actions is None else total_actions
    return math.ceil(n / CHAR_ACTIONS_PER_SHEET)
