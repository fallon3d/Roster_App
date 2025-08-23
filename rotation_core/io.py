# FILE: rotation_core/io.py
import pandas as pd
import json
from io import BytesIO
from reportlab.pdfgen import canvas

def read_roster_csv(path):
    return pd.read_csv(path)

def save_rotations_csv(rotations):
    if not rotations:
        return ""
    df = pd.DataFrame(rotations)
    return df.to_csv(index=False)

def generate_cards(rotations):
    """
    Generate a PDF with one page per rotation, listing position and player.
    """
    buffer = BytesIO()
    c = canvas.Canvas(buffer)
    for i, assignment in enumerate(rotations, start=1):
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, 750, f"Rotation {i}")
        y = 720
        for pos, name in assignment.items():
            c.setFont("Helvetica", 12)
            c.drawString(72, y, f"{pos}: {name}")
            y -= 20
        c.showPage()
    c.save()
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

def save_snapshot(state):
    snapshot = {}
    roster = state.get("roster")
    if isinstance(roster, pd.DataFrame):
        snapshot["roster"] = roster.to_dict(orient="records")
    else:
        snapshot["roster"] = roster
    snapshot["rotations"] = state.get("rotations", [])
    snapshot["exceptions"] = state.get("exceptions", [])
    return json.dumps(snapshot)

def load_sample():
    try:
        df = pd.read_csv("sample_data/roster_sample.csv")
        return df
    except FileNotFoundError:
        return pd.DataFrame()
