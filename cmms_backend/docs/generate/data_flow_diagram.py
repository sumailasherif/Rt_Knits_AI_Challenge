"""
Data Flow Diagram — docs/output/data_flow.pdf
Shows the Pydantic schemas that move between every agent stage,
the external systems each stage calls, and the DB writes at each step.
Landscape A3, single page.
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
WHITE   = HexColor("#FFFFFF")
BLACK   = HexColor("#000000")
LGREY   = HexColor("#F2F3F4")
MGREY   = HexColor("#BDC3C7")

A_BLUE   = HexColor("#1B6CA8")
A_ORANGE = HexColor("#E67E22")
A_GREEN  = HexColor("#1E8449")
A_PURPLE = HexColor("#7D3C98")
A_RED    = HexColor("#C0392B")
A_TEAL   = HexColor("#17A589")
A_GOLD   = HexColor("#B7950B")

L_BLUE   = HexColor("#D6EAF8")
L_ORANGE = HexColor("#FDEBD0")
L_GREEN  = HexColor("#D5F5E3")
L_PURPLE = HexColor("#E8DAEF")
L_RED    = HexColor("#FADBD8")
L_TEAL   = HexColor("#D1F2EB")
L_GOLD   = HexColor("#FEF9E7")

DB_COL   = HexColor("#1A5276")
EXT_COL  = HexColor("#4A235A")

W, H = landscape(A3)
PAD  = 10 * mm


# ── Stage definitions ─────────────────────────────────────────────────────────
# Each stage:  (x_mm, label, accent, light, input_schema, output_schema, db_writes, ext_calls)
STAGES = [
    (
        22, "WhatsApp\nWebhook",
        A_BLUE, L_BLUE,
        # input
        ["WhatsAppInbound\n(Meta payload)"],
        # output (→ next)
        ["OrchestratorState\n(initial)"],
        # DB writes
        [],
        # external
        ["Meta Cloud API\n(mark as read)"],
    ),
    (
        88, "Rating Gate\nNode",
        A_ORANGE, L_ORANGE,
        ["OrchestratorState\n(sender_phone)"],
        ["RatingGateBlock\n(blocked, pending_wo_ids)"],
        ["SELECT work_order\n+ feedback\n(unrated WOs)"],
        [],
    ),
    (
        154, "Intake\nAgent",
        A_RED, L_RED,
        ["IntakeInput\n(raw_text,\nimage_id?,\naudio_id?)"],
        ["IntakeOutput\n(request_id,\nfault: FaultDetail,\nis_complete)"],
        ["INSERT task_request"],
        ["Whisper API\n(audio→text)",
         "GPT-4o Vision\n(image→desc)",
         "GPT-4o Chat\n(extract fault)"],
    ),
    (
        220, "Knowledge\nAgent",
        A_PURPLE, L_PURPLE,
        ["KnowledgeInput\n(query, asset_id,\ntop_k=3)"],
        ["KnowledgeOutput\n(snippets[],\ncombined_context)"],
        ["SELECT knowledge_doc\n(via ChromaDB ref)"],
        ["text-embedding-\n3-small (embed)",
         "ChromaDB\n(cosine search)"],
    ),
    (
        286, "Triage\nAgent",
        A_ORANGE, L_ORANGE,
        ["TriageInput\n(request_id,\nfault,\nasset_is_critical)\n+ knowledge_context"],
        ["TriageOutput\n(wo_id, priority,\nrequired_trade,\nestimated_minutes,\nsla_hours)"],
        ["INSERT work_order\n(wo_id, priority,\nstatus=Open,\nsla_due_at)"],
        ["GPT-4o Chat\n(validate priority,\nestimate time)"],
    ),
    (
        352, "Dispatch\nAgent",
        A_GREEN, L_GREEN,
        ["DispatchInput\n(wo_id, priority,\nrequired_trade,\nestimated_minutes)"],
        ["DispatchOutput\n(assignment_id,\nassigned_tech,\nescalation_scheduled)"],
        ["SELECT technician\n(trade, on_shift,\nactive_jobs)",
         "INSERT assignment",
         "UPDATE work_order\nstatus=Assigned"],
        ["WhatsApp Cloud API\n(dispatch notify\n+ ACK buttons)"],
    ),
    (
        412, "APScheduler\nP0 Escalation",
        A_RED, L_RED,
        ["assignment_id\n(P0 only)"],
        ["Re-dispatch or\nack confirmed"],
        ["UPDATE assignment\n(acknowledged_at\nor abandoned)",
         "INSERT assignment\n(next tech)"],
        ["WhatsApp Cloud API\n(escalation alert)"],
    ),
]

# Planning agent — separate lane below main flow
PLANNING = (
    220, 62,   # cx_mm, cy_mm
    "Planning Agent\n(Nightly Batch — Loop 1)",
    A_TEAL, L_TEAL,
    ["PlanningInput\n(plan_date, force)"],
    ["PlanningOutput\n(plans_created[],\nbacklog_rolled_forward[])"],
    ["SELECT technician\n(on_shift)",
     "SELECT work_order\n(Open/Queued/Paused)",
     "INSERT daily_plan"],
    ["WhatsApp Cloud API\n(shift plans\n+ CONFIRM/CONFLICT)"],
)

# Analytics agent — separate lane below
ANALYTICS = (
    380, 62,
    "Analytics Agent\n(On-demand)",
    A_GOLD, L_GOLD,
    ["AnalyticsInput\n(report_type,\ndate_from/to,\ndept_id)"],
    ["AnalyticsOutput\n(kpi, tech_perf,\nasset_failures)"],
    ["SELECT work_order\n+ assignment\n+ feedback\n+ technician\n+ asset"],
    ["GPT-4o Chat\n(NL summary)"],
)

# Arrow flows between stages (from_idx, to_idx, label)
FLOW = [
    (0, 1, ""),
    (1, 2, "proceed"),
    (2, 3, "is_complete\n= True"),
    (3, 4, ""),
    (4, 5, ""),
    (5, 6, "P0 only"),
]

STAGE_W  = 52 * mm
STAGE_H  = 70 * mm
MAIN_Y   = H - 50 * mm   # top of main stage cards
SIDE_W   = 58 * mm
SIDE_H   = 58 * mm

SCHEMA_BOX_W = 48 * mm
SCHEMA_BOX_H =  8 * mm


# ── Helpers ───────────────────────────────────────────────────────────────────

def rr(c, x, y, w, h, fill=WHITE, stroke=MGREY, lw=1.0, r=2 * mm):
    c.saveState()
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(lw)
    c.roundRect(x, y, w, h, r, fill=1, stroke=1)
    c.restoreState()


def txt(c, x, y, text, size=7, bold=False, align="centre", color=BLACK):
    lines = text.split("\n")
    line_h = size * 1.35
    total = line_h * (len(lines) - 1)
    c.saveState()
    c.setFillColor(color)
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    for i, line in enumerate(lines):
        ly = y + total / 2 - i * line_h
        if align == "centre":
            c.drawCentredString(x, ly, line)
        elif align == "left":
            c.drawString(x, ly, line)
        elif align == "right":
            c.drawRightString(x, ly, line)
    c.restoreState()


def arrow_h(c, x1, y, x2, label="", color=MGREY, lw=1.6):
    c.saveState()
    c.setStrokeColor(color)
    c.setLineWidth(lw)
    c.line(x1, y, x2 - 7, y)
    # arrowhead
    c.setFillColor(color)
    p = c.beginPath()
    p.moveTo(x2, y)
    p.lineTo(x2 - 8, y + 4)
    p.lineTo(x2 - 8, y - 4)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    if label:
        c.setFillColor(BLACK)
        c.setFont("Helvetica-Bold", 6)
        c.drawCentredString((x1 + x2) / 2, y + 3, label)
    c.restoreState()


def arrow_v(c, x, y1, y2, label="", color=MGREY, lw=1.4):
    c.saveState()
    c.setStrokeColor(color)
    c.setLineWidth(lw)
    c.setDash(4, 3)
    c.line(x, y1, x, y2 + 7)
    c.setDash()
    c.setFillColor(color)
    p = c.beginPath()
    p.moveTo(x, y2)
    p.lineTo(x - 4, y2 + 8)
    p.lineTo(x + 4, y2 + 8)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    if label:
        c.setFillColor(BLACK)
        c.setFont("Helvetica-Bold", 5.5)
        c.drawString(x + 3, (y1 + y2) / 2, label)
    c.restoreState()


def schema_pill(c, cx, y, lines, accent, light):
    """Draw a small pill showing schema fields."""
    n = len(lines)
    h = n * 4.5 * mm + 3 * mm
    w = SCHEMA_BOX_W
    x = cx - w / 2
    rr(c, x, y - h, w, h, fill=light, stroke=accent, lw=0.8, r=1.5 * mm)
    for i, line in enumerate(lines):
        c.setFillColor(BLACK)
        c.setFont("Helvetica", 5.8)
        c.drawCentredString(cx, y - 3 * mm - i * 4.5 * mm, line)
    return h


def ext_badge(c, x, y, text, color=EXT_COL):
    lines = text.split("\n")
    bw = max(len(l) for l in lines) * 4.2 + 8
    bh = len(lines) * 5.5 + 5
    c.setFillColor(color)
    c.roundRect(x, y, bw, bh, 1.5 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica", 5.5)
    for i, l in enumerate(lines):
        c.drawCentredString(x + bw / 2, y + bh - 4.5 - i * 5.5, l)
    return bw, bh


def db_badge(c, x, y, text, color=DB_COL):
    lines = text.split("\n")
    bw = max(len(l) for l in lines) * 3.8 + 8
    bh = len(lines) * 5 + 5
    c.setFillColor(color)
    c.roundRect(x, y, bw, bh, 1 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica", 5.2)
    for i, l in enumerate(lines):
        c.drawCentredString(x + bw / 2, y + bh - 4 - i * 5, l)
    return bw, bh


def draw_stage(c, cx_mm, label, accent, light, inputs, outputs,
               db_writes, ext_calls, y_top, card_w=STAGE_W, card_h=STAGE_H):
    cx = cx_mm * mm
    x  = cx - card_w / 2
    y  = y_top - card_h

    # Shadow
    c.setFillColor(MGREY)
    c.roundRect(x + 2, y - 2, card_w, card_h, 3 * mm, fill=1, stroke=0)

    # Body
    rr(c, x, y, card_w, card_h, fill=light, stroke=accent, lw=1.6, r=3 * mm)

    # Header
    hdr_h = 10 * mm
    c.setFillColor(accent)
    c.roundRect(x, y + card_h - hdr_h, card_w, hdr_h, 3 * mm, fill=1, stroke=0)
    c.rect(x, y + card_h - hdr_h, card_w, hdr_h / 2, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 8)
    label_lines = label.split("\n")
    for i, ll in enumerate(label_lines):
        c.drawCentredString(cx, y + card_h - 5 * mm - i * 5 * mm, ll)

    body_y = y + card_h - hdr_h - 3 * mm

    # INPUT label
    c.setFillColor(accent)
    c.setFont("Helvetica-Bold", 5.5)
    c.drawString(x + 3 * mm, body_y - 3.5 * mm, "INPUT")
    body_y -= 5 * mm
    for inp in inputs:
        lines = inp.split("\n")
        h = len(lines) * 4 * mm + 2 * mm
        rr(c, x + 2 * mm, body_y - h, card_w - 4 * mm, h,
           fill=WHITE, stroke=accent, lw=0.7, r=1 * mm)
        for i, l in enumerate(lines):
            c.setFillColor(BLACK)
            c.setFont("Helvetica", 5.5)
            c.drawCentredString(cx, body_y - 3.5 * mm - i * 4 * mm, l)
        body_y -= h + 2 * mm

    # OUTPUT label
    c.setFillColor(accent)
    c.setFont("Helvetica-Bold", 5.5)
    c.drawString(x + 3 * mm, body_y - 3.5 * mm, "OUTPUT")
    body_y -= 5 * mm
    for out in outputs:
        lines = out.split("\n")
        h = len(lines) * 4 * mm + 2 * mm
        rr(c, x + 2 * mm, body_y - h, card_w - 4 * mm, h,
           fill=HexColor("#EBF5FB"), stroke=accent, lw=0.7, r=1 * mm)
        for i, l in enumerate(lines):
            c.setFillColor(BLACK)
            c.setFont("Helvetica", 5.5)
            c.drawCentredString(cx, body_y - 3.5 * mm - i * 4 * mm, l)
        body_y -= h + 2 * mm

    # DB writes (below card)
    if db_writes:
        db_y = y - 3 * mm
        for dw in db_writes:
            db_bw, db_bh = db_badge(c, cx - 24 * mm, db_y - db_bh if False else 0, dw)
            # recalculate properly
            lines = dw.split("\n")
            db_bw2 = max(len(l) for l in lines) * 3.8 + 8
            db_bh2 = len(lines) * 5 + 5
            db_badge(c, cx - db_bw2 / 2, db_y - db_bh2, dw)
            db_y -= db_bh2 + 2 * mm

    # Ext calls (top of card, above)
    if ext_calls:
        ext_y = y_top + 3 * mm
        for ec in ext_calls:
            lines = ec.split("\n")
            ext_bw = max(len(l) for l in lines) * 4.2 + 8
            ext_bh = len(lines) * 5.5 + 5
            ext_badge(c, cx - ext_bw / 2, ext_y, ec)
            # dashed line from badge down to card top
            arrow_v(c, cx, ext_y, y_top, color=EXT_COL, lw=0.8)
            ext_y += ext_bh + 2 * mm


def generate():
    path = OUTPUT / "data_flow.pdf"
    c = canvas.Canvas(str(path), pagesize=landscape(A3))
    c.setTitle("RT Knits CMMS — Data Flow Diagram")

    # Background
    c.setFillColor(LGREY)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # ── Title bar ─────────────────────────────────────────────────────────────
    c.setFillColor(NAVY)
    c.rect(0, H - 20 * mm, W, 20 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(PAD, H - 13 * mm, "RT Knits Agentic CMMS — Data Flow Diagram")
    c.setFont("Helvetica", 9)
    c.drawRightString(W - PAD, H - 13 * mm, "Pydantic v2 schemas · PostgreSQL · ChromaDB · OpenAI APIs  ·  CBBR-NATEC 2026")

    # ── Section labels ────────────────────────────────────────────────────────
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(PAD, H - 24 * mm, "MAIN FLOW  (Loop 2 — triggered by each inbound WhatsApp message)")

    # ── Draw main flow stages ─────────────────────────────────────────────────
    MAIN_TOP = H - 28 * mm

    for stage in STAGES:
        cx_mm, label, accent, light, inputs, outputs, db_writes, ext_calls = stage
        draw_stage(c, cx_mm, label, accent, light, inputs, outputs,
                   db_writes, ext_calls, MAIN_TOP,
                   card_w=STAGE_W, card_h=STAGE_H)

    # ── Horizontal flow arrows between stages ─────────────────────────────────
    mid_y = MAIN_TOP - STAGE_H / 2
    for from_idx, to_idx, lbl in FLOW:
        from_cx = STAGES[from_idx][0] * mm + STAGE_W / 2
        to_cx   = STAGES[to_idx][0] * mm - STAGE_W / 2
        arrow_h(c, from_cx, mid_y, to_cx, label=lbl,
                color=A_GREEN if "proceed" in lbl else MGREY)

    # ── "Blocked" branch arrow (rating gate → send_reply, downward) ──────────
    rg_cx = STAGES[1][0] * mm
    c.setFillColor(A_RED)
    c.setStrokeColor(A_RED)
    c.setLineWidth(1.4)
    blocked_y = MAIN_TOP - STAGE_H - 5 * mm
    c.setDash(5, 3)
    c.line(rg_cx, MAIN_TOP - STAGE_H, rg_cx, blocked_y)
    c.setDash()
    # blocked label
    c.setFillColor(A_RED)
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(rg_cx, blocked_y - 3, "blocked → send WA rating request")

    # ── "Clarify" branch arrow (intake → send_reply) ──────────────────────────
    intake_cx = STAGES[2][0] * mm
    c.setStrokeColor(A_ORANGE)
    c.setLineWidth(1.2)
    c.setDash(4, 3)
    c.line(intake_cx, MAIN_TOP - STAGE_H, intake_cx, blocked_y - 5 * mm)
    c.setDash()
    c.setFillColor(A_ORANGE)
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(intake_cx, blocked_y - 8 * mm, "is_complete=False → ask clarification")

    # ── Feedback loop label ───────────────────────────────────────────────────
    c.setFillColor(NAVY)
    c.setFont("Helvetica", 6.5)
    c.drawCentredString(STAGES[5][0] * mm, MAIN_TOP - STAGE_H - 14 * mm,
                        "On completion: INSERT feedback → UPDATE technician.reward_score (base+urgency+quality+speed)")

    # ── Bottom lane separator ─────────────────────────────────────────────────
    lane_y = MAIN_TOP - STAGE_H - 20 * mm
    c.setStrokeColor(MGREY)
    c.setLineWidth(0.7)
    c.setDash(6, 4)
    c.line(PAD, lane_y, W - PAD, lane_y)
    c.setDash()
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(PAD, lane_y - 4 * mm,
                 "BACKGROUND LOOPS  (not triggered by inbound message)")

    # ── Planning Agent side card ──────────────────────────────────────────────
    p_cx, p_cy, p_lbl, p_acc, p_light, p_in, p_out, p_db, p_ext = PLANNING
    PLAN_TOP = lane_y - 7 * mm
    draw_stage(c, p_cx, p_lbl, p_acc, p_light, p_in, p_out,
               p_db, p_ext, PLAN_TOP, card_w=SIDE_W, card_h=SIDE_H)

    # APScheduler trigger badge
    c.setFillColor(A_TEAL)
    c.roundRect(p_cx * mm - 28 * mm, PLAN_TOP + 3 * mm, 56 * mm, 6 * mm,
                1.5 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawCentredString(p_cx * mm, PLAN_TOP + 6 * mm,
                        "APScheduler  ·  NIGHTLY_PLAN_HOUR=21:00  (UTC+4)")

    # ── Analytics Agent side card ─────────────────────────────────────────────
    a_cx, a_cy, a_lbl, a_acc, a_light, a_in, a_out, a_db, a_ext = ANALYTICS
    draw_stage(c, a_cx, a_lbl, a_acc, a_light, a_in, a_out,
               a_db, a_ext, PLAN_TOP, card_w=SIDE_W, card_h=SIDE_H)

    # REST API trigger badge
    c.setFillColor(A_GOLD)
    c.roundRect(a_cx * mm - 28 * mm, PLAN_TOP + 3 * mm, 56 * mm, 6 * mm,
                1.5 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawCentredString(a_cx * mm, PLAN_TOP + 6 * mm,
                        "GET /api/v1/analytics/*  (on-demand, dashboard)")

    # ── Legend ────────────────────────────────────────────────────────────────
    lx, ly = PAD, PAD + 1 * mm
    c.setFillColor(HexColor("#1A1A2E"))
    c.roundRect(lx, ly, 190 * mm, 10 * mm, 2 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(lx + 3 * mm, ly + 3 * mm, "LEGEND:")

    items = [
        (DB_COL,  "PostgreSQL write (SQL)"),
        (EXT_COL, "External API call"),
        (A_GREEN, "Happy-path flow arrow"),
        (A_RED,   "Blocked / error branch"),
        (A_ORANGE,"Clarification branch"),
    ]
    for i, (col, lbl) in enumerate(items):
        ix = lx + 22 * mm + i * 34 * mm
        c.setFillColor(col)
        c.roundRect(ix, ly + 2.5 * mm, 10 * mm, 5 * mm, 1 * mm, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica", 6)
        c.drawString(ix + 11.5 * mm, ly + 3.8 * mm, lbl)

    c.save()
    print(f"  ✓  data_flow.pdf  →  {path}")
    return path


if __name__ == "__main__":
    generate()
