# FILE: rotation_core/constants.py
from __future__ import annotations

# --- Positions (spec) ---
OFFENSE_POSITIONS = [
    "QB", "AB", "HB", "WR", "Slot", "C", "LG", "LT", "RG", "RT", "TE",
]

DEFENSE_53_POSITIONS = [
    "NT", "LDT", "RDT", "LDE", "RDE", "MLB", "LLB", "RLB", "LC", "RC", "S",
]

# Spec 4-4 (11 positions): LDT, RDT, LDE, RDE, LOLB, ROLB, LMLB, RMLB, LC, RC, S
DEFENSE_44_POSITIONS = [
    "LDT", "RDT", "LDE", "RDE", "LOLB", "ROLB", "LMLB", "RMLB", "LC", "RC", "S",
]

# --- Category fairness (for warnings/bias, not hard constraint) ---
CATEGORY_MAP = {
    # Offense
    "QB": "QB",
    "AB": "Backfield",
    "HB": "Backfield",
    "WR": "Wide",
    "Slot": "Wide",
    "TE": "TE",
    "C": "Interior Line",
    "LG": "Interior Line",
    "LT": "Interior Line",
    "RG": "Interior Line",
    "RT": "Interior Line",
    # Defense
    "NT": "DLine",
    "LDT": "DLine",
    "RDT": "DLine",
    "LDE": "DE",
    "RDE": "DE",
    "MLB": "Linebacker",
    "LLB": "Linebacker",
    "RLB": "Linebacker",
    "LOLB": "Linebacker",
    "ROLB": "Linebacker",
    "LMLB": "Linebacker",
    "RMLB": "Linebacker",
    "LC": "Secondary",
    "RC": "Secondary",
    "S": "Secondary",
}

CATEGORY_POSITIONS = {}
for pos, cat in CATEGORY_MAP.items():
    CATEGORY_POSITIONS.setdefault(cat, []).append(pos)


def positions_for(side: str, formation: str | None) -> list[str]:
    if side.lower() == "offense":
        return OFFENSE_POSITIONS[:]
    if side.lower() == "defense":
        if formation == "5-3":
            return DEFENSE_53_POSITIONS[:]
        return DEFENSE_44_POSITIONS[:]
    raise ValueError(f"Unknown side: {side}")
