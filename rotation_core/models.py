# rotation_core/models.py
from __future__ import annotations
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, validator

class AppConfig(BaseModel):
    total_series: int = 8
    varsity_penalty: float = 0.3
    evenness_cap_enabled: bool = True
    evenness_cap_value: int = 1
    preference_weights: List[float] = Field(default_factory=lambda: [1.0, 0.6])
    objective_lambda: float = 0.0
    objective_mu: float = 1.0
    random_seed: int = 42

    @validator("preference_weights")
    def _nonempty(cls, v):
        if not v or any((not isinstance(x, (float, int))) for x in v):
            raise ValueError("preference_weights must be a non-empty list of numbers")
        return v

class SolveResult(BaseModel):
    assignment: Optional[List[Dict[str, Optional[str]]]] = None
    error: Optional[str] = None
