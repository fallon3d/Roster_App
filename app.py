# app.py
import io
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
import streamlit as st

from rotation_core.config import (
    DEFAULT_CONFIG,
    ROLE_SCORE,
    ENERGY_SCORE,
    load_formations_file,
    ensure_assets_exist,
    ui_css,                 # 2025 theme (style tag)
    aliases_for_position,   # alias-aware eligibility (DT1/DT2->DT, OLB1/OLB2->OLB, CB_L/R->CB, etc.)
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
    ss.setdefault("assignments", {"Offense": {}, "Defense": {}})  # planned (solver) rotations
    ss.setdefault("selected_category", "Defense")
    ss.setdefault("selected_formation", "DEFENSE_53")
    ss.setdefault("excluded_ids", set())
    ss.setdefault("random_seed", 42)

    # ---- In-game engine (HTML-like) ----
    ss.setdefault("game_active", False)
    ss.setdefault("game_turn", 1)              # 1-indexed
    ss.setdefault("game_idx_cycle", 0)         # which planned series index
    ss.setdefault("game_history", [])          # list of dict(turn, series_idx, lineup)
    ss.setdefault("game_manual_overrides", {}) # {series_idx: {pos: player_id}}
    ss.setdefault("game_played_counts", {})    # {player_id: appearances}
    ss.setdefault("game_played_counts_cat", {})# {category: {player_id: appearances}}
    ss.setdefault("game_fairness_debt_cat", {})# {category: {player_id: debt}}
    ss.setdefault("game_pos_cycles", {})       # {pos: [player_ids eligible sorted]}
    ss.setdefault("game_pos_idx", {})          # {pos: next index pointing in cycle}
    ss.setdefault("game_last_summary_df", None)

_init_state()

# ---------- Category map (mirrors the HTML) ----------
OFFENSE_CATEGORY = {
    "QB": "QB",
    "AB": "Backfield", "HB": "Backfield",
    "WR": "Wide", "Slot": "Wide",
    "TE": "TE",
    "RT": "Interior Line", "RG": "Interior Line", "C": "Interior Line", "LG": "Interior Line", "LT": "Interior Line",
}
DEFENSE_CATEGORY = {
    # 5–3 canonical
    "LDE": "DE", "RDE": "DE",
    "DT1": "DLine", "NT": "DLine", "DT2": "DLine",
    "OLB1": "Linebacker", "MLB": "Linebacker", "OLB2": "Linebacker",
    "LCB": "Secondary", "S": "Secondary", "RCB": "Secondary",
    # Alt aliases (DEFENSE_53_ALT)
    "DE_L": "DE", "DE_R": "DE",
    "LB_SAM": "Linebacker", "LB_MIKE": "Linebacker", "LB_WILL": "Linebacker",
    "CB_L": "Secondary", "FS": "Secondary", "CB_R": "Secondary",
}

def position_category(category: str, pos: str) -> str:
    if category == "Offense":
        return OFFENSE_CATEGORY.get(pos, "GEN")
    return DEFENSE_CATEGORY.get(pos, "GEN")


# ---------- Sidebar (advanced controls; logic unchanged) ----------
with st.sidebar:
    st.header("⚙️ Advanced Config")
    total_series = st.number_input(
        "Total series",
        min_value=1, max_value=40,
        value=st.session_state.app_config.total_series,
        step=1,
    )
    evenness_cap_enabled = st.checkbox(
        "Evenness Cap (±)",
        value=st.session_state.app_config.evenness_cap_enabled,
        help="Keeps appearances within ±N where N is the cap value."
    )
    evenness_cap_value = st.number_input(
        "Cap value",
        min_value=0, max_value=4,
        value=st.session_state.app_config.evenness_cap_value,
        step=1,
    )

    # preference weights from CSV auto-length (we keep two by default)
    pref_count = 2
    if st.session_state.roster_df is not None:
        off_cols = detect_pref_cols(st.session_state.roster_df, "Offense")
        def_cols = detect_pref_cols(st.session_state.roster_df, "Defense")
        pref_count = max(len(off_cols), len(def_cols)) or 2
    default_pw = ",".join(["1.0", "0.6", "0.3", "0.1"][:pref_count])
    pref_weights_str = st.text_input(
        "Preference weights",
        value=default_pw,
        help="Comma separated; first is strongest preference."
    )

    objective_mu = st.number_input(
        "μ (mismatch penalty)",
        min_value=0.0, max_value=10.0,
        value=st.session_state.app_config.objective_mu,
        step=0.1,
        help="Penalty for using lower prefs when better fits exist."
    )
    rand = st.number_input(
        "Random seed",
        min_value=0, max_value=10_000,
        value=st.session_state.random_seed, step=1
    )

    def _parse_weights(s: str) -> List[float]:
        try:
            parts = [float(x.strip()) for x in s.split(",") if x.strip() != ""]
            if not parts:
                raise ValueError
            return parts
        except Exception:
            st.warning("Invalid weights; falling back to [1.0, 0.6].")
            return [1.0, 0.6]

    # apply to session
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
        st.download_button(
            "template.csv",
            data=generate_template_csv_bytes(),
            file_name="template.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with colS:
        with open("assets/sample_roster.csv", "rb") as f:
            st.download_button(
                "sample_roster.csv",
                data=f.read(),
                file_name="sample_roster.csv",
                mime="text/csv",
                use_container_width=True,
            )

    st.divider()
    st.subheader("📐 Formations")
    if st.button("Reload formations.yaml", use_container_width=True):
        st.session_state.formations = load_formations_yaml("assets/formations.yaml")
        st.success("Formations reloaded.")


# ---------- Header card ----------
st.markdown(
    """
<div class="app">
  <div class="card section">
    <h2>Youth Football Rotation Builder</h2>
    <div class="small">
      Order: 1) Import & edit roster → 2) Choose segment → 3) Set Role & Energy → <b>1st Lineup</b>.
      In-game use <b>Change</b> on Current/Next. +2 category fairness shows <span class="tag warn" style="margin:0 4px">⚠ Fairness</span> but is allowed.
    </div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# ---------- Helpers to render staged UI ----------
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

def _strength_index(role: str, energy: str) -> int:
    r = ROLE_SCORE.get(str(role), 2)
    e = ENERGY_SCORE.get(str(energy), 1)
    return r * 10 + e  # 10..32


# ============================================================
# STAGE 1 — Import roster (CSV) & live editor
# ============================================================
if st.session_state.stage == 1:
    _card_start()
    _chip_row()
    st.markdown("<h3>1) Import roster (CSV) & live edit</h3>", unsafe_allow_html=True)

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
        st.download_button(
            "Download template.csv",
            data=generate_template_csv_bytes(),
            file_name="template.csv",
            mime="text/csv",
        )

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
                default_idx = 0
                if st.session_state.selected_category == "Defense" and "DEFENSE_53" in formation_names:
                    default_idx = formation_names.index("DEFENSE_53")
                st.session_state.selected_formation = st.selectbox("Formation", formation_names, index=default_idx)

        # mark unavailable players (optional)
        df = st.session_state.roster_df
        unavailable = st.multiselect(
            "Exclude players (injury/unavailable):",
            options=list(df["name"].values),
            default=[],
        )
        st.session_state.excluded_ids = set(df[df["name"].isin(unavailable)]["player_id"].astype(str).tolist())

        # feasibility notice
        positions = st.session_state.formations.get(st.session_state.selected_category, {}).get(st.session_state.selected_formation, [])
        T = len(positions) * st.session_state.app_config.total_series
        P = len(df) - len(st.session_state.excluded_ids)
        msg = check_impossible_minimums(T, P)
        if msg:
            st.warning(msg)

        _stage_nav(back_to=1, next_to=3, next_label="Next: Set Role & Energy")
        _card_end()

# ============================================================
# STAGE 3 — Ratings (Role & Energy)
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
# STAGE 4 — First Lineup (Series 1) + Generate & Game Mode
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

        # id->name map
        all_players = dict(zip(df["player_id"].astype(str), df["name"]))

        st.caption("Pick your Series 1 starters. Leave blank and we’ll smart fill.")
        start_map = st.session_state.starting_lineup.get(category, {}).get(formation_name, {}) or {}

        # grid of selects (3 columns)
        cols = st.columns(3)
        for i, pos in enumerate(positions):
            if i % 3 == 0 and i > 0:
                cols = st.columns(3)
            with cols[i % 3]:
                mask = _eligible_mask(df, category, pos)
                eligible_df = df[mask & ~df["player_id"].astype(str).isin(st.session_state.excluded_ids)]
                opts = [""] + [f"{pid} | {all_players[str(pid)]}" for pid in eligible_df["player_id"].astype(str)]
                cur = start_map.get(pos, "")
                label = f"{pos}"
                val = st.selectbox(
                    label,
                    options=opts,
                    index=opts.index(cur) if cur in opts else 0,
                    key=f"starter_{category}_{formation_name}_{pos}"
                )
                pid = val.split(" | ")[0] if val else ""
                start_map[pos] = pid if pid else None

        # persist + check duplicates
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
            st.caption("After generating, scroll to Game to run live like your HTML demo.")

        _card_end()

        # ---------- Rotation Board (planned) ----------
        assignment = st.session_state.assignments.get(category, {}).get(formation_name)
        if assignment:
            _card_start()
            st.markdown("<h3>Rotation Board (Planned)</h3>", unsafe_allow_html=True)
            grid_df = series_grid_to_df(
                assignment=assignment,
                positions=positions,
                roster_df=df,
                category=category,
            )
            st.dataframe(grid_df, use_container_width=True, height=min(600, 50 + 28 * len(grid_df)))
            st.caption("Planned grid from solver. Live game can override per-series picks.")
            _card_end()

        # =====================================================
        # GAME MODE — behave like your HTML (Current/Next/Prev)
        # =====================================================
        if assignment:
            def _eligible_for_pos_ids(pos: str) -> List[str]:
                al = aliases_for_position(pos)
                elig_cols = detect_pref_cols(df, category)
                mask = df[elig_cols].apply(lambda r: any(str(v).strip() in al for v in r.values), axis=1)
                mask &= ~df["player_id"].astype(str).isin(st.session_state.excluded_ids)
                return df[mask]["player_id"].astype(str).tolist()

            def _strength_for(pid: str) -> int:
                r = df.loc[df["player_id"].astype(str) == pid, "role_today"].values
                e = df.loc[df["player_id"].astype(str) == pid, "energy_today"].values
                role = r[0] if len(r) else "steady/reliable"
                energy = e[0] if len(e) else "Medium"
                return _strength_index(role, energy)

            def _pref_rank(pid: str, pos: str) -> Optional[int]:
                al = aliases_for_position(pos)
                cols = detect_pref_cols(df, category)
                row = df.loc[df["player_id"].astype(str) == pid, cols]
                if row.empty:
                    return None
                vals = [str(row.iloc[0, j]).strip() for j in range(len(cols))]
                for idx, v in enumerate(vals, start=1):
                    if v in al:
                        return idx
                return None

            def _planned_lineup(series_idx: int) -> Dict[str, Optional[str]]:
                # assignment keys are 1..N; series_idx is 0..N-1
                k = series_idx + 1
                return assignment.get(k, {}).copy()

            def _build_cycles():
                pos_cycles, pos_idx = {}, {}
                for pos in positions:
                    ids = _eligible_for_pos_ids(pos)
                    # sort: (has pref), pref rank asc, strength desc, name asc
                    def _key(pid):
                        pr = _pref_rank(pid, pos)
                        return (
                            0 if pr else 1,
                            pr if pr else 99,
                            -_strength_for(pid),
                            df.loc[df["player_id"].astype(str) == pid, "name"].values[0],
                        )
                    ids.sort(key=_key)
                    pos_cycles[pos] = ids
                    pos_idx[pos] = 0
                st.session_state.game_pos_cycles = pos_cycles
                st.session_state.game_pos_idx = pos_idx

            def _inc_cat(counts_cat: Dict[str, Dict[str, int]], pos: str, pid: str):
                cat = position_category(category, pos)
                if cat not in counts_cat:
                    counts_cat[cat] = {}
                counts_cat[cat][pid] = counts_cat[cat].get(pid, 0) + 1

            def _min_cat(counts_cat: Dict[str, Dict[str, int]], cat: str, eligible_ids: List[str]) -> int:
                if not eligible_ids:
                    return 0
                base = counts_cat.get(cat, {})
                vals = [base.get(i, 0) for i in eligible_ids]
                return min(vals) if vals else 0

            def _fairness_cap_exceeded(counts_cat: Dict[str, Dict[str, int]], pos: str, pid: str) -> bool:
                cat = position_category(category, pos)
                eligible_ids = _eligible_for_pos_ids(pos)  # per-position category fairness set
                debt = st.session_state.game_fairness_debt_cat.get(cat, {})
                current = counts_cat.get(cat, {}).get(pid, 0) + debt.get(pid, 0)
                m = _min_cat(counts_cat, cat, eligible_ids)
                return (current + 1) > (m + 1)  # allow +1 window

            def _compute_effective(series_idx: int,
                                   counts_cat_snap: Dict[str, Dict[str, int]],
                                   pos_idx_snap: Dict[str, int],
                                   manual: Optional[Dict[str, str]] = None) -> Dict[str, Optional[str]]:
                planned = _planned_lineup(series_idx)
                manual = manual or {}
                assign: Dict[str, Optional[str]] = {}
                in_series: Set[str] = set()
                working_cat = {c: v.copy() for c, v in counts_cat_snap.items()}

                # Pass 0: manual
                for pos in positions:
                    pid = manual.get(pos)
                    if not pid:
                        continue
                    if pid in in_series:
                        continue
                    if pid not in _eligible_for_pos_ids(pos):
                        continue
                    assign[pos] = pid
                    in_series.add(pid)
                    _inc_cat(working_cat, pos, pid)

                # Pass 1: planned, bias away if fairness category would exceed
                for pos in positions:
                    if pos in assign:
                        continue
                    pid = planned.get(pos)
                    if not pid:
                        continue
                    if pid in in_series:
                        continue
                    if _fairness_cap_exceeded(working_cat, pos, pid):
                        continue
                    assign[pos] = pid
                    in_series.add(pid)
                    _inc_cat(working_cat, pos, pid)

                # Pass 2: fill blanks via cycles with fairness first
                for pos in positions:
                    if pos in assign:
                        continue
                    cycle = st.session_state.game_pos_cycles.get(pos, [])
                    if not cycle:
                        assign[pos] = None
                        continue
                    idx = pos_idx_snap.get(pos, 0)
                    chosen = None

                    # try respecting fairness within category
                    for t in range(len(cycle)):
                        pid = cycle[(idx + t) % len(cycle)]
                        if pid in in_series:
                            continue
                        if not _fairness_cap_exceeded(working_cat, pos, pid):
                            chosen = pid
                            idx = (idx + t) % len(cycle)
                            break
                    # if none, pick next eligible ignoring fairness
                    if chosen is None:
                        for t in range(len(cycle)):
                            pid = cycle[(idx + t) % len(cycle)]
                            if pid not in in_series:
                                chosen = pid
                                idx = (idx + t) % len(cycle)
                                break

                    assign[pos] = chosen
                    if chosen:
                        in_series.add(chosen)
                        _inc_cat(working_cat, pos, chosen)
                return assign

            def _start_game():
                st.session_state.game_active = True
                st.session_state.game_turn = 1
                st.session_state.game_idx_cycle = 0
                st.session_state.game_history = []
                st.session_state.game_manual_overrides = {}
                st.session_state.game_played_counts = {}
                st.session_state.game_played_counts_cat = {}
                st.session_state.game_fairness_debt_cat = {}
                _build_cycles()

            def _end_series():
                if not st.session_state.game_active:
                    return
                n = len(assignment)
                planned_idx = st.session_state.game_idx_cycle % n
                manual = st.session_state.game_manual_overrides.get(planned_idx, {})
                eff = _compute_effective(
                    planned_idx,
                    st.session_state.game_played_counts_cat,
                    st.session_state.game_pos_idx,
                    manual,
                )

                # commit counts + advance cycles
                for pos, pid in eff.items():
                    if not pid:
                        continue
                    st.session_state.game_played_counts[pid] = st.session_state.game_played_counts.get(pid, 0) + 1
                    _inc_cat(st.session_state.game_played_counts_cat, pos, pid)
                    # advance cycle index to next after used pid
                    lst = st.session_state.game_pos_cycles.get(pos, [])
                    if pid in lst and lst:
                        cur = lst.index(pid)
                        st.session_state.game_pos_idx[pos] = (cur + 1) % len(lst)

                st.session_state.game_history.append(
                    {"turn": st.session_state.game_turn, "series_idx": planned_idx, "lineup": eff}
                )
                st.session_state.game_idx_cycle = (st.session_state.game_idx_cycle + 1) % n
                st.session_state.game_turn += 1

                # recompute fairness debt per category: any over (m+1) becomes positive debt
                new_debt = {}
                for pos in positions:
                    cat = position_category(category, pos)
                    elig_ids = _eligible_for_pos_ids(pos)
                    if not elig_ids:
                        continue
                    m = _min_cat(st.session_state.game_played_counts_cat, cat, elig_ids)
                    for pid in elig_ids:
                        cur = st.session_state.game_played_counts_cat.get(cat, {}).get(pid, 0)
                        over = cur - (m + 1)
                        if over > 0:
                            new_debt.setdefault(cat, {})[pid] = over
                st.session_state.game_fairness_debt_cat = new_debt

            def _end_game():
                st.session_state.game_active = False

                # Build summary df
                rows = []
                for p in df.itertuples(index=False):
                    pid = str(p.player_id)
                    rows.append({
                        "player": p.name,
                        "appearances": st.session_state.game_played_counts.get(pid, 0),
                    })
                out = pd.DataFrame(rows).sort_values(["appearances", "player"], ascending=[False, True])
                st.session_state.game_last_summary_df = out

            # ---------- GAME UI ----------
            _card_start()
            st.markdown("<h3>Game</h3>", unsafe_allow_html=True)
            c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 1])
            with c1:
                if st.button("Start Game", type="primary", use_container_width=True, disabled=st.session_state.game_active):
                    _start_game()
                    st.rerun()
            with c2:
                if st.button("End Series", use_container_width=True, disabled=not st.session_state.game_active):
                    _end_series()
                    st.rerun()
            with c3:
                if st.button("End Game", use_container_width=True, disabled=not st.session_state.game_active and len(st.session_state.game_history) == 0):
                    _end_game()
                    st.rerun()
            with c4:
                review_disabled = st.session_state.game_active or len(st.session_state.game_history) == 0
                if st.button("Review Last", use_container_width=True, disabled=review_disabled):
                    st.session_state.game_active = False
            with c5:
                rt_disabled = not st.session_state.game_active
                rt_clicked = st.button("Real-time Stats", use_container_width=True, disabled=rt_disabled)

            badge = "Idle"
            if st.session_state.game_active:
                badge = f"Playing — Series {st.session_state.game_turn}"
            elif st.session_state.starting_lineup.get(category, {}).get(formation_name):
                badge = "Ready"
            st.markdown(f'<div class="badge">{badge}</div>', unsafe_allow_html=True)

            # Render carousel (Prev / Current / Next)
            if st.session_state.game_active and len(assignment):
                n = len(assignment)
                planned_idx = st.session_state.game_idx_cycle % n

                # build CURRENT effective (using current counts)
                cur_manual = st.session_state.game_manual_overrides.get(planned_idx, {})
                cur_eff = _compute_effective(planned_idx, st.session_state.game_played_counts_cat, st.session_state.game_pos_idx, cur_manual)

                # simulate NEXT counts
                sim_cat = {c: v.copy() for c, v in st.session_state.game_played_counts_cat.items()}
                for pos, pid in cur_eff.items():
                    if pid:
                        _inc_cat(sim_cat, pos, pid)

                next_idx = (planned_idx + 1) % n
                next_manual = st.session_state.game_manual_overrides.get(next_idx, {})
                next_eff = _compute_effective(next_idx, sim_cat, st.session_state.game_pos_idx, next_manual)

                # PREVIOUS
                if st.session_state.game_history:
                    last = st.session_state.game_history[-1]
                    with st.expander(f"Previous — Series {last['turn']}", expanded=False):
                        tbl = []
                        for pos in positions:
                            nm = df.loc[df["player_id"].astype(str) == (last["lineup"].get(pos) or ""), "name"]
                            tbl.append([pos, nm.values[0] if len(nm) else ""])
                        st.table(pd.DataFrame(tbl, columns=["Position", "Player"]))

                # CURRENT card with Change controls
                with st.expander(f"Current — Series {st.session_state.game_turn}", expanded=True):
                    cur_tbl = []
                    for pos in positions:
                        eff_pid = cur_eff.get(pos)
                        eff_name = df.loc[df["player_id"].astype(str) == (eff_pid or ""), "name"]
                        eff_label = eff_name.values[0] if len(eff_name) else ""
                        # candidates (not already used in this effective series)
                        taken = set(v for k, v in cur_eff.items() if k != pos and v)
                        candidates = [pid for pid in _eligible_for_pos_ids(pos) if pid not in taken]
                        # Build select options with fairness badge
                        opts = ["(auto)"]
                        labels = ["(auto – follow plan/fairness)"]
                        for pid in candidates:
                            # fair warn?
                            base_cat = {c: v.copy() for c, v in st.session_state.game_played_counts_cat.items()}
                            # add all other decided picks into base
                            for p2, pid2 in cur_eff.items():
                                if p2 != pos and pid2:
                                    _inc_cat(base_cat, p2, pid2)
                            cat = position_category(category, pos)
                            eligible_ids = _eligible_for_pos_ids(pos)
                            m = _min_cat(base_cat, cat, eligible_ids)
                            cur = base_cat.get(cat, {}).get(pid, 0)
                            warn = (cur + 1) > (m + 1)
                            nm = df.loc[df["player_id"].astype(str) == pid, "name"].values[0]
                            pr = _pref_rank(pid, pos)
                            tag = " ⚠ Fairness" if warn else " OK"
                            labels.append(f"{nm}  (pref {pr if pr else '-'}){tag}")
                            opts.append(pid)

                        sel = st.selectbox(
                            f"{pos}",
                            options=opts,
                            format_func=lambda x: labels[opts.index(x)],
                            key=f"cur_change_{pos}",
                        )
                        # write manual override for CURRENT planned_idx
                        mo = st.session_state.game_manual_overrides.get(planned_idx, {}).copy()
                        if sel == "(auto)":
                            if pos in mo:
                                mo.pop(pos, None)
                        else:
                            mo[pos] = sel
                        st.session_state.game_manual_overrides[planned_idx] = mo
                        cur_tbl.append([pos, eff_label])
                    st.caption("Pick a player to override; (auto) follows plan + fairness.")

                # NEXT card with Change controls
                with st.expander(f"Next — Series {st.session_state.game_turn + 1}", expanded=False):
                    next_tbl = []
                    for pos in positions:
                        eff_pid = next_eff.get(pos)
                        eff_name = df.loc[df["player_id"].astype(str) == (eff_pid or ""), "name"]
                        eff_label = eff_name.values[0] if len(eff_name) else ""
                        taken = set(v for k, v in next_eff.items() if k != pos and v)
                        candidates = [pid for pid in _eligible_for_pos_ids(pos) if pid not in taken]
                        opts = ["(auto)"]
                        labels = ["(auto – follow plan/fairness)"]
                        for pid in candidates:
                            base_cat = {c: v.copy() for c, v in sim_cat.items()}
                            for p2, pid2 in next_eff.items():
                                if p2 != pos and pid2:
                                    _inc_cat(base_cat, p2, pid2)
                            cat = position_category(category, pos)
                            eligible_ids = _eligible_for_pos_ids(pos)
                            m = _min_cat(base_cat, cat, eligible_ids)
                            cur = base_cat.get(cat, {}).get(pid, 0)
                            warn = (cur + 1) > (m + 1)
                            nm = df.loc[df["player_id"].astype(str) == pid, "name"].values[0]
                            pr = _pref_rank(pid, pos)
                            tag = " ⚠ Fairness" if warn else " OK"
                            labels.append(f"{nm}  (pref {pr if pr else '-'}){tag}")
                            opts.append(pid)

                        sel = st.selectbox(
                            f"{pos} ",
                            options=opts,
                            format_func=lambda x: labels[opts.index(x)],
                            key=f"next_change_{pos}",
                        )
                        mo2 = st.session_state.game_manual_overrides.get(next_idx, {}).copy()
                        if sel == "(auto)":
                            if pos in mo2:
                                mo2.pop(pos, None)
                        else:
                            mo2[pos] = sel
                        st.session_state.game_manual_overrides[next_idx] = mo2
                        next_tbl.append([pos, eff_label])

            # Real-time stats modal substitute
            if st.session_state.game_active and rt_clicked:
                st.info("Real-time Stats")
                rows = []
                for p in df.itertuples(index=False):
                    pid = str(p.player_id)
                    rows.append({"player": p.name, "appearances so far": st.session_state.game_played_counts.get(pid, 0)})
                live = pd.DataFrame(rows).sort_values(["appearances so far", "player"], ascending=[False, True])
                st.dataframe(live, use_container_width=True)

            # Game summary after ending
            if not st.session_state.game_active and st.session_state.game_last_summary_df is not None:
                st.markdown("---")
                st.subheader("Game Summary")
                st.dataframe(st.session_state.game_last_summary_df, use_container_width=True)
                # Export played rotations CSV
                csv_rows = []
                for item in st.session_state.game_history:
                    csv_rows.append([f"Series {item['turn']}"])
                    csv_rows.append(["Position", "Player"])
                    for pos in positions:
                        pid = item["lineup"].get(pos)
                        nm = df.loc[df["player_id"].astype(str) == (pid or ""), "name"]
                        csv_rows.append([pos, (nm.values[0] if len(nm) else "")])
                    csv_rows.append([])
                csv_bytes = pd.DataFrame(csv_rows).to_csv(index=False, header=False).encode("utf-8")
                st.download_button(
                    "Download Played Rotations (CSV)",
                    data=csv_bytes,
                    file_name="played-rotations.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            _card_end()

        # ---------- Exports (planned) ----------
        if assignment:
            _card_start()
            st.markdown("<h3>Export (Planned Rotation)</h3>", unsafe_allow_html=True)
            grid_df = series_grid_to_df(
                assignment=assignment,
                positions=positions,
                roster_df=df,
                category=category,
            )
            csv_bytes = grid_df.to_csv(index=True).encode("utf-8")
            fname = f"rotation_{category.lower()}_{formation_name.replace(' ','_')}.csv"
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "Download CSV",
                    data=csv_bytes,
                    file_name=fname,
                    mime="text/csv",
                    use_container_width=True,
                )
            with col2:
                pdf_bytes = render_pdf(
                    category=category,
                    formation_name=formation_name,
                    positions=positions,
                    grid_df=grid_df,
                )
                pdf_name = f"rotation_{category.lower()}_{formation_name.replace(' ','_')}.pdf"
                st.download_button(
                    "Download PDF",
                    data=pdf_bytes,
                    file_name=pdf_name,
                    mime="application/pdf",
                    use_container_width=True,
                )
            _card_end()

        # nav
        _card_start()
        _stage_nav(back_to=3, next_to=None)
        _card_end()
