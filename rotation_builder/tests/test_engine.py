from __future__ import annotations
from rotation_core.engine import (
    strength_index, pref_rank_for_pos, build_pos_cycles, suggest_series1,
    compute_effective_lineup, fairness_cap_exceeded
)
from rotation_core.models import Player, Settings, Series
from rotation_core.engine_test_helpers import quick_player

def test_strength_index_and_prefs():
    p = quick_player("p1","A",["QB","WR"],["RC","S"], role="Driver", energy="High")
    assert strength_index(p) == 3*10 + 2
    s = Settings(segment="Offense")
    assert pref_rank_for_pos(p, "QB", s) == 1
    assert pref_rank_for_pos(p, "WR", s) == 2
    assert pref_rank_for_pos(p, "HB", s) is None

def test_cycles_and_suggest_series1_no_dupes():
    roster = [
        quick_player("p1","A",["QB"],["RC"]),
        quick_player("p2","B",["HB","WR"],["LC"]),
        quick_player("p3","C",["HB","Slot"],["S"]),
        quick_player("p4","D",["C","LG","LT","RG"],["NT"]),
        quick_player("p5","E",["RT","TE"],["RDT"]),
    ]
    s = Settings(segment="Offense")
    cycles = build_pos_cycles(roster, s)
    assert "QB" in cycles and "HB" in cycles and "RT" in cycles

    series = suggest_series1(roster, s)
    # must not duplicate player ids within the same series
    picks = [pid for pid in series.positions.values() if pid]
    assert len(picks) == len(set(picks))

def test_44_mapping_normalizes_legacy_labels():
    # ROLB -> RLB, LOLB -> LLB, RMLB/LMLB/RILB/LILB -> MLB
    p = quick_player("p1","A",["QB"],["ROLB","LMLB","RILB","LOLB"])
    s = Settings(segment="Defense", def_form="4-4")
    # pref ranks reflect normalized positions
    assert pref_rank_for_pos(p, "RLB", s) == 1
    assert pref_rank_for_pos(p, "MLB", s) == 2  # RMLB/LMLB/RILB/LILB => MLB
    assert pref_rank_for_pos(p, "LLB", s) == 4  # LOLB => LLB

def test_effective_lineup_respects_manual_and_fairness():
    roster = [
        quick_player("a","A",["QB"],["RC"]),
        quick_player("b","B",["QB"],["LC"]),
        quick_player("c","C",["QB"],["S"]),
    ]
    s = Settings(segment="Offense")
    planned = Series(label="Series 1", positions={"QB": "a"})
    counts = {"QB": {"a": 0, "b": 0, "c": 0}}
    pos_idx = {"QB": 0}
    # manual override to 'b'
    manual = {"QB": "b"}
    assigns, out = compute_effective_lineup(
        0, planned, counts, pos_idx, manual, roster, s
    )
    assert assigns["QB"] == "b"  # manual wins

def test_fairness_plus1_rule():
    roster = [
        quick_player("a","A",["QB"],["RC"]),
        quick_player("b","B",["QB"],["LC"]),
    ]
    s = Settings(segment="Offense")
    counts = {"QB": {"a": 2, "b": 1}}
    # adding one more to 'a' would make (2+1) > (min=1)+1 => (3>2) True
    assert fairness_cap_exceeded(counts, "QB", "a", roster, s) is True
    # adding to 'b' => (1+1) > (min=1)+1 => (2>2) False
    assert fairness_cap_exceeded(counts, "QB", "b", roster, s) is False
