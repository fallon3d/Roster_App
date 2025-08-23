# FILE: pages/1_Roster.py
import streamlit as st
import pandas as pd
from rotation_core.aliases import map_headers

st.title("1. Roster: Import & Manage")
st.write("Upload a CSV file with your roster or load the sample roster from the sidebar.")

uploaded_file = st.file_uploader("Upload roster CSV", type=["csv"])
if uploaded_file:
    df = pd.read_csv(uploaded_file)
    mapped_df, mapping = map_headers(df)
    mapping_report = ", ".join(f"{col}→{new}" for col, new in mapping.items() if new)
    st.success(f"Header mapping: {mapping_report}")
    st.session_state.roster = mapped_df
    st.dataframe(mapped_df)
else:
    if "roster" in st.session_state:
        st.dataframe(st.session_state.roster)
    else:
        st.write("No roster loaded.")

if st.button("Add New Player"):
    st.info("Add Player feature is not implemented in this stub.")
if st.button("Delete Selected Player"):
    st.info("Delete Player feature is not implemented in this stub.")
