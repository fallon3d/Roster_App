# FILE: app.py
import streamlit as st
from rotation_core.io import load_sample, save_snapshot
from rotation_core.models import Config

st.set_page_config(page_title="Rotation Generator", layout="wide")

# Coach PIN gate
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if not st.session_state.authenticated:
    pin = st.text_input("Enter Coach PIN", type="password")
    if pin == "2468":
        st.session_state.authenticated = True
    else:
        st.warning("Incorrect PIN. Please enter the coach PIN to proceed.")
        st.stop()

st.title("Coach-Only Football Rotation Generator")
st.write("Welcome! Use the sidebar to configure rotations and import the roster.")

# Global Sidebar Settings
st.sidebar.title("Global Settings")
mode = st.sidebar.selectbox("Mode", ["Offense", "Defense"])
formation = None
if mode == "Defense":
    formation = st.sidebar.radio("Defense Formation", ["5-3", "4-4"])
fairness_priority = st.sidebar.selectbox("Fairness Priority", ["Fairness-first", "Balanced", "Win-push"])
rotation_length = st.sidebar.selectbox("Rotation Segment", ["Quarter", "Half", "Custom"])
if rotation_length == "Custom":
    minutes = st.sidebar.number_input("Minutes per Segment", min_value=1, max_value=20, value=5)
max_consecutive = st.sidebar.number_input("Max Consecutive Series (0=off)", min_value=0, max_value=5, value=0)

# Roster Controls
if st.sidebar.button("Load Sample Roster"):
    sample_df = load_sample()
    if not sample_df.empty:
        st.session_state.roster = sample_df
        st.success("Sample roster loaded.")
if st.sidebar.button("Reset Roster"):
    st.session_state.pop("roster", None)
    st.info("Roster has been reset.")

# Show current roster
if "roster" in st.session_state:
    st.subheader("Current Roster")
    st.dataframe(st.session_state.roster)

st.info("Use the pages above to import data, build rotations, and export results.")
