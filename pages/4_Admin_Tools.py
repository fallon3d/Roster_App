# FILE: pages/4_Admin_Tools.py
import streamlit as st
from rotation_core.validation import run_self_test

st.title("4. Admin & Self-Test")

if st.button("Run Self-Test"):
    results = run_self_test()
    st.write(results)

st.write("Use this page for diagnostics and configurations.")
