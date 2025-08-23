# FILE: rotation_core/suitability.py
from rotation_core.models import Player

PREFERENCE_WEIGHTS = [4, 3, 2, 1]

def strength_index(player: Player) -> int:
    return player.strength_index

def calculate_suitability(player: Player, position: str, side: str) -> int:
    """
    Calculate the suitability score for assigning a player to a position.
    """
    prefs = []
    if side == "offense":
        prefs = player.offense_preferences
    elif side == "defense":
        prefs = player.defense_preferences
    if position in prefs:
        idx = prefs.index(position)
        weight = PREFERENCE_WEIGHTS[idx] if idx < len(PREFERENCE_WEIGHTS) else 1
        return player.strength_index * weight
    return 0
