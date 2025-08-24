# rotation_core/io.py
from __future__ import annotations
import io
import re
import yaml
import pandas as pd

# 2-preference CSV required columns
REQUIRED_COLUMNS = [
    "player_id", "name", "season_minutes", "varsity_minutes_recent",
    "role_today", "energy_today",
    "off_pos_1", "off_pos_2",
    "def_pos_1", "def_pos_2",
    "notes",
]

OFF_PREFIX = "off_pos_"
DEF_PREFIX = "def_pos_"
NUMERIC_SUFFIX = re.compile(r".*_(\d+)$")

def detect_pref_cols(df: pd.DataFrame, category: str) -> list:
    """Return ordered preference columns that exist in the roster for the given category."""
    if category == "Offense":
        cols = [c for c in df.columns if c.startswith(OFF_PREFIX)]
    else:
        cols = [c for c in df.columns if c.startswith(DEF_PREFIX)]
    # sort by trailing number
    def suffix_num(c: str) -> int:
        m = NUMERIC_SUFFIX.match(c)
        return int(m.group(1)) if m else 99
    return sorted(cols, key=suffix_num)

def load_roster_csv(file_like) -> pd.DataFrame:
    df = pd.read_csv(file_like)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["player_id"] = df["player_id"].astype(str)
    df["name"] = df["name"].astype(str)
    for c in ["season_minutes", "varsity_minutes_recent"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    # Normalize preference columns that exist (2 each required, but allow extras)
    for c in detect_pref_cols(df, "Offense") + detect_pref_cols(df, "Defense"):
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
    empty = pd.DataFrame(columns=REQUIRED_COLUMNS)
    buf = io.StringIO()
    empty.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")

def load_formations_yaml(path: str):
    with open(path, "r", encoding="utf-8") as f:
        obj = yaml.safe_load(f) or {}
    for cat, fm in obj.items():
        for k, v in fm.items():
            if not isinstance(v, list):
                raise ValueError(f"Formation {cat}.{k} must be a list of positions.")
    return obj

def save_formations_yaml(path: str, text: str):
    _ = yaml.safe_load(text)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
