"""
Entity Relationship Diagram — docs/output/data_model.pdf
All text in pure black (#000000).
CBBR-NATEC Innovation Cup 2026
"""
from __future__ import annotations
from pathlib import Path
from reportlab.lib.pagesizes import A2, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
import math

OUTPUT = Path(__file__).parent.parent / "output"
OUTPUT.mkdir(parents=True, exist_ok=True)

NAVY   = HexColor("#0D1B2A")
BLUE   = HexColor("#1B6CA8")
TEAL   = HexColor("#17A589")
ORANGE = HexColor("#E67E22")
GREEN  = HexColor("#1E8449")
RED    = HexColor("#C0392B")
WHITE  = HexColor("#FFFFFF")
LGREY  = HexColor("#F2F3F4")
MGREY  = HexColor("#BDC3C7")
PURPLE = HexColor("#7D3C98")
GOLD   = HexColor("#F0B429")
STEEL  = HexColor("#5D8AA8")
BLACK  = HexColor("#000000")   # ALL text
LBLUE  = HexColor("#D6EAF8")   # title bar background

W, H   = landscape(A2)
COL_W  = 74*mm
ROW_H  = 5.5*mm
HDR_H  = 8.5*mm

TABLES = {
    "department": (BLUE, [
        ("dept_id",     "VARCHAR(36)",  "PK"),
        ("name",        "VARCHAR(120)", "NN UNIQUE"),
        ("location",    "VARCHAR(200)", ""),
        ("description", "TEXT",         ""),
    ]),
    "requester": (TEAL, [
        ("requester_id",  "VARCHAR(36)",  "PK"),
        ("name",          "VARCHAR(150)", "NN"),
        ("phone_number",  "VARCHAR(20)",  "NN UNIQUE"),
        ("language",      "VARCHAR(10)",  "NN"),
        ("dept_id",       "VARCHAR(36)",  "FK → department"),
        ("is_active",     "BOOLEAN",      "NN"),
    ]),
    "asset": (GREEN, [
        ("asset_id",       "VARCHAR(36)",  "PK"),
        ("name",           "VARCHAR(200)", "NN"),
        ("category",       "VARCHAR(100)", ""),
        ("model_number",   "VARCHAR(100)", ""),
        ("serial_number",  "VARCHAR(100)", "UNIQUE"),
        ("location",       "VARCHAR(200)", ""),
        ("dept_id",        "VARCHAR(36)",  "FK → department"),
        ("required_trade", "VARCHAR(80)",  ""),
        ("is_critical",    "BOOLEAN",      "NN"),
        ("notes",          "TEXT",         ""),
    ]),
    "knowledge_doc": (PURPLE, [
        ("doc_id",        "VARCHAR(36)",  "PK"),
        ("asset_id",      "VARCHAR(36)",  "FK → asset"),
        ("source_type",   "ENUM",         "manual|SOP|history"),
        ("title",         "VARCHAR(300)", "NN"),
        ("raw_content",   "TEXT",         ""),
        ("embedding_ref", "VARCHAR(200)", "ChromaDB ID"),
        ("created_at",    "TIMESTAMPTZ",  "NN"),
    ]),
    "task_request": (ORANGE, [
        ("request_id",          "VARCHAR(36)",  "PK"),
        ("requester_id",        "VARCHAR(36)",  "FK → requester"),
        ("asset_id",            "VARCHAR(36)",  "FK → asset"),
        ("raw_text",            "TEXT",         ""),
        ("photo_url",           "VARCHAR(500)", ""),
        ("audio_transcription", "TEXT",         ""),
        ("structured_fault",    "TEXT",         "JSON"),
        ("whatsapp_message_id", "VARCHAR(200)", "UNIQUE"),
        ("created_at",          "TIMESTAMPTZ",  "NN"),
    ]),
    "work_order": (RED, [
        ("wo_id",             "VARCHAR(36)",  "PK"),
        ("request_id",        "VARCHAR(36)",  "FK → task_request"),
        ("asset_id",          "VARCHAR(36)",  "FK → asset"),
        ("priority",          "ENUM",         "P0|P1|P2"),
        ("status",            "ENUM",         "Open…Completed"),
        ("description",       "TEXT",         ""),
        ("required_trade",    "VARCHAR(80)",  ""),
        ("assigned_techs",    "JSON",         "[]"),
        ("estimated_minutes", "INTEGER",      ""),
        ("sla_due_at",        "TIMESTAMPTZ",  ""),
        ("created_at",        "TIMESTAMPTZ",  "NN"),
        ("closed_at",         "TIMESTAMPTZ",  ""),
    ]),
    "technician": (HexColor("#1A5276"), [
        ("tech_id",             "VARCHAR(36)",  "PK"),
        ("name",                "VARCHAR(150)", "NN"),
        ("trade",               "ENUM",         "Mech|Elec|Civil…"),
        ("pool",                "ENUM",         "LTKTech|DyeTech"),
        ("phone_number",        "VARCHAR(20)",  "NN UNIQUE"),
        ("on_shift",            "BOOLEAN",      "NN"),
        ("is_active",           "BOOLEAN",      "NN"),
        ("reward_score",        "FLOAT",        "default 0"),
        ("max_concurrent_jobs", "INTEGER",      "default 2"),
    ]),
    "assignment": (HexColor("#117A65"), [
        ("assignment_id",   "VARCHAR(36)",  "PK"),
        ("wo_id",           "VARCHAR(36)",  "FK → work_order"),
        ("tech_id",         "VARCHAR(36)",  "FK → technician"),
        ("created_at",      "TIMESTAMPTZ",  "NN"),
        ("acknowledged_at", "TIMESTAMPTZ",  "nullable"),
        ("arrived_at",      "TIMESTAMPTZ",  "nullable"),
        ("paused_at",       "TIMESTAMPTZ",  "nullable"),
        ("completed_at",    "TIMESTAMPTZ",  "nullable"),
        ("completion_notes","TEXT",         ""),
        ("is_preempted",    "BOOLEAN",      "NN"),
    ]),
    "daily_plan": (HexColor("#784212"), [
        ("plan_id",       "VARCHAR(36)", "PK"),
        ("tech_id",       "VARCHAR(36)", "FK → technician"),
        ("plan_date",     "DATE",        "NN"),
        ("items",         "JSON",        "wo_ids[]"),
        ("sent_at",       "TIMESTAMPTZ", "nullable"),
        ("confirmed",     "BOOLEAN",     "NN"),
        ("conflict_note", "VARCHAR(500)","nullable"),
        ("created_at",    "TIMESTAMPTZ", "NN"),
    ]),
    "feedback": (HexColor("#922B21"), [
        ("feedback_id",  "VARCHAR(36)", "PK"),
        ("wo_id",        "VARCHAR(36)", "FK → work_order UNIQUE"),
        ("requester_id", "VARCHAR(36)", "FK → requester"),
        ("rating",       "INTEGER",     "CHECK 1..5"),
        ("comment",      "TEXT",        "nullable"),
        ("created_at",   "TIMESTAMPTZ", "NN"),
    ]),
}

POSITIONS = {
    "department":    (20,  295),
    "requester":     (20,  160),
    "asset":         (112, 245),
    "knowledge_doc": (215, 315),
    "task_request":  (215, 175),
    "work_order":    (335, 220),
    "technician":    (465, 285),
    "assignment":    (465, 120),
    "daily_plan":    (465, 340),
    "feedback":      (335, 55),
}

RELATIONS = [
    ("requester",    "department"),
    ("asset",        "department"),
    ("knowledge_doc","asset"),
    ("task_request", "requester"),
    ("task_request", "asset"),
    ("work_order",   "task_request"),
    ("work_order",   "asset"),
    ("assignment",   "work_order"),
    ("assignment",   "technician"),
    ("daily_plan",   "technician"),
    ("feedback",     "work_order"),
    ("feedback",     "requester"),
]


def table_rect(name):
    x_mm, y_mm = POSITIONS[name]
    _, cols = TABLES[name]
    th = HDR_H + len(cols)*ROW_H + 2*mm
    return x_mm*mm, y_mm*mm, COL_W, th


def centre_of(name):
    x, y, w, h = table_rect(name)
    return x + w/2, y - h/2


def draw_table(c: canvas.Canvas, name: str):
    hdr_color, cols = TABLES[name]
    x_mm, y_mm = POSITIONS[name]
    x, y = x_mm*mm, y_mm*mm
    th = HDR_H + len(cols)*ROW_H + 2*mm

    # Shadow
    c.setFillColor(MGREY)
    c.roundRect(x+1.5*mm, y-th-1.5*mm, COL_W, th, 2*mm, fill=1, stroke=0)

    # Header fill
    c.setFillColor(hdr_color)
    c.setStrokeColor(hdr_color)
    c.roundRect(x, y-HDR_H, COL_W, HDR_H, 2*mm, fill=1, stroke=0)
    c.rect(x, y-HDR_H, COL_W, HDR_H/2, fill=1, stroke=0)

    # Header text — BLACK
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(x+COL_W/2, y-6*mm, name.upper())

    # Rows
    alt = [WHITE, HexColor("#F8F9FA")]
    for i, (col, ctype, flags) in enumerate(cols):
        ry = y - HDR_H - (i+1)*ROW_H
        c.setFillColor(alt[i % 2])
        c.setStrokeColor(MGREY)
        c.setLineWidth(0.3)
        c.rect(x, ry, COL_W, ROW_H, fill=1, stroke=1)

        # Badge
        if "PK" in flags:
            c.setFillColor(GOLD)
            c.roundRect(x+1.5*mm, ry+1.2*mm, 5.5*mm, 3*mm, 0.8*mm, fill=1, stroke=0)
            c.setFillColor(BLACK)
            c.setFont("Helvetica-Bold", 5)
            c.drawString(x+2.3*mm, ry+2*mm, "PK")
        elif "FK" in flags:
            c.setFillColor(STEEL)
            c.roundRect(x+1.5*mm, ry+1.2*mm, 5.5*mm, 3*mm, 0.8*mm, fill=1, stroke=0)
            c.setFillColor(BLACK)
            c.setFont("Helvetica-Bold", 5)
            c.drawString(x+2.3*mm, ry+2*mm, "FK")

        # Col name — BLACK
        c.setFillColor(BLACK)
        c.setFont("Helvetica-Bold" if "PK" in flags else "Helvetica", 6.5)
        c.drawString(x+8.5*mm, ry+1.8*mm, col)

        # Type — BLACK
        c.setFont("Helvetica", 5.5)
        c.drawRightString(x+COL_W-1.5*mm, ry+1.8*mm, ctype)

    # Outer border
    c.setStrokeColor(hdr_color)
    c.setLineWidth(1.3)
    bottom = y - HDR_H - len(cols)*ROW_H - 2*mm
    c.roundRect(x, bottom, COL_W, th, 2*mm, fill=0, stroke=1)


def draw_relation(c: canvas.Canvas, ft: str, tt: str):
    fx, fy = centre_of(ft)
    tx, ty = centre_of(tt)
    c.saveState()
    c.setStrokeColor(MGREY)
    c.setLineWidth(1)
    c.setDash(5, 3)
    c.line(fx, fy, tx, ty)
    c.setDash()
    c.setFillColor(MGREY)
    c.circle(fx, fy, 2.5, fill=1, stroke=0)
    dx, dy = tx-fx, ty-fy
    ln = math.sqrt(dx*dx+dy*dy) or 1
    ux, uy = dx/ln, dy/ln
    sx, sy = -uy*3.5, ux*3.5
    p = c.beginPath()
    p.moveTo(tx, ty)
    p.lineTo(tx-ux*8+sx, ty-uy*8+sy)
    p.lineTo(tx-ux*8-sx, ty-uy*8-sy)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    c.restoreState()


def generate():
    path = OUTPUT / "data_model.pdf"
    c = canvas.Canvas(str(path), pagesize=landscape(A2))
    c.setTitle("RT Knits CMMS — Data Model ERD")

    c.setFillColor(LGREY)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # Title bar — light background, black text
    c.setFillColor(LBLUE)
    c.setStrokeColor(BLUE)
    c.setLineWidth(1.5)
    c.rect(0, H-20*mm, W, 20*mm, fill=1, stroke=0)
    c.line(0, H-20*mm, W, H-20*mm)
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(15*mm, H-13*mm, "RT Knits Agentic CMMS — Entity Relationship Diagram")
    c.setFont("Helvetica", 9)
    c.drawRightString(W-15*mm, H-13*mm, "CBBR-NATEC Innovation Cup 2026  ·  PostgreSQL · 10 Tables · pgvector")

    # Relations behind tables
    for ft, tt in RELATIONS:
        draw_relation(c, ft, tt)

    # Tables
    for name in TABLES:
        draw_table(c, name)

    # Legend — all BLACK text
    lx, ly = 15*mm, 10*mm
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(lx, ly+6*mm, "Legend:")

    c.setFillColor(GOLD)
    c.roundRect(lx+20*mm, ly+3.5*mm, 7*mm, 4*mm, 1*mm, fill=1, stroke=0)
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 5.5)
    c.drawCentredString(lx+23.5*mm, ly+5*mm, "PK")
    c.setFont("Helvetica", 7)
    c.drawString(lx+29*mm, ly+5*mm, "Primary Key")

    c.setFillColor(STEEL)
    c.roundRect(lx+62*mm, ly+3.5*mm, 7*mm, 4*mm, 1*mm, fill=1, stroke=0)
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 5.5)
    c.drawCentredString(lx+65.5*mm, ly+5*mm, "FK")
    c.setFont("Helvetica", 7)
    c.drawString(lx+71*mm, ly+5*mm, "Foreign Key")

    # Relation line sample
    rx = lx+115*mm
    c.setStrokeColor(MGREY)
    c.setLineWidth(1)
    c.setDash(5, 3)
    c.line(rx, ly+5*mm, rx+18*mm, ly+5*mm)
    c.setDash()
    c.setFillColor(MGREY)
    c.circle(rx, ly+5*mm, 2.5, fill=1, stroke=0)
    c.setFillColor(BLACK)
    c.setFont("Helvetica", 7)
    c.drawString(rx+20*mm, ly+4*mm, "FK → PK relationship")

    c.save()
    print(f"  ✓  data_model.pdf  →  {path}")
    return path


if __name__ == "__main__":
    generate()
