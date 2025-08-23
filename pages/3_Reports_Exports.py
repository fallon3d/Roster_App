# FILE: pages/3_Reports_Exports.py
import streamlit as st
from rotation_core.io import save_snapshot, generate_cards
import pandas as pd

st.title("3. Reports & Exports")
if "rotations" not in st.session_state:
    st.warning("No rotations generated yet. Please build rotations first.")
    st.stop()

rotations = st.session_state.rotations

# Download CSV of rotations
csv_str = "\n".join(str(r) for r in rotations)
st.download_button("Download Rotations CSV", data=csv_str, file_name="rotations.csv")

# Download state as JSON
json_str = save_snapshot(st.session_state)
st.download_button("Download State JSON", data=json_str, file_name="rotation_state.json")

# Download printable cards PDF
pdf_bytes = generate_cards(rotations)
st.download_button("Download Printable Cards (PDF)", data=pdf_bytes, file_name="rotations.pdf", mime="application/pdf")

st.subheader("Exception Log")
exceptions = st.session_state.get("exceptions", [])
if exceptions:
    for exc in exceptions:
        st.error(exc)
else:
    st.write("No exceptions recorded.")
