"""
Small, UI-agnostic helpers shared by app.py.
"""
from __future__ import annotations
from typing import Dict, List
from .models import Player

def by_id(roster: List[Player]) -> Dict[str, Player]:
    return {p.id: p for p in roster}

def display_name(p: Player) -> str:
    return f"{p.Name} ({p.RoleToday}/{p.EnergyToday})"
