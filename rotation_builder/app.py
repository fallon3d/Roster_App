from __future__ import annotations
import os
import json
from typing import List, Dict
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

# Minimal CSS polish (dark, cards, chips)
st.markdown(
    """
<style>
.block-container{padding-top:1rem;}
.card{border:1px solid #2a3142; background:rgba(18,22,31,.78); border-radius:12px; padding:16px; margin-bottom:12px;}
.kv{display:flex; gap:.5rem; flex-wrap:wrap;}
.kv .chip{background:#16202e; border:1px solid #223146; color:#eaf1fb; padding:2px 10px; border-radius:999px; font-size:.8rem;}
.badge{background:#1f2a3a; border:1px solid #324862; color:#cfe1ff; padding:2px 10px; border-radius:999px; font-size:.8rem;}
.hint{font-size:.85rem; color:#B7C2D3;}
fieldset[disabled] .stButton>button{opacity:.6;}
</style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# Session state init
# -----------------------------
def _ensure_state():
    ss = st.session_state
    ss.setdefault("stage", 1)
    ss.setdefault("roster", [])  # List[Player|dict]
    ss.setdefault("settings", Settings().model_dump())
    ss.setdefault("series_list", [])  # List[Series], currently only Series 1
    ss.setdefault("first_locked", False)
    ss.setdefault("gamestate", GameState().model_dump())
    ss.setdefault("name_pool", [])  # list[str]
    ss.setdefault("name_pool_mem_only", True)  # fallback if fs not writable
    ss.setdefault("override_modal", {"open": False, "pos": None})
    ss.setdefault("stats_modal_open", False)
    ss.setdefault("_name_pool_loaded_once", False)

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
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()

# segmented control helper with robust fallback and signature handling
def _seg_control(label: str, options: List, index: int, key: str, format_func=None):
    """Return a segmented control (if available) else a radio with the same semantics.
    Handles both 'index' and 'selection' signatures for segmented_control across versions.
    """
    # Clamp index to valid range
    if not options:
        return None
    if index is None or index < 0 or index >= len(options):
        index = 0

    # Prefer segmented_control if present
    if hasattr(st, "segmented_control"):
        try:
            # Newer signature often supports index + format_func
            return st.segmented_control(
                label=label,
                options=options,
                index=index,
                key=key,
                format_func=format_func or (lambda x: x),
            )
        except TypeError:
            # Fallback to selection signature
            try:
                selection = options[index]
                return st.segmented_control(
                    label=label,
                    options=options,
                    selection=selection,
                    key=key,
                    format_func=format_func or (lambda x: x),
                )
            except Exception:
                pass
        except Exception:
            pass

    # Radio fallback
    if format_func:
        fopts = [format_func(x) for x in options]
    else:
        fopts = options
    choice = st.radio(label, options=fopts, index=index, key=key)
    # Map back if formatted
    if fopts is not options:
        selected_index = fopts.index(choice)
        return options[selected_index]
    return choice

# Name pool persistence
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

if not st.session_state["_name_pool_loaded_once"]:
    _load_name_pool_from_disk()
    st.session_state["_name_pool_loaded_once"] = True

def _load_sample_roster():
    path = os.path.join(os.path.dirname(__file__), "assets", "sample_roster.csv")
    with open(path, "r", encoding="utf-8") as f:
        players = parse_roster_csv(f)
    st.session_state["roster"] = [p.model_copy(update={}) for p in players]

# -----------------------------
# Helpers
# -----------------------------
def _positions_for_ui(settings: Settings) -> List[str]:
    return current_positions(settings)

def _ensure_series1(settings: Settings):
    if not st.session_state["series_list"]:
        positions = {pos: "" for pos in _positions_for_ui(settings)}
        st.session_state["series_list"] = [Series(label="Series 1", positions=positions).model_dump()]
    else:
        s1 = Series(**st.session_state["series_list"][0])
        want = _positions_for_ui(settings)
        new_positions = {pos: s1.positions.get(pos, "") for pos in want}
        st.session_state["series_list"][0] = Series(label="Series 1", positions=new_positions).model_dump()

def _roster_map() -> Dict[str, Player]:
    return by_id([Player(**p) if isinstance(p, dict) else p for p in st.session_state["roster"]])

def _resolve_pid_from_label(lbl: str) -> str:
    return lbl.split(" • ", 1)[0] if " • " in lbl else lbl

def _validate_no_dup_series1(s1: Series) -> bool:
    vals = [pid for pid in s1.positions.values() if pid]
    return len(vals) == len(set(vals))

# Status chips
def _status_bar():
    settings = _settings_obj()
    roster_count = len(st.session_state["roster"])
    locked = st.session_state["first_locked"]
    gs = _gamestate_obj()

    chips = [
        f'<span class="chip">Roster: {roster_count}</span>',
        f'<span class="chip">Segment: {settings.segment}</span>',
    ]
    if settings.segment == "Defense":
        chips.append(f'<span class="chip">Formation: {settings.def_form}</span>')
    chips.append(f'<span class="chip">1st Lineup: {"Locked" if locked else "Drafting"}</span>')
    chips.append(f'<span class="chip">Game: {"Active" if gs.active else "Idle"}</span>')

    st.markdown(f'<div class="kv">{"".join(chips)}</div>', unsafe_allow_html=True)

# -----------------------------
# Sidebar (wizard + quick actions)
# -----------------------------
with st.sidebar:
    st.header("Setup & Progress")
    # Wizard stepper
    options = [1, 2, 3, 4]
    labels = {1: "1) Roster", 2: "2) Segment", 3: "3) Roles", 4: "4) First Lineup"}
    cur_stage = st.session_state["stage"]
    idx = options.index(cur_stage) if cur_stage in options else 0
    stage_choice = _seg_control("Stage", options, idx, "nav_stage", format_func=lambda i: labels[i])
    st.session_state["stage"] = stage_choice

    st.divider()
    _status_bar()

    st.divider()
    st.caption("Quick Links")
    if st.button("Load Sample Roster", key="sb_load_sample"):
        _load_sample_roster()
        st.success("Sample roster loaded.")

    # Downloads
    tpl = build_template_csv()
    st.download_button("Download CSV Template", data=tpl, file_name="roster_template.csv", key="sb_dl_tpl")

# -----------------------------
# Stage 1: Roster & Name Pool
# -----------------------------
def stage1():
    st.title("Youth Football Rotation Builder — Coach UI")
    _status_bar()

    with st.container():
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Stage 1 — Import roster & live edit")

        colA, colB = st.columns([1,1])
        with colA:
            up = st.file_uploader("Upload Roster CSV", type=["csv"], key="uploader_roster")
            if up is not None:
                st.session_state["roster"] = [p.model_dump() for p in parse_roster_csv(up)]
                st.success(f"Loaded {len(st.session_state['roster'])} players.")
        with colB:
            st.markdown('<div class="hint">Tip: You can edit cells directly and add/remove rows.</div>', unsafe_allow_html=True)

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
        st.markdown('</div>', unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="card">', unsafe_allow_html=True)
        with st.expander("Name Pool", expanded=False):
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
                    df_now = roster_to_dataframe([Player(**p) if isinstance(p, dict) else p for p in st.session_state["roster"]])
                    for n in sel_to_add:
                        df_now.loc[len(df_now)] = {
                            "id": "", "Name": n,
                            "Off1":"","Off2":"","Off3":"","Off4":"",
                            "Def1":"","Def2":"","Def3":"","Def4":"",
                            "RoleToday":"Connector","EnergyToday":"Medium"
                        }
                    st.session_state["roster"] = [p.model_dump() for p in dataframe_to_roster(df_now)]
                    st.success(f"Added {len(sel_to_add)} to roster.")
        st.markdown('</div>', unsafe_allow_html=True)

    nav = st.columns([1,6])
    with nav[0]:
        if st.button("Next →", key="stage1_next"):
            st.session_state["stage"] = 2

# -----------------------------
# Stage 2: Segment & Formation
# -----------------------------
def stage2():
    st.title("Youth Football Rotation Builder — Coach UI")
    _status_bar()

    with st.container():
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Stage 2 — Choose segment + defense formation")

        settings = _settings_obj()
        c1, c2 = st.columns([1,1])
        with c1:
            seg = _seg_control("Segment", options=["Offense","Defense"], index=0 if settings.segment=="Offense" else 1, key="seg_radio")
            settings.segment = seg
        with c2:
            if settings.segment == "Defense":
                def_form = _seg_control("Defense Formation", options=["5-3","4-4"], index=0 if settings.def_form=="5-3" else 1, key="def_form_radio")
                settings.def_form = def_form
            else:
                st.markdown('<div class="hint">Defense formation is hidden for Offense.</div>', unsafe_allow_html=True)

        _set_settings(settings)
        _ensure_series1(settings)
        st.markdown('</div>', unsafe_allow_html=True)

    nav = st.columns([1,6])
    with nav[0]:
        if st.button("← Back", key="stage2_back"):
            st.session_state["stage"] = 1
    with nav[1]:
        if st.button("Next →", key="stage2_next"):
            st.session_state["stage"] = 3

# -----------------------------
# Stage 3: Role & Energy
# -----------------------------
def stage3():
    st.title("Youth Football Rotation Builder — Coach UI")
    _status_bar()

    roster = [Player(**p) if isinstance(p, dict) else p for p in st.session_state["roster"]]
    if not roster:
        st.warning("Add some players in Stage 1.")
        return

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Stage 3 — Set Role & Energy")

    with st.form(key="roles_form"):
        for p in roster:
            c1, c2, c3 = st.columns([2,1,1])
            with c1:
                st.write(f"**{p.Name}**")
            with c2:
                role = _seg_control("Role", ROLES, index=ROLES.index(p.RoleToday), key=f"role_{p.id}")
            with c3:
                energy = _seg_control("Energy", ENERGY, index=ENERGY.index(p.EnergyToday), key=f"energy_{p.id}")
            p.RoleToday = role
            p.EnergyToday = energy
            st.markdown("---")

        submitted = st.form_submit_button("Save Roles & Energy")
        if submitted:
            st.session_state["roster"] = [p.model_dump() for p in roster]
            st.success("Saved player roles & energy.")

    st.markdown('</div>', unsafe_allow_html=True)

    nav = st.columns([1,6])
    with nav[0]:
        if st.button("← Back", key="stage3_back"):
            st.session_state["stage"] = 2
    with nav[1]:
        if st.button("Next →", key="stage3_next"):
            st.session_state["stage"] = 4

# -----------------------------
# Stage 4: 1st Lineup Editor + Lock
# -----------------------------
def stage4():
    st.title("Youth Football Rotation Builder — Coach UI")
    _status_bar()

    settings = _settings_obj()
    roster = [Player(**p) if isinstance(p, dict) else p for p in st.session_state["roster"]]
    if not roster:
        st.warning("Add players first.")
        return

    _ensure_series1(settings)
    s1 = Series(**st.session_state["series_list"][0])

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Stage 4 — First Lineup (Series 1)")

    with st.form(key="s1_form"):
        c1, c2 = st.columns([1,3])
        with c1:
            if st.form_submit_button("Auto-Fill Empty", use_container_width=True):
                sugg = suggest_series1(roster, settings)
                for pos, pid in sugg.positions.items():
                    if not s1.positions.get(pos):
                        s1.positions[pos] = pid
                st.session_state["series_list"][0] = s1.model_dump()
                st.success("Filled empty positions.")
                _safe_rerun()
        with c2:
            st.markdown('<div class="hint">Prevent duplicates; locking hides controls and saves Series 1.</div>', unsafe_allow_html=True)

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

        ok = _validate_no_dup_series1(s1)
        if not ok:
            st.error("Duplicate player in Series 1. Fix before locking.")

        lock = st.form_submit_button("Lock 1st Lineup ✓", disabled=not ok)
        if lock:
            sugg = suggest_series1(roster, settings)
            for pos, pid in s1.positions.items():
                if not pid:
                    s1.positions[pos] = sugg.positions.get(pos, "")
            st.session_state["series_list"][0] = s1.model_dump()
            st.session_state["first_locked"] = True
            st.success("1st Lineup Locked.")
            _safe_rerun()

    if st.session_state["first_locked"]:
        st.markdown('<span class="badge">1st Lineup Locked</span>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    nav = st.columns([1,6])
    with nav[0]:
        if st.button("← Back", key="stage4_back"):
            st.session_state["stage"] = 3

# -----------------------------
# Game helpers
# -----------------------------
def _compute_current_and_next(gs: GameState, roster: List[Player], settings: Settings, series_list: List[Series]):
    planned = series_list[gs.idx_cycle % len(series_list)]
    manual = gs.manual_overrides.get(gs.turn, {})
    assigns_cur, counts_cur = compute_effective_lineup(
        gs.idx_cycle, planned, clone_counts_cat(gs.played_counts_cat), dict(gs.pos_idx),
        manual, roster, settings
    )
    # simulate next snapshot
    snap_counts_next = clone_counts_cat(gs.played_counts_cat)
    from rotation_core.engine import inc_cat
    for pos, pid in assigns_cur.items():
        if pid:
            inc_cat(snap_counts_next, pos, pid)
    snap_pos_next = dict(gs.pos_idx)
    cycles = build_pos_cycles(roster, settings)
    for pos, pid in assigns_cur.items():
        cyc = cycles.get(pos, [])
        if cyc and pid in cyc:
            idx = cyc.index(pid)
            snap_pos_next[pos] = (idx + 1) % len(cyc)

    planned_next = series_list[(gs.idx_cycle + 1) % len(series_list)]
    manual_next = gs.manual_overrides.get(gs.turn + 1, {})
    assigns_next, _ = compute_effective_lineup(
        (gs.idx_cycle + 1), planned_next, snap_counts_next, snap_pos_next, manual_next, roster, settings
    )
    return assigns_cur, assigns_next

def _open_override_dialog(roster: List[Player], settings: Settings):
    # Use modern dialog if available for a true modal UX; fallback to inline panel.
    if hasattr(st, "dialog"):
        @st.dialog("Change Player")
        def _dlg():
            _override_panel(roster, settings)
        _dlg()
    else:
        st.markdown("---")
        _override_panel(roster, settings)

def _override_panel(roster: List[Player], settings: Settings):
    gs = _gamestate_obj()
    pos = st.session_state["override_modal"].get("pos")
    if not pos:
        return
    counts_snap = clone_counts_cat(gs.played_counts_cat)
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
            gs.manual_overrides[gs.turn][pos] = pid
            _set_gamestate(gs)
            st.session_state["override_modal"] = {"open": False, "pos": None}
            _safe_rerun()
    with c2:
        if st.button("Cancel", key=f"ov_cancel_{pos}_{gs.turn}"):
            st.session_state["override_modal"] = {"open": False, "pos": None}
            _safe_rerun()

def _render_lineup_table(assigns: Dict[str, str], roster_map: Dict[str, Player], allow_change: bool,
                         counts_snap, roster: List[Player], settings: Settings, turn_key: str):
    for pos in current_positions(settings):
        pid = assigns.get(pos, "")
        name = roster_map[pid].Name if pid and pid in roster_map else "—"
        cols = st.columns([2,5,2,2])
        with cols[0]:
            st.write(pos)
        with cols[1]:
            # fairness tag on already-chosen player (snapshot check)
            if pid and fairness_cap_exceeded(counts_snap, pos, pid, roster, settings):
                st.write(f"{name}  ⚠︎")
            else:
                st.write(name)
        with cols[2]:
            if pid:
                st.caption(roster_map[pid].RoleToday + " / " + roster_map[pid].EnergyToday)
            else:
                st.caption("—")
        with cols[3]:
            if allow_change:
                if st.button("Change", key=f"chg_{settings.segment}_{pos}_{turn_key}"):
                    st.session_state["override_modal"] = {"open": True, "pos": pos}

# -----------------------------
# Game Section
# -----------------------------
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

    gs = _gamestate_obj()

    with st.container():
        st.markdown('<div class="card">', unsafe_allow_html=True)
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

        if len(gs.history) > 0:
            csv_bytes = export_played_rotations_csv(gs.history)
            st.download_button(
                "Download played-rotations.csv",
                data=csv_bytes,
                file_name="played-rotations.csv",
                key="dl_played",
                use_container_width=True
            )
        st.markdown('</div>', unsafe_allow_html=True)

    # Carousel as tabs (mobile friendly)
    roster_map = by_id(roster)
    tabs = st.tabs(["Previous", "Current", "Next"])
    with tabs[0]:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        if len(gs.history) == 0:
            st.write("—")
        else:
            prev = gs.history[-1]["assignments"]
            _render_lineup_table(prev, roster_map, False, gs.played_counts_cat, roster, settings, f"prev_{gs.turn}")
        st.markdown('</div>', unsafe_allow_html=True)

    with tabs[1]:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        if not gs.active:
            st.write("—")
        else:
            cur, nxt = _compute_current_and_next(gs, roster, settings, series_list)
            _render_lineup_table(cur, roster_map, True, gs.played_counts_cat, roster, settings, f"cur_{gs.turn}")
        st.markdown('</div>', unsafe_allow_html=True)

    with tabs[2]:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        if not gs.active:
            st.write("—")
        else:
            cur, nxt = _compute_current_and_next(gs, roster, settings, series_list)
            _render_lineup_table(nxt, roster_map, False, gs.played_counts_cat, roster, settings, f"next_{gs.turn}")
        st.markdown('</div>', unsafe_allow_html=True)

    # Change picker modal/panel
    if st.session_state["override_modal"]["open"]:
        _open_override_dialog(roster, settings)

    # Stats modal/expander
    if st.session_state["stats_modal_open"]:
        st.markdown("---")
        st.markdown("### Stats")
        gs = _gamestate_obj()
        df_counts = pd.DataFrame([
            {"Player": roster_map.get(pid).Name if pid in roster_map else pid, "Appearances": cnt}
            for pid, cnt in gs.played_counts.items()
        ]).sort_values("Appearances", ascending=False)
        st.dataframe(df_counts, use_container_width=True)
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
# Router
# -----------------------------
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
