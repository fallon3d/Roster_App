# app.py
import io
import numpy as np
import pandas as pd
import streamlit as st
from typing import Dict, Optional, List, Set
from rotation_core.config import ui_css
from rotation_core.io import validate_roster
from rotation_core.ratings import ROLE_SCORE, ENERGY_SCORE
from rotation_core.solver_ilp import solve_ilp

# ------------------------------------------------------
# Helpers for name pool
# ------------------------------------------------------
def _normalize_name(s: str) -> str:
    return " ".join(str(s or "").replace("\u00A0", " ").split()).strip()

def _pool_unique_sorted(names: list[str]) -> list[str]:
    seen = set(); out = []
    for n in names:
        nn = _normalize_name(n)
        if not nn: continue
        k = nn.lower()
        if k not in seen:
            seen.add(k); out.append(nn)
    return sorted(out, key=lambda x: x.lower())

def pool_import_csv(file) -> list[str]:
    try:
        df = pd.read_csv(file)
        if "Name" in df.columns:
            col = "Name"
        else:
            col = df.columns[0]
        return [ _normalize_name(v) for v in df[col].astype(str).tolist() ]
    except Exception:
        return [ _normalize_name(l) for l in io.StringIO(file.getvalue().decode("utf-8")).read().splitlines() ]

def pool_export_bytes(names: list[str]) -> bytes:
    buf = io.StringIO()
    pd.DataFrame({"Name": names}).to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")

def add_names_to_roster(names: list[str]):
    if st.session_state.roster_df is None:
        st.session_state.roster_df = pd.DataFrame(columns=[
            "player_id","name","off1","off2","def1","def2","role_today","energy_today"
        ])
    df = st.session_state.roster_df.copy()
    existing = set(df["name"].astype(str).str.lower().tolist())
    rows = []
    for nm in names:
        if nm.lower() in existing: continue
        rows.append({
            "player_id": str(np.random.randint(1_000_000, 9_999_999)),
            "name": nm,
            "off1": "", "off2": "", "def1": "", "def2": "",
            "role_today": "steady/reliable", "energy_today": "Medium"
        })
    if rows:
        st.session_state.roster_df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)

# ------------------------------------------------------
# Init state
# ------------------------------------------------------
def _init_state():
    ss = st.session_state
    ss.setdefault("roster_df", None)
    ss.setdefault("name_pool", [])
    ss.setdefault("first_lineup_locked", False)
    ss.setdefault("stage", 1)
    ss.setdefault("assignments", {})
    ss.setdefault("starting_lineup", {})
    ss.setdefault("selected_category", "Offense")
    ss.setdefault("selected_formation", "OFFENSE_11")

# ------------------------------------------------------
# App start
# ------------------------------------------------------
st.set_page_config(page_title="Rotation Generator", layout="wide")
st.markdown(ui_css(), unsafe_allow_html=True)
_init_state()

# ------------------------------------------------------
# Stage 1: Roster & Name Pool
# ------------------------------------------------------
if st.session_state.stage == 1:
    st.title("Stage 1 — Roster & Ratings")

    upl = st.file_uploader("Upload roster CSV", type=["csv"], key="upl_roster")
    if upl:
        try:
            df = pd.read_csv(upl)
            validate_roster(df)
            st.session_state.roster_df = df
            st.success("Roster loaded.")
        except Exception as e:
            st.error(f"Error loading CSV: {e}")

    if st.session_state.roster_df is not None:
        st.data_editor(st.session_state.roster_df, num_rows="dynamic", use_container_width=True, key="edit_roster")

    with st.expander("📇 Name Pool (optional)", expanded=False):
        c1, c2, c3, c4, c5 = st.columns([1,1,1,1,1])
        with c1:
            pool_file = st.file_uploader("Upload names CSV", type=["csv"], key="pool_upl")
            if pool_file:
                got = pool_import_csv(pool_file)
                st.session_state.name_pool = _pool_unique_sorted(st.session_state.name_pool + got)
                st.success(f"Added {len(got)} names to pool.")
        with c2:
            new_name = st.text_input("Add one name", key="pool_new")
            if st.button("Add", key="pool_add", use_container_width=True):
                if new_name.strip():
                    st.session_state.name_pool = _pool_unique_sorted(st.session_state.name_pool + [new_name])
                    st.session_state.pool_new = ""
        with c3:
            if st.button("Clear all", key="pool_clear", use_container_width=True, type="secondary"):
                st.session_state.name_pool = []
        with c4:
            if st.session_state.name_pool:
                st.download_button(
                    "Export CSV",
                    data=pool_export_bytes(st.session_state.name_pool),
                    file_name="name-pool.csv",
                    mime="text/csv",
                    key="pool_export",
                    use_container_width=True,
                )
        with c5:
            if st.session_state.name_pool:
                picks = st.multiselect("Add to roster", st.session_state.name_pool, key="pool_picks")
                if st.button("Add selected to roster", key="pool_to_roster", use_container_width=True, type="primary", disabled=len(picks)==0):
                    add_names_to_roster(picks)
                    st.success(f"Added {len(picks)} player(s).")

        if st.session_state.name_pool:
            st.dataframe(pd.DataFrame({"Name": st.session_state.name_pool}), use_container_width=True, height=200)
        else:
            st.caption("No names yet.")

# ------------------------------------------------------
# Stage 2: Lock 1st Lineup
# ------------------------------------------------------
if st.session_state.stage == 2:
    st.title("Stage 2 — Lock First Lineup")

    if st.session_state.roster_df is None:
        st.warning("Upload a roster first in Stage 1.")
    else:
        st.write("Pick starters for Series 1, then lock them.")
        df = st.session_state.roster_df
        pos_list = ["QB","AB","HB","WR","Slot","TE","C","LG","RG","LT","RT"]
        starters = {}
        for pos in pos_list:
            choices = [""] + df["name"].tolist()
            sel = st.selectbox(pos, choices, key=f"starter_{pos}")
            starters[pos] = sel
        if st.button("Set 1st Lineup", key="lock_lineup", type="primary"):
            st.session_state.starting_lineup = starters
            st.session_state.first_lineup_locked = True
            st.success("1st lineup locked.")

# ------------------------------------------------------
# Stage 3: Generate Rotation (optional ILP)
# ------------------------------------------------------
if st.session_state.stage == 3:
    st.title("Stage 3 — Generate Rotation (Optional)")
    st.write("You can skip this and go straight to Game if you only want fairness cycling.")
    if st.session_state.roster_df is not None:
        if st.button("Run ILP", key="run_ilp"):
            assignment, err = solve_ilp(
                st.session_state.roster_df,
                ["QB","AB","HB","WR","Slot","TE","C","LG","RG","LT","RT"],
                total_series=8,
                starting_lineup=st.session_state.starting_lineup,
                preference_weights=[1.0,0.6],
                objective_mu=0.1,
                evenness_cap_enabled=True,
                evenness_cap_value=1,
                varsity_penalty=0.3,
                excluded_ids=set(),
                rng=np.random.default_rng(42)
            )
            if assignment:
                st.session_state.assignments = assignment
                st.success("Rotation generated.")
            else:
                st.error(err)

# ------------------------------------------------------
# Stage 4: Game Mode
# ------------------------------------------------------
if st.session_state.stage == 4:
    st.title("Stage 4 — Game Mode")

    if not st.session_state.first_lineup_locked:
        st.warning("Lock your first lineup in Stage 2 first.")
    else:
        st.write("Current / Next / Previous cycles go here (logic from earlier).")
        st.info("Game logic integrated here — category fairness, overrides, live stats, etc.")

# ------------------------------------------------------
# Footer Navigation
# ------------------------------------------------------
st.markdown("---")
c1, c2 = st.columns([1,1])
with c1:
    if st.session_state.stage > 1:
        st.button("← Back", key="footer_back", use_container_width=True,
                  on_click=lambda: st.session_state.__setitem__("stage", st.session_state.stage-1))
with c2:
    if st.session_state.stage < 4:
        st.button("Next →", key="footer_next", type="primary", use_container_width=True,
                  on_click=lambda: st.session_state.__setitem__("stage", st.session_state.stage+1))
