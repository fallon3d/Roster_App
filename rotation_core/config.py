# rotation_core/config.py
from __future__ import annotations
import os
from typing import Dict, List
import textwrap

ROLE_SCORE = {"newer/learning": 1, "steady/reliable": 2, "confident/impactful": 3}
ENERGY_SCORE = {"Low": 0, "Medium": 1, "High": 2}

DEFAULT_CONFIG = {
    "total_series": 8,
    "varsity_penalty": 0.3,
    "evenness_cap_enabled": True,
    "evenness_cap_value": 1,
    # default for 2-preference CSV
    "preference_weights": [1.0, 0.6],
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

# Sample roster matches 2-preference CSV (off_pos_1..2, def_pos_1..2)
DEFAULT_SAMPLE_ROSTER_CSV = textwrap.dedent("""\
player_id,name,season_minutes,varsity_minutes_recent,role_today,energy_today,off_pos_1,off_pos_2,def_pos_1,def_pos_2,notes
1,Alex Carter,210,0,steady/reliable,High,QB,WR,LCB,S,
2,Blake Diaz,180,0,confident/impactful,Medium,HB,AB,OLB1,MLB,
3,Casey Ellis,90,0,newer/learning,High,LG,RG,DT2,NT,
4,Drew Fox,160,0,steady/reliable,Medium,WR,Slot,LCB,RCB,
5,Emery Gray,200,0,confident/impactful,High,LT,LG,LDE,DT1,
6,Fin Hayes,80,0,newer/learning,Medium,TE,WR,LB_SAM,LB_MIKE,needs reps
7,Gabe Irwin,140,0,steady/reliable,Low,AB,HB,OLB2,OLB1,
8,Harper Jones,60,0,newer/learning,Medium,C,LG,NT,DT2,
9,Izzy Kim,175,0,steady/reliable,High,RG,RT,DT1,DT2,
10,Jordan Lee,220,15,confident/impactful,High,WR,Slot,LCB,RCB,varsity mins
11,Kai Miller,150,0,steady/reliable,Medium,RT,RG,RDE,LDE,
12,Lane Novak,120,0,newer/learning,High,AB,HB,MLB,OLB1,
13,Morgan Ortiz,90,0,newer/learning,Medium,HB,AB,DT2,NT,
14,Nico Park,130,0,steady/reliable,Low,LG,C,DT1,RDE,
15,Owen Quinn,210,0,confident/impactful,Medium,QB,WR,LCB,S,
16,Parker Reed,80,0,newer/learning,Medium,TE,HB,LB_WILL,LB_SAM,
17,Quinn Shaw,160,0,steady/reliable,High,WR,Slot,RCB,LCB,
18,Riley Tran,100,0,newer/learning,Medium,C,RG,NT,DT2,
19,Sky Underwood,190,0,steady/reliable,High,LT,LG,LDE,DT1,
20,Tate Vega,230,20,confident/impactful,High,HB,AB,MLB,OLB1,varsity mins
21,Uma Wyatt,110,0,newer/learning,Low,Slot,WR,S,LCB,
22,Vic Xu,150,0,steady/reliable,Medium,RG,RT,DT1,DT2,
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
