from __future__ import annotations
from rotation_core.models import Settings, Series, GameState
from rotation_core.engine_test_helpers import quick_player
from rotation_core.game import start_game, end_series, end_game

def _mini_roster():
    # minimal roster with QB and HB rotation
    return [
        quick_player("p1","A",["QB","HB"],["RC"]),
        quick_player("p2","B",["QB","HB"],["LC"]),
        quick_player("p3","C",["HB","QB"],["S"]),
    ]

def test_game_flow_and_cycle_advance():
    roster = _mini_roster()
    s = Settings(segment="Offense")
    series = [Series(label="Series 1", positions={"QB": "p1", "HB": ""})]
    state = GameState()

    start_game(state, roster, s, series)
    # Run two series, cycles should advance
    end_series(state, roster, s, series)
    first_history = state.history[-1]["assignments"]
    end_series(state, roster, s, series)
    second_history = state.history[-1]["assignments"]

    assert state.turn == 3
    # we should see different players show up at QB/HB across the two series, if possible
    assert first_history != second_history

    summary = end_game(state)
    assert summary["turns"] == 2
    assert sum(summary["appearances"].values()) >= 2
