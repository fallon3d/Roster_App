# rotation_core/config.py
from __future__ import annotations
import os
from typing import Dict, List
import textwrap

ROLE_SCORE = {"newer/learning": 1, "steady/reliable": 2, "confident/impactful": 3}
ENERGY_SCORE = {"Low": 0, "Medium": 1, "High": 2}

DEFAULT_CONFIG = {
    "total_series": 8,
    "varsity_penalty": 0.3,          # subtract from upper bound slots if varsity_minutes_recent > 0
    "evenness_cap_enabled": True,
    "evenness_cap_value": 1,         # ±1
    "preference_weights": [1.0, 0.6, 0.3, 0.1],
    "objective_lambda": 0.0,         # placeholder; ILP objective uses fairness by constraints
    "objective_mu": 1.0,             # mismatch penalty weight
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
      OFFENSE_11:  # Matches your final requested labels
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
      OFFENSE_11_RB2:  # Alternate with RB1/RB2, WR1/WR2
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
      DEFENSE_53:   # Matches your final requested 5-3 naming
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
      DEFENSE_53_ALT:  # Alternative labels
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

DEFAULT_SAMPLE_ROSTER_CSV = textwrap.dedent("""\
player_id,name,season_minutes,varsity_minutes_recent,role_today,energy_today,off_pos_1,off_pos_2,off_pos_3,off_pos_4,def_pos_1,def_pos_2,def_pos_3,def_pos_4,notes
1,Alex Carter,210,0,steady/reliable,High,QB,WR,Slot,TE,LCB,S,RCB,OLB1,
2,Blake Diaz,180,0,confident/impactful,Medium,HB,AB,WR,Slot,OLB1,MLB,DT1,S,
3,Casey Ellis,90,0,newer/learning,High,LG,RG,C,LT,DT2,NT,DT1,RDE,
4,Drew Fox,160,0,steady/reliable,Medium,WR,Slot,TE,HB,LCB,RCB,S,OLB2,
5,Emery Gray,200,0,confident/impactful,High,LT,LG,RG,RT,LDE,DT1,DT2,RDE,
6,Fin Hayes,80,0,newer/learning,Medium,TE,WR,Slot,HB,LB_SAM,LB_MIKE,LB_WILL,S,needs reps
7,Gabe Irwin,140,0,steady/reliable,Low,AB,HB,WR,Slot,OLB2,OLB1,MLB,LCB,
8,Harper Jones,60,0,newer/learning,Medium,C,LG,RG,LT,NT,DT2,DT1,RDE,
9,Izzy Kim,175,0,steady/reliable,High,RG,LG,RT,C,DT1,DT2,NT,LDE,
10,Jordan Lee,220,15,confident/impactful,High,WR,Slot,AB,HB,LCB,RCB,S,OLB1,varsity mins
11,Kai Miller,150,0,steady/reliable,Medium,RT,RG,LT,LG,RDE,LDE,DT2,DT1,
12,Lane Novak,120,0,newer/learning,High,AB,HB,Slot,WR,MLB,OLB1,OLB2,S,
13,Morgan Ortiz,90,0,newer/learning,Medium,HB,AB,WR,Slot,DT2,DT1,NT,RDE,
14,Nico Park,130,0,steady/reliable,Low,LG,C,RG,LT,DT1,RDE,NT,LDE,
15,Owen Quinn,210,0,confident/impactful,Medium,QB,WR,Slot,TE,LCB,S,RCB,OLB2,
16,Parker Reed,80,0,newer/learning,Medium,TE,HB,WR,Slot,LB_WILL,LB_SAM,LB_MIKE,S,
17,Quinn Shaw,160,0,steady/reliable,High,WR,Slot,AB,HB,RCB,LCB,S,OLB2,
18,Riley Tran,100,0,newer/learning,Medium,C,RG,LG,RT,NT,DT2,DT1,LDE,
19,Sky Underwood,190,0,steady/reliable,High,LT,LG,RG,RT,LDE,DT1,DT2,RDE,
20,Tate Vega,230,20,confident/impactful,High,HB,AB,WR,Slot,MLB,OLB1,OLB2,S,varsity mins
21,Uma Wyatt,110,0,newer/learning,Low,Slot,WR,TE,HB,S,LCB,RCB,OLB1,
22,Vic Xu,150,0,steady/reliable,Medium,RG,RT,LG,C,DT1,DT2,NT,RDE,
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
