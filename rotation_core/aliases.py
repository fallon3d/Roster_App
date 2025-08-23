# FILE: rotation_core/aliases.py
ALIASES = {
    "Name": ["Name", "Player", "Full Name"],
    "Off1": ["Off1", "Offense1", "Primary Offense", "Offense 1st"],
    "Off2": ["Off2", "Offense2", "Secondary Offense", "Offense 2nd"],
    "Off3": ["Off3", "Offense3", "Third Offense", "Offense 3rd"],
    "Off4": ["Off4", "Offense4", "Fourth Offense", "Offense 4th"],
    "Def1": ["Def1", "Defense1", "Primary Defense", "Defense 1st"],
    "Def2": ["Def2", "Defense2", "Secondary Defense", "Defense 2nd"],
    "Def3": ["Def3", "Defense3", "Third Defense", "Defense 3rd"],
    "Def4": ["Def4", "Defense4", "Fourth Defense", "Defense 4th"],
    "RoleToday": ["Role", "RoleToday", "Position Role"],
    "EnergyToday": ["Energy", "EnergyToday", "Energy Level"],
    "SatLast": ["SatLast", "Sat Previous", "Sat-Last"],
    "IsPresent": ["IsPresent", "Present", "Available"]
}

def map_headers(df):
    """
    Map input DataFrame columns to expected canonical names using aliases.
    Returns (renamed_df, mapping_report).
    """
    mapping = {}
    rename_cols = {}
    for col in df.columns:
        matched = False
        for canon, aliases in ALIASES.items():
            if col.lower() == canon.lower() or col.lower() in [alias.lower() for alias in aliases]:
                rename_cols[col] = canon
                mapping[col] = canon
                matched = True
                break
        if not matched:
            mapping[col] = None
    df = df.rename(columns=rename_cols)
    return df, mapping
