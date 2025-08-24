# rotation_core/solver_ilp.py
from __future__ import annotations
from typing import Dict, List, Optional, Tuple, Set
import numpy as np
import pandas as pd
import pulp

from .ratings import compute_strength_index_series
from .constraints import compute_fairness_bounds, build_eligibility_maps

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
    # Active players
    adf = df[~df["player_id"].astype(str).isin(excluded_ids)].copy()
    if adf.empty:
        return None, "All players excluded. Nothing to assign."

    pid_list = adf["player_id"].astype(str).tolist()
    P = len(pid_list)
    S = total_series
    POS = positions

    # Strength and tie-breakers
    strength = compute_strength_index_series(adf).to_numpy()
    pid_to_strength = dict(zip(pid_list, strength))

    # Normalize season_minutes to 0..1 for a small negative tie-break
    minutes = adf["season_minutes"].to_numpy(dtype=float)
    if minutes.max() > minutes.min():
        minutes_norm = (minutes - minutes.min()) / (minutes.max() - minutes.min())
    else:
        minutes_norm = np.zeros_like(minutes)
    pid_to_minutes_norm = dict(zip(pid_list, minutes_norm))

    # Small random jitter for deterministic tie-breaks
    rand_jitter = rng.uniform(0, 0.01, size=P)
    pid_to_jitter = dict(zip(pid_list, rand_jitter))

    # Eligibility and preference ranks
    # player_id -> {pos: rank(1..4)}
    elig_map = build_eligibility_maps(adf, category="Offense")  # placeholder; we will rebuild twice below if needed
    # But we need the correct category; detect via positions label membership
    # A simple approach: assume if a position appears in any off_pos list, it's offense; otherwise defense.
    # To be robust, we’ll compute for both and then pick ranks from the one that contains the position.
    elig_off = build_eligibility_maps(adf, "Offense")
    elig_def = build_eligibility_maps(adf, "Defense")

    def pref_rank(pid: str, pos: str) -> Optional[int]:
        if pos in elig_off.get(pid, {}):
            return elig_off[pid][pos]
        if pos in elig_def.get(pid, {}):
            return elig_def[pid][pos]
        return None

    # Build problem
    prob = pulp.LpProblem("rotation_assignment", pulp.LpMaximize)

    # Decision variables x[p,s,pos] ∈ {0,1}
    X = {}
    for pid in pid_list:
        for s in range(S):
            for pos in POS:
                allowed = pref_rank(pid, pos) is not None
                if not allowed:
                    continue
                X[(pid, s, pos)] = pulp.LpVariable(f"x_{pid}_{s}_{pos}", cat="Binary")

    # Objective: sum over s,pos,p of (strength_adj * x) - mu*mismatch
    # strength_adj = strength - 0.5*minutes_norm + jitter; then * preference_weight(rank)
    obj_terms = []
    for pid in pid_list:
        st = pid_to_strength[pid]
        mn = pid_to_minutes_norm[pid]
        jt = pid_to_jitter[pid]
        base = st - 0.5 * mn + jt
        for s in range(S):
            for pos in POS:
                if (pid, s, pos) not in X:
                    continue
                r = pref_rank(pid, pos)
                w = preference_weights[r - 1] if r else 0.0
                mismatch = (1.0 - w)
                coeff = base * w - objective_mu * mismatch
                obj_terms.append(coeff * X[(pid, s, pos)])
    prob += pulp.lpSum(obj_terms)

    # Constraints:
    # 1) Fill every position per series
    for s in range(S):
        for pos in POS:
            prob += pulp.lpSum(X.get((pid, s, pos), 0) for pid in pid_list) == 1, f"fill_{s}_{pos}"

    # 2) One position per player per series
    for pid in pid_list:
        for s in range(S):
            prob += pulp.lpSum(X.get((pid, s, pos), 0) for pos in POS) <= 1, f"onepos_{pid}_{s}"

    # 3) Fairness bounds across total series
    T = len(POS) * S
    for pid in pid_list:
        vmins = int(adf.loc[adf["player_id"].astype(str) == pid, "varsity_minutes_recent"].iloc[0])
        has_v = vmins > 0
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
        # Minimum guarantee: If T >= P enforce ≥1
        if T >= P:
            prob += total_for_pid >= max(1, lb), f"min_{pid}"
        else:
            prob += total_for_pid >= 0, f"min_{pid}"
        prob += total_for_pid <= ub, f"max_{pid}"

    # 4) Lock starting lineup for series 0 (Series 1)
    # If a spot left blank, let the solver fill it.
    for pos, pid in starting_lineup.items():
        if pid:
            # force this assignment
            if (pid, 0, pos) not in X:
                # starter picked a non-eligible spot
                return None, f"Starter {pid} is not eligible for {pos}."
            prob += X[(pid, 0, pos)] == 1, f"starter_{pos}"

    # 5) No duplicate players in Series 1 when coach picked overlapping
    # (implicit from onepos_{pid}_0 constraints)

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
