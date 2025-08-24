# rotation_core/constraints.py
from __future__ import annotations
from typing import Dict, List, Optional, Tuple, Set
import numpy as np
import pandas as pd

from .config import ROLE_SCORE, ENERGY_SCORE
from .io import detect_pref_cols

ALLOWED_ROLES = set(ROLE_SCORE.keys())
ALLOWED_ENERGIES = set(ENERGY_SCORE.keys())

def validate_roster(df: pd.DataFrame) -> List[str]:
    errs = []
    required = [
        "player_id","name","season_minutes","varsity_minutes_recent",
        "role_today","energy_today",
        "off_pos_1","off_pos_2",
        "def_pos_1","def_pos_2",
        "notes"
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        errs.append(f"Missing required columns: {missing}")
        return errs

    if df["player_id"].astype(str).duplicated().any():
        dupes = df[df["player_id"].astype(str).duplicated()]["player_id"].astype(str).tolist()
        errs.append(f"Duplicate player_id detected: {', '.join(dupes)}")

    bad_roles = df[~df["role_today"].isin(ALLOWED_ROLES)]
    if not bad_roles.empty:
        rows = ", ".join(str(i+2) for i in bad_roles.index.tolist())
        errs.append(f"Invalid role_today at rows: {rows}")

    bad_energy = df[~df["energy_today"].isin(ALLOWED_ENERGIES)]
    if not bad_energy.empty:
        rows = ", ".join(str(i+2) for i in bad_energy.index.tolist())
        errs.append(f"Invalid energy_today at rows: {rows}")

    return errs

def build_eligibility_maps(df: pd.DataFrame, category: str) -> Dict[str, Dict[str, int]]:
    prefix_cols = detect_pref_cols(df, category)
    result: Dict[str, Dict[str, int]] = {}
    for _, r in df.iterrows():
        pid = str(r["player_id"])
        elig: Dict[str, int] = {}
        for i, c in enumerate(prefix_cols, start=1):
            pos = str(r[c]).strip()
            if pos:
                elig[pos] = min(elig.get(pos, i), i)
        result[pid] = elig
    return result

def compute_fairness_bounds(
    positions_count: int,
    total_series: int,
    active_players: int,
    evenness_cap_enabled: bool,
    evenness_cap_value: int,
    has_varsity: bool,
    varsity_penalty: float,
) -> Tuple[int, int]:
    T = positions_count * total_series
    if active_players <= 0:
        return 0, 0
    mean = T / active_players
    base_lb = int(np.floor(mean))
    base_ub = int(np.ceil(mean))
    if evenness_cap_enabled:
        lb = max(0, base_lb - evenness_cap_value)
        ub = base_ub + evenness_cap_value
    else:
        lb, ub = base_lb, base_ub

    if has_varsity and varsity_penalty > 0:
        ub = max(lb, int(np.floor(ub - varsity_penalty)))
    return lb, ub

def check_impossible_minimums(T: int, P: int) -> Optional[str]:
    if P <= 0:
        return "No active players."
    if T < P:
        return (f"Warning: total slots ({T}) < active players ({P}). "
                "Minimum guarantee (≥1 each) is impossible. The solver will do its best within limits.")
    return None

def detect_duplicate_starters(start_map: Dict[str, Optional[str]]) -> List[str]:
    chosen = [pid for pid in start_map.values() if pid]
    dupes = []
    seen: Set[str] = set()
    for pid in chosen:
        if pid in seen:
            dupes.append(pid)
        seen.add(pid)
    return dupes

def series_grid_to_df(assignment: List[Dict[str, Optional[str]]], positions: List[str], roster_df: pd.DataFrame, category: str) -> pd.DataFrame:
    pid_to_name = dict(zip(roster_df["player_id"].astype(str), roster_df["name"]))
    pref_cols = detect_pref_cols(roster_df, category)
    pref_map: Dict[str, Dict[str, int]] = {}
    for _, r in roster_df.iterrows():
        pid = str(r["player_id"])
        pref_map[pid] = {}
        for i, c in enumerate(pref_cols, start=1):
            p = str(r[c]).strip()
            if p:
                pref_map[pid][p] = i

    data = {}
    for s_idx, s_assign in enumerate(assignment, start=1):
        col = []
        for pos in positions:
            pid = s_assign.get(pos)
            if pid is None:
                col.append("")
                continue
            name = pid_to_name.get(str(pid), f"#{pid}")
            badges = assignment_badges_for_cell(pid, pos, pref_map)
            cell = f"{name} {badges}".strip()
            col.append(cell)
        data[f"Series {s_idx}"] = col

    df = pd.DataFrame(data, index=positions)
    return df

def fairness_dashboard_df(assignment: List[Dict[str, Optional[str]]], roster_df: pd.DataFrame, app_config) -> pd.DataFrame:
    pid_to_name = dict(zip(roster_df["player_id"].astype(str), roster_df["name"]))
    counts: Dict[str, int] = {pid: 0 for pid in pid_to_name.keys()}
    for s in assignment:
        used = set()
        for pos, pid in s.items():
            if pid is None:
                continue
            if pid in used:
                continue
            counts[str(pid)] += 1
            used.add(pid)

    rows = []
    T = sum(1 for s in assignment for _ in s.values())
    P = len(pid_to_name)

    for pid, name in pid_to_name.items():
        vmins = int(roster_df.loc[roster_df["player_id"].astype(str) == pid, "varsity_minutes_recent"].iloc[0])
        has_v = vmins > 0
        lb, ub = compute_fairness_bounds(
            positions_count=len(assignment[0]) if assignment else 0,
            total_series=len(assignment),
            active_players=len(pid_to_name),
            evenness_cap_enabled=app_config.evenness_cap_enabled,
            evenness_cap_value=app_config.evenness_cap_value,
            has_varsity=has_v,
            varsity_penalty=app_config.varsity_penalty,
        )
        rows.append({
            "player_id": pid,
            "name": name,
            "assigned_slots": counts[pid],
            "lower_bound": lb,
            "upper_bound": ub,
            "varsity_recent": vmins,
            "flag_evenness_violation": counts[pid] < lb or counts[pid] > ub,
        })

    dash = pd.DataFrame(rows).sort_values(["flag_evenness_violation", "assigned_slots", "name"], ascending=[False, False, True])
    return dash

def assignment_badges_for_cell(pid: str, pos: str, pref_map: Dict[str, Dict[str, int]]) -> str:
    badges = []
    rank = pref_map.get(str(pid), {}).get(pos, None)
    # With 2-preference CSV, we only badge if beyond listed prefs (rare). Keep ⚠ for rank >=3.
    if rank is not None and rank >= 3:
        badges.append("⚠")
    return " ".join(badges)
