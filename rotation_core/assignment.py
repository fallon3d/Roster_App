# FILE: rotation_core/assignment.py
from __future__ import annotations
from typing import Dict, List, Tuple, Optional
import math
import numpy as np

from rotation_core.constants import positions_for, CATEGORY_MAP
from rotation_core.hungarian import hungarian
from rotation_core.models import Player, Roster, Config
from rotation_core.suitability import suitability, preference_rank
from rotation_core.fairness import fairness_bias, at_cap_mask


def _present_players(df) -> List[Player]:
    from rotation_core.models import Player as P
    return [P(**row) for _, row in df.iterrows() if int(row.get("IsPresent", 1)) == 1]


def _build_cost_matrix(
    positions: List[str],
    players: List[Player],
    side: str,
    appearances: Dict[str, int],
    quotas: Dict[str, int] | None,
    slider: str,
    consecutive: Dict[str, int] | None = None,
    max_consecutive: int = 0,
    pins: Optional[Dict[str, str]] = None,  # pos -> player_id (Name acts as id)
    excludes: Optional[Dict[str, bool]] = None,  # player_id -> bool
) -> Tuple[np.ndarray, List[str], List[str]]:
    """
    Build a cost matrix for Hungarian:
    - maximize suitability & fairness => minimize (BIG - score)
    - fairness slider: boosts bias toward underused players
    - block ineligible / excluded / cap-breaching when possible
    """
    BIG = 1e9
    pids = [p.Name for p in players]  # use Name as identifier in this offline app
    bias = fairness_bias(appearances or {})
    cap = at_cap_mask(appearances or {})

    # slider weight: Fairness-first -> higher alpha; Win-push -> lower alpha
    if slider == "Fairness-first":
        alpha = 0.50
    elif slider == "Balanced":
        alpha = 0.25
    else:
        alpha = 0.10

    n_pos, n_pl = len(positions), len(players)
    cost = np.full((n_pos, n_pl), BIG, dtype=float)

    for i, pos in enumerate(positions):
        for j, p in enumerate(players):
            if excludes and excludes.get(p.Name):
                continue
            pr = preference_rank(p, pos, "offense" if side == "offense" else "defense")
            if pr is None:
                continue  # ineligible
            base = suitability(p, pos, "offense" if side == "offense" else "defense")
            if base <= 0:
                continue

            # fairness bias
            fb = bias.get(p.Name, 1.0)
            score = base * (1.0 + alpha * (fb - 1.0))

            # consecutive limit penalty
            if max_consecutive and consecutive and consecutive.get(p.Name, 0) >= max_consecutive:
                score *= 0.6  # reduce attractiveness

            # soft quota guidance (prefer under-quota)
            if quotas is not None:
                q = quotas.get(p.Name, None)
                if q is not None and appearances.get(p.Name, 0) >= q:
                    score *= 0.5  # de-prioritize if already at quota

            # hard evenness cap block when feasible (avoid > +1 leads)
            if cap.get(p.Name, False):
                # keep available, but heavily penalize so it's only picked if no alternative
                score *= 0.25

            # pin binding
            if pins and pos in pins and pins[pos] != p.Name:
                continue  # other player is pinned here

            cost[i, j] = (BIG - float(score))

    return cost, positions, pids


def _pad_and_assign(cost: np.ndarray) -> List[int]:
    return hungarian(cost)


def assign_one_rotation(
    df,
    side: str,
    formation: Optional[str],
    config: Config,
    appearances: Dict[str, int],
    quotas: Optional[Dict[str, int]],
    consecutive: Optional[Dict[str, int]] = None,
    pins: Optional[Dict[str, str]] = None,
    excludes: Optional[Dict[str, bool]] = None,
) -> Tuple[Dict[str, str], List[str]]:
    """
    Return (assignment_map, explanations[])
    assignment_map: {position -> player_name or ""} for a single rotation
    """
    players = _present_players(df)
    positions = positions_for(side, formation)

    # Build cost matrix with current state
    cost, pos_list, pids = _build_cost_matrix(
        positions, players, side,
        appearances=appearances or {},
        quotas=quotas,
        slider=config.fairness,
        consecutive=consecutive or {},
        max_consecutive=config.max_consecutive or 0,
        pins=pins, excludes=excludes
    )

    # Run Hungarian
    assign_idx = _pad_and_assign(cost)

    assignment: Dict[str, str] = {}
    explain: List[str] = []
    for i, j in enumerate(assign_idx):
        pos = pos_list[i]
        if j < 0 or j >= len(pids):
            assignment[pos] = ""
            explain.append(f"{pos}: no eligible player (coach review).")
        else:
            # If the cost was BIG (ineligible), treat as unfilled
            if math.isclose(cost[i, j], 1e9, rel_tol=0, abs_tol=1e-6):
                assignment[pos] = ""
                explain.append(f"{pos}: no eligible player (coach review).")
            else:
                assignment[pos] = pids[j]

    # If any blanks remain, leave to UI to prompt exceptions; we also attach a quick hint
    if any(v == "" for v in assignment.values()):
        explain.append("At least one slot had no eligible players; consider coach-approved exception(s).")

    # Category fairness hints (warn if a chosen player would exceed +1 in category snapshot)
    # NOTE: this is advisory; hard fairness enforced by global appearances cap biasing above.
    from rotation_core.constants import CATEGORY_POSITIONS, CATEGORY_MAP
    cat_counts = {}  # snapshot if we were to commit
    for pos, name in assignment.items():
        if not name:
            continue
        cat = CATEGORY_MAP.get(pos, "GEN")
        cat_counts.setdefault(cat, {}).setdefault(name, 0)
        cat_counts[cat][name] += 1

    # (We only add a light message; detailed per-candidate warnings are in UI lists.)
    if cat_counts:
        explain.append("Category fairness: lineup biased to avoid >+1 leads; warnings shown during swaps.")

    return assignment, explain


def solve_rotation(df, mode, formation, config) -> List[Dict[str, str]]:
    """
    Backwards-compatible wrapper used by existing page/tests.
    Produces 'num_rotations' rotations by iterating assignment and updating appearances.
    """
    side = "offense" if mode.lower() == "offense" else "defense"
    n = getattr(config, "num_rotations", 1)
    positions = positions_for(side, formation)
    players = _present_players(df)

    # Simple quotas based on desired rotations
    total_slots = len(positions) * n
    if not players:
        return []

    # Distribute quotas evenly; key by Name (ID surrogate)
    from rotation_core.fairness import compute_quotas
    base_q = compute_quotas(len(players), total_slots)
    quotas = {p.Name: base_q[i] for i, p in enumerate(players)}

    appearances: Dict[str, int] = {p.Name: 0 for p in players}
    consecutive: Dict[str, int] = {p.Name: 0 for p in players}
    rotations: List[Dict[str, str]] = []

    pins: Dict[str, str] = {}
    excludes: Dict[str, bool] = {}

    for r in range(n):
        assignment, _ = assign_one_rotation(
            df, side, formation, config, appearances, quotas,
            consecutive=consecutive, pins=pins, excludes=excludes,
        )
        # update counts
        used = set()
        for pos, name in assignment.items():
            if not name:
                continue
            appearances[name] = appearances.get(name, 0) + 1
            if name in used:
                # Within-rotation dupes should not happen; guard anyway
                consecutive[name] = 1
            else:
                consecutive[name] = consecutive.get(name, 0) + 1
                used.add(name)
        # reset consecutive for those not used
        for p in appearances.keys():
            if p not in used:
                consecutive[p] = 0
        rotations.append(assignment)

    return rotations
