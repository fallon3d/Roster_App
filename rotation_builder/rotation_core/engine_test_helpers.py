"""
Internal helpers for tests (not imported by app).
"""
from __future__ import annotations
from typing import List
from .models import Settings, Player
from .constants import normalize_pos

def quick_player(pid: str, name: str, offs: List[str], defs: List[str], role="Connector", energy="Medium") -> Player:
    def nz(i):
        return i if i is not None else ""
    o = [normalize_pos(x) for x in offs] + ["", "", "", ""]
    d = [normalize_pos(x) for x in defs] + ["", "", "", ""]
    return Player(
        id=pid, Name=name,
        Off1=o[0], Off2=o[1], Off3=o[2], Off4=o[3],
        Def1=d[0], Def2=d[1], Def3=d[2], Def4=d[3],
        RoleToday=role, EnergyToday=energy
    )
