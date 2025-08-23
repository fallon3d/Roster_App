# FILE: rotation_core/suitability.py
from __future__ import annotations
from typing import List
from rotation_core.models import Player

PREFERENCE_WEIGHTS = [4, 3, 2, 1]  # 1st..4th


def strength_index(player: Player) -> int:
    return player.strength_index


def preference_rank(player: Player, position: str, side: str) -> int | None:
    prefs: List[str] = player.offense_preferences if side == "offense" else player.defense_preferences
    for i, p in enumerate(prefs):
        if p == position:
            return i + 1
    return None


def suitability(player: Player, position: str, side: str) -> int:
    pr = preference_rank(player, position, side)
    if pr is None:
        return 0
    w = PREFERENCE_WEIGHTS[pr - 1] if 0 < pr <= len(PREFERENCE_WEIGHTS) else 1
    return strength_index(player) * w
