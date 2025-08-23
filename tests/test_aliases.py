# FILE: tests/test_aliases.py
import pandas as pd
from rotation_core.aliases import map_headers

def test_map_headers_basic():
    df = pd.DataFrame(columns=["Name", "Offense1", "Defense2", "Unknown"])
    mapped_df, mapping = map_headers(df)
    assert mapping["Name"] == "Name"
    assert mapping["Offense1"] == "Off1"
    assert mapping["Defense2"] == "Def2"
    assert mapping["Unknown"] is None
