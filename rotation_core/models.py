# FILE: rotation_core/models.py
from pydantic import BaseModel
from typing import List
import pandas as pd

class Player(BaseModel):
    Name: str
    Off1: str = None
    Off2: str = None
    Off3: str = None
    Off4: str = None
    Def1: str = None
    Def2: str = None
    Def3: str = None
    Def4: str = None
    RoleToday: str = None
    EnergyToday: str = None
    SatLast: int = 0
    IsPresent: int = 1

    @property
    def offense_preferences(self) -> List[str]:
        return [pos for pos in (self.Off1, self.Off2, self.Off3, self.Off4) if pos]

    @property
    def defense_preferences(self) -> List[str]:
        return [pos for pos in (self.Def1, self.Def2, self.Def3, self.Def4) if pos]

    @property
    def strength_index(self) -> int:
        role_score = {"Explorer": 1, "Connector": 2, "Driver": 3}.get(self.RoleToday, 0)
        energy_score = {"Low": 0, "Medium": 1, "High": 2}.get(self.EnergyToday, 0)
        return role_score * 10 + energy_score

class Roster(BaseModel):
    players: List[Player]

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame):
        players = [Player(**row) for _, row in df.iterrows()]
        return cls(players=players)

    def to_dataframe(self):
        return pd.DataFrame([p.dict() for p in self.players])

class Config(BaseModel):
    fairness: str         # "Fairness-first", "Balanced", "Win-push"
    formation: str = None # e.g. "5-3", "4-4", or None for offense
    num_rotations: int = 1
    max_consecutive: int = 0

class ExceptionLog(BaseModel):
    exceptions: List[str] = []
