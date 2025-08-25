from __future__ import annotations
from typing import Dict, List

# -----------------------------
# Positions (match HTML exactly)
# -----------------------------
OFF_POS: List[str] = ["QB", "AB", "HB", "WR", "Slot", "C", "LG", "LT", "RG", "RT", "TE"]

DEF_53_POS: List[str] = ["NT", "LDT", "RDT", "LDE", "RDE", "MLB", "LLB", "RLB", "LC", "RC", "S"]
DEF_44_POS: List[str] = ["LDT", "RDT", "LDE", "RDE", "LLB", "MLB", "RLB", "LC", "RC", "S"]

FORMATION_POSITION_MAP_44: Dict[str, str] = {
    "RILB": "MLB",
    "LILB": "MLB",
    "RMLB": "MLB",
    "LMLB": "MLB",
    "ROLB": "RLB",
    "LOLB": "LLB",
}

ALL_DEF = sorted(set(DEF_53_POS + DEF_44_POS))

# --------------------------------
# Category Fairness (exact mapping)
# --------------------------------
FAIRNESS_CATEGORIES: Dict[str, str] = {
    # Offense
    "QB": "QB",
    "AB": "Backfield", "HB": "Backfield",
    "WR": "Wide", "Slot": "Wide",
    "TE": "TE",
    "RT": "Interior Line", "RG": "Interior Line", "C": "Interior Line", "LG": "Interior Line", "LT": "Interior Line",

    # Defense
    "NT": "DLine", "RDT": "DLine", "LDT": "DLine",
    "RLB": "Linebacker", "MLB": "Linebacker", "LLB": "Linebacker",
    "RC": "Secondary", "LC": "Secondary", "S": "Secondary",
    "RDE": "DE", "LDE": "DE",
}

CATEGORY_POSITIONS: Dict[str, List[str]] = {
    "QB": ["QB"],
    "Backfield": ["AB", "HB"],
    "Wide": ["WR", "Slot"],
    "TE": ["TE"],
    "Interior Line": ["RT", "RG", "C", "LG", "LT"],
    "DLine": ["NT", "RDT", "LDT"],
    "Linebacker": ["RLB", "MLB", "LLB"],
    "Secondary": ["RC", "LC", "S"],
    "DE": ["RDE", "LDE"],
}

# ---------------------
# Roles / Energy / Weights
# ---------------------
ROLES = ["Explorer", "Connector", "Driver"]
ROLE_SCORE = {"Explorer": 1, "Connector": 2, "Driver": 3}

ENERGY = ["Low", "Medium", "High"]
ENERGY_SCORE = {"Low": 0, "Medium": 1, "High": 2}

PREF_WEIGHT = {1: 4, 2: 3, 3: 2, 4: 1}

CSV_HEADERS = ["Name", "Off1", "Off2", "Off3", "Off4", "Def1", "Def2", "Def3", "Def4"]
HEADER_ALIASES = {
    # canonical -> set of aliases
    "Name": {"name"},
    "Off1": {"off1", "offense 1"},
    "Off2": {"off2", "offense 2"},
    "Off3": {"off3", "offense 3"},
    "Off4": {"off4", "offense 4"},
    "Def1": {"def1", "defense 1"},
    "Def2": {"def2", "defense 2"},
    "Def3": {"def3", "defense 3"},
    "Def4": {"def4", "defense 4"},
}

# ---------------------
# Normalization helpers
# ---------------------
def normalize_name(s: str) -> str:
    if s is None:
        return ""
    s = s.strip()
    if not s:
        return ""
    return " ".join(w.capitalize() for w in s.split())

def normalize_pos(p: str) -> str:
    # Uppercase and map legacy -> core for 4–4 labels when present
    if not p:
        return ""
    p = p.strip().upper()
    if p in FORMATION_POSITION_MAP_44:
        return FORMATION_POSITION_MAP_44[p]
    return p
