# rotation_core/ratings.py
from __future__ import annotations
import numpy as np
import pandas as pd
from .config import ROLE_SCORE, ENERGY_SCORE

def compute_strength_index_series(df: pd.DataFrame) -> pd.Series:
    role = df["role_today"].map(ROLE_SCORE).fillna(1)
    energy = df["energy_today"].map(ENERGY_SCORE).fillna(0)
    return (role * 10 + energy).astype(int)
