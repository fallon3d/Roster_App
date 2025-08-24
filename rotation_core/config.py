# rotation_core/config.py
from __future__ import annotations
import os
import textwrap

# ===== Ratings mapping (unchanged) =====
ROLE_SCORE = {"newer/learning": 1, "steady/reliable": 2, "confident/impactful": 3}
ENERGY_SCORE = {"Low": 0, "Medium": 1, "High": 2}

# ===== App defaults (minutes-free; 2 preference schema OK) =====
DEFAULT_CONFIG = {
    "total_series": 8,
    "varsity_penalty": 0.3,          # Ignored unless 'varsity_minutes_recent' exists
    "evenness_cap_enabled": True,
    "evenness_cap_value": 1,         # ±1
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

# ===== Position aliases (visual eligibility / starters pickers) =====
_POS_ALIASES = {
    # Defense twins
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
    # Alt 5–3
    "DE_L": ["DE_L", "DE", "LDE"],
    "DE_R": ["DE_R", "DE", "RDE"],
    "LB_SAM": ["LB_SAM", "OLB"],
    "LB_WILL": ["LB_WILL", "OLB"],
    "LB_MIKE": ["LB_MIKE", "MLB"],
    "CB_L": ["CB_L", "CB", "LCB"],
    "CB_R": ["CB_R", "CB", "RCB"],
    "FS": ["FS", "S"],
    "S": ["S", "FS"],
    # Offense pairs
    "WR1": ["WR1", "WR"],
    "WR2": ["WR2", "WR"],
    "RB1": ["RB1", "HB", "RB", "AB"],
    "RB2": ["RB2", "HB", "RB", "AB"],
}

def aliases_for_position(pos: str) -> set[str]:
    """Return accepted roster tokens for a given formation slot name."""
    p = str(pos).strip()
    vals = set([p])
    if p in _POS_ALIASES:
        vals.update(_POS_ALIASES[p])
    return vals

# ===== Default formations (used in sidebar and stage 2) =====
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

# ===== Sample roster compatible with 2-preference schema =====
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

# ===== 2025 Visual Theme (wrapped in <style>) =====
def ui_css() -> str:
    return """
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0b0e14; 
  --surface: rgba(18, 22, 31, 0.78);
  --muted: rgba(24, 30, 44, 0.7);
  --line:#2a3142;
  --text:#eaf1fb; 
  --sub:#B7C2D3;
  --accent-h: 210; --accent-s: 90%; --accent-l: 60%;
  --accent: hsl(var(--accent-h), var(--accent-s), var(--accent-l));
  --good:#25d790; --warn:#ffb547; --danger:#ff6b6b;
  --radius:16px; 
  --shadow:0 12px 40px rgba(0,0,0,.35);
}
html, body { background:
  radial-gradient(80vw 40vh at 10% -10%, rgba(21, 30, 48, .6), transparent 60%),
  radial-gradient(50vw 35vh at 110% -20%, rgba(17, 23, 60, .5), transparent 60%),
  linear-gradient(180deg,#0a0e13,#0e1219 220px) !important;
}
body, .stApp, .block-container {
  font-family: Inter, system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif; color: var(--text);
}
.block-container { padding-top: 1rem; max-width: 1200px; }

.card{
  background: var(--surface) !important;
  border:1px solid rgba(255,255,255,.05);
  border-radius:var(--radius);
  box-shadow:var(--shadow);
  backdrop-filter: blur(12px);
}
.section{padding:18px}
.row{display:flex;gap:12px;flex-wrap:wrap;align-items:center}
.small{color:var(--sub);font-size:12px}

.stButton > button, .stDownloadButton > button {
  background: rgba(10,14,22,.8); border:1px solid var(--line); color: var(--text);
  border-radius:12px; padding:10px 12px;
  transition: transform .08s ease, box-shadow .15s ease, background-color .2s ease, opacity .2s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover { transform: translateY(-1px); }
.stButton > button:active, .stDownloadButton > button:active { transform: translateY(0); }

.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
  background: linear-gradient(180deg, hsl(var(--accent-h),85%,58%), hsl(var(--accent-h),80%,50%));
  border-color: hsl(var(--accent-h), 80%, 45%); color:#071423; box-shadow: 0 8px 20px rgba(38,124,245,.25);
}

.stRadio > div { gap: 8px; }
.stRadio label {
  padding:8px 10px; border:1px solid var(--line); border-radius:999px; background:var(--muted);
}
.stRadio .st-af { display:none; } /* hide default dots */

input, select, textarea { color: var(--text) !important; }
[data-baseweb="select"] > div { background: rgba(10,14,22,.8) !important; border-radius: 12px !important; }

.stDataFrame, .stDataEditor { font-size: 0.95rem; }
thead tr th {
  background: linear-gradient(180deg,rgba(22,29,44,.9),rgba(17,23,35,.9)) !important;
  border-bottom: 1px solid var(--line) !important;
}
tbody tr td { border-bottom: 1px solid var(--line) !important; }
tbody tr:hover td { background: rgba(255,255,255,.02) !important; }

.app{max-width:1100px;margin:18px auto;padding:0 14px}
.drop{border:2px dashed var(--line);border-radius:14px;padding:14px;text-align:center;color:var(--sub);}
.chip{
  padding:8px 10px;border:1px solid var(--line);
  border-radius:999px;background:var(--muted);cursor:default;
}
.chip.active{ background: var(--accent); color:#071423; border-color: hsl(var(--accent-h),75%,42%); }

.caption { color: var(--sub); font-size: 12px; margin-top: 6px }
</style>
"""
