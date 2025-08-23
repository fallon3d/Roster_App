# FILE: rotation_core/validation.py
from rotation_core.models import Player

def is_eligible(player: Player, position: str, side: str) -> bool:
    if side == "offense":
        return position in player.offense_preferences
    if side == "defense":
        return position in player.defense_preferences
    return False

def check_formation(roster_df, mode, formation):
    """
    Check if the roster can fill the required positions.
    """
    players = roster_df.to_dict(orient='records')
    needed = []
    if mode == "Offense":
        needed = ["QB", "AB", "HB", "WR", "Slot", "C", "LG", "LT", "RG", "RT", "TE"]
    elif mode == "Defense":
        if formation == "5-3":
            needed = ["NT", "LDT", "RDT", "LDE", "RDE", "MLB", "LLB", "RLB", "LC", "RC", "S"]
        else:
            needed = ["LDT", "RDT", "LDE", "RDE", "LOLB", "ROLB", "LMLB", "RMLB", "LC", "RC", "S"]
    for pos in needed:
        if not any(pos == p.get("Off1") or pos == p.get("Off2") or
                   pos == p.get("Off3") or pos == p.get("Off4") or
                   pos == p.get("Def1") or pos == p.get("Def2") or
                   pos == p.get("Def3") or pos == p.get("Def4")
                   for p in players):
            return False
    return True

def run_self_test():
    """
    Run a basic suite of self-tests.
    """
    results = {"tests": []}
    from rotation_core.fairness import compute_quotas, check_evenness
    quotas = compute_quotas(3, 8)
    results["tests"].append(("Quotas sum to 8", sum(quotas) == 8))
    results["tests"].append(("Evenness check", check_evenness(quotas)))
    from rotation_core.hungarian import hungarian
    matrix = [[1, 2], [2, 1]]
    assignment = hungarian(matrix)
    results["tests"].append(("Hungarian full matching", set(assignment) == {0, 1}))
    return results
