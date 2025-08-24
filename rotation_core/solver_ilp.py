# rotation_core/solver_ilp.py
from __future__ import annotations
from typing import Dict, List, Optional, Tuple, Set
import numpy as np
import pandas as pd
import pulp

from .ratings import compute_strength_index_series
from .constraints import compute_fairness_bounds  # <-- removed build_eligibility_maps import

def solve_ilp(
    df: pd.DataFrame,
    positions: List[str],
    total_series: int,
    starting_lineup: Dict[str, Optional[str]],
    preference_weights: List[float],
    objective_mu: float,
    evenness_cap_enabled: bool,
    evenness_cap_value: int,
    varsity_penalty: float,
    excluded_ids: Set[str],
    rng: np.random.Generator,
) -> Tuple[Optional[List[Dict[str, Optional[str]]]], Optional[str]]:
    adf = df[~df["player_id"].astype(str).isin(excluded_ids)].copy()
    if adf.empty:
        return None, "All players excluded. Nothing to assign."

    pid_list = adf["player_id"].astype(str).tolist()
    P = len(pid_list)
    S = total_series
    POS = positions

    strength = compute_strength_index_series(adf).to_numpy()
    pid_to_strength = dict(zip(pid_list, strength))

    # Optional minutes columns are ignored; if absent, zeros
    if "season_minutes" in adf.columns:
        minutes = adf["season_minutes"].to_numpy(dtype=float)
        minutes_norm = (minutes - minutes.min()) / (minutes.max() - minutes.min()) if minutes.max() > minutes.min() else np.zeros_like(minutes)
    else:
        minutes_norm = np.zeros(P, dtype=float)
    pid_to_minutes_norm = dict(zip(pid_list, minutes_norm))

    rand_jitter = rng.uniform(0, 0.01, size=P)
    pid_to_jitter = dict(zip(pid_list, rand_jitter))

    # Determine preference rank by scanning available *_pos_i columns on both sides
    def pref_rank(pid: str, pos: str) -> Optional[int]:
        # Offense
        for i in range(1, 9):
            col = f"off_pos_{i}"
            if col in adf.columns:
                val = adf.loc[adf["player_id"].astype(str) == pid, col]
                if not val.empty and str(val.iloc[0]).strip() == pos:
                    return i
        # Defense
        for i in range(1, 9):
            col = f"def_pos_{i}"
            if col in adf.columns:
                val = adf.loc[adf["player_id"].astype(str) == pid, col]
                if not val.empty and str(val.iloc[0]).strip() == pos:
                    return i
        return None

    prob = pulp.LpProblem("rotation_assignment", pulp.LpMaximize)

    # Decision vars
    X = {}
    for pid in pid_list:
        for s in range(S):
            for pos in POS:
                if pref_rank(pid, pos) is None:
                    continue
                X[(pid, s, pos)] = pulp.LpVariable(f"x_{pid}_{s}_{pos}", cat="Binary")

    # Objective: preference-weighted strength, penalize mismatch
    obj_terms = []
    last_weight = preference_weights[-1] if preference_weights else 0.0
    for pid in pid_list:
        st = pid_to_strength[pid]
        mn = pid_to_minutes_norm[pid]
        jt = pid_to_jitter[pid]
        base = st - 0.0 * mn + jt  # minutes not used; keep structure for stability
        for s in range(S):
            for pos in POS:
                if (pid, s, pos) not in X:
                    continue
                r = pref_rank(pid, pos)
                if r is None:
                    continue
                w = preference_weights[r - 1] if r - 1 < len(preference_weights) else last_weight
                mismatch = (1.0 - w)
                coeff = base * w - objective_mu * mismatch
                obj_terms.append(coeff * X[(pid, s, pos)])
    prob += pulp.lpSum(obj_terms)

    # Constraints
    # 1) Fill every position per series
    for s in range(S):
        for pos in POS:
            prob += pulp.lpSum(X.get((pid, s, pos), 0) for pid in pid_list) == 1, f"fill_{s}_{pos}"

    # 2) One position per player per series
    for pid in pid_list:
        for s in range(S):
            prob += pulp.lpSum(X.get((pid, s, pos), 0) for pos in POS) <= 1, f"onepos_{pid}_{s}"

    # 3) Fairness bounds across series (minutes-free; optional varsity column respected if present)
    T = len(POS) * S
    for pid in pid_list:
        if "varsity_minutes_recent" in adf.columns:
            vmins = int(adf.loc[adf["player_id"].astype(str) == pid, "varsity_minutes_recent"].iloc[0])
            has_v = vmins > 0
        else:
            has_v = False

        lb, ub = compute_fairness_bounds(
            positions_count=len(POS),
            total_series=S,
            active_players=P,
            evenness_cap_enabled=evenness_cap_enabled,
            evenness_cap_value=evenness_cap_value,
            has_varsity=has_v,
            varsity_penalty=varsity_penalty,
        )
        total_for_pid = pulp.lpSum(X.get((pid, s, pos), 0) for s in range(S) for pos in POS)
        if T >= P:
            prob += total_for_pid >= max(1, lb), f"min_{pid}"
        else:
            prob += total_for_pid >= 0, f"min_{pid}"
        prob += total_for_pid <= ub, f"max_{pid}"

    # 4) Lock coach-picked starters for Series 1 (index 0)
    for pos, pid in starting_lineup.items():
        if pid:
            if (pid, 0, pos) not in X:
                return None, f"Starter {pid} is not eligible for {pos}."
            prob += X[(pid, 0, pos)] == 1, f"starter_{pos}"

    # Solve
    status = prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[status] != "Optimal":
        return None, f"ILP solver status: {pulp.LpStatus[status]}"

    # Extract assignment
    assignment: List[Dict[str, Optional[str]]] = []
    for s in range(S):
        ser: Dict[str, Optional[str]] = {}
        for pos in POS:
            found = None
            for pid in pid_list:
                var = X.get((pid, s, pos))
                if var is not None and pulp.value(var) > 0.5:
                    found = pid
                    break
            ser[pos] = found
        assignment.append(ser)

    return assignment, None
