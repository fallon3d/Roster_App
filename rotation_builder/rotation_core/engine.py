from __future__ import annotations
from typing import Dict, List, Tuple, Optional, Iterable, Set
from copy import deepcopy

from .models import Player, Settings, Series
from .constants import (
    OFF_POS, DEF_53_POS, DEF_44_POS, CATEGORY_POSITIONS,
    FAIRNESS_CATEGORIES, ROLE_SCORE, ENERGY_SCORE, PREF_WEIGHT, normalize_pos
)

# -----------------------
# Core convenience lookups
# -----------------------
def strength_index(p: Player) -> int:
    # strength_index = ROLE_SCORE[role]*10 + ENERGY_SCORE[energy]
    return ROLE_SCORE[p.RoleToday] * 10 + ENERGY_SCORE[p.EnergyToday]

def _player_positions_by_segment(p: Player, settings: Settings) -> List[str]:
    if settings.segment == "Offense":
        return [normalize_pos(p.Off1), normalize_pos(p.Off2), normalize_pos(p.Off3), normalize_pos(p.Off4)]
    else:
        # Defense; 4-4 mapping already handled in normalize_pos
        return [normalize_pos(p.Def1), normalize_pos(p.Def2), normalize_pos(p.Def3), normalize_pos(p.Def4)]

def pref_rank_for_pos(player: Player, target_pos: str, settings: Optional[Settings] = None) -> Optional[int]:
    pos = normalize_pos(target_pos)
    prefs = _player_positions_by_segment(player, settings or Settings())
    for idx, pp in enumerate(prefs, start=1):
        if pp == pos:
            return idx
    return None

def current_positions(settings: Settings) -> List[str]:
    if settings.segment == "Offense":
        return OFF_POS[:]
    else:
        if settings.def_form == "5-3":
            return DEF_53_POS[:]
        else:  # 4-4
            return DEF_44_POS[:]

def eligible_for_pos(roster: List[Player], pos: str, settings: Settings) -> List[Player]:
    npos = normalize_pos(pos)
    out = []
    for p in roster:
        prefs = _player_positions_by_segment(p, settings)
        if npos in [pp for pp in prefs if pp]:
            out.append(p)
    return out

def eligible_roster_in_category(roster: List[Player], cat: str, settings: Settings) -> List[Player]:
    pos_list = CATEGORY_POSITIONS[cat]
    out = []
    for p in roster:
        prefs = _player_positions_by_segment(p, settings)
        if any(pp in pos_list for pp in prefs if pp):
            out.append(p)
    return out

# -----------------------
# Suggestion & cycles
# -----------------------
def suggest_series1(roster: List[Player], settings: Settings) -> Series:
    pos_list = current_positions(settings)
    used: Set[str] = set()
    picks: Dict[str, str] = {}

    for pos in pos_list:
        candidates = eligible_for_pos(roster, pos, settings)
        if not candidates:
            picks[pos] = ""
            continue

        best_pid = ""
        best_score = -1
        for p in candidates:
            if p.id in used:
                continue
            si = strength_index(p)
            pr = pref_rank_for_pos(p, pos, settings)
            weight = PREF_WEIGHT.get(pr, 1)
            score = si * weight
            if score > best_score:
                best_score = score
                best_pid = p.id

        if best_pid == "" and candidates:
            # fallback to strongest unused
            cand = sorted((c for c in candidates if c.id not in used),
                          key=lambda x: (-strength_index(x), x.Name))
            best_pid = cand[0].id if cand else ""

        picks[pos] = best_pid
        if best_pid:
            used.add(best_pid)

    return Series(label="Series 1", positions=picks)

def build_pos_cycles(roster: List[Player], settings: Settings) -> Dict[str, List[str]]:
    cycles: Dict[str, List[str]] = {}
    for pos in current_positions(settings):
        cands = eligible_for_pos(roster, pos, settings)

        # sort: has pref (True before False), then smaller pref rank first (1 best), then strength desc, name asc
        def key(p: Player):
            pr = pref_rank_for_pos(p, pos, settings)
            has = pr is not None
            return (not has, pr if pr is not None else 99, -strength_index(p), p.Name)

        ordered = [p.id for p in sorted(cands, key=key)]
        cycles[pos] = ordered
    return cycles

# -----------------------
# Fairness utilities
# -----------------------
def _cat_for_pos(pos: str) -> Optional[str]:
    pos = normalize_pos(pos)
    return FAIRNESS_CATEGORIES.get(pos)

def clone_counts_cat(counts_cat: Dict[str, Dict[str, int]]) -> Dict[str, Dict[str, int]]:
    return {c: dict(d) for c, d in counts_cat.items()}

def min_cat(counts_cat: Dict[str, Dict[str, int]], cat: str, eligible_pids: List[str]) -> int:
    if not eligible_pids:
        return 0
    values = [counts_cat.get(cat, {}).get(pid, 0) for pid in eligible_pids]
    return min(values) if values else 0

def fairness_cap_exceeded(counts_cat: Dict[str, Dict[str, int]], pos: str, pid: str,
                          roster: List[Player], settings: Settings) -> bool:
    cat = _cat_for_pos(pos)
    if not cat:
        return False
    elig = [p.id for p in eligible_roster_in_category(roster, cat, settings)]
    if not elig or pid not in elig:
        return False
    cur = counts_cat.get(cat, {}).get(pid, 0)
    mmin = min_cat(counts_cat, cat, elig)
    # "+1 lead" rule: (cur + 1) > (minEligible + 1) => violation
    return (cur + 1) > (mmin + 1)

def inc_cat(counts_cat: Dict[str, Dict[str, int]], pos: str, pid: str):
    cat = _cat_for_pos(pos)
    if not cat:
        return
    if cat not in counts_cat:
        counts_cat[cat] = {}
    counts_cat[cat][pid] = counts_cat[cat].get(pid, 0) + 1

# -----------------------
# Effective lineup computation
# -----------------------
def compute_effective_lineup(
    series_idx: int,
    planned_series: Series,
    counts_cat_snap: Dict[str, Dict[str, int]],
    pos_idx_snap: Dict[str, int],
    manual_overrides_for_idx: Dict[str, str],
    roster: List[Player],
    settings: Settings,
) -> Tuple[Dict[str, str], Dict[str, Dict[str, int]]]:
    """
    Returns:
      assignments: pos -> pid
      counts_cat_out: counts snapshot after assigning (not committed to state)
    """
    assignments: Dict[str, str] = {}
    used: Set[str] = set()
    counts_out = clone_counts_cat(counts_cat_snap)

    pos_list = current_positions(settings)
    cycles = build_pos_cycles(roster, settings)

    # Pass 0: Manual overrides (eligible only; no in-series dupes)
    for pos, pid in (manual_overrides_for_idx or {}).items():
        if pos not in pos_list or not pid:
            continue
        # eligibility
        if pid not in [p.id for p in eligible_for_pos(roster, pos, settings)]:
            continue
        if pid in used:
            continue
        assignments[pos] = pid
        used.add(pid)
        inc_cat(counts_out, pos, pid)

    # Pass 1: Planned (if not exceeding fairness cap and not duped)
    for pos in pos_list:
        if assignments.get(pos):
            continue
        planned_pid = planned_series.positions.get(pos, "")
        if planned_pid and planned_pid not in used:
            if planned_pid in [p.id for p in eligible_for_pos(roster, pos, settings)]:
                # check fairness cap
                if not fairness_cap_exceeded(counts_out, pos, planned_pid, roster, settings):
                    assignments[pos] = planned_pid
                    used.add(planned_pid)
                    inc_cat(counts_out, pos, planned_pid)

    # Pass 2: Fill blanks via rotation cycles with fairness bias, then fallback ignoring fairness if needed
    for pos in pos_list:
        if assignments.get(pos):
            continue
        rota = cycles.get(pos, [])
        if not rota:
            assignments[pos] = ""
            continue

        start = pos_idx_snap.get(pos, 0) % (len(rota) if rota else 1)
        # First try respecting fairness + no dupes
        picked = ""
        for step in range(len(rota)):
            pid = rota[(start + step) % len(rota)]
            if pid in used:
                continue
            # must be eligible (cycle is eligible by construction)
            if not fairness_cap_exceeded(counts_out, pos, pid, roster, settings):
                picked = pid
                break

        if not picked:
            # fallback ignoring fairness
            for step in range(len(rota)):
                pid = rota[(start + step) % len(rota)]
                if pid in used:
                    continue
                picked = pid
                break

        assignments[pos] = picked
        if picked:
            used.add(picked)
            inc_cat(counts_out, pos, picked)

    return assignments, counts_out
