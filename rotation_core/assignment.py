# FILE: rotation_core/assignment.py
from rotation_core.hungarian import hungarian

def solve_rotation(roster_df, mode, formation, config):
    """
    Generate rotations given a roster DataFrame, mode, and configuration.
    """
    players = roster_df.to_dict(orient="records")
    positions = []
    if mode == "Offense":
        positions = ["QB", "AB", "HB", "WR", "Slot", "C", "LG", "LT", "RG", "RT", "TE"]
    elif mode == "Defense":
        if formation == "5-3":
            positions = ["NT", "LDT", "RDT", "LDE", "RDE", "MLB", "LLB", "RLB", "LC", "RC", "S"]
        else:  # "4-4"
            positions = ["LDT", "RDT", "LDE", "RDE", "LOLB", "ROLB", "LMLB", "RMLB", "LC", "RC", "S"]
    rotations = []
    num_rot = getattr(config, "num_rotations", 1)
    for r in range(num_rot):
        assignment = {}
        for i, pos in enumerate(positions):
            if i < len(players):
                player = players[i]
                assignment[pos] = player.get("Name", f"Player{i+1}")
            else:
                assignment[pos] = None
        rotations.append(assignment)
    return rotations
