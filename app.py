# app.py
# Youth Football Rotation Builder — Streamlit edition
# Mirrors the single-file HTML beta's behavior and game logic (category fairness, lockable 1st lineup, live editor, name pool, current/next picker, stats, export).

import io
import uuid
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd
import streamlit as st

# -----------------------------
# Page config / theme accents
# -----------------------------
st.set_page_config(
    page_title="Youth Football Rotation Builder",
    layout="wide",
)

BADGE_CSS = """
<style>
.badge{display:inline-flex;gap:.35rem;align-items:center;padding:.25rem .55rem;border-radius:999px;border:1px solid #2a3142;background:rgba(12,18,28,.8);color:#B7C2D3;font-size:12px}
.tag {display:inline-block;padding:0 .4rem;border-radius:6px;border:1px solid #2a3142;background:rgba(255,255,255,.05);color:#B7C2D3;font-size:11px;margin-left:.35rem}
.tag.warn{ background: rgba(255,181,71,.15); border-color: rgba(255,181,71,.35); color: #ffda9a; }
.tag.ok{ background: rgba(37,215,144,.12); border-color: rgba(37,215,144,.35); color: #a9ffd6; }
hr{border:none;border-top:1px solid rgba(255,255,255,.08)}
.small{color:#B7C2D3;font-size:12px}
</style>
"""
st.markdown(BADGE_CSS, unsafe_allow_html=True)

# -----------------------------
# Constants (mirror HTML)
# -----------------------------
OFF_POS = ["QB","AB","HB","WR","Slot","C","LG","LT","RG","RT","TE"]
DEF_53_POS = ["NT","LDT","RDT","LDE","RDE","MLB","LLB","RLB","LC","RC","S"]
# 4–4 simplified (no ROLB/LOLB/LMLB/RMLB in the pick list)
DEF_44_POS = ["LDT","RDT","LDE","RDE","LLB","MLB","RLB","LC","RC","S"]
ALL_DEF = sorted(list({*DEF_53_POS, *DEF_44_POS}))

ROLES = ["Explorer","Connector","Driver"]
ROLE_SCORE = {"Explorer":1, "Connector":2, "Driver":3}
ENERGY = ["Low","Medium","High"]
ENERGY_SCORE = {"Low":0, "Medium":1, "High":2}
PREF_WEIGHT = {1:4, 2:3, 3:2, 4:1}

# Category mapping (exactly like the HTML)
FAIRNESS_CATEGORIES = {
    # Offense
    "QB": "QB",
    "AB": "Backfield", "HB": "Backfield",
    "WR": "Wide", "Slot": "Wide",
    "TE": "TE",
    "RT": "Interior Line", "RG": "Interior Line", "C": "Interior Line", "LG": "Interior Line", "LT": "Interior Line",
    # Defense
    "NT": "DLine", "RDT":"DLine", "LDT":"DLine",
    "RLB":"Linebacker", "MLB":"Linebacker", "LLB":"Linebacker",
    "RC":"Secondary", "LC":"Secondary", "S":"Secondary",
    "RDE":"DE", "LDE":"DE",
}
CATEGORY_POSITIONS = {
    "QB": ["QB"],
    "Backfield": ["AB","HB"],
    "Wide": ["WR","Slot"],
    "TE": ["TE"],
    "Interior Line": ["RT","RG","C","LG","LT"],
    "DLine": ["NT","RDT","LDT"],
    "Linebacker": ["RLB","MLB","LLB"],
    "Secondary": ["RC","LC","S"],
    "DE": ["RDE","LDE"],
}

# Map legacy 4–4 labels to core roles (like the HTML)
FORMATION_POSITION_MAP_44 = {
  "RILB": "MLB", "LILB":"MLB", "RMLB":"MLB", "LMLB":"MLB",
  "ROLB":"RLB", "LOLB":"LLB"
}

SAMPLE_CSV = """Name,Off1,Off2,Off3,Off4,Def1,Def2,Def3,Def4
Alex Quinn,QB,WR,Slot,TE,RC,S,LC,RLB
Brooke Lee,HB,WR,Slot,AB,LLB,MLB,LMLB,LOLB
Chris Park,LT,LG,RT,C,LDE,RDE,LDT,RDT
Dev Patel,RG,RT,C,LG,NT,LDT,RDT,MLB
Evan Gray,WR,Slot,TE,HB,RC,S,LC,RLB
Faith Tran,AB,HB,WR,Slot,LOLB,ROLB,LMLB,RMLB
Gabe Diaz,C,RG,LG,RT,NT,LDT,RDT,MLB
Hana Kim,LG,LT,RG,C,LDE,RDE,LDT,RDT
Ivy Cruz,TE,WR,Slot,HB,LC,S,RC,RLB
Jalen Fox,RT,RG,LT,C,RDE,LDE,RDT,LDT
Kara Ngo,WR,Slot,HB,AB,LC,RC,S,LLB
Leo Moss,HB,AB,WR,Slot,MLB,LLB,RLB,LMLB
Maya Iqbal,Slot,WR,HB,TE,S,RC,LC,LOLB
Nico Yu,LT,LG,C,RG,LDT,RDT,LDE,RDE
Owen Reed,LG,C,RG,RT,RDT,LDT,NT,MLB
Pia Soto,WR,Slot,TE,HB,RC,LC,S,ROLB
Quinn Roy,HB,AB,WR,Slot,RLB,LLB,MLB,RMLB
Rey Cole,AB,HB,Slot,WR,ROLB,LOLB,RMLB,LMLB
Sage Zhu,C,RG,LG,RT,NT,LDT,RDT,MLB
Tess Wu,TE,WR,Slot,HB,S,LC,RC,LLB
Uma Rao,LT,LG,RT,C,LDE,RDE,LDT,RDT
Vik Shah,RG,RT,LG,C,RDT,LDT,NT,MLB
Will Poe,QB,WR,TE,Slot,LC,RC,S,LLB
"""

# -----------------------------
# Utilities
# -----------------------------
def _normalize_name(s: str) -> str:
    return " ".join(str(s or "").replace("\u00A0", " ").split()).strip()

def _new_id() -> str:
    return uuid.uuid4().hex[:12]

def parse_csv_bytes(file_bytes: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(file_bytes))
    return normalize_roster_columns(df)

def normalize_roster_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map CSV headers to canonical lower-case names and ensure required columns exist."""
    col_map = {}
    for c in df.columns:
        lc = str(c).strip().lower()
        # aliases
        if lc in {"name"}: col_map[c] = "name"; continue
        if lc in {"off1","offense 1"}: col_map[c] = "off1"; continue
        if lc in {"off2","offense 2"}: col_map[c] = "off2"; continue
        if lc in {"off3","offense 3"}: col_map[c] = "off3"; continue
        if lc in {"off4","offense 4"}: col_map[c] = "off4"; continue
        if lc in {"def1","defense 1"}: col_map[c] = "def1"; continue
        if lc in {"def2","defense 2"}: col_map[c] = "def2"; continue
        if lc in {"def3","defense 3"}: col_map[c] = "def3"; continue
        if lc in {"def4","defense 4"}: col_map[c] = "def4"; continue
    df = df.rename(columns=col_map)

    # keep only these (if present)
    keep = ["name","off1","off2","off3","off4","def1","def2","def3","def4"]
    for k in keep:
        if k not in df.columns:
            df[k] = ""

    # Add runtime columns
    if "player_id" not in df.columns:
        df["player_id"] = [ _new_id() for _ in range(len(df)) ]
    if "role_today" not in df.columns:
        df["role_today"] = "Connector"
    if "energy_today" not in df.columns:
        df["energy_today"] = "Medium"

    # sanitize strings
    for k in keep + ["role_today","energy_today"]:
        df[k] = df[k].astype(str).fillna("").map(_normalize_name)

    # sort by name for stable UI
    df = df[["player_id","name","off1","off2","off3","off4","def1","def2","def3","def4","role_today","energy_today"]]
    return df

def build_template_csv_bytes() -> bytes:
    buf = io.StringIO()
    headers = ["Name","Off1","Off2","Off3","Off4","Def1","Def2","Def3","Def4"]
    example = ["Jane Doe","QB","WR","Slot","HB","LC","RC","S","RLB"]
    pd.DataFrame([example], columns=headers).to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")

def strength_index(row: pd.Series) -> int:
    role = row.get("role_today","Connector")
    energy = row.get("energy_today","Medium")
    return ROLE_SCORE.get(role,2)*10 + ENERGY_SCORE.get(energy,1)

def normalize_pos(raw: str, segment: str, formation: str) -> str:
    pos = (raw or "").strip().upper()
    if not pos:
        return ""
    if segment == "Defense" and formation == "DEFENSE_44":
        # map legacy
        pos = FORMATION_POSITION_MAP_44.get(pos, pos)
    return pos

def aliases_for_position(pos: str, segment: str, formation: str) -> List[str]:
    """Return acceptable strings that 'match' a target position, including 4–4 normalization."""
    base = normalize_pos(pos, segment, formation)
    if segment == "Defense" and formation == "DEFENSE_44":
        # already normalized; accept original + normalized
        rev = [k for k,v in FORMATION_POSITION_MAP_44.items() if v == base]
        return [base, *rev]
    return [base]

def position_category(segment: str, pos: str) -> str:
    key = normalize_pos(pos, segment, st.session_state.selected_formation)
    return FAIRNESS_CATEGORIES.get(key, "GEN")

def detect_pref_cols(df: pd.DataFrame, segment: str) -> List[str]:
    return ["off1","off2","off3","off4"] if segment == "Offense" else ["def1","def2","def3","def4"]

def pref_rank_for_pos(df: pd.DataFrame, pid: str, pos: str, segment: str, formation: str) -> Optional[int]:
    row = df.loc[df["player_id"] == pid]
    if row.empty: return None
    row = row.iloc[0]
    cols = detect_pref_cols(df, segment)
    aliases = set(aliases_for_position(pos, segment, formation))
    for i, c in enumerate(cols, start=1):
        if normalize_pos(row[c], segment, formation) in aliases and row[c] != "":
            return i
    return None

def eligible_ids_for_pos(df: pd.DataFrame, pos: str, segment: str, formation: str) -> List[str]:
    cols = detect_pref_cols(df, segment)
    aliases = set(aliases_for_position(pos, segment, formation))
    mask = df[cols].apply(lambda r: any(normalize_pos(str(v), segment, formation) in aliases for v in r.values), axis=1)
    return df.loc[mask, "player_id"].astype(str).tolist()

def current_positions(segment: str, formation: str) -> List[str]:
    if segment == "Offense":
        return OFF_POS[:]
    # Defense
    if formation == "DEFENSE_53":
        return DEF_53_POS[:]
    # DEFENSE_44
    return DEF_44_POS[:]

def to_csv(rows: List[List[str]]) -> bytes:
    buf = io.StringIO()
    pd.DataFrame(rows).to_csv(buf, index=False, header=False)
    return buf.getvalue().encode("utf-8")

# -----------------------------
# Session state init
# -----------------------------
def _init_state():
    ss = st.session_state
    ss.setdefault("stage", 1)  # 1..4
    ss.setdefault("roster_df", None)  # DataFrame
    ss.setdefault("name_pool", [])  # list[str]
    ss.setdefault("selected_segment", "Offense")  # "Offense" | "Defense"
    ss.setdefault("selected_formation", "OFFENSE")  # "OFFENSE" | "DEFENSE_53" | "DEFENSE_44"
    ss.setdefault("starting_lineup", {})  # {category->formation->pos->pid}
    ss.setdefault("first_lineup_locked", False)

    # Game state
    ss.setdefault("game_active", False)
    ss.setdefault("game_turn", 1)
    ss.setdefault("game_idx_cycle", 0)
    ss.setdefault("game_history", [])  # list[ {turn, lineup: {pos: pid}} ]
    ss.setdefault("game_manual_overrides", {})  # {series_idx: {pos: pid}}
    ss.setdefault("game_played_counts", {})  # {pid: int}
    ss.setdefault("game_played_counts_cat", {})  # {cat: {pid: int}}
    ss.setdefault("game_fairness_debt_cat", {})  # {cat: {pid: debt}}
    ss.setdefault("game_pos_cycles", {})  # {pos: [pid]}
    ss.setdefault("game_pos_idx", {})     # {pos: int}

_init_state()

# -----------------------------
# Name pool helpers
# -----------------------------
def pool_unique_sorted(names: List[str]) -> List[str]:
    seen = set(); out=[]
    for n in names:
        nn = _normalize_name(n)
        if not nn: continue
        k = nn.lower()
        if k not in seen:
            seen.add(k)
            out.append(nn)
    return sorted(out, key=lambda x: x.lower())

def pool_import_csv(file) -> List[str]:
    try:
        df = pd.read_csv(file)
        col = "Name" if "Name" in df.columns else df.columns[0]
        return [ _normalize_name(v) for v in df[col].tolist() ]
    except Exception:
        try:
            text = file.getvalue().decode("utf-8")
            return [ _normalize_name(x) for x in text.splitlines() ]
        except Exception:
            return []

def pool_export_bytes(names: List[str]) -> bytes:
    buf = io.StringIO()
    pd.DataFrame({"Name": names}).to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")

def add_names_to_roster(names: List[str]):
    df = st.session_state.roster_df
    if df is None:
        df = pd.DataFrame(columns=["player_id","name","off1","off2","off3","off4","def1","def2","def3","def4","role_today","energy_today"])
    exist = set(df["name"].astype(str).str.lower().tolist())
    rows = []
    for nm in names:
        if nm.lower() in exist: continue
        rows.append({
            "player_id": _new_id(),
            "name": nm,
            "off1":"", "off2":"", "off3":"", "off4":"",
            "def1":"", "def2":"", "def3":"", "def4":"",
            "role_today":"Connector",
            "energy_today":"Medium",
        })
    if rows:
        st.session_state.roster_df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)

# -----------------------------
# Series 1 (starting lineup)
# -----------------------------
def suggest_series1(df: pd.DataFrame, segment: str, formation: str) -> Dict[str, Optional[str]]:
    pos_list = current_positions(segment, formation)
    used: Set[str] = set()
    # sort by strength descending
    srt = df.copy()
    srt["__strength"] = srt.apply(strength_index, axis=1)
    srt = srt.sort_values("__strength", ascending=False)

    s0: Dict[str, Optional[str]] = {}
    for pos in pos_list:
        best_pid = None
        best_score = -1
        for _, row in srt.iterrows():
            pid = row["player_id"]
            if pid in used:
                continue
            pr = pref_rank_for_pos(df, pid, pos, segment, formation)
            if pr is None:
                continue
            score = row["__strength"] * (PREF_WEIGHT.get(pr,1))
            if score > best_score:
                best_score = score
                best_pid = pid
        s0[pos] = best_pid
        if best_pid:
            used.add(best_pid)
    return s0

def ensure_starting_lineup(segment: str, formation: str):
    st.session_state.starting_lineup.setdefault(segment, {})
    st.session_state.starting_lineup[segment].setdefault(formation, {})

def get_starting_lineup(segment: str, formation: str) -> Dict[str, Optional[str]]:
    ensure_starting_lineup(segment, formation)
    return st.session_state.starting_lineup[segment][formation]

def set_starting_lineup(segment: str, formation: str, lineup: Dict[str, Optional[str]]):
    ensure_starting_lineup(segment, formation)
    st.session_state.starting_lineup[segment][formation] = lineup

def autofill_series1_gaps(df: pd.DataFrame, lineup: Dict[str, Optional[str]], segment: str, formation: str) -> Dict[str, Optional[str]]:
    out = dict(lineup)
    used = {pid for pid in out.values() if pid}
    for pos in current_positions(segment, formation):
        if out.get(pos):
            continue
        # pick eligible not used, by (pref, strength)
        elig = []
        for pid in eligible_ids_for_pos(df, pos, segment, formation):
            if pid in used: continue
            pr = pref_rank_for_pos(df, pid, pos, segment, formation)
            row = df.loc[df["player_id"] == pid].iloc[0]
            strength = strength_index(row)
            # order: with pref first (lower pr better), then strength desc, then name
            nm = row["name"]
            key = (0 if pr else 1, pr if pr else 99, -strength, nm)
            elig.append((key, pid))
        if elig:
            elig.sort(key=lambda x:x[0])
            pick = elig[0][1]
            out[pos] = pick
            used.add(pick)
    return out

# -----------------------------
# Category fairness helpers
# -----------------------------
def inc_cat(counts_cat: Dict[str, Dict[str,int]], cat: str, pid: str):
    counts_cat.setdefault(cat, {})
    counts_cat[cat][pid] = counts_cat[cat].get(pid, 0) + 1

def min_cat(counts_cat: Dict[str, Dict[str,int]], cat: str, eligible_ids: List[str]) -> int:
    if not eligible_ids: return 0
    base = counts_cat.get(cat, {})
    return min((base.get(i,0) for i in eligible_ids), default=0)

def fairness_cap_exceeded_raw(counts_cat: Dict[str, Dict[str,int]], pos: str, pid: str, segment: str, formation: str) -> bool:
    cat = position_category(segment, pos)
    elig = eligible_ids_for_pos(st.session_state.roster_df, pos, segment, formation)
    cur = counts_cat.get(cat, {}).get(pid, 0)
    m = min_cat(counts_cat, cat, elig)
    # would become +2? i.e., (cur+1) > (m+1)
    return (cur + 1) > (m + 1)

def fairness_cap_exceeded_with_debt(work_cat: Dict[str, Dict[str,int]], debt: Dict[str, Dict[str,int]], pos: str, pid: str, segment: str, formation: str) -> bool:
    cat = position_category(segment, pos)
    elig = eligible_ids_for_pos(st.session_state.roster_df, pos, segment, formation)
    cur = work_cat.get(cat, {}).get(pid, 0) + debt.get(cat, {}).get(pid, 0)
    m = min_cat(work_cat, cat, elig)
    return (cur + 1) > (m + 1)

# -----------------------------
# Game lineup computation
# -----------------------------
def build_cycles(df: pd.DataFrame, positions: List[str], segment: str, formation: str) -> Tuple[Dict[str, List[str]], Dict[str,int]]:
    pos_cycles, pos_idx = {}, {}
    for pos in positions:
        ids = eligible_ids_for_pos(df, pos, segment, formation)
        def key(pid: str):
            pr = pref_rank_for_pos(df, pid, pos, segment, formation)
            row = df.loc[df["player_id"] == pid].iloc[0]
            strength = strength_index(row)
            nm = row["name"]
            return (0 if pr else 1, pr if pr else 99, -strength, nm)
        ids.sort(key=key)
        pos_cycles[pos] = ids
        pos_idx[pos] = 0
    return pos_cycles, pos_idx

def compute_effective_lineup(series_idx: int,
                             positions: List[str],
                             counts_cat_snap: Dict[str, Dict[str,int]],
                             pos_idx_snap: Dict[str,int],
                             manual: Optional[Dict[str,str]],
                             debt: Dict[str, Dict[str,int]],
                             segment: str, formation: str) -> Dict[str, Optional[str]]:
    df = st.session_state.roster_df
    manual = manual or {}
    planned = get_starting_lineup(segment, formation)  # use Series 1 plan by default (like HTML)
    assign: Dict[str, Optional[str]] = {}
    in_series: Set[str] = set()
    # working copy
    work_cat = {c: v.copy() for c, v in counts_cat_snap.items()}

    # Pass 0: manual
    for pos in positions:
        pid = manual.get(pos)
        if not pid: continue
        # must be eligible and not duplicated
        if pid in in_series: continue
        if pid not in eligible_ids_for_pos(df, pos, segment, formation): continue
        assign[pos] = pid
        in_series.add(pid)
        inc_cat(work_cat, position_category(segment, pos), pid)

    # Pass 1: planned (bias away if fairness exceeded)
    for pos in positions:
        if pos in assign: continue
        pid = planned.get(pos)
        if not pid: continue
        if pid in in_series: continue
        if fairness_cap_exceeded_with_debt(work_cat, debt, pos, pid, segment, formation):
            continue
        assign[pos] = pid
        in_series.add(pid)
        inc_cat(work_cat, position_category(segment, pos), pid)

    # Pass 2: cycles fairness-first
    # build local cycles
    pos_cycles, _ = build_cycles(df, positions, segment, formation)
    for pos in positions:
        if pos in assign: continue
        cycle = pos_cycles.get(pos, [])
        if not cycle:
            assign[pos] = None
            continue
        idx = pos_idx_snap.get(pos, 0)
        chosen = None
        for t in range(len(cycle)):
            pid = cycle[(idx + t) % len(cycle)]
            if pid in in_series: continue
            if not fairness_cap_exceeded_with_debt(work_cat, debt, pos, pid, segment, formation):
                chosen = pid
                idx = (idx + t) % len(cycle)
                break
        if chosen is None:
            # fallback ignoring fairness
            for t in range(len(cycle)):
                pid = cycle[(idx + t) % len(cycle)]
                if pid not in in_series:
                    chosen = pid
                    idx = (idx + t) % len(cycle)
                    break
        assign[pos] = chosen
        if chosen:
            in_series.add(chosen)
            inc_cat(work_cat, position_category(segment, pos), chosen)

    return assign

# -----------------------------
# Header + breadcrumb
# -----------------------------
st.markdown("## Youth Football Rotation Builder")
st.markdown(
    '<div class="small">Order: <b>1)</b> Import & edit roster → <b>2)</b> Choose segment → <b>3)</b> Set Role & Energy → <b>1st Lineup</b>. '
    'In-game, set <b>Change</b> on Current/Next. Picks that would create <b>+2 fairness</b> (within category) are flagged but allowed.</div>',
    unsafe_allow_html=True
)
st.write("")

# -----------------------------
# STAGE 1 — Import + Live Editor (+ Name Pool)
# -----------------------------
if st.session_state.stage == 1:
    with st.container(border=True):
        st.subheader("1) Import roster (CSV) & live edit")

        c_up, c_btns = st.columns([2,3])
        with c_up:
            upl = st.file_uploader("Drop CSV here", type=["csv"])
        with c_btns:
            c1, c2, c3 = st.columns([1,1,1])
            with c1:
                if st.button("Load Sample", use_container_width=True):
                    st.session_state.roster_df = normalize_roster_columns(pd.read_csv(io.StringIO(SAMPLE_CSV)))
                    st.success(f"Imported {len(st.session_state.roster_df)} players from sample.")
            with c2:
                st.download_button("Download CSV Template",
                                   data=build_template_csv_bytes(),
                                   file_name="roster-template.csv",
                                   mime="text/csv",
                                   use_container_width=True)
            with c3:
                if st.button("Add Player", use_container_width=True):
                    df = st.session_state.roster_df
                    if df is None:
                        df = normalize_roster_columns(pd.DataFrame(columns=["Name","Off1","Off2","Off3","Off4","Def1","Def2","Def3","Def4"]))
                    newrow = pd.DataFrame([{
                        "player_id": _new_id(),
                        "name": "New Player",
                        "off1":"", "off2":"", "off3":"", "off4":"",
                        "def1":"", "def2":"", "def3":"", "def4":"",
                        "role_today":"Connector", "energy_today":"Medium"
                    }])
                    st.session_state.roster_df = pd.concat([df, newrow], ignore_index=True)

        if upl is not None:
            try:
                st.session_state.roster_df = parse_csv_bytes(upl.read())
                st.success(f"Imported {len(st.session_state.roster_df)} players.")
            except Exception as e:
                st.error(f"Could not read CSV: {e}")

        # Name Pool manage / select
        with st.expander("📇 Name Pool (optional)", expanded=False):
            c1, c2, c3, c4, c5 = st.columns([1,1,1,1,1])
            with c1:
                pool_file = st.file_uploader("Upload names CSV", type=["csv"], key="pool_upl")
                if pool_file:
                    got = pool_import_csv(pool_file)
                    st.session_state.name_pool = pool_unique_sorted(st.session_state.name_pool + got)
                    st.success(f"Added {len(got)} names to pool.")
            with c2:
                new_name = st.text_input("Add one name", key="pool_new")
                if st.button("Add", use_container_width=True):
                    if new_name.strip():
                        st.session_state.name_pool = pool_unique_sorted(st.session_state.name_pool + [new_name])
                        st.session_state.pool_new = ""
            with c3:
                if st.button("Clear all", type="secondary", use_container_width=True):
                    st.session_state.name_pool = []
            with c4:
                if st.session_state.name_pool:
                    st.download_button("Export CSV",
                                       data=pool_export_bytes(st.session_state.name_pool),
                                       file_name="name-pool.csv",
                                       mime="text/csv",
                                       use_container_width=True)
            with c5:
                if st.session_state.name_pool:
                    picks = st.multiselect("Add to roster", st.session_state.name_pool, key="pool_picks")
                    st.button("Add selected to roster",
                              use_container_width=True, type="primary",
                              disabled=len(picks)==0,
                              on_click=lambda: add_names_to_roster(picks))
            if st.session_state.name_pool:
                st.caption("Names in pool")
                st.dataframe(pd.DataFrame({"Name": st.session_state.name_pool}),
                             use_container_width=True, height=200)
            else:
                st.caption("No names yet. Upload a CSV with a 'Name' column, or add manually.")

        # Live editor table
        st.markdown("#### Live Editor")
        if st.session_state.roster_df is None or len(st.session_state.roster_df)==0:
            st.info("Awaiting CSV… Required headers: Name, Off1–4, Def1–4.")
        else:
            df = st.session_state.roster_df.copy()

            # Provide select options constraints
            col_cfg = {
                "off1": st.column_config.SelectboxColumn(options=[""] + OFF_POS, required=False),
                "off2": st.column_config.SelectboxColumn(options=[""] + OFF_POS, required=False),
                "off3": st.column_config.SelectboxColumn(options=[""] + OFF_POS, required=False),
                "off4": st.column_config.SelectboxColumn(options=[""] + OFF_POS, required=False),
                "def1": st.column_config.SelectboxColumn(options=[""] + ALL_DEF, required=False),
                "def2": st.column_config.SelectboxColumn(options=[""] + ALL_DEF, required=False),
                "def3": st.column_config.SelectboxColumn(options=[""] + ALL_DEF, required=False),
                "def4": st.column_config.SelectboxColumn(options=[""] + ALL_DEF, required=False),
                "role_today": st.column_config.SelectboxColumn(options=ROLES),
                "energy_today": st.column_config.SelectboxColumn(options=ENERGY),
            }

            edited = st.data_editor(
                df,
                use_container_width=True,
                num_rows="dynamic",
                hide_index=True,
                column_config=col_cfg,
                column_order=["name","off1","off2","off3","off4","def1","def2","def3","def4","role_today","energy_today","player_id"],
            )

            # ensure player_id assigned for rows user added
            if "player_id" not in edited.columns:
                edited["player_id"] = ""
            edited["player_id"] = edited["player_id"].apply(lambda x: x if isinstance(x,str) and x else _new_id())

            st.session_state.roster_df = normalize_roster_columns(edited)

        st.write("")
        st.button("Next: Choose Segment →", type="primary", use_container_width=True,
                  on_click=lambda: st.session_state.__setitem__("stage", 2) if (st.session_state.roster_df is not None and len(st.session_state.roster_df)>0) else st.warning("Please import or add players first."),
                  )

# -----------------------------
# STAGE 2 — Choose segment / formation
# -----------------------------
elif st.session_state.stage == 2:
    with st.container(border=True):
        st.subheader("2) Choose segment")
        c1, c2 = st.columns([1,3])
        with c1:
            st.session_state.selected_segment = st.radio("Segment", ["Offense","Defense"], index=0 if st.session_state.selected_segment=="Offense" else 1)
        with c2:
            if st.session_state.selected_segment == "Defense":
                st.session_state.selected_formation = st.segmented_control(
                    "Formation",
                    options=["DEFENSE_53","DEFENSE_44"],
                    format_func=lambda x: "5–3" if x=="DEFENSE_53" else "4–4",
                    default=st.session_state.selected_formation if st.session_state.selected_formation!="OFFENSE" else "DEFENSE_53"
                )
            else:
                st.session_state.selected_formation = "OFFENSE"
                st.caption("Offense has a fixed set of positions.")

        st.write("")
        c_back, c_next = st.columns([1,1])
        with c_back:
            st.button("← Back", use_container_width=True, on_click=lambda: st.session_state.__setitem__("stage", 1))
        with c_next:
            st.button("Next: Set Role & Energy →", type="primary", use_container_width=True,
                      on_click=lambda: st.session_state.__setitem__("stage", 3))

# -----------------------------
# STAGE 3 — Role & Energy
# -----------------------------
elif st.session_state.stage == 3:
    with st.container(border=True):
        st.subheader("3) Set Role & Energy (two taps per player)")
        st.caption("If you skip a player, we’ll default to Connector / Medium.")

        if st.session_state.roster_df is None or len(st.session_state.roster_df)==0:
            st.warning("No roster loaded.")
        else:
            df = st.session_state.roster_df[["player_id","name","role_today","energy_today"]].copy()
            edited = st.data_editor(
                df,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "role_today": st.column_config.SelectboxColumn(options=ROLES),
                    "energy_today": st.column_config.SelectboxColumn(options=ENERGY),
                },
            )
            # merge back
            base = st.session_state.roster_df.set_index("player_id")
            for _, r in edited.iterrows():
                pid = r["player_id"]
                base.loc[pid, "role_today"] = r["role_today"]
                base.loc[pid, "energy_today"] = r["energy_today"]
            st.session_state.roster_df = base.reset_index()

        st.write("")
        c_back, c_next = st.columns([1,1])
        with c_back:
            st.button("← Back", use_container_width=True, on_click=lambda: st.session_state.__setitem__("stage", 2))
        with c_next:
            st.button("Next: 1st Lineup →", type="primary", use_container_width=True,
                      on_click=lambda: st.session_state.__setitem__("stage", 4))

# -----------------------------
# STAGE 4 — 1st Lineup + Game
# -----------------------------
elif st.session_state.stage == 4:
    seg = st.session_state.selected_segment
    fmt = st.session_state.selected_formation
    pos_list = current_positions(seg, fmt)

    # fallback formations (mirror HTML behavior if a custom formation dictionary isn't present)
    if seg == "Defense" and fmt not in ("DEFENSE_53", "DEFENSE_44"):
        fmt = "DEFENSE_53"

    with st.container(border=True):
        c_top_l, c_top_r = st.columns([2,2])
        with c_top_l:
            st.subheader("1st Lineup")
            st.caption("Edit Series 1 below. Remaining series will be generated automatically when the game starts.")
        with c_top_r:
            if not st.session_state.first_lineup_locked:
                if st.button("Set 1st Lineup", type="primary", use_container_width=True):
                    # accept incomplete; we’ll try to fill on start
                    st.session_state.first_lineup_locked = True
                    st.success("1st Lineup locked.")
            else:
                st.markdown('<span class="badge">1st Lineup Locked</span>', unsafe_allow_html=True)

        # Ensure starting lineup exists
        ensure_starting_lineup(seg, fmt)
        starters = get_starting_lineup(seg, fmt)
        if not starters:
            starters = suggest_series1(st.session_state.roster_df, seg, fmt)
            set_starting_lineup(seg, fmt, starters)

        # Draw editable lineup (disable when locked)
        id2name = dict(zip(st.session_state.roster_df["player_id"], st.session_state.roster_df["name"]))
        used_now = {v for v in starters.values() if v}
        new_starters = dict(starters)

        def options_for_position(pos: str, cur_id: Optional[str]) -> Tuple[List[str], List[str]]:
            df = st.session_state.roster_df
            # order: eligible first (by pref rank asc then strength desc), no duplicates
            ids = eligible_ids_for_pos(df, pos, seg, fmt)
            rows = []
            for pid in ids:
                if pid != cur_id and pid in used_now:
                    continue
                pr = pref_rank_for_pos(df, pid, pos, seg, fmt)
                row = df.loc[df["player_id"] == pid].iloc[0]
                s = strength_index(row)
                label = f"{id2name.get(pid,'')}  (pref {pr if pr else '-'})"
                rows.append(((0 if pr else 1, pr if pr else 99, -s, id2name.get(pid,"")), pid, label))
            rows.sort(key=lambda x:x[0])
            opts = [""] + [r[1] for r in rows]
            labels = [""] + [r[2] for r in rows]
            return opts, labels

        grid_cols = st.columns(3)
        for i, pos in enumerate(pos_list):
            with grid_cols[i % 3]:
                cur = starters.get(pos, "")
                opts, labels = options_for_position(pos, cur)
                if st.session_state.first_lineup_locked:
                    # show as static text
                    nm = id2name.get(cur,"(empty)") if cur else "(empty)"
                    st.selectbox(pos, options=[cur] if cur else [""], index=0, disabled=True, key=f"sl_{pos}", format_func=lambda x: id2name.get(x,"(empty)") if x else "(empty)")
                else:
                    sel = st.selectbox(pos, options=opts, index=opts.index(cur) if cur in opts else 0, format_func=lambda x: (labels[opts.index(x)] if x in opts else ""), key=f"sl_{pos}")
                    new_starters[pos] = sel
                    # update used set live
                    used_now = {v for v in new_starters.values() if v}

        if not st.session_state.first_lineup_locked:
            set_starting_lineup(seg, fmt, new_starters)

    # ---------------- Game Card ----------------
    with st.container(border=True):
        st.subheader("Game")
        c1, c2, c3, c4, c5, c6 = st.columns([1,1,1,1,1,2])
        # Build positions (ensure not empty)
        positions = current_positions(seg, fmt)

        # Buttons
        with c1:
            st.button("Start Game",
                      type="primary",
                      use_container_width=True,
                      disabled=not st.session_state.first_lineup_locked or st.session_state.game_active or len(positions)==0,
                      on_click=lambda: (
                          st.session_state.__setitem__("game_active", True),
                          st.session_state.__setitem__("game_turn", 1),
                          st.session_state.__setitem__("game_idx_cycle", 0),
                          st.session_state.__setitem__("game_history", []),
                          st.session_state.__setitem__("game_manual_overrides", {}),
                          st.session_state.__setitem__("game_played_counts", {}),
                          st.session_state.__setitem__("game_played_counts_cat", {}),
                          st.session_state.__setitem__("game_fairness_debt_cat", {}),
                          (lambda cyc_idx: (
                              st.session_state.__setitem__("game_pos_cycles", cyc_idx[0]),
                              st.session_state.__setitem__("game_pos_idx", cyc_idx[1])
                          ))(build_cycles(st.session_state.roster_df, positions, seg, fmt))
                      ))

        with c2:
            def end_series():
                if not st.session_state.game_active:
                    return
                planned_idx = 0  # single planned series (Series 1) like HTML
                manual = st.session_state.game_manual_overrides.get(planned_idx, {})
                eff = compute_effective_lineup(
                    planned_idx, positions,
                    st.session_state.game_played_counts_cat,
                    st.session_state.game_pos_idx,
                    manual,
                    st.session_state.game_fairness_debt_cat,
                    seg, fmt
                )
                # commit counts + advance cycles
                for pos, pid in eff.items():
                    if not pid: continue
                    st.session_state.game_played_counts[pid] = st.session_state.game_played_counts.get(pid, 0) + 1
                    cat = position_category(seg, pos)
                    inc_cat(st.session_state.game_played_counts_cat, cat, pid)
                    cyc = st.session_state.game_pos_cycles.get(pos, [])
                    if pid in cyc and cyc:
                        st.session_state.game_pos_idx[pos] = (cyc.index(pid) + 1) % len(cyc)

                st.session_state.game_history.append({"turn": st.session_state.game_turn, "lineup": eff})
                st.session_state.game_idx_cycle = (st.session_state.game_idx_cycle + 1) % 1
                st.session_state.game_turn += 1
                # clear manual for this index
                if planned_idx in st.session_state.game_manual_overrides:
                    st.session_state.game_manual_overrides.pop(planned_idx, None)

                # recompute debt
                new_debt: Dict[str, Dict[str,int]] = {}
                for pos in positions:
                    cat = position_category(seg, pos)
                    elig = eligible_ids_for_pos(st.session_state.roster_df, pos, seg, fmt)
                    if not elig: continue
                    base = st.session_state.game_played_counts_cat.get(cat, {})
                    m = min((base.get(i,0) for i in elig), default=0)
                    for i in elig:
                        over = base.get(i,0) - (m + 1)
                        if over > 0:
                            new_debt.setdefault(cat, {})[i] = over
                st.session_state.game_fairness_debt_cat = new_debt

            st.button("End Series", use_container_width=True, disabled=not st.session_state.game_active, on_click=end_series)

        with c3:
            st.button("End Game",
                      use_container_width=True,
                      disabled=not st.session_state.game_active,
                      on_click=lambda: (
                          st.session_state.__setitem__("game_active", False),
                          st.session_state.__setitem__("game_idx_cycle", 0),
                          st.session_state.__setitem__("game_turn", 1),
                      ))

        with c4:
            show_review = st.button("Review Last", use_container_width=True, disabled=st.session_state.game_active or len(st.session_state.game_history)==0)

        with c5:
            show_rt = st.button("Real-time Stats", use_container_width=True, disabled=not st.session_state.game_active)

        with c6:
            badge = ("Playing — Series " + str(st.session_state.game_turn)) if st.session_state.game_active else ("Ready" if st.session_state.first_lineup_locked else "Awaiting 1st lineup…")
            st.markdown(f'<div class="badge">{badge}</div>', unsafe_allow_html=True)

        # Previous
        if st.session_state.game_history:
            last = st.session_state.game_history[-1]
            with st.expander(f"Previous — Series {last['turn']}", expanded=False):
                rows = []
                for pos in positions:
                    pid = last["lineup"].get(pos)
                    rows.append([pos, id2name.get(pid or "", "")])
                st.table(pd.DataFrame(rows, columns=["Position","Player"]))

        # Current / Next panels with fairness flags
        if st.session_state.game_active:
            planned_idx = 0  # single planned series
            cur_manual = st.session_state.game_manual_overrides.get(planned_idx, {})
            cur_eff = compute_effective_lineup(
                planned_idx, positions,
                st.session_state.game_played_counts_cat,
                st.session_state.game_pos_idx,
                cur_manual,
                st.session_state.game_fairness_debt_cat,
                seg, fmt
            )

            # simulate NEXT
            sim_cat = {c: v.copy() for c,v in st.session_state.game_played_counts_cat.items()}
            for pos, pid in cur_eff.items():
                if pid:
                    inc_cat(sim_cat, position_category(seg, pos), pid)

            next_manual = st.session_state.game_manual_overrides.get((planned_idx+1)%1, {})
            next_eff = compute_effective_lineup(
                (planned_idx+1)%1, positions,
                sim_cat,
                st.session_state.game_pos_idx,
                next_manual,
                st.session_state.game_fairness_debt_cat,
                seg, fmt
            )

            c_cur, c_next = st.columns(2)
            with c_cur:
                st.markdown(f"**Current — Series {st.session_state.game_turn}**")
                for pos in positions:
                    # Build base counts excluding current pos but including others for warning
                    base = {c: v.copy() for c,v in st.session_state.game_played_counts_cat.items()}
                    for pp, pid2 in cur_eff.items():
                        if pp != pos and pid2:
                            inc_cat(base, position_category(seg, pp), pid2)
                    taken = {pid2 for pp, pid2 in cur_eff.items() if pp != pos and pid2}
                    cands = [pid for pid in eligible_ids_for_pos(st.session_state.roster_df, pos, seg, fmt) if pid not in taken]
                    opts = ["(auto)"]; labels = ["(auto – follow plan/fairness)"]
                    m = min_cat(base, position_category(seg, pos), eligible_ids_for_pos(st.session_state.roster_df, pos, seg, fmt))
                    for pid in cands:
                        nm = id2name.get(pid,"")
                        pr = pref_rank_for_pos(st.session_state.roster_df, pid, pos, seg, fmt)
                        curv = base.get(position_category(seg, pos), {}).get(pid, 0)
                        warn = (curv + 1) > (m + 1)
                        tag = " ⚠ Fairness" if warn else " OK"
                        labels.append(f"{nm}  (pref {pr if pr else '-'}){tag}")
                        opts.append(pid)
                    sel = st.selectbox(pos, options=opts, key=f"cur_{pos}")
                    mo = st.session_state.game_manual_overrides.get(planned_idx, {}).copy()
                    if sel == "(auto)":
                        mo.pop(pos, None)
                    else:
                        mo[pos] = sel
                    st.session_state.game_manual_overrides[planned_idx] = mo

            with c_next:
                st.markdown(f"**Next — Series {st.session_state.game_turn + 1}**")
                for pos in positions:
                    base = {c: v.copy() for c,v in sim_cat.items()}
                    for pp, pid2 in next_eff.items():
                        if pp != pos and pid2:
                            inc_cat(base, position_category(seg, pp), pid2)
                    taken = {pid2 for pp, pid2 in next_eff.items() if pp != pos and pid2}
                    cands = [pid for pid in eligible_ids_for_pos(st.session_state.roster_df, pos, seg, fmt) if pid not in taken]
                    opts = ["(auto)"]; labels = ["(auto – follow plan/fairness)"]
                    m = min_cat(base, position_category(seg, pos), eligible_ids_for_pos(st.session_state.roster_df, pos, seg, fmt))
                    for pid in cands:
                        nm = id2name.get(pid,"")
                        pr = pref_rank_for_pos(st.session_state.roster_df, pid, pos, seg, fmt)
                        curv = base.get(position_category(seg, pos), {}).get(pid, 0)
                        warn = (curv + 1) > (m + 1)
                        tag = " ⚠ Fairness" if warn else " OK"
                        labels.append(f"{nm}  (pref {pr if pr else '-'}){tag}")
                        opts.append(pid)
                    sel = st.selectbox(pos + " ", options=opts, key=f"next_{pos}")
                    mo2 = st.session_state.game_manual_overrides.get((planned_idx+1)%1, {}).copy()
                    if sel == "(auto)":
                        mo2.pop(pos, None)
                    else:
                        mo2[pos] = sel
                    st.session_state.game_manual_overrides[(planned_idx+1)%1] = mo2

        # Real-time stats
        if st.session_state.game_active and show_rt:
            rows = [{"Player": id2name[pid], "Appearances so far": cnt}
                    for pid, cnt in sorted(st.session_state.game_played_counts.items(),
                                           key=lambda x: (-x[1], id2name.get(x[0],"")))]
            st.info("Real-time Stats")
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True)
            else:
                st.caption("No series completed yet.")

        # Review/summary (after End Game or via button)
        if (not st.session_state.game_active and st.session_state.game_history) or show_review:
            st.markdown("---")
            st.subheader("Game Summary")
            # appearances table
            rows = []
            for pid, cnt in st.session_state.game_played_counts.items():
                rows.append({"Player": id2name.get(pid,""), "Appearances": cnt})
            out = pd.DataFrame(rows).sort_values(["Appearances","Player"], ascending=[False, True]) if rows else pd.DataFrame(columns=["Player","Appearances"])
            st.dataframe(out, use_container_width=True)

            # All played series accordion
            with st.expander("All Played Series", expanded=True):
                for item in st.session_state.game_history:
                    with st.expander(f"Series {item['turn']}", expanded=False):
                        tbl = []
                        for pos in positions:
                            pid = item["lineup"].get(pos)
                            tbl.append([pos, id2name.get(pid or "", "")])
                        st.table(pd.DataFrame(tbl, columns=["Position","Player"]))

            # Export Played Rotations CSV
            csv_rows = []
            for item in st.session_state.game_history:
                csv_rows.append([f"Series {item['turn']}"])
                csv_rows.append(["Position","Player"])
                for pos in positions:
                    pid = item["lineup"].get(pos)
                    csv_rows.append([pos, id2name.get(pid or "", "")])
                csv_rows.append([])
            st.download_button(
                "Download Played Rotations (CSV)",
                data=to_csv(csv_rows),
                file_name="played-rotations.csv",
                mime="text/csv",
                use_container_width=True,
            )

    # Tip: show readiness state line
    st.caption("Tip: you can start the game without filling every position — we’ll try to auto-fill with eligible players.")

# -----------------------------
# Footer nav
# -----------------------------
st.write("")
c_prev, c_next = st.columns([1,1])
with c_prev:
    if st.session_state.stage > 1:
        st.button("← Back", use_container_width=True, on_click=lambda: st.session_state.__setitem__("stage", st.session_state.stage-1))
with c_next:
    if st.session_state.stage < 4:
        st.button("Next →", use_container_width=True, type="primary", on_click=lambda: st.session_state.__setitem__("stage", st.session_state.stage+1))
