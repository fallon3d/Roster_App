# rotation_core/config.py
from __future__ import annotations
import os
import textwrap

ROLE_SCORE = {"newer/learning": 1, "steady/reliable": 2, "confident/impactful": 3}
ENERGY_SCORE = {"Low": 0, "Medium": 1, "High": 2}

DEFAULT_CONFIG = {
    "total_series": 8,
    "varsity_penalty": 0.3,          # Ignored unless 'varsity_minutes_recent' column exists
    "evenness_cap_enabled": True,
    "evenness_cap_value": 1,         # ±1
    "preference_weights": [1.0, 0.6],# 2-preference default
    "objective_lambda": 0.0,
    "objective_mu": 1.0,
    "random_seed": 42,
}

def ensure_assets_exist():
    os.makedirs("assets", exist_ok=True)
    if not os.path.exists("assets/formations.yaml"):
        with open("assets/formations.yaml", "w", encoding="utf-8") as f:
            f.write(DEFAULT_FORMATIONS_YAML)
    if not os.path.exists("assets/sample_roster.csv"):
        with open("assets/sample_roster.csv", "w", encoding="utf-8") as f:
            f.write(DEFAULT_SAMPLE_ROSTER_CSV)

def load_formations_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# -------- Position aliases (key = formation slot; values = allowed roster tokens) --------
# Defense
_POS_ALIASES = {
    "DT1": ["DT1", "DT"],
    "DT2": ["DT2", "DT"],
    "LCB": ["LCB", "CB"],
    "RCB": ["RCB", "CB"],
    "OLB1": ["OLB1", "OLB"],
    "OLB2": ["OLB2", "OLB"],
    "LDE": ["LDE", "DE"],
    "RDE": ["RDE", "DE"],
    "NT": ["NT"],
    "MLB": ["MLB", "LB_MIKE"],
    # Alt 5-3 labels
    "DE_L": ["DE_L", "DE", "LDE"],
    "DE_R": ["DE_R", "DE", "RDE"],
    "LB_SAM": ["LB_SAM", "OLB"],
    "LB_WILL": ["LB_WILL", "OLB"],
    "LB_MIKE": ["LB_MIKE", "MLB"],
    "CB_L": ["CB_L", "CB", "LCB"],
    "CB_R": ["CB_R", "CB", "RCB"],
    "FS": ["FS", "S"],
    "S": ["S", "FS"],
    # Offense (for completeness if you use WR1/WR2 or RB1/RB2)
    "WR1": ["WR1", "WR"],
    "WR2": ["WR2", "WR"],
    "RB1": ["RB1", "HB", "RB", "AB"],
    "RB2": ["RB2", "HB", "RB", "AB"],
}

def aliases_for_position(pos: str) -> set[str]:
    """Return the set of acceptable roster tokens for a given formation slot name."""
    p = str(pos).strip()
    vals = set([p])
    if p in _POS_ALIASES:
        vals.update(_POS_ALIASES[p])
    return vals

DEFAULT_FORMATIONS_YAML = textwrap.dedent("""\
    Offense:
      OFFENSE_11:
        - QB
        - AB
        - HB
        - WR
        - Slot
        - TE
        - LT
        - LG
        - C
        - RG
        - RT
      OFFENSE_11_RB2:
        - QB
        - RB1
        - RB2
        - WR1
        - WR2
        - TE
        - LT
        - LG
        - C
        - RG
        - RT

    Defense:
      DEFENSE_53:
        - LDE
        - DT1
        - NT
        - DT2
        - RDE
        - OLB1
        - MLB
        - OLB2
        - LCB
        - S
        - RCB
      DEFENSE_53_ALT:
        - DE_L
        - DT1
        - NT
        - DT2
        - DE_R
        - LB_SAM
        - LB_MIKE
        - LB_WILL
        - CB_L
        - FS
        - CB_R
    """)

# Sample roster for 2-preference schema WITHOUT any minutes columns
DEFAULT_SAMPLE_ROSTER_CSV = textwrap.dedent("""\
player_id,name,role_today,energy_today,off_pos_1,off_pos_2,def_pos_1,def_pos_2,notes
1,Alex Carter,steady/reliable,High,QB,WR,LCB,S,
2,Blake Diaz,confident/impactful,Medium,HB,AB,OLB,MLB,
3,Casey Ellis,newer/learning,High,LG,RG,DT,NT,
4,Drew Fox,steady/reliable,Medium,WR,Slot,CB,CB,
5,Emery Gray,confident/impactful,High,LT,LG,DE,DT,
6,Fin Hayes,newer/learning,Medium,TE,WR,OLB,LB_MIKE,needs reps
7,Gabe Irwin,steady/reliable,Low,AB,HB,OLB,OLB,
8,Harper Jones,newer/learning,Medium,C,LG,NT,DT,
9,Izzy Kim,steady/reliable,High,RG,RT,DT,DT,
10,Jordan Lee,confident/impactful,High,WR,Slot,CB,CB,
11,Kai Miller,steady/reliable,Medium,RT,RG,DE,DE,
12,Lane Novak,newer/learning,High,AB,HB,MLB,OLB,
13,Morgan Ortiz,newer/learning,Medium,HB,AB,DT,NT,
14,Nico Park,steady/reliable,Low,LG,C,DT,DE,
15,Owen Quinn,confident/impactful,Medium,QB,WR,LCB,S,
16,Parker Reed,newer/learning,Medium,TE,HB,OLB,OLB,
17,Quinn Shaw,steady/reliable,High,WR,Slot,CB,CB,
18,Riley Tran,newer/learning,Medium,C,RG,NT,DT,
19,Sky Underwood,steady/reliable,High,LT,LG,DE,DT,
20,Tate Vega,confident/impactful,High,HB,AB,MLB,OLB,
21,Uma Wyatt,newer/learning,Low,Slot,WR,S,LCB,
22,Vic Xu,steady/reliable,Medium,RG,RT,DT,DT,
""")

def ui_css() -> str:
    return """
    <style>
      .stDataFrame, .stDataEditor { font-size: 0.95rem; }
      .st-emotion-cache-10trblm, .st-emotion-cache-16idsys { padding-top: 0.5rem; }
      .stButton > button { border-radius: 8px; }
      .rotation-cell {
        padding: 2px 6px; border-radius: 6px; display: inline-block;
        border: 1px solid var(--secondary-text);
      }
    </style>
    """
