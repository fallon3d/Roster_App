from __future__ import annotations
from typing import Dict, List, Tuple
from copy import deepcopy
import io
import csv

from .models import Player, Settings, Series, GameState
from .constants import CATEGORY_POSITIONS, FAIRNESS_CATEGORIES
from .engine import (
    build_pos_cycles, compute_effective_lineup, fairness_cap_exceeded, inc_cat, clone_counts_cat
)

def _init_counts(players: List[Player]) -> Dict[str, int]:
    return {p.id: 0 for p in players}

def _init_counts_cat(players: List[Player]) -> Dict[str, Dict[str, int]]:
    cats = set(FAIRNESS_CATEGORIES.values())
    out: Dict[str, Dict[str, int]] = {c: {} for c in cats}
    for p in players:
        for c in cats:
            out[c][p.id] = 0
    return out

def start_game(state: GameState, roster: List[Player], settings: Settings, series_list: List[Series]):
    state.active = True
    state.idx_cycle = 0
    state.turn = 1
    state.played_counts = _init_counts(roster)
    state.played_counts_cat = _init_counts_cat(roster)
    state.history = []
    state.pos_cycles = build_pos_cycles(roster, settings)
    state.pos_idx = {pos: 0 for pos in state.pos_cycles.keys()}
    state.manual_overrides = {}
    state.fairness_debt_cat = {c: {} for c in state.played_counts_cat.keys()}

def end_series(state: GameState, roster: List[Player], settings: Settings, series_list: List[Series]):
    # pick planned series by idx_cycle
    if not series_list:
        return
    planned = series_list[state.idx_cycle % len(series_list)]

    manual = state.manual_overrides.get(state.turn, {})

    # compute current effective lineup (snapshot)
    snap_counts = clone_counts_cat(state.played_counts_cat)
    snap_pos_idx = dict(state.pos_idx)
    assigns, counts_out = compute_effective_lineup(
        state.idx_cycle, planned, snap_counts, snap_pos_idx, manual, roster, settings
    )

    # commit: appearances + category counts + advance pointers
    # debt accounting: if fairness would have been exceeded at snapshot time
    for pos, pid in assigns.items():
        if not pid:
            continue
        # fairness debt check before increment
        violated = fairness_cap_exceeded(snap_counts, pos, pid, roster, settings)
        if violated:
            cat = FAIRNESS_CATEGORIES.get(pos)
            if cat:
                state.fairness_debt_cat.setdefault(cat, {})
                state.fairness_debt_cat[cat][pid] = state.fairness_debt_cat[cat].get(pid, 0) + 1

        # commit to totals
        state.played_counts[pid] = state.played_counts.get(pid, 0) + 1
        inc_cat(state.played_counts_cat, pos, pid)

        # advance pointer for this position to the used pid index + 1
        cycle = state.pos_cycles.get(pos, [])
        if cycle:
            try:
                idx = cycle.index(pid)
            except ValueError:
                idx = state.pos_idx.get(pos, 0)
            state.pos_idx[pos] = (idx + 1) % len(cycle)

    # push to history
    state.history.append({
        "turn": state.turn,
        "planned": deepcopy(planned.positions),
        "overrides": deepcopy(manual),
        "assignments": deepcopy(assigns),
    })

    # advance
    state.turn += 1
    state.idx_cycle = (state.idx_cycle + 1) % (len(series_list) if series_list else 1)

def end_game(state: GameState):
    state.active = False
    # produce a lightweight summary
    # appearances table and category deltas (max-min)
    summary = {
        "turns": state.turn - 1,
        "appearances": dict(state.played_counts),
        "category_delta": {},
    }
    for cat, mp in state.played_counts_cat.items():
        vals = list(mp.values())
        if not vals:
            summary["category_delta"][cat] = 0
        else:
            summary["category_delta"][cat] = max(vals) - min(vals)
    return summary

def export_played_rotations_csv(history: List[Dict]) -> bytes:
    """
    Shape: for each series, a header row 'Series N', then Position,Player rows, then a blank line.
    """
    buf = io.StringIO()
    w = csv.writer(buf)
    for entry in history:
        turn = entry.get("turn")
        assigns = entry.get("assignments", {})
        w.writerow([f"Series {turn}"])
        w.writerow(["Position", "Player"])
        for pos in sorted(assigns.keys()):
            w.writerow([pos, assigns[pos]])
        w.writerow([])  # blank separator
    return buf.getvalue().encode("utf-8")

