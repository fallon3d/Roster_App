# app.py
import io
import os
from typing import Dict, List, Optional

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
)
from rotation_core.io import (
    load_roster_csv,
    save_roster_csv_bytes,
    generate_template_csv_bytes,
    load_formations_yaml,
    save_formations_yaml,
)
from rotation_core.models import AppConfig
from rotation_core.ratings import compute_strength_index_series
from rotation_core.constraints import (
    validate_roster,
    build_eligibility_maps,
    compute_fairness_bounds,
    check_impossible_minimums,
    detect_duplicate_starters,
    series_grid_to_df,
    fairness_dashboard_df,
    assignment_badges_for_cell,
)
from rotation_core.scheduler import schedule_rotation
from rotation_core.export_pdf import render_pdf


# ---------- Streamlit Page Setup ----------
st.set_page_config(page_title="Youth Football Rotation Generator", layout="wide")
st.markdown(ui_css(), unsafe_allow_html=True)

ensure_assets_exist()

# ---------- Session State ----------
if "roster_df" not in st.session_state:
    st.session_state.roster_df = None

if "formations" not in st.session_state:
    st.session_state.formations = load_formations_yaml("assets/formations.yaml")

if "app_config" not in st.session_state:
    st.session_state.app_config = AppConfig(**DEFAULT_CONFIG)

if "starting_lineup" not in st.session_state:
    # Dict[category]["formation_name"]["pos"] = player_id or None
    st.session_state.starting_lineup = {"Offense": {}, "Defense": {}}

if "assignments" not in st.session_state:
    # Dict[category]["formation_name"] = List[Dict[pos, player_id]]
    st.session_state.assignments = {"Offense": {}, "Defense": {}}

if "random_seed" not in st.session_state:
    st.session_state.random_seed = 42


# ---------- Sidebar Controls ----------
with st.sidebar:
    st.header("⚙️ Config")
    total_series = st.number_input("Total series", min_value=1, max_value=40, value=8, step=1)
    varsity_penalty = st.number_input("Varsity penalty (slots)", min_value=0.0, max_value=2.0, value=0.3, step=0.1)
    evenness_cap_enabled = st.checkbox("Enforce Evenness Cap (± cap)", value=True)
    evenness_cap_value = st.number_input("Evenness Cap (±)", min_value=0, max_value=4, value=1, step=1)
    pref_weights_str = st.text_input("Preference weights [w1,w2,w3,w4]", value="1.0,0.6,0.3,0.1")
    objective_lambda = st.number_input("λ (balance proxy)", min_value=0.0, max_value=10.0, value=0.0, step=0.1)
    objective_mu = st.number_input("μ (mismatch penalty)", min_value=0.0, max_value=10.0, value=1.0, step=0.1)
    st.session_state.random_seed = st.number_input("Random seed (deterministic)", min_value=0, max_value=10_000, value=42, step=1)

    def _parse_weights(s: str) -> List[float]:
        try:
            parts = [float(x.strip()) for x in s.split(",")]
            if len(parts) != 4:
                raise ValueError
            return parts
        except Exception:
            st.warning("Invalid preference weights; reverting to [1.0,0.6,0.3,0.1].")
            return [1.0, 0.6, 0.3, 0.1]

    pref_weights = _parse_weights(pref_weights_str)

    # Update app_config model
    st.session_state.app_config.total_series = total_series
    st.session_state.app_config.varsity_penalty = varsity_penalty
    st.session_state.app_config.evenness_cap_enabled = evenness_cap_enabled
    st.session_state.app_config.evenness_cap_value = evenness_cap_value
    st.session_state.app_config.preference_weights = pref_weights
    st.session_state.app_config.objective_lambda = objective_lambda
    st.session_state.app_config.objective_mu = objective_mu
    st.session_state.app_config.random_seed = st.session_state.random_seed

    st.divider()
    st.subheader("📄 Files")
    st.caption("Download a clean template (headers only) or a realistic sample roster.")
    colT, colS = st.columns(2)
    with colT:
        st.download_button(
            "Download template.csv",
            data=generate_template_csv_bytes(),
            file_name="template.csv",
            mime="text/csv",
        )
    with colS:
        with open("assets/sample_roster.csv", "rb") as f:
            st.download_button(
                "Download sample_roster.csv",
                data=f.read(),
                file_name="sample_roster.csv",
                mime="text/csv",
            )

    st.divider()
    st.subheader("📐 Formations")
    if st.button("Reload formations.yaml"):
        st.session_state.formations = load_formations_yaml("assets/formations.yaml")
        st.success("Formations reloaded.")

    if st.checkbox("Edit formations inline (advanced)", value=False):
        text = load_formations_file("assets/formations.yaml")
        edited_text = st.text_area("formations.yaml", value=text, height=300)
        if st.button("Save formations.yaml"):
            save_formations_yaml("assets/formations.yaml", edited_text)
            st.session_state.formations = load_formations_yaml("assets/formations.yaml")
            st.success("Saved formations.yaml")


# ---------- Main Tabs ----------
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "1) Roster & Ratings",
    "2) Starting Lineups",
    "3) Generate Rotation",
    "4) Rotation Board",
    "5) Fairness Dashboard",
    "6) Export",
])


# ---------- Tab 1: Roster & Ratings ----------
with tab1:
    st.subheader("Upload or Edit Roster CSV")
    file = st.file_uploader("Upload roster CSV", type=["csv"])
    if file is not None:
        try:
            df = load_roster_csv(file)
            st.session_state.roster_df = df
            st.success("Roster loaded.")
        except Exception as e:
            st.error(f"Error loading CSV: {e}")

    if st.session_state.roster_df is None:
        st.info("No roster loaded yet. Download the sample or template from the sidebar.")
    else:
        df = st.session_state.roster_df.copy()

        # Inline edit
        st.caption("Edit values below (double-click a cell). Use the “Add row” button to add new players.")
        edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="roster_editor")
        st.session_state.roster_df = edited

        # Validate
        errors = validate_roster(edited)
        if errors:
            st.error("Validation errors:")
            for e in errors:
                st.write("•", e)
        else:
            st.success("Roster looks valid ✅")

        # Save back to CSV
        st.download_button(
            "Download current roster.csv",
            data=save_roster_csv_bytes(st.session_state.roster_df),
            file_name="roster.csv",
            mime="text/csv",
        )


# ---------- Tab 2: Starting Lineups ----------
with tab2:
    st.subheader("Coach-Picked Starting Lineup (Series 1)")

    if st.session_state.roster_df is None:
        st.info("Upload a roster in tab 1 first.")
    else:
        category = st.radio("Category", ["Offense", "Defense"], horizontal=True)
        formation_names = list(st.session_state.formations.get(category, {}).keys())
        if not formation_names:
            st.warning("No formations defined for this category in formations.yaml.")
        else:
            formation_name = st.selectbox("Formation", formation_names, index=0, key=f"start_{category}_formation")
            positions = st.session_state.formations[category][formation_name]

            df = st.session_state.roster_df
            all_players = dict(zip(df["player_id"].astype(str), df["name"]))

            st.caption("Pick your Series 1 starters. Leave any position blank; the solver will smart-fill it.")
            start_map = {}
            for pos in positions:
                # Eligible players for this pos (Category)
                elig_col_prefix = "off" if category == "Offense" else "def"
                elig_cols = [f"{elig_col_prefix}_pos_{i}" for i in range(1, 5)]
                mask = df[elig_cols].apply(lambda r: pos in set(r.values), axis=1)
                eligible_df = df[mask]

                opts = [""] + [f"{pid} | {all_players[str(pid)]}" for pid in eligible_df["player_id"].astype(str)]
                val = st.selectbox(f"{pos}", options=opts, key=f"starter_{category}_{formation_name}_{pos}")
                pid = None
                if val:
                    pid = val.split(" | ")[0]
                start_map[pos] = pid

            # Store starting lineup in session
            st.session_state.starting_lineup.setdefault(category, {})
            st.session_state.starting_lineup[category][formation_name] = start_map

            dupes = detect_duplicate_starters(start_map)
            if dupes:
                st.error(f"Duplicate starter assignments found: {', '.join(dupes)}")

            st.info("Your selections are saved automatically.")


# ---------- Tab 3: Generate Rotation ----------
with tab3:
    st.subheader("Generate Rotation")

    if st.session_state.roster_df is None:
        st.info("Upload a roster in tab 1 first.")
    else:
        category = st.radio("Category", ["Offense", "Defense"], horizontal=True, key="gen_category")
        formation_names = list(st.session_state.formations.get(category, {}).keys())
        if not formation_names:
            st.warning("No formations for this category.")
        else:
            formation_name = st.selectbox("Formation", formation_names, index=0, key="gen_formation")
            positions = st.session_state.formations[category][formation_name]
            df = st.session_state.roster_df.copy()

            # Availability filter
            unavailable = st.multiselect(
                "Mark players unavailable/injured (excluded from this match):",
                options=list(df["name"].values),
                default=[],
            )
            excluded_ids = set(df[df["name"].isin(unavailable)]["player_id"].astype(str).tolist())

            # Show quick math feasibility
            T = len(positions) * st.session_state.app_config.total_series
            P = len(df) - len(excluded_ids)
            impossible_reason = check_impossible_minimums(T, P)
            if impossible_reason:
                st.warning(impossible_reason)

            # Run
            if st.button("Run Solver (ILP with heuristic fallback)"):
                rng = np.random.default_rng(st.session_state.random_seed)

                # starting lineup selection
                starting = st.session_state.starting_lineup.get(category, {}).get(formation_name, {})

                result = schedule_rotation(
                    df=df,
                    category=category,
                    formation_positions=positions,
                    starting_lineup=starting,
                    config=st.session_state.app_config,
                    excluded_ids=excluded_ids,
                    rng=rng,
                )

                if result.error:
                    st.error(result.error)
                else:
                    st.session_state.assignments[category][formation_name] = result.assignment  # list[dict]
                    st.success(f"Generated rotation for {category} / {formation_name} ✅")


# ---------- Tab 4: Rotation Board ----------
with tab4:
    st.subheader("Rotation Board")

    if st.session_state.roster_df is None:
        st.info("Upload a roster in tab 1 first.")
    else:
        category = st.radio("Category", ["Offense", "Defense"], horizontal=True, key="board_category")
        formation_names = list(st.session_state.formations.get(category, {}).keys())
        if not formation_names:
            st.warning("No formations for this category.")
        else:
            formation_name = st.selectbox("Formation", formation_names, index=0, key="board_formation")
            assignment = st.session_state.assignments.get(category, {}).get(formation_name)

            if not assignment:
                st.info("No rotation generated yet. Use tab 3.")
            else:
                df = st.session_state.roster_df.copy()
                grid_df = series_grid_to_df(
                    assignment=assignment,
                    positions=st.session_state.formations[category][formation_name],
                    roster_df=df,
                    category=category,
                )

                st.dataframe(grid_df, use_container_width=True, height=min(600, 50 + 28 * len(grid_df)))

                st.caption("Badges: (R)=newer/learning, (V)=varsity-reduced, (S)=sat last, (⚠)=3rd/4th preference")


# ---------- Tab 5: Fairness Dashboard ----------
with tab5:
    st.subheader("Fairness Dashboard")

    if st.session_state.roster_df is None:
        st.info("Upload a roster in tab 1 first.")
    else:
        category = st.radio("Category", ["Offense", "Defense"], horizontal=True, key="fair_category")
        formation_names = list(st.session_state.formations.get(category, {}).keys())
        if not formation_names:
            st.warning("No formations for this category.")
        else:
            formation_name = st.selectbox("Formation", formation_names, index=0, key="fair_formation")
            assignment = st.session_state.assignments.get(category, {}).get(formation_name)
            if not assignment:
                st.info("No rotation generated yet.")
            else:
                df = st.session_state.roster_df.copy()
                dash = fairness_dashboard_df(assignment, df, st.session_state.app_config)
                st.dataframe(dash, use_container_width=True, height=min(600, 50 + 28 * len(dash)))


# ---------- Tab 6: Export ----------
with tab6:
    st.subheader("Export")

    if st.session_state.roster_df is None:
        st.info("Upload a roster in tab 1 first.")
    else:
        category = st.radio("Category", ["Offense", "Defense"], horizontal=True, key="exp_category")
        formation_names = list(st.session_state.formations.get(category, {}).keys())
        if not formation_names:
            st.warning("No formations for this category.")
        else:
            formation_name = st.selectbox("Formation", formation_names, index=0, key="exp_formation")
            assignment = st.session_state.assignments.get(category, {}).get(formation_name)
            if not assignment:
                st.info("No rotation generated yet.")
            else:
                # CSV export (grid form)
                grid_df = series_grid_to_df(
                    assignment=assignment,
                    positions=st.session_state.formations[category][formation_name],
                    roster_df=st.session_state.roster_df,
                    category=category,
                )
                csv_bytes = grid_df.to_csv(index=True).encode("utf-8")
                fname = f"rotation_{category.lower()}_{formation_name.replace(' ','_')}.csv"
                st.download_button("Download CSV", data=csv_bytes, file_name=fname, mime="text/csv")

                # PDF export (single page per category/formation)
                pdf_bytes = render_pdf(
                    category=category,
                    formation_name=formation_name,
                    positions=st.session_state.formations[category][formation_name],
                    grid_df=grid_df,
                )
                pdf_name = f"rotation_{category.lower()}_{formation_name.replace(' ','_')}.pdf"
                st.download_button("Download PDF", data=pdf_bytes, file_name=pdf_name, mime="application/pdf")

                st.success("Exports ready.")
