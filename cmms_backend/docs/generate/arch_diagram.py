"""
Architecture Diagram — docs/output/architecture.pdf
All text rendered in pure black (#000000) for maximum visibility.
CBBR-NATEC Innovation Cup 2026
"""
from __future__ import annotations
from pathlib import Path
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, black

OUTPUT = Path(__file__).parent.parent / "output"
OUTPUT.mkdir(parents=True, exist_ok=True)

# ── Palette ───────────────────────────────────────────────────────────────────
NAVY   = HexColor("#0D1B2A")
BLUE   = HexColor("#1B6CA8")
TEAL   = HexColor("#17A589")
ORANGE = HexColor("#E67E22")
RED    = HexColor("#C0392B")
GREEN  = HexColor("#1E8449")
PURPLE = HexColor("#7D3C98")
WHITE  = HexColor("#FFFFFF")
LGREY  = HexColor("#F2F3F4")
MGREY  = HexColor("#BDC3C7")
BLACK  = HexColor("#000000")   # ALL text uses this

W, H = landscape(A3)
PAD  = 12 * mm


def rr(c, x, y, w, h, r=4*mm, fill=WHITE, stroke=BLUE, lw=1.2):
    c.saveState()
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(lw)
    c.roundRect(x, y, w, h, r, fill=1, stroke=1)
    c.restoreState()


def txt(c, x, y, text, size=9, bold=False, align="centre"):
    c.saveState()
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    if align == "centre":
        c.drawCentredString(x, y, text)
    elif align == "left":
        c.drawString(x, y, text)
    elif align == "right":
        c.drawRightString(x, y, text)
    c.restoreState()


def arrow(c, x1, y1, x2, y2):
    import math
    c.saveState()
    c.setStrokeColor(MGREY)
    c.setLineWidth(1.5)
    c.setDash(4, 3)
    c.line(x1, y1, x2, y2)
    c.setDash()
    c.setFillColor(MGREY)
    dx, dy = x2-x1, y2-y1
    ln = math.sqrt(dx*dx+dy*dy) or 1
    ux, uy = dx/ln, dy/ln
    sx, sy = -uy*4, ux*4
    p = c.beginPath()
    p.moveTo(x2, y2)
    p.lineTo(x2-ux*8+sx, y2-uy*8+sy)
    p.lineTo(x2-ux*8-sx, y2-uy*8-sy)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    c.restoreState()


LAYERS = [
    ("LAYER 1 — ENTRY POINT", "WhatsApp Cloud API / Meta",
     HexColor("#D6EAF8"), BLUE, [
         ("WhatsApp\nCloud API", "Meta Graph v19"),
         ("Requester\n(Worker)", "+230 phone"),
         ("Technician\n(Worker)", "+230 phone"),
     ]),
    ("LAYER 2 — API GATEWAY", "FastAPI + Uvicorn",
     HexColor("#D5F5E3"), GREEN, [
         ("POST /webhook",        "HMAC verified"),
         ("GET /webhook",         "Hub verify"),
         ("/api/v1/work-orders",  "CRUD"),
         ("/api/v1/technicians",  "CRUD + shifts"),
         ("/api/v1/analytics",    "KPI reports"),
         ("/api/v1/planning",     "Trigger + plans"),
         ("/api/v1/knowledge",    "Search + ingest"),
     ]),
    ("LAYER 3 — ORCHESTRATOR", "LangGraph StateGraph",
     HexColor("#FDEBD0"), ORANGE, [
         ("Rating Gate\nNode",  "Block / pass"),
         ("Intake Node",        "Extract fault"),
         ("Knowledge Node",     "Inject SOPs"),
         ("Triage Node",        "P0 / P1 / P2"),
         ("Dispatch Node",      "Assign tech"),
         ("Reply Node",         "Send WA msg"),
     ]),
    ("LAYER 4 — AGENTS", "7 Specialised Agents (GPT-4o)",
     HexColor("#F9EBEA"), RED, [
         ("Intake Agent",     "Whisper + Vision"),
         ("Triage Agent",     "Rules + LLM"),
         ("Dispatch Agent",   "SQL + assign"),
         ("Planning Agent",   "Bin-packing"),
         ("Knowledge Agent",  "ChromaDB"),
         ("Analytics Agent",  "KPI / perf"),
     ]),
    ("LAYER 5 — DATA STORES", "PostgreSQL · ChromaDB · OpenAI APIs",
     HexColor("#E8DAEF"), PURPLE, [
         ("PostgreSQL\n(pgvector)", "10 tables"),
         ("ChromaDB",              "Embeddings"),
         ("OpenAI GPT-4o",         "LLM + Vision"),
         ("OpenAI Whisper",        "Audio → text"),
         ("APScheduler",           "Nightly + P0"),
     ]),
]


def generate():
    path = OUTPUT / "architecture.pdf"
    c = canvas.Canvas(str(path), pagesize=landscape(A3))
    c.setTitle("RT Knits CMMS — System Architecture")

    # Background
    c.setFillColor(LGREY)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # Title bar
    c.setFillColor(NAVY)
    c.rect(0, H-22*mm, W, 22*mm, fill=1, stroke=0)
    # Title text in WHITE on dark background for readability
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(PAD, H-14*mm, "RT Knits Agentic CMMS — System Architecture")
    c.setFont("Helvetica", 9)
    c.drawRightString(W-PAD, H-14*mm, "CBBR-NATEC Innovation Cup 2026")

    top     = H - 26*mm
    layer_h = 30*mm
    gap     = 5*mm
    y       = top

    for i, (lbl, sub, bg, accent, boxes) in enumerate(LAYERS):
        # Band
        rr(c, PAD, y-layer_h, W-2*PAD, layer_h, r=3*mm, fill=bg, stroke=accent, lw=1.8)

        # Layer label — BLACK text
        txt(c, PAD+3*mm, y-7*mm,  lbl, size=8, bold=True, align="left")
        txt(c, PAD+3*mm, y-12*mm, sub, size=7, align="left")

        # Boxes
        n      = len(boxes)
        usable = W - 2*PAD - 30*mm
        bw     = min(28*mm, usable/n - 3*mm)
        bh     = 18*mm
        bx0    = PAD + 28*mm
        sp     = (usable - bw*n) / max(n-1, 1)

        for j, (bname, bsub) in enumerate(boxes):
            bx = bx0 + j*(bw+sp)
            by = y - layer_h + (layer_h-bh)/2
            rr(c, bx, by, bw, bh, r=2*mm, fill=WHITE, stroke=accent, lw=1)

            lines  = bname.split("\n")
            line_y = by + bh - 5.5*mm
            for ln in lines:
                txt(c, bx+bw/2, line_y, ln, size=7, bold=True)
                line_y -= 4*mm
            txt(c, bx+bw/2, by+2.5*mm, bsub, size=6)

        # Downward arrow between layers
        if i < len(LAYERS)-1:
            mx = W/2
            arrow(c, mx, y-layer_h-0.5*mm, mx, y-layer_h-gap+0.5*mm)

        y -= layer_h + gap

    # Legend
    lx, ly = PAD, PAD+2*mm
    txt(c, lx, ly+6*mm, "Legend:", size=7, bold=True, align="left")
    items = [
        (BLUE,   "Entry Point"),
        (GREEN,  "API Router"),
        (ORANGE, "Orchestrator"),
        (RED,    "AI Agent"),
        (PURPLE, "Data Store"),
    ]
    for i, (col, lbl) in enumerate(items):
        cx = lx + 22*mm + i*38*mm
        c.setFillColor(col)
        c.roundRect(cx, ly+3*mm, 10*mm, 5*mm, 1.5*mm, fill=1, stroke=0)
        txt(c, cx+12*mm, ly+4.5*mm, lbl, size=7, align="left")

    c.save()
    print(f"  ✓  architecture.pdf  →  {path}")
    return path


if __name__ == "__main__":
    generate()
