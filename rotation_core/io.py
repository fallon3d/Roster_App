# rotation_core/io.py
from __future__ import annotations
import io
import yaml
import pandas as pd

REQUIRED_COLUMNS = [
    "player_id", "name", "season_minutes", "varsity_minutes_recent",
    "role_today", "energy_today",
    "off_pos_1", "off_pos_2", "off_pos_3", "off_pos_4",
    "def_pos_1", "def_pos_2", "def_pos_3", "def_pos_4",
    "notes",
]

def load_roster_csv(file_like) -> pd.DataFrame:
    df = pd.read_csv(file_like)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    # normalize dtypes
    df["player_id"] = df["player_id"].astype(str)
    df["name"] = df["name"].astype(str)
    for c in ["season_minutes", "varsity_minutes_recent"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    for c in [f"off_pos_{i}" for i in range(1,5)] + [f"def_pos_{i}" for i in range(1,5)]:
        df[c] = df[c].fillna("").astype(str)
    df["role_today"] = df["role_today"].astype(str)
    df["energy_today"] = df["energy_today"].astype(str)
    df["notes"] = df["notes"].fillna("").astype(str)
    return df

def save_roster_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")

def generate_template_csv_bytes() -> bytes:
    import pandas as pd
    empty = pd.DataFrame(columns=REQUIRED_COLUMNS)
    buf = io.StringIO()
    empty.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")

def load_formations_yaml(path: str):
    with open(path, "r", encoding="utf-8") as f:
        obj = yaml.safe_load(f) or {}
    # Ensure structure {Category: {FormationName: [positions...]}}
    for cat, fm in obj.items():
        for k, v in fm.items():
            if not isinstance(v, list):
                raise ValueError(f"Formation {cat}.{k} must be a list of positions.")
    return obj

def save_formations_yaml(path: str, text: str):
    # Validate before saving
    _ = yaml.safe_load(text)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
