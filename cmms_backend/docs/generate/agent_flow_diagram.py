"""
Agent Flow Diagram — docs/output/agent_flow.pdf
LangGraph StateGraph: node-by-node flow with conditional edges,
agent responsibilities, and external calls.
CBBR-NATEC Innovation Cup 2026
"""
from __future__ import annotations
from pathlib import Path
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
import math

OUTPUT = Path(__file__).parent.parent / "output"
OUTPUT.mkdir(parents=True, exist_ok=True)

# ── Palette ───────────────────────────────────────────────────────────────────
NAVY    = HexColor("#0D1B2A")
BLUE    = HexColor("#1B6CA8")
TEAL    = HexColor("#17A589")
ORANGE  = HexColor("#E67E22")
RED     = HexColor("#C0392B")
GREEN   = HexColor("#1E8449")
PURPLE  = HexColor("#7D3C98")
WHITE   = HexColor("#FFFFFF")
LGREY   = HexColor("#F2F3F4")
MGREY   = HexColor("#BDC3C7")
YELLOW  = HexColor("#F9E79F")
LGREEN  = HexColor("#D5F5E3")
LBLUE   = HexColor("#D6EAF8")
LORANGE = HexColor("#FDEBD0")
LPURPLE = HexColor("#E8DAEF")
PINK    = HexColor("#FADBD8")
BLACK   = HexColor("#000000")

W, H = landscape(A3)   # 420 × 297 mm
PAD  = 10 * mm


# ── Helpers ───────────────────────────────────────────────────────────────────

def rr(c, x, y, w, h, fill=WHITE, stroke=BLUE, lw=1.2, r=3 * mm):
    c.saveState()
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(lw)
    c.roundRect(x, y, w, h, r, fill=1, stroke=1)
    c.restoreState()


def txt(c, x, y, text, size=8, bold=False, align="centre"):
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


def diamond(c, cx, cy, hw, hh, fill=YELLOW, stroke=ORANGE, lw=1.3):
    c.saveState()
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(lw)
    p = c.beginPath()
    p.moveTo(cx, cy + hh)
    p.lineTo(cx + hw, cy)
    p.lineTo(cx, cy - hh)
    p.lineTo(cx - hw, cy)
    p.close()
    c.drawPath(p, fill=1, stroke=1)
    c.restoreState()


def arrow(c, x1, y1, x2, y2, color=MGREY, lw=1.4, label="", dashed=False):
    c.saveState()
    c.setStrokeColor(color)
    c.setLineWidth(lw)
    if dashed:
        c.setDash(5, 3)
    c.line(x1, y1, x2, y2)
    c.setDash()
    # arrowhead
    dx, dy = x2 - x1, y2 - y1
    ln = math.sqrt(dx * dx + dy * dy) or 1
    ux, uy = dx / ln, dy / ln
    sx, sy = -uy * 4, ux * 4
    c.setFillColor(color)
    p = c.beginPath()
    p.moveTo(x2, y2)
    p.lineTo(x2 - ux * 8 + sx, y2 - uy * 8 + sy)
    p.lineTo(x2 - ux * 8 - sx, y2 - uy * 8 - sy)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        c.setFillColor(BLACK)
        c.setFont("Helvetica-Bold", 6.5)
        c.drawCentredString(mx + 6, my + 3, label)
    c.restoreState()


def node_box(c, cx, y_top, w, h, title, sub, ext,
             fill=WHITE, stroke=BLUE, accent=BLUE):
    """
    Draw a node card:
      - coloured header bar with title
      - sub-title in body
      - ext: list of external call strings shown as small badges
    """
    x = cx - w / 2
    # Shadow
    c.setFillColor(MGREY)
    c.roundRect(x + 1.5, y_top - h - 1.5, w, h, 3 * mm, fill=1, stroke=0)
    # Body
    rr(c, x, y_top - h, w, h, fill=fill, stroke=stroke, lw=1.5)
    # Header band
    hdr_h = 9 * mm
    c.setFillColor(accent)
    c.roundRect(x, y_top - hdr_h, w, hdr_h, 3 * mm, fill=1, stroke=0)
    c.rect(x, y_top - hdr_h, w, hdr_h / 2, fill=1, stroke=0)  # flatten bottom corners
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawCentredString(cx, y_top - 6 * mm, title)
    # Sub
    txt(c, cx, y_top - h + (h - hdr_h) / 2 + 1 * mm, sub, size=7)
    # Ext badges
    if ext:
        bx = x + 3 * mm
        by = y_top - h + 2 * mm
        for e in ext:
            bw_badge = len(e) * 3.8 + 6
            c.setFillColor(HexColor("#1A1A2E"))
            c.roundRect(bx, by, bw_badge, 4.5 * mm, 1 * mm, fill=1, stroke=0)
            c.setFillColor(WHITE)
            c.setFont("Helvetica", 5.5)
            c.drawString(bx + 3, by + 1.3 * mm, e)
            bx += bw_badge + 2 * mm


# ── Node definitions ──────────────────────────────────────────────────────────

NODES = [
    # (id, x_mm, y_mm, title, sub, ext_calls, fill, stroke, accent)
    ("start",       20,  135, "WhatsApp\nInbound",
     "POST /webhook  ·  HMAC verified  ·  Dedup",
     ["Meta Cloud API", "HMAC-SHA256"],
     LBLUE, BLUE, BLUE),

    ("rating_gate", 75,  135, "Rating Gate\nNode",
     "check_rating_gate(requester_id, db)",
     ["PostgreSQL"],
     YELLOW, ORANGE, ORANGE),

    ("send_reply",  75,   75, "send_reply\nNode",
     "send_whatsapp_message(to, body, buttons)",
     ["WhatsApp Cloud API"],
     PINK, RED, RED),

    ("intake",      145, 135, "Intake\nNode",
     "IntakeAgent.run(IntakeInput)  →  IntakeOutput",
     ["Whisper API", "GPT-4o Vision", "PostgreSQL"],
     LORANGE, ORANGE, ORANGE),

    ("knowledge",   215, 135, "Knowledge\nNode",
     "KnowledgeAgent.run(KnowledgeInput)  →  KnowledgeOutput",
     ["ChromaDB", "text-embedding-3-small"],
     LPURPLE, PURPLE, PURPLE),

    ("triage",      285, 135, "Triage\nNode",
     "TriageAgent.run(TriageInput)  →  TriageOutput",
     ["GPT-4o", "Rule engine"],
     LORANGE, ORANGE, ORANGE),

    ("dispatch",    355, 135, "Dispatch\nNode",
     "DispatchAgent.run(DispatchInput, db)  →  DispatchOutput",
     ["PostgreSQL", "WhatsApp Cloud API"],
     LGREEN, GREEN, GREEN),

    ("end",         400,  75, "END",
     "OrchestratorState complete",
     [],
     LGREY, MGREY, MGREY),
]

NODE_W = 52 * mm
NODE_H = 28 * mm

# Decision diamond positions (cx_mm, cy_mm, label, hw_mm, hh_mm)
DIAMONDS = [
    (75,  110, "blocked?", 16, 8),
    (145, 110, "complete?", 16, 8),
]

# Arrows: (from_id, to_id, label, dashed)
EDGES = [
    ("start",       "rating_gate", "",         False),
    ("rating_gate", "send_reply",  "blocked",  False),
    ("rating_gate", "intake",      "proceed",  False),
    ("intake",      "send_reply",  "clarify",  False),
    ("intake",      "knowledge",   "proceed",  False),
    ("knowledge",   "triage",      "",         False),
    ("triage",      "dispatch",    "",         False),
    ("dispatch",    "send_reply",  "",         False),
    ("send_reply",  "end",         "",         False),
]


def node_centre(node_id):
    for nid, xmm, ymm, *_ in NODES:
        if nid == node_id:
            return xmm * mm, ymm * mm
    raise KeyError(node_id)


def generate():
    path = OUTPUT / "agent_flow.pdf"
    c = canvas.Canvas(str(path), pagesize=landscape(A3))
    c.setTitle("RT Knits CMMS — Agent Flow (LangGraph)")

    # Background
    c.setFillColor(LGREY)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # ── Title bar ─────────────────────────────────────────────────────────────
    c.setFillColor(NAVY)
    c.rect(0, H - 20 * mm, W, 20 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(PAD, H - 13 * mm, "RT Knits Agentic CMMS — Agent Flow Diagram (LangGraph StateGraph)")
    c.setFont("Helvetica", 9)
    c.drawRightString(W - PAD, H - 13 * mm, "CBBR-NATEC Innovation Cup 2026")

    # ── Section label ─────────────────────────────────────────────────────────
    txt(c, W / 2, H - 25 * mm,
        "Each inbound WhatsApp message creates a fresh OrchestratorState and traverses the graph left → right.",
        size=8)

    # ── Draw edges first (behind nodes) ──────────────────────────────────────
    for fid, tid, lbl, dashed in EDGES:
        fx, fy = node_centre(fid)
        tx, ty = node_centre(tid)
        # Route edge from right-mid of source to left-mid of target
        # (or bottom-mid when going downward to send_reply)
        if ty < fy - 5 * mm:
            # downward: from bottom of source, to top of dest
            arrow(c, fx, fy - NODE_H / 2, tx, ty + NODE_H / 2,
                  color=RED if "clarify" in lbl or "blocked" in lbl else MGREY,
                  lw=1.5, label=lbl, dashed=dashed)
        else:
            arrow(c, fx + NODE_W / 2, fy, tx - NODE_W / 2, ty,
                  color=GREEN if "proceed" in lbl else MGREY,
                  lw=1.5, label=lbl, dashed=dashed)

    # ── Draw decision diamonds ────────────────────────────────────────────────
    for cxmm, cymm, lbl, hwmm, hhmm in DIAMONDS:
        diamond(c, cxmm * mm, cymm * mm, hwmm * mm, hhmm * mm)
        txt(c, cxmm * mm, cymm * mm - 2.5 * mm, lbl, size=7, bold=True)

    # ── Draw nodes ────────────────────────────────────────────────────────────
    for nid, xmm, ymm, title, sub, ext, fill, stroke, accent in NODES:
        node_box(c, xmm * mm, ymm * mm + NODE_H / 2,
                 NODE_W, NODE_H,
                 title, sub, ext,
                 fill=fill, stroke=stroke, accent=accent)

    # ── State payload panel ───────────────────────────────────────────────────
    px, py, pw, ph = PAD, PAD + 2 * mm, 115 * mm, 50 * mm
    rr(c, px, py, pw, ph, fill=LBLUE, stroke=BLUE, lw=1.2)
    c.setFillColor(BLUE)
    c.roundRect(px, py + ph - 8 * mm, pw, 8 * mm, 2 * mm, fill=1, stroke=0)
    c.rect(px, py + ph - 8 * mm, pw, 4 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(px + 3 * mm, py + ph - 5.5 * mm, "OrchestratorState  (shared graph state)")
    fields = [
        "session_id  ·  sender_phone  ·  whatsapp_message_id",
        "messages[]  ·  current_route  ·  awaiting_reply",
        "rating_gate: RatingGateBlock",
        "intake_output: IntakeOutput | None",
        "knowledge_output: KnowledgeOutput | None",
        "triage_output: TriageOutput | None",
        "dispatch_output: DispatchOutput | None",
        "outbound_message  ·  outbound_buttons  ·  error",
    ]
    for i, f in enumerate(fields):
        txt(c, px + pw / 2, py + ph - 11 * mm - i * 4.8 * mm, f, size=6.5)

    # ── P0 Escalation note ────────────────────────────────────────────────────
    ex, ey, ew, eh = W - PAD - 115 * mm, PAD + 2 * mm, 115 * mm, 30 * mm
    rr(c, ex, ey, ew, eh, fill=PINK, stroke=RED, lw=1.2)
    c.setFillColor(RED)
    c.roundRect(ex, ey + eh - 8 * mm, ew, 8 * mm, 2 * mm, fill=1, stroke=0)
    c.rect(ex, ey + eh - 8 * mm, ew, 4 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(ex + 3 * mm, ey + eh - 5.5 * mm, "P0 Escalation Ladder  (APScheduler)")
    esc_lines = [
        "On P0 dispatch: schedule_p0_escalation(assignment_id)",
        "Countdown: 5 minutes from dispatch time",
        "If ack within 5 min → no action (acknowledged_at IS NOT NULL)",
        "If no ack → close assignment, find_next_technician(), restart",
        "Repeat until acknowledged or CRITICAL alert logged",
    ]
    for i, l in enumerate(esc_lines):
        txt(c, ex + ew / 2, ey + eh - 12 * mm - i * 4.2 * mm, l, size=6.5)

    # ── Legend ────────────────────────────────────────────────────────────────
    lx, ly = PAD + 120 * mm, PAD + 2 * mm
    rr(c, lx, ly, 100 * mm, 30 * mm, fill=LGREY, stroke=MGREY, lw=0.8)
    txt(c, lx + 50 * mm, ly + 26 * mm, "LEGEND", size=7.5, bold=True)
    items = [
        (ORANGE, "Rating Gate / Intake / Triage (LLM)"),
        (GREEN,  "Dispatch (SQL + WA notify)"),
        (PURPLE, "Knowledge (ChromaDB)"),
        (RED,    "Send Reply / Escalation path"),
        (MGREY,  "Normal flow"),
    ]
    for i, (col, lbl) in enumerate(items):
        row = i // 2
        col_offset = (i % 2) * 50 * mm
        ix = lx + 3 * mm + col_offset
        iy = ly + 20 * mm - row * 7 * mm
        c.setFillColor(col)
        c.roundRect(ix, iy, 8 * mm, 4.5 * mm, 1 * mm, fill=1, stroke=0)
        txt(c, ix + 10 * mm + 18 * mm, iy + 1.5 * mm, lbl, size=6.5, align="left")

    c.save()
    print(f"  ✓  agent_flow.pdf  →  {path}")
    return path


if __name__ == "__main__":
    generate()
