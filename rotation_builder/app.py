from __future__ import annotations
import os
import json
from typing import List, Dict, Optional
from copy import deepcopy

import streamlit as st
import pandas as pd

from rotation_core.models import Player, Settings, Series, GameState
from rotation_core.constants import (
    OFF_POS, DEF_53_POS, DEF_44_POS, CATEGORY_POSITIONS,
    FAIRNESS_CATEGORIES, ROLES, ENERGY, normalize_pos, normalize_name
)
from rotation_core.csv_io import parse_roster_csv, build_template_csv, roster_to_dataframe, dataframe_to_roster
from rotation_core.engine import (
    suggest_series1, current_positions, build_pos_cycles,
    compute_effective_lineup, eligible_for_pos, fairness_cap_exceeded, clone_counts_cat
)
from rotation_core.game import start_game, end_series, end_game, export_played_rotations_csv
from rotation_core.ui_helpers import by_id, display_name

# -----------------------------
# Page config
# -----------------------------
st.set_page_config(layout="wide", page_title="Youth Football Rotation Builder")

# -----------------------------
# Session state init
# -----------------------------
def _ensure_state():
    ss = st.session_state
    ss.setdefault("stage", 1)
    ss.setdefault("roster", [])  # List[Player]
    ss.setdefault("settings", Settings().model_dump())
    ss.setdefault("series_list", [])  # List[Series], currently only Series 1
    ss.setdefault("first_locked", False)
    ss.setdefault("gamestate", GameState().model_dump())
    ss.setdefault("name_pool", [])  # list of names
    ss.setdefault("name_pool_mem_only", True)  # fallback if fs not writable
    ss.setdefault("override_modal", {"open": False, "pos": None})
    ss.setdefault("stats_modal_open", False)

_ensure_state()

def _settings_obj() -> Settings:
    return Settings(**st.session_state["settings"])

def _gamestate_obj() -> GameState:
    return GameState(**st.session_state["gamestate"])

def _set_gamestate(gs: GameState):
    st.session_state["gamestate"] = gs.model_dump()

def _set_settings(s: Settings):
    st.session_state["settings"] = s.model_dump()

# --- compatibility rerun helper (Streamlit >=1.31 uses st.rerun) ---
def _safe_rerun():
    """Rerun compatible with both new and older Streamlit versions."""
    if hasattr(st, "rerun"):
        st.rerun()
    else:  # fallback for older releases
        st.experimental_rerun()

def _load_sample_roster():
    path = os.path.join(os.path.dirname(__file__), "assets", "sample_roster.csv")
    with open(path, "r", encoding="utf-8") as f:
        players = parse_roster_csv(f)
    st.session_state["roster"] = [p.model_copy(update={}) for p in players]

def _save_name_pool_to_disk():
    try:
        data_dir = os.path.join(os.path.dirname(__file__), ".data")
        os.makedirs(data_dir, exist_ok=True)
        path = os.path.join(data_dir, "name_pool.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(st.session_state["name_pool"], f, ensure_ascii=False, indent=2)
        st.session_state["name_pool_mem_only"] = False
    except Exception:
        st.session_state["name_pool_mem_only"] = True

def _load_name_pool_from_disk():
    try:
        data_dir = os.path.join(os.path.dirname(__file__), ".data")
        path = os.path.join(data_dir, "name_pool.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                st.session_state["name_pool"] = json.load(f)
            st.session_state["name_pool_mem_only"] = False
    except Exception:
        st.session_state["name_pool_mem_only"] = True

# call once
if st.session_state.get("_name_pool_loaded_once") is None:
    _load_name_pool_from_disk()
    st.session_state["_name_pool_loaded_once"] = True

# -----------------------------
# Helper views / small funcs
# -----------------------------
def _stage_nav():
    col1, col2, col3, col4, col5 = st.columns([1,1,1,1,2])
    with col1:
        if st.button("Stage 1: Roster", key="btn_stage1"):
            st.session_state["stage"] = 1
    with col2:
        if st.button("Stage 2: Segment", key="btn_stage2"):
            st.session_state["stage"] = 2
    with col3:
        if st.button("Stage 3: Roles", key="btn_stage3"):
            st.session_state["stage"] = 3
    with col4:
        if st.button("Stage 4: 1st Lineup", key="btn_stage4"):
            st.session_state["stage"] = 4
    with col5:
        st.markdown("### &nbsp;&nbsp;**Game** Section below")

def _positions_for_ui(settings: Settings) -> List[str]:
    return current_positions(settings)

def _ensure_series1(settings: Settings):
    if not st.session_state["series_list"]:
        # empty series with positions
        positions = {pos: "" for pos in _positions_for_ui(settings)}
        st.session_state["series_list"] = [Series(label="Series 1", positions=positions).model_dump()]
    else:
        # ensure positions reflect current settings; preserve chosen ids where possible
        s1 = Series(**st.session_state["series_list"][0])
        want = _positions_for_ui(settings)
        new_positions = {}
        for pos in want:
            new_positions[pos] = s1.positions.get(pos, "")
        st.session_state["series_list"][0] = Series(label="Series 1", positions=new_positions).model_dump()

def _roster_map() -> Dict[str, Player]:
    return by_id([Player(**p) if isinstance(p, dict) else p for p in st.session_state["roster"]])

def _eligible_labels_for_pos(pos: str, settings: Settings) -> List[str]:
    roster = [Player(**p) if isinstance(p, dict) else p for p in st.session_state["roster"]]
    labels = []
    for p in eligible_for_pos(roster, pos, settings):
        labels.append(f"{p.id} • {p.Name} ({p.RoleToday}/{p.EnergyToday})")
    return labels

def _resolve_pid_from_label(lbl: str) -> str:
    return lbl.split(" • ", 1)[0] if " • " in lbl else lbl

def _has_dupes(values: List[str]) -> bool:
    vals = [v for v in values if v]
    return len(vals) != len(set(vals))

def _render_fairness_tag(pid: str, pos: str, counts_snap, roster: List[Player], settings: Settings):
    if fairness_cap_exceeded(counts_snap, pos, pid, roster, settings):
        st.markdown("⚠︎ Fairness")

# -----------------------------
# Stage 1: Roster & Name Pool
# -----------------------------
def stage1():
    st.subheader("Stage 1 — Import roster & live edit")

    c1, c2, c3, c4 = st.columns([1,1,1,2])
    with c1:
        if st.button("Load Sample", key="load_sample"):
            _load_sample_roster()
    with c2:
        template = build_template_csv()
        st.download_button("Download CSV Template", data=template, file_name="roster_template.csv", key="dl_tpl")
    with c3:
        up = st.file_uploader("Upload Roster CSV", type=["csv"], key="uploader_roster")
        if up is not None:
            st.session_state["roster"] = [p.model_dump() for p in parse_roster_csv(up)]
            st.success(f"Loaded {len(st.session_state['roster'])} players.")
    with c4:
        st.info("Tip: You can edit cells directly and add/remove rows.")

    # Live editor (data_editor with dynamic rows)
    df = roster_to_dataframe([Player(**p) if isinstance(p, dict) else p for p in st.session_state["roster"]])
    edited = st.data_editor(
        df,
        num_rows="dynamic",
        key="roster_editor",
        use_container_width=True,
        column_config={
            "id": st.column_config.TextColumn("id", help="Stable identifier", disabled=True),
            "Name": st.column_config.TextColumn("Name", required=True),
            "Off1": st.column_config.TextColumn("Off1"),
            "Off2": st.column_config.TextColumn("Off2"),
            "Off3": st.column_config.TextColumn("Off3"),
            "Off4": st.column_config.TextColumn("Off4"),
            "Def1": st.column_config.TextColumn("Def1"),
            "Def2": st.column_config.TextColumn("Def2"),
            "Def3": st.column_config.TextColumn("Def3"),
            "Def4": st.column_config.TextColumn("Def4"),
            "RoleToday": st.column_config.SelectboxColumn("RoleToday", options=ROLES, required=True),
            "EnergyToday": st.column_config.SelectboxColumn("EnergyToday", options=ENERGY, required=True),
        }
    )
    st.session_state["roster"] = [p.model_dump() for p in dataframe_to_roster(edited)]

    with st.expander("Name Pool"):
        c1, c2, c3 = st.columns([1,1,2])
        with c1:
            new_name = st.text_input("Add Name", key="np_add_name")
            if st.button("Add to Pool", key="np_add_btn") and new_name.strip():
                st.session_state["name_pool"].append(normalize_name(new_name))
                _save_name_pool_to_disk()
        with c2:
            if st.button("Export Pool CSV", key="np_export"):
                csv_bytes = ("Name\n" + "\n".join(st.session_state["name_pool"])).encode("utf-8")
                st.download_button("Download Names CSV", data=csv_bytes, file_name="name_pool.csv", key="np_dl", use_container_width=True)
        with c3:
            upnp = st.file_uploader("Import Names CSV", type=["csv"], key="np_uploader")
            if upnp is not None:
                try:
                    df_np = pd.read_csv(upnp)
                    for n in df_np.get("Name", []):
                        n = normalize_name(str(n))
                        if n and n not in st.session_state["name_pool"]:
                            st.session_state["name_pool"].append(n)
                    _save_name_pool_to_disk()
                    st.success("Imported names.")
                except Exception as e:
                    st.error(f"Import error: {e}")

        if st.session_state["name_pool"]:
            st.write("Names in Pool:")
            sel_to_add = st.multiselect("Select names to add to current roster", st.session_state["name_pool"], key="np_select")
            if st.button("Add Selected To Roster", key="np_add_selected"):
                # append blank rows with only Name
                df_now = roster_to_dataframe([Player(**p) if isinstance(p, dict) else p for p in st.session_state["roster"]])
                for n in sel_to_add:
                    df_now.loc[len(df_now)] = {"id": "", "Name": n, "Off1":"","Off2":"","Off3":"","Off4":"","Def1":"","Def2":"","Def3":"","Def4":"","RoleToday":"Connector","EnergyToday":"Medium"}
                st.session_state["roster"] = [p.model_dump() for p in dataframe_to_roster(df_now)]
                st.success(f"Added {len(sel_to_add)} to roster.")

    # Navigation
    cprev, cnext = st.columns([1,6])
    with cprev:
        if st.button("Next →", key="stage1_next"):
            st.session_state["stage"] = 2

# -----------------------------
# Stage 2: Segment & Formation
# -----------------------------
def stage2():
    st.subheader("Stage 2 — Choose segment + defense formation")

    settings = _settings_obj()
    c1, c2 = st.columns([1,1])
    with c1:
        seg = st.radio("Segment", options=["Offense","Defense"], index=0 if settings.segment=="Offense" else 1, key="seg_radio")
        settings.segment = seg
    with c2:
        if settings.segment == "Defense":
            def_form = st.radio("Defense Formation", options=["5-3","4-4"], index=0 if settings.def_form=="5-3" else 1, key="def_form_radio")
            settings.def_form = def_form
        else:
            st.info("Defense formation is hidden for Offense.")

    _set_settings(settings)
    _ensure_series1(settings)

    cprev, cnext = st.columns([1,6])
    with cprev:
        if st.button("← Back", key="stage2_back"):
            st.session_state["stage"] = 1
    with cnext:
        if st.button("Next →", key="stage2_next"):
            st.session_state["stage"] = 3

# -----------------------------
# Stage 3: Role & Energy
# -----------------------------
def stage3():
    st.subheader("Stage 3 — Set Role & Energy (two-tap equivalents)")
    roster = [Player(**p) if isinstance(p, dict) else p for p in st.session_state["roster"]]
    if not roster:
        st.warning("Add some players in Stage 1.")
        return

    # Render per-player controls with deterministic keys
    for idx, p in enumerate(roster):
        c1, c2, c3 = st.columns([2,1,1])
        with c1:
            st.write(f"**{p.Name}**")
        with c2:
            role = st.radio("Role", ROLES, index=ROLES.index(p.RoleToday), key=f"role_{p.id}")
        with c3:
            energy = st.radio("Energy", ENERGY, index=ENERGY.index(p.EnergyToday), key=f"energy_{p.id}")

        # update
        p.RoleToday = role
        p.EnergyToday = energy

    st.session_state["roster"] = [p.model_dump() for p in roster]

    cprev, cnext = st.columns([1,6])
    with cprev:
        if st.button("← Back", key="stage3_back"):
            st.session_state["stage"] = 2
    with cnext:
        if st.button("Next →", key="stage3_next"):
            st.session_state["stage"] = 4

# -----------------------------
# Stage 4: 1st Lineup Editor + Lock
# -----------------------------
def _validate_no_dup_series1(s1: Series) -> bool:
    vals = [pid for pid in s1.positions.values() if pid]
    return len(vals) == len(set(vals))

def stage4():
    st.subheader("Stage 4 — First Lineup (Series 1)")

    settings = _settings_obj()
    roster = [Player(**p) if isinstance(p, dict) else p for p in st.session_state["roster"]]
    if not roster:
        st.warning("Add players first.")
        return

    _ensure_series1(settings)
    s1 = Series(**st.session_state["series_list"][0])

    # Suggest button (fills empty only)
    c1, c2 = st.columns([1,3])
    with c1:
        if st.button("Auto-Fill Empty", key="s1_autofill"):
            sugg = suggest_series1(roster, settings)
            for pos, pid in sugg.positions.items():
                if not s1.positions.get(pos):
                    s1.positions[pos] = pid
            st.session_state["series_list"][0] = s1.model_dump()
    with c2:
        st.info("Prevent duplicates within series; lock hides controls and saves Series 1.")

    # Editor per position
    pos_list = current_positions(settings)
    pid_to_player = by_id(roster)
    for pos in pos_list:
        elig = eligible_for_pos(roster, pos, settings)
        options = [""] + [f"{p.id} • {p.Name} ({p.RoleToday}/{p.EnergyToday})" for p in elig]
        current_pid = s1.positions.get(pos, "")
        current_label = ""
        if current_pid and current_pid in pid_to_player:
            pp = pid_to_player[current_pid]
            current_label = f"{pp.id} • {pp.Name} ({pp.RoleToday}/{pp.EnergyToday})"

        sel = st.selectbox(
            f"{pos}",
            options=options,
            index=options.index(current_label) if current_label in options else 0,
            key=f"s1_{pos}",
        )
        new_pid = _resolve_pid_from_label(sel) if sel else ""
        s1.positions[pos] = new_pid

    # Validate no duplicates
    ok = _validate_no_dup_series1(s1)
    if not ok:
        st.error("Duplicate player in Series 1. Fix before locking.")

    # Lock
    cprev, cnext = st.columns([1,6])
    with cprev:
        if st.button("← Back", key="stage4_back"):
            st.session_state["stage"] = 3
    with cnext:
        if st.button("Lock 1st Lineup", key="lock_s1", disabled=not ok):
            # auto-fill any remaining gaps if possible via suggestion
            sugg = suggest_series1(roster, settings)
            for pos, pid in s1.positions.items():
                if not pid:
                    s1.positions[pos] = sugg.positions.get(pos, "")
            st.session_state["series_list"][0] = s1.model_dump()
            st.session_state["first_locked"] = True
            st.success("1st Lineup Locked ✓")

    # Show badge if locked
    if st.session_state["first_locked"]:
        st.markdown("#### ✅ 1st Lineup Locked")

# -----------------------------
# Game Section
# -----------------------------
def _render_lineup_card(title: str, assigns: Dict[str, str], roster_map: Dict[str, Player], show_change: bool, counts_snap, roster: List[Player], settings: Settings):
    st.markdown(f"**{title}**")
    for pos in current_positions(settings):
        pid = assigns.get(pos, "")
        label = roster_map[pid].Name if pid and pid in roster_map else "—"
        cols = st.columns([2,4,2])
        with cols[0]:
            st.write(pos)
        with cols[1]:
            st.write(label)
        with cols[2]:
            if show_change:
                if st.button("Change", key=f"chg_{settings.segment}_{pos}_{_gamestate_obj().turn}"):
                    st.session_state["override_modal"] = {"open": True, "pos": pos}

def _compute_current_and_next(gs: GameState, roster: List[Player], settings: Settings, series_list: List[Series]):
    # snapshots
    planned = series_list[gs.idx_cycle % len(series_list)]
    manual = gs.manual_overrides.get(gs.turn, {})
    assigns_cur, counts_cur = compute_effective_lineup(
        gs.idx_cycle, planned, clone_counts_cat(gs.played_counts_cat), dict(gs.pos_idx),
        manual, roster, settings
    )
    # hypothetical next: advance snapshots by applying current assigns
    snap_counts_next = clone_counts_cat(gs.played_counts_cat)
    for pos, pid in assigns_cur.items():
        if pid:
            from rotation_core.engine import inc_cat
            inc_cat(snap_counts_next, pos, pid)
    # pos pointers hypothetical: advance to used pid +1
    snap_pos_next = dict(gs.pos_idx)
    cycles = build_pos_cycles(roster, settings)
    for pos, pid in assigns_cur.items():
        cyc = cycles.get(pos, [])
        if cyc and pid in cyc:
            idx = cyc.index(pid)
            snap_pos_next[pos] = (idx + 1) % len(cyc)

    # planned for next
    planned_next = series_list[(gs.idx_cycle + 1) % len(series_list)]
    manual_next = gs.manual_overrides.get(gs.turn + 1, {})
    assigns_next, counts_next = compute_effective_lineup(
        (gs.idx_cycle + 1), planned_next, snap_counts_next, snap_pos_next, manual_next, roster, settings
    )
    return assigns_cur, assigns_next

def _override_modal(roster: List[Player], settings: Settings):
    gs = _gamestate_obj()
    pos = st.session_state["override_modal"].get("pos")
    if not pos:
        return
    roster_map = by_id(roster)
    counts_snap = clone_counts_cat(gs.played_counts_cat)

    st.write(f"### Change: {pos}")
    elig = eligible_for_pos(roster, pos, settings)
    options = []
    for p in elig:
        warn = " ⚠︎" if fairness_cap_exceeded(counts_snap, pos, p.id, roster, settings) else ""
        options.append(f"{p.id} • {p.Name}{warn}")

    sel = st.selectbox("Eligible Players", options=[""] + options, key=f"ov_sel_{pos}_{gs.turn}")
    c1, c2 = st.columns([1,1])
    with c1:
        if st.button("Apply Override", key=f"ov_apply_{pos}_{gs.turn}") and sel:
            pid = _resolve_pid_from_label(sel.split(" ⚠︎")[0])
            gs.manual_overrides.setdefault(gs.turn, {})
            # ensure no duplicate in the planned effective lineup — engine protects, we just record desired override
            gs.manual_overrides[gs.turn][pos] = pid
            _set_gamestate(gs)
            st.session_state["override_modal"] = {"open": False, "pos": None}
            _safe_rerun()
    with c2:
        if st.button("Cancel", key=f"ov_cancel_{pos}_{gs.turn}"):
            st.session_state["override_modal"] = {"open": False, "pos": None}
            _safe_rerun()

def game_section():
    st.markdown("---")
    st.subheader("Game")

    roster = [Player(**p) if isinstance(p, dict) else p for p in st.session_state["roster"]]
    if not roster:
        st.info("Load a roster first.")
        return
    settings = _settings_obj()
    if not st.session_state["first_locked"]:
        st.info("Lock the 1st lineup in Stage 4 to enable Game.")
        return
    series_list = [Series(**s) if isinstance(s, dict) else s for s in st.session_state["series_list"]]
    s1 = series_list[0]

    gs = _gamestate_obj()

    c1, c2, c3, c4, c5 = st.columns([1,1,1,1,2])
    with c1:
        if st.button("Start Game", key="btn_start", disabled=gs.active):
            start_game(gs, roster, settings, series_list)
            _set_gamestate(gs)
            st.success("Game started")
    with c2:
        if st.button("End Series", key="btn_end_series", disabled=not gs.active):
            end_series(gs, roster, settings, series_list)
            _set_gamestate(gs)
            st.success("Series ended")
    with c3:
        if st.button("End Game", key="btn_end_game", disabled=not gs.active):
            summary = end_game(gs)
            _set_gamestate(gs)
            st.success(f"Game ended. Series played: {summary.get('turns',0)}")
    with c4:
        if st.button("Review Last Game", key="btn_review", disabled=gs.active or len(gs.history)==0):
            st.session_state["stats_modal_open"] = True
    with c5:
        if st.button("Real-time Stats", key="btn_stats", disabled=not (gs.active or len(gs.history)>0)):
            st.session_state["stats_modal_open"] = True

    # Export played rotations CSV
    if len(gs.history) > 0:
        csv_bytes = export_played_rotations_csv(gs.history)
        st.download_button("Download played-rotations.csv", data=csv_bytes, file_name="played-rotations.csv", key="dl_played")

    # Carousel: Previous | Current | Next
    roster_map = by_id(roster)
    cprev, ccur, cnext = st.columns([1,1,1])
    with cprev:
        st.markdown("### Previous")
        if len(gs.history) == 0:
            st.write("—")
        else:
            prev = gs.history[-1]["assignments"]
            _render_lineup_card("Prev", prev, roster_map, False, gs.played_counts_cat, roster, settings)
    with ccur:
        st.markdown("### Current")
        if not gs.active:
            st.write("—")
        else:
            cur, nxt = _compute_current_and_next(gs, roster, settings, series_list)
            _render_lineup_card("Current", cur, roster_map, True, gs.played_counts_cat, roster, settings)
    with cnext:
        st.markdown("### Next")
        if not gs.active:
            st.write("—")
        else:
            cur, nxt = _compute_current_and_next(gs, roster, settings, series_list)
            _render_lineup_card("Next", nxt, roster_map, False, gs.played_counts_cat, roster, settings)

    # Change picker "modal"
    if st.session_state["override_modal"]["open"]:
        st.markdown("---")
        _override_modal(roster, settings)

    # Stats modal/expander
    if st.session_state["stats_modal_open"]:
        st.markdown("---")
        st.markdown("### Stats")
        gs = _gamestate_obj()
        # simple summary of counts + fairness debt
        # Show totals per player
        df_counts = pd.DataFrame([
            {"Player": roster_map.get(pid).Name if pid in roster_map else pid, "Appearances": cnt}
            for pid, cnt in gs.played_counts.items()
        ]).sort_values("Appearances", ascending=False)
        st.dataframe(df_counts, use_container_width=True)

        # Fairness by category
        for cat, mp in gs.played_counts_cat.items():
            st.markdown(f"**{cat}**")
            dfc = pd.DataFrame([
                {"Player": roster_map.get(pid).Name if pid in roster_map else pid, "Count": cnt}
                for pid, cnt in mp.items()
            ]).sort_values("Count", ascending=False)
            st.dataframe(dfc, use_container_width=True)
        if st.button("Close Stats", key="btn_close_stats"):
            st.session_state["stats_modal_open"] = False

# -----------------------------
# Layout render
# -----------------------------
st.title("Youth Football Rotation Builder — Coach UI (Streamlit)")

# Stage navigation header
def _stage_navbar():
    cols = st.columns(4)
    labels = ["1) Roster", "2) Segment", "3) Roles", "4) First Lineup"]
    for i, c in enumerate(cols, start=1):
        with c:
            if st.button(labels[i-1], key=f"stage_nav_{i}"):
                st.session_state["stage"] = i

_stage_navbar()

stage = st.session_state["stage"]
if stage == 1:
    stage1()
elif stage == 2:
    stage2()
elif stage == 3:
    stage3()
else:
    stage4()

game_section()
