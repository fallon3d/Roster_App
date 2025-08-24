# rotation_core/export_pdf.py
from __future__ import annotations
from typing import List
import io
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

def render_pdf(category: str, formation_name: str, positions: List[str], grid_df) -> bytes:
    buf = io.BytesIO()
    page_size = landscape(letter)
    c = canvas.Canvas(buf, pagesize=page_size)

    title = f"{category} — {formation_name} Rotation"
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, page_size[1] - 40, title)

    cols = ["Position"] + list(grid_df.columns)
    data = [cols]
    for pos in grid_df.index:
        row = [pos] + list(grid_df.loc[pos, :].values)
        data.append(row)

    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("TEXTCOLOR", (0,0), (-1,0), colors.black),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 10),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("ALIGN", (0,0), (-1,-1), "LEFT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))

    table_w, table_h = t.wrapOn(c, page_size[0] - 80, page_size[1] - 100)
    x = 40
    y = page_size[1] - 80 - table_h
    t.drawOn(c, x, y)

    c.showPage()
    c.save()
    return buf.getvalue()
