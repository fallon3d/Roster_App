from __future__ import annotations
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field

class Player(BaseModel):
    id: str
    Name: str
    Off1: str = ""
    Off2: str = ""
    Off3: str = ""
    Off4: str = ""
    Def1: str = ""
    Def2: str = ""
    Def3: str = ""
    Def4: str = ""
    RoleToday: Literal["Explorer","Connector","Driver"] = "Connector"
    EnergyToday: Literal["Low","Medium","High"] = "Medium"

class Settings(BaseModel):
    segment: Literal["Offense", "Defense"] = "Offense"
    def_form: Literal["5-3", "4-4"] = "5-3"

class Series(BaseModel):
    label: str
    positions: Dict[str, str] = Field(default_factory=dict)  # pos -> player_id or ""

class GameState(BaseModel):
    active: bool = False
    idx_cycle: int = 0         # planned series index pointer (for multiple series; with 1 series this cycles on 1)
    turn: int = 1
    played_counts: Dict[str, int] = Field(default_factory=dict)  # pid -> appearances
    played_counts_cat: Dict[str, Dict[str, int]] = Field(default_factory=dict)  # cat -> pid -> count
    history: List[Dict] = Field(default_factory=list)  # per series result snapshots
    pos_cycles: Dict[str, List[str]] = Field(default_factory=dict)  # pos -> [pid,...]
    pos_idx: Dict[str, int] = Field(default_factory=dict)  # pos -> idx pointer in cycle
    manual_overrides: Dict[int, Dict[str, str]] = Field(default_factory=dict)  # turn -> {pos: pid}
    fairness_debt_cat: Dict[str, Dict[str, int]] = Field(default_factory=dict)  # cat -> pid -> debt tokens
