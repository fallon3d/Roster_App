# app.py
import io
import os
from typing import Dict, List, Optional, Set

import numpy as np
import pandas as pd
import streamlit as st

from rotation_core.config import (
    DEFAULT_CONFIG,
    ROLE_SCORE,
    ENERGY_SCORE,
    load_formations_file,
    ensure_assets_exist,
    ui_css,
    aliases_for_position,  # visual uses eligible list via aliases
)
from rotation_core.io import (
    load_roster_csv,
    save_roster_csv_bytes,
    generate_template_csv_bytes,
    load_formations_yaml,
    save_formations_yaml,
    detect_pref_cols,
)
from rotation_core.models import AppConfig
from rotation_core.constraints import (
    validate_roster,
    compute_fairness_bounds,
    check_impossible_minimums,
    detect_duplicate_starters,
    series_grid_to_df,
    fairness_dashboard_df,
)
from rotation_core.scheduler import schedule_rotation
from rotation_core.export_pdf import render_pdf


# ---------- Page & Theme ----------
st.set_page_config(page_title="Youth Football Rotation Builder", layout="wide")
st.markdown(ui_css(), unsafe_allow_html=True)

ensure_assets_exist()

# ---------- Session State ----------
def _init_state():
    ss = st.session_state
    ss.setdefault("stage", 1)  # 1..4
    ss.setdefault("roster_df", None)
    ss.setdefault("formations", load_formations_yaml("assets/formations.yaml"))
    ss.setdefault("app_config", AppConfig(**DEFAULT_CONFIG))
    ss.setdefault("starting_lineup", {"Offense": {}, "Defense": {}})
    ss.setdefault("assignments", {"Offense": {}, "Defense": {}})
    ss.setdefault("selected_category", "Defense")
    ss.setdefault("selected_formation", "DEFENSE_53")
    ss.setdefault("excluded_ids", set())
    ss.setdefault("random_seed", 42)

_init_state()

# ---------- Sidebar (kept as advanced) ----------
with st.sidebar:
    st.header("⚙️ Advanced Config")
    total_series = st.number_input("Total series", min_value=1, max_value=40, value=st.session_state.app_config.total_series, step=1)
    evenness_cap_enabled = st.checkbox("Evenness Cap (±)", value=st.session_state.app_config.evenness_cap_enabled)
    evenness_cap_value = st.number_input("Cap value", min_value=0, max_value=4, value=st.session_state.app_config.evenness_cap_value, step=1)

    # preference weights: auto-length based on roster (default 2)
    pref_count = 2
    if st.session_state.roster_df is not None:
        off_cols = detect_pref_cols(st.session_state.roster_df, "Offense")
        def_cols = detect_pref_cols(st.session_state.roster_df, "Defense")
        pref_count = max(len(off_cols), len(def_cols)) or 2
    default_pw = ",".join(["1.0", "0.6", "0.3", "0.1"][:pref_count])
    pref_weights_str = st.text_input("Preference weights", value=default_pw, help="Comma separated; length auto-detected from CSV columns")

    objective_mu = st.number_input("μ (mismatch penalty)", min_value=0.0, max_value=10.0, value=st.session_state.app_config.objective_mu, step=0.1)
    rand = st.number_input("Random seed", min_value=0, max_value=10_000, value=st.session_state.random_seed, step=1)

    def _parse_weights(s: str) -> List[float]:
        try:
            parts = [float(x.strip()) for x in s.split(",") if x.strip() != ""]
            if not parts:
                raise ValueError
            return parts
        except Exception:
            st.warning("Invalid weights; falling back to [1.0,0.6].")
            return [1.0, 0.6]

    # apply
    st.session_state.app_config.total_series = total_series
    st.session_state.app_config.evenness_cap_enabled = evenness_cap_enabled
    st.session_state.app_config.evenness_cap_value = evenness_cap_value
    st.session_state.app_config.preference_weights = _parse_weights(pref_weights_str)
    st.session_state.app_config.objective_mu = objective_mu
    st.session_state.random_seed = rand
    st.session_state.app_config.random_seed = rand

    st.divider()
    st.subheader("📄 Files")
    colT, colS = st.columns(2)
    with colT:
        st.download_button("template.csv", data=generate_template_csv_bytes(), file_name="template.csv", mime="text/csv")
    with colS:
        with open("assets/sample_roster.csv", "rb") as f:
            st.download_button("sample_roster.csv", data=f.read(), file_name="sample_roster.csv", mime="text/csv")

    st.divider()
    st.subheader("📐 Formations")
    if st.button("Reload formations.yaml"):
        st.session_state.formations = load_formations_yaml("assets/formations.yaml")
        st.success("Formations reloaded.")

# ---------- Header card ----------
st.markdown(
    """
<div class="app">
  <div class="card section">
    <h2>Youth Football Rotation Builder</h2>
    <div class="small">Order: 1) Import & edit roster → 2) Choose segment → 3) Set Role & Energy → <b>1st Lineup</b>. Solver fills remaining series with fairness first, strength next.</div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# helpers
def _card_start():
    st.markdown('<div class="app"><div class="card section">', unsafe_allow_html=True)

def _card_end():
    st.markdown("</div></div>", unsafe_allow_html=True)

def _chip_row():
    st.markdown(
        """
<div class="row" style="margin:6px 0 12px">
  <div class="chip {a1}">1) Import</div>
  <div class="chip {a2}">2) Segment</div>
  <div class="chip {a3}">3) Ratings</div>
  <div class="chip {a4}">4) 1st Lineup</div>
</div>
""".format(
            a1="active" if st.session_state.stage == 1 else "",
            a2="active" if st.session_state.stage == 2 else "",
            a3="active" if st.session_state.stage == 3 else "",
            a4="active" if st.session_state.stage == 4 else "",
        ),
        unsafe_allow_html=True,
    )

def _stage_nav(back_to=None, next_to=None, next_label="Next"):
    cols = st.columns([1, 1])
    with cols[0]:
        if back_to is not None and st.button("Back", key=f"back_{back_to}", use_container_width=True):
            st.session_state.stage = back_to
            st.rerun()
    with cols[1]:
        if next_to is not None and st.button(next_label, key=f"next_{next_to}", use_container_width=True):
            st.session_state.stage = next_to
            st.rerun()

def _eligible_mask(df: pd.DataFrame, category: str, pos: str):
    pos_aliases = aliases_for_position(pos)
    elig_cols = detect_pref_cols(df, category)
    return df[elig_cols].apply(lambda r: any(str(v).strip() in pos_aliases for v in r.values), axis=1)

# ============================================================
# STAGE 1 — Import roster (CSV) & live editor
# ============================================================
if st.session_state.stage == 1:
    _card_start()
    _chip_row()
    st.markdown("<h3>1) Import roster (CSV) & live edit</h3>", unsafe_allow_html=True)

    # Drop area UI mimic: Streamlit uploader + buttons
    up_col1, up_col2, up_col3 = st.columns([2, 1, 1])
    with up_col1:
        file = st.file_uploader("Drop CSV here or click to select", type=["csv"])
    with up_col2:
        st.caption("Load sample")
        if st.button("Load sample roster"):
            with open("assets/sample_roster.csv", "rb") as f:
                st.session_state.roster_df = pd.read_csv(io.BytesIO(f.read()))
                st.success("Sample loaded into live editor.")
    with up_col3:
        st.caption("Download template")
        st.download_button("Download template.csv", data=generate_template_csv_bytes(), file_name="template.csv", mime="text/csv")

    if file is not None:
        try:
            df = load_roster_csv(file)
            st.session_state.roster_df = df
            st.success(f"Imported {len(df)} players.")
        except Exception as e:
            st.error(f"Error loading CSV: {e}")

    st.markdown('<div style="max-height:360px;overflow:auto;border:1px solid var(--line);border-radius:12px">', unsafe_allow_html=True)
    if st.session_state.roster_df is None:
        st.info("No roster loaded yet. Use the buttons above.")
        editable_df = None
    else:
        df = st.session_state.roster_df.copy()

        # Live editor with select options for positions (keeps your logic unchanged)
        st.caption("Live Editor")
        editable_df = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

    if editable_df is not None:
        st.session_state.roster_df = editable_df
        errors = validate_roster(editable_df)
        if errors:
            st.error("Validation errors:")
            for e in errors:
                st.write("•", e)
        else:
            st.success("Roster looks valid ✅")

    _stage_nav(back_to=None, next_to=2, next_label="Next: Choose segment")
    _card_end()

# ============================================================
# STAGE 2 — Choose segment (Offense / Defense + formation)
# ============================================================
elif st.session_state.stage == 2:
    _card_start()
    _chip_row()
    st.markdown("<h3>2) Choose segment</h3>", unsafe_allow_html=True)

    if st.session_state.roster_df is None:
        st.info("Upload a roster in stage 1 first.")
        _stage_nav(back_to=1, next_to=None)
        _card_end()
    else:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.session_state.selected_category = st.radio("Segment", ["Offense", "Defense"], horizontal=True, key="seg_radio")
        with c2:
            formation_names = list(st.session_state.formations.get(st.session_state.selected_category, {}).keys())
            if not formation_names:
                st.warning("No formations defined for this segment.")
            else:
                # if Defense, your default is 5-3 (DEFENSE_53)
                default_idx = 0
                if st.session_state.selected_category == "Defense" and "DEFENSE_53" in formation_names:
                    default_idx = formation_names.index("DEFENSE_53")
                st.session_state.selected_formation = st.selectbox("Formation", formation_names, index=default_idx)

        # Optional: mark unavailable players
        df = st.session_state.roster_df
        unavailable = st.multiselect(
            "Mark players unavailable/injured (excluded for this match):",
            options=list(df["name"].values),
            default=[],
        )
        st.session_state.excluded_ids = set(df[df["name"].isin(unavailable)]["player_id"].astype(str).tolist())

        # Feasibility notice
        positions = st.session_state.formations.get(st.session_state.selected_category, {}).get(st.session_state.selected_formation, [])
        T = len(positions) * st.session_state.app_config.total_series
        P = len(df) - len(st.session_state.excluded_ids)
        msg = check_impossible_minimums(T, P)
        if msg:
            st.warning(msg)

        _stage_nav(back_to=1, next_to=3, next_label="Next: Set Role & Energy")
        _card_end()

# ============================================================
# STAGE 3 — Ratings (Role & Energy) quick editor
# ============================================================
elif st.session_state.stage == 3:
    _card_start()
    _chip_row()
    st.markdown("<h3>3) Set Role & Energy (two taps per player)</h3>", unsafe_allow_html=True)
    st.caption("Roles: newer/learning • steady/reliable • confident/impactful — Energy: Low • Medium • High")

    if st.session_state.roster_df is None:
        st.info("Upload a roster in stage 1 first.")
        _stage_nav(back_to=2, next_to=None)
        _card_end()
    else:
        df = st.session_state.roster_df.copy()
        # constrain values via data_editor column_config
        role_opts = list(ROLE_SCORE.keys())
        energy_opts = list(ENERGY_SCORE.keys())
        st.markdown('<div style="max-height:380px;overflow:auto;border:1px solid var(--line);border-radius:12px;margin-top:8px">', unsafe_allow_html=True)
        edited = st.data_editor(
            df,
            use_container_width=True,
            column_config={
                "role_today": st.column_config.SelectboxColumn("role_today", options=role_opts, width="small"),
                "energy_today": st.column_config.SelectboxColumn("energy_today", options=energy_opts, width="small"),
            },
        )
        st.markdown("</div>", unsafe_allow_html=True)
        st.session_state.roster_df = edited

        _stage_nav(back_to=2, next_to=4, next_label="Next: 1st Lineup")
        _card_end()

# ============================================================
# STAGE 4 — First Lineup (Series 1) + Generate & Show results
# ============================================================
elif st.session_state.stage == 4:
    _card_start()
    _chip_row()
    st.markdown("<h3>1st Lineup (Series 1)</h3>", unsafe_allow_html=True)

    if st.session_state.roster_df is None:
        st.info("Upload a roster in stage 1 first.")
        _stage_nav(back_to=3, next_to=None)
        _card_end()
    else:
        category = st.session_state.selected_category
        formation_name = st.session_state.selected_formation
        positions = st.session_state.formations.get(category, {}).get(formation_name, [])
        df = st.session_state.roster_df.copy()
        all_players = dict(zip(df["player_id"].astype(str), df["name"]))

        st.caption("Pick your Series 1 starters. Leave any position blank; smart fill will cover it.")
        start_map = st.session_state.starting_lineup.get(category, {}).get(formation_name, {}) or {}

        # Render fancy grid of selects (styled by CSS)
        cols = st.columns(3)
        for i, pos in enumerate(positions):
            if i % 3 == 0 and i > 0:
                cols = st.columns(3)
            with cols[i % 3]:
                mask = _eligible_mask(df, category, pos)
                eligible_df = df[mask]
                opts = [""] + [f"{pid} | {all_players[str(pid)]}" for pid in eligible_df["player_id"].astype(str)]
                cur = start_map.get(pos, "")
                label = f"{pos}"
                val = st.selectbox(label, options=opts, index=opts.index(cur) if cur in opts else 0, key=f"starter_{category}_{formation_name}_{pos}")
                pid = val.split(" | ")[0] if val else ""
                start_map[pos] = pid if pid else None

        # Persist and validate duplicates
        st.session_state.starting_lineup.setdefault(category, {})
        st.session_state.starting_lineup[category][formation_name] = start_map
        dupes = detect_duplicate_starters(start_map)
        if dupes:
            st.error(f"Duplicate starter assignments found: {', '.join(dupes)}")

        st.markdown("---")
        left, right = st.columns([1, 2])
        with left:
            if st.button("Generate Rotation (ILP → heuristic fallback)", use_container_width=True):
                rng = np.random.default_rng(st.session_state.random_seed)
                result = schedule_rotation(
                    df=df,
                    category=category,
                    formation_positions=positions,
                    starting_lineup=start_map,
                    config=st.session_state.app_config,
                    excluded_ids=st.session_state.excluded_ids,
                    rng=rng,
                )
                if result.error and result.assignment is None:
                    st.error(result.error)
                else:
                    st.session_state.assignments[category][formation_name] = result.assignment
                    if result.error:
                        st.warning(result.error)
                    st.success("Rotation generated ✅")
        with right:
            st.caption("Tip: After generating, scroll to see the Rotation Board, Fairness Dashboard, and Export cards.")

        _card_end()

        # ---------- Rotation Board ----------
        assignment = st.session_state.assignments.get(category, {}).get(formation_name)
        if assignment:
            _card_start()
            st.markdown("<h3>Rotation Board</h3>", unsafe_allow_html=True)
            grid_df = series_grid_to_df(
                assignment=assignment,
                positions=positions,
                roster_df=df,
                category=category,
            )
            st.dataframe(grid_df, use_container_width=True, height=min(600, 50 + 28 * len(grid_df)))
            st.caption("Badge: (⚠) appears only if assignment falls below top preferences.")
            _card_end()

            # ---------- Fairness Dashboard ----------
            _card_start()
            st.markdown("<h3>Fairness Dashboard</h3>", unsafe_allow_html=True)
            dash = fairness_dashboard_df(assignment, df, st.session_state.app_config)
            st.dataframe(dash, use_container_width=True, height=min(600, 50 + 28 * len(dash)))
            _card_end()

            # ---------- Export ----------
            _card_start()
            st.markdown("<h3>Export</h3>", unsafe_allow_html=True)
            csv_bytes = grid_df.to_csv(index=True).encode("utf-8")
            fname = f"rotation_{category.lower()}_{formation_name.replace(' ','_')}.csv"
            col1, col2 = st.columns(2)
            with col1:
                st.download_button("Download CSV", data=csv_bytes, file_name=fname, mime="text/csv", use_container_width=True)
            with col2:
                pdf_bytes = render_pdf(
                    category=category,
                    formation_name=formation_name,
                    positions=positions,
                    grid_df=grid_df,
                )
                pdf_name = f"rotation_{category.lower()}_{formation_name.replace(' ','_')}.pdf"
                st.download_button("Download PDF", data=pdf_bytes, file_name=pdf_name, mime="application/pdf", use_container_width=True)
            _card_end()

        # nav
        _card_start()
        _stage_nav(back_to=3, next_to=None)
        _card_end()
