# FILE: pages/2_Rotation_Builder.py
import streamlit as st
from rotation_core.assignment import solve_rotation
from rotation_core.models import Config

st.title("2. Rotation Builder")
if "roster" not in st.session_state:
    st.warning("Please import a roster on the Roster page first.")
    st.stop()

mode = st.sidebar.selectbox("Mode", ["Offense", "Defense"])
formation = None
if mode == "Defense":
    formation = st.sidebar.radio("Defense Formation", ["5-3", "4-4"])
fairness_priority = st.sidebar.selectbox("Fairness vs Strength", ["Fairness-first", "Balanced", "Win-push"])
num_series = st.sidebar.number_input("Number of Rotations", min_value=1, max_value=10, value=3)

if st.button("Calculate Rotations"):
    roster_df = st.session_state.roster
    config = Config(fairness=fairness_priority, formation=formation, num_rotations=num_series)
    rotations = solve_rotation(roster_df, mode, formation, config)
    st.session_state.rotations = rotations
    st.success("Rotations calculated successfully.")

if "rotations" in st.session_state:
    for i, rotation in enumerate(st.session_state.rotations, start=1):
        st.subheader(f"Rotation {i}")
        # Display as a table
        st.table(rotation)
    if st.button("Explain this lineup"):
        explanation = "All players have been assigned respecting fairness (±1 cap) and maximizing StrengthIndex within those constraints."
        st.info(explanation)
