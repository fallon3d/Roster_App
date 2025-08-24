# rotation_core/solver_heuristic.py
from __future__ import annotations
from typing import Dict, List, Optional, Set, Tuple
import numpy as np
import pandas as pd

from .ratings import compute_strength_index_series
from .constraints import build_eligibility_maps

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
    """Heuristic fallback:
    - Fill Series 1 honoring coach picks, smart-fill blanks
    - Then for series 2..N, greedily assign per position:
      choose eligible player with (lowest assigned so far, then highest score)
    """
    adf = df[~df["player_id"].astype(str).isin(excluded_ids)].copy()
    pid_list = adf["player_id"].astype(str).tolist()
    strength = compute_strength_index_series(adf)
    pid_to_strength = dict(zip(adf["player_id"].astype(str), strength))

    elig_off = build_eligibility_maps(adf, "Offense")
    elig_def = build_eligibility_maps(adf, "Defense")

    def pref_rank(pid: str, pos: str) -> Optional[int]:
        if pos in elig_off.get(pid, {}):
            return elig_off[pid][pos]
        if pos in elig_def.get(pid, {}):
            return elig_def[pid][pos]
        return None

    assigned_counts = {pid: 0 for pid in pid_list}

    S = total_series
    POS = positions
    assignment: List[Dict[str, Optional[str]]] = []

    # Series 1
    used = set()
    ser0: Dict[str, Optional[str]] = {}
    for pos in POS:
        pid = starting_lineup.get(pos)
        if pid and pid in pid_list and pref_rank(pid, pos) is not None and pid not in used:
            ser0[pos] = pid
            used.add(pid)
            assigned_counts[pid] += 1
        else:
            ser0[pos] = None
    # Smart-fill blanks
    for pos in POS:
        if ser0[pos] is None:
            # pick the best eligible not used
            cands = []
            for pid in pid_list:
                if pid in used:
                    continue
                r = pref_rank(pid, pos)
                if r is None:
                    continue
                w = preference_weights[r - 1]
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
        # fairness-first: compute min assigned so far
        min_assigned = min(assigned_counts.values()) if assigned_counts else 0
        for pos in POS:
            cands = []
            for pid in pid_list:
                if pid in used:
                    continue
                r = pref_rank(pid, pos)
                if r is None:
                    continue
                w = preference_weights[r - 1]
                # prioritize those with fewer assignments
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
