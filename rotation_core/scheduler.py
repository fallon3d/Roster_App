# rotation_core/scheduler.py
from __future__ import annotations
from typing import Dict, List, Optional, Set
import numpy as np
import pandas as pd

from .models import AppConfig, SolveResult
from .solver_ilp import solve_ilp
from .solver_heuristic import solve_greedy

def schedule_rotation(
    df: pd.DataFrame,
    category: str,
    formation_positions: List[str],
    starting_lineup: Dict[str, Optional[str]],
    config: AppConfig,
    excluded_ids: Set[str],
    rng: np.random.Generator,
) -> SolveResult:
    assignment, err = solve_ilp(
        df=df,
        positions=formation_positions,
        total_series=config.total_series,
        starting_lineup=starting_lineup or {},
        preference_weights=config.preference_weights,
        objective_mu=config.objective_mu,
        evenness_cap_enabled=config.evenness_cap_enabled,
        evenness_cap_value=config.evenness_cap_value,
        varsity_penalty=config.varsity_penalty,
        excluded_ids=excluded_ids,
        rng=rng,
    )
    if assignment is not None:
        return SolveResult(assignment=assignment)

    assignment2 = solve_greedy(
        df=df,
        positions=formation_positions,
        total_series=config.total_series,
        starting_lineup=starting_lineup or {},
        preference_weights=config.preference_weights,
        evenness_cap_enabled=config.evenness_cap_enabled,
        evenness_cap_value=config.evenness_cap_value,
        varsity_penalty=config.varsity_penalty,
        excluded_ids=excluded_ids,
        rng=rng,
    )
    empties = sum(1 for s in assignment2 for v in s.values() if v is None)
    if empties > 0:
        return SolveResult(assignment=assignment2, error=f"Heuristic filled with {empties} empty slots due to eligibility/availability limits.")
    return SolveResult(assignment=assignment2)
