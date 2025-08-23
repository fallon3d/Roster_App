# FILE: tests/test_validation.py
import pandas as pd
from rotation_core.validation import is_eligible, check_formation
from rotation_core.models import Player

def test_is_eligible():
    p = Player(Name="P", Off1="QB", Off2="RB", RoleToday="Explorer", EnergyToday="Low")
    assert is_eligible(p, "QB", "offense")
    assert not is_eligible(p, "WR", "offense")

def test_check_formation_offense():
    data = {"Name": ["P1","P2","P3","P4","P5"],
            "Off1": ["QB","AB","HB","WR","Slot"]}
    df = pd.DataFrame(data)
    assert check_formation(df, "Offense", None)

def test_check_formation_impossible():
    data = {"Name": ["P1"], "Off1": ["QB"]}
    df = pd.DataFrame(data)
    assert not check_formation(df, "Offense", None)
