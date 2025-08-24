# rotation_core/solver_heuristic.py
from __future__ import annotations
from typing import Dict, List, Optional, Set
import numpy as np
import pandas as pd

from .ratings import compute_strength_index_series

def solve_greedy(
    df: pd.DataFrame,
    positions: List[str],
    total_series: int,
    starting_lineup: Dict[str, Optional[str]],
    preference_weights: List[float],
    evenness_cap_enabled: bool,
    evenness_cap_value: int,
    varsity_penalty: float,
    excluded_ids: Set[str],
    rng: np.random.Generator,
) -> List[Dict[str, Optional[str]]]:
    adf = df[~df["player_id"].astype(str).isin(excluded_ids)].copy()
    pid_list = adf["player_id"].astype(str).tolist()
    strength = compute_strength_index_series(adf)
    pid_to_strength = dict(zip(adf["player_id"].astype(str), strength))

    # helper: rank and weight
    def pref_rank(pid: str, pos: str) -> Optional[int]:
        for i in range(1, 9):
            col = f"off_pos_{i}"
            if col in adf.columns:
                v = adf.loc[adf["player_id"].astype(str) == pid, col]
                if not v.empty and str(v.iloc[0]).strip() == pos:
                    return i
        for i in range(1, 9):
            col = f"def_pos_{i}"
            if col in adf.columns:
                v = adf.loc[adf["player_id"].astype(str) == pid, col]
                if not v.empty and str(v.iloc[0]).strip() == pos:
                    return i
        return None

    last_weight = preference_weights[-1] if preference_weights else 0.0
    def weight_for_rank(r: Optional[int]) -> float:
        if r is None:
            return 0.0
        return preference_weights[r - 1] if r - 1 < len(preference_weights) else last_weight

    assigned_counts = {pid: 0 for pid in pid_list}

    S = total_series
    POS = positions
    assignment: List[Dict[str, Optional[str]]] = []

    # Series 1 with coach picks
    used = set()
    ser0: Dict[str, Optional[str]] = {}
    for pos in POS:
        pid = starting_lineup.get(pos)
        r = pref_rank(pid, pos) if pid else None
        if pid and pid in pid_list and r is not None and pid not in used:
            ser0[pos] = pid
            used.add(pid)
            assigned_counts[pid] += 1
        else:
            ser0[pos] = None

    # Smart fill for blanks
    for pos in POS:
        if ser0[pos] is None:
            cands = []
            for pid in pid_list:
                if pid in used:
                    continue
                r = pref_rank(pid, pos)
                if r is None:
                    continue
                w = weight_for_rank(r)
                score = pid_to_strength[pid] * w + rng.uniform(0, 0.01)
                cands.append((score, pid))
            if cands:
                cands.sort(reverse=True)
                best = cands[0][1]
                ser0[pos] = best
                used.add(best)
                assigned_counts[best] += 1
    assignment.append(ser0)

    # Subsequent series
    for s in range(1, S):
        used = set()
        ser: Dict[str, Optional[str]] = {}
        for pos in POS:
            cands = []
            for pid in pid_list:
                if pid in used:
                    continue
                r = pref_rank(pid, pos)
                if r is None:
                    continue
                w = weight_for_rank(r)
                fairness_priority = -assigned_counts[pid]
                score = (pid_to_strength[pid] * w) + fairness_priority + rng.uniform(0, 0.01)
                cands.append((score, pid))
            if cands:
                cands.sort(reverse=True)
                best = cands[0][1]
                ser[pos] = best
                used.add(best)
                assigned_counts[best] += 1
            else:
                ser[pos] = None
        assignment.append(ser)

    return assignment
