# FILE: tests/test_assignment.py
import pandas as pd
from rotation_core.assignment import solve_rotation

def test_single_rotation_offense():
    df = pd.DataFrame([{"Name":"A"}, {"Name":"B"}, {"Name":"C"}])
    class Cfg: num_rotations = 1
    rotations = solve_rotation(df, "Offense", None, Cfg())
    assert len(rotations) == 1
    rotation = rotations[0]
    assert rotation["QB"] == "A"
    assert rotation["AB"] == "B"
    assert rotation["HB"] == "C"
