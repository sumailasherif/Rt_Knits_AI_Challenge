"""
Flow Map Diagram — docs/output/flow_map.pdf
Covers both operational loops on two portrait A3 pages.
All text in pure black (#000000).
CBBR-NATEC Innovation Cup 2026
"""
from __future__ import annotations
from pathlib import Path
from reportlab.lib.pagesizes import A3
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
RED    = HexColor("#C0392B")
GREEN  = HexColor("#1E8449")
PURPLE = HexColor("#7D3C98")
WHITE  = HexColor("#FFFFFF")
LGREY  = HexColor("#F2F3F4")
MGREY  = HexColor("#BDC3C7")
YELLOW = HexColor("#F9E79F")
PINK   = HexColor("#FADBD8")
LGREEN = HexColor("#D5F5E3")
LBLUE  = HexColor("#D6EAF8")
LORANGE= HexColor("#FDEBD0")
LPURPLE= HexColor("#E8DAEF")
BLACK  = HexColor("#000000")

W, H = A3   # portrait  297 × 420 mm
PAD  = 12*mm


# ─────────────────────────────────────────────────────────────────────────────
# Primitive helpers
# ─────────────────────────────────────────────────────────────────────────────

def box(c, x, y, w, h, fill=WHITE, stroke=BLUE, lw=1.2, r=3*mm):
    c.saveState()
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(lw)
    c.roundRect(x, y, w, h, r, fill=1, stroke=1)
    c.restoreState()


def diamond(c, cx, cy, hw, hh, fill=YELLOW, stroke=ORANGE, lw=1.2):
    """Draw a decision diamond centred at (cx,cy)."""
    c.saveState()
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(lw)
    p = c.beginPath()
    p.moveTo(cx,      cy+hh)
    p.lineTo(cx+hw,   cy)
    p.lineTo(cx,      cy-hh)
    p.lineTo(cx-hw,   cy)
    p.close()
    c.drawPath(p, fill=1, stroke=1)
    c.restoreState()


def txt(c, x, y, text, size=8, bold=False, align="centre", color=BLACK):
    c.saveState()
    c.setFillColor(BLACK)          # always black
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    if align == "centre":
        c.drawCentredString(x, y, text)
    elif align == "left":
        c.drawString(x, y, text)
    elif align == "right":
        c.drawRightString(x, y, text)
    c.restoreState()


def arrow_v(c, x, y_top, y_bot, label_txt="", lw=1.3):
    """Vertical downward arrow."""
    c.saveState()
    c.setStrokeColor(MGREY)
    c.setLineWidth(lw)
    c.line(x, y_top, x, y_bot+4)
    # arrowhead
    c.setFillColor(MGREY)
    p = c.beginPath()
    p.moveTo(x, y_bot)
    p.lineTo(x-3, y_bot+7)
    p.lineTo(x+3, y_bot+7)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    if label_txt:
        c.setFillColor(BLACK)
        c.setFont("Helvetica", 6.5)
        c.drawString(x+3, (y_top+y_bot)/2, label_txt)
    c.restoreState()


def arrow_h(c, x_l, x_r, y, label_txt="", lw=1.3, right=True):
    """Horizontal arrow."""
    c.saveState()
    c.setStrokeColor(MGREY)
    c.setLineWidth(lw)
    c.line(x_l, y, x_r, y)
    c.setFillColor(MGREY)
    if right:
        p = c.beginPath()
        p.moveTo(x_r, y)
        p.lineTo(x_r-7, y+3)
        p.lineTo(x_r-7, y-3)
        p.close()
    else:
        p = c.beginPath()
        p.moveTo(x_l, y)
        p.lineTo(x_l+7, y+3)
        p.lineTo(x_l+7, y-3)
        p.close()
    c.drawPath(p, fill=1, stroke=0)
    if label_txt:
        c.setFillColor(BLACK)
        c.setFont("Helvetica", 6.5)
        mid = (x_l+x_r)/2
        c.drawCentredString(mid, y+2.5, label_txt)
    c.restoreState()


def section_band(c, y, label_txt, fill=LBLUE, stroke=BLUE):
    """Full-width section header band."""
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(0.8)
    c.roundRect(PAD, y-6*mm, W-2*PAD, 6*mm, 1.5*mm, fill=1, stroke=1)
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawCentredString(W/2, y-4.3*mm, label_txt)


def title_bar(c, title, subtitle):
    # Light blue band — black text on light background for maximum visibility
    c.setFillColor(LBLUE)
    c.setStrokeColor(BLUE)
    c.setLineWidth(1.5)
    c.rect(0, H-22*mm, W, 22*mm, fill=1, stroke=0)
    c.line(0, H-22*mm, W, H-22*mm)
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(W/2, H-13*mm, title)
    c.setFont("Helvetica", 8)
    c.drawCentredString(W/2, H-19*mm, subtitle)


def footer(c, page_num, total):
    # Light grey band — black text
    c.setFillColor(HexColor("#E0E0E0"))
    c.setStrokeColor(MGREY)
    c.setLineWidth(0.5)
    c.rect(0, 0, W, 10*mm, fill=1, stroke=0)
    c.line(0, 10*mm, W, 10*mm)
    c.setFillColor(BLACK)
    c.setFont("Helvetica", 7)
    c.drawCentredString(W/2, 3.5*mm, f"RT Knits Agentic CMMS  ·  CBBR-NATEC Innovation Cup 2026  ·  Page {page_num} of {total}")


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 1 — Loop 1: Nightly Batch Planning
# ─────────────────────────────────────────────────────────────────────────────

def page1(c: canvas.Canvas):
    title_bar(c,
              "LOOP 1 — Nightly Batch Planning & Technician Conflict Resolution",
              "APScheduler fires at 21:00 (Mauritius time) · Greedy bin-packing · WhatsApp plan delivery")
    footer(c, 1, 2)

    cx   = W / 2
    bw   = 100*mm   # standard box width
    bh   = 12*mm    # standard box height
    bw_s = 72*mm    # small box
    bh_s = 10*mm
    y    = H - 28*mm

    def step(label, sub, fill, stroke, y_pos, w=None):
        w = w or bw
        x = cx - w/2
        box(c, x, y_pos-bh, w, bh, fill=fill, stroke=stroke, lw=1.4)
        txt(c, cx, y_pos-bh/2+2, label, size=8, bold=True)
        if sub:
            txt(c, cx, y_pos-bh/2-3, sub, size=6.5)
        return y_pos - bh

    # ── Phase band 1 ─────────────────────────────────────────────────────────
    section_band(c, y, "PHASE 1 — Data Collection", fill=LBLUE, stroke=BLUE)
    y -= 8*mm

    y = step("APScheduler Trigger", "NIGHTLY_PLAN_HOUR=21:00  (Indian/Mauritius UTC+4)", LBLUE, BLUE, y)
    arrow_v(c, cx, y, y-7*mm)
    y -= 7*mm
    y = step("Fetch On-Shift Technicians", "SELECT technician WHERE on_shift=TRUE AND is_active=TRUE", LBLUE, BLUE, y)
    arrow_v(c, cx, y, y-7*mm)
    y -= 7*mm
    y = step("Fetch Open Work Orders", "SELECT work_order WHERE status IN (Open, Queued, Paused)\nORDER BY priority ASC, created_at ASC", LBLUE, BLUE, y)

    # ── Phase band 2 ─────────────────────────────────────────────────────────
    y -= 9*mm
    section_band(c, y, "PHASE 2 — Greedy Bin-Packing (420 min / shift)", fill=LORANGE, stroke=ORANGE)
    y -= 8*mm

    y = step("balance_workload()", "Match WO trade → technician bucket  |  Cap: 420 min per technician", LORANGE, ORANGE, y)
    arrow_v(c, cx, y, y-7*mm)
    y -= 7*mm

    # Decision diamond
    dh = 10*mm
    diamond(c, cx, y-dh, 52*mm, dh, fill=YELLOW, stroke=ORANGE)
    txt(c, cx, y-dh, "WO fits in\ntech capacity?", size=7.5, bold=True)
    y -= 2*dh

    # Yes branch (straight down)
    arrow_v(c, cx, y, y-7*mm, "YES — assign")
    y -= 7*mm
    bx_assign = cx - bw_s/2
    box(c, bx_assign, y-bh_s, bw_s, bh_s, fill=LGREEN, stroke=GREEN, lw=1.2)
    txt(c, cx, y-bh_s/2+1.5, "Add WO to tech bucket", size=7.5, bold=True)
    txt(c, cx, y-bh_s/2-3.5, "remaining_minutes -= estimated_minutes", size=6)
    y -= bh_s

    # No branch (right side)
    no_x = cx + 68*mm
    no_y = y + bh_s + 7*mm + 2*dh - dh
    arrow_h(c, cx+52*mm, no_x-30*mm, no_y, "NO")
    box(c, no_x-30*mm, no_y-bh_s, 40*mm, bh_s, fill=PINK, stroke=RED, lw=1.2)
    txt(c, no_x-10*mm, no_y-bh_s/2+1, "Roll to Backlog", size=7.5, bold=True)
    txt(c, no_x-10*mm, no_y-bh_s/2-4, "backlog_rolled_forward[]", size=6)

    # ── Phase band 3 ─────────────────────────────────────────────────────────
    y -= 9*mm
    section_band(c, y, "PHASE 3 — Persist & Notify", fill=LGREEN, stroke=GREEN)
    y -= 8*mm

    y = step("INSERT daily_plan rows", "plan_id, tech_id, plan_date, items=wo_ids[]", LGREEN, GREEN, y)
    arrow_v(c, cx, y, y-7*mm)
    y -= 7*mm
    y = step("Send WhatsApp Plan to Each Technician", "📋 Shift Plan · Buttons: [✅ CONFIRM]  [⚠️ CONFLICT]", LGREEN, GREEN, y)
    arrow_v(c, cx, y, y-7*mm)
    y -= 7*mm

    # Decision diamond — confirm vs conflict
    diamond(c, cx, y-dh, 52*mm, dh, fill=YELLOW, stroke=ORANGE)
    txt(c, cx, y-dh, "Technician\nconfirms?", size=7.5, bold=True)
    y -= 2*dh

    # YES
    yes_bx = cx - bw_s/2 - 30*mm
    arrow_h(c, cx-52*mm, yes_bx+bw_s, y+dh, "YES", right=False)
    box(c, yes_bx, y+dh-bh_s, bw_s, bh_s, fill=LGREEN, stroke=GREEN)
    txt(c, yes_bx+bw_s/2, y+dh-bh_s/2+1, "SET confirmed=TRUE", size=7.5, bold=True)
    txt(c, yes_bx+bw_s/2, y+dh-bh_s/2-4, "Reply: ✅ Shift plan confirmed!", size=6)

    # NO — conflict flow
    arrow_v(c, cx, y, y-7*mm, "CONFLICT")
    y -= 7*mm
    y = step("Tech replies with conflict reason", "UPDATE daily_plan SET conflict_note=...", PINK, RED, y, w=bw_s+10*mm)
    arrow_v(c, cx, y, y-7*mm)
    y -= 7*mm
    y = step("Planning Agent re-balances", "Redistribute conflicted WOs to available technicians", LORANGE, ORANGE, y)
    arrow_v(c, cx, y, y-7*mm)
    y -= 7*mm
    y = step("Send updated plan", "All plans confirmed or adjusted before shift start", LGREEN, GREEN, y)


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 2 — Loop 2: Live Triage, Rating Gate, P0 Escalation
# ─────────────────────────────────────────────────────────────────────────────

def page2(c: canvas.Canvas):
    title_bar(c,
              "LOOP 2 — Live Arbitration: Intake → Rating Gate → Triage → Dispatch → P0 Escalation",
              "Continuous  ·  Real-time WhatsApp messages  ·  Async P0 countdown (5 min)")
    footer(c, 2, 2)

    cx  = W / 2
    bw  = 105*mm
    bh  = 11*mm
    bws = 74*mm
    bhs = 9*mm
    dh  = 9*mm
    y   = H - 28*mm

    def step(label, sub, fill, stroke, y_pos, w=None, h=None):
        ew = w or bw
        eh = h or bh
        x  = cx - ew/2
        box(c, x, y_pos-eh, ew, eh, fill=fill, stroke=stroke, lw=1.3)
        txt(c, cx, y_pos-eh/2+2,   label, size=7.5, bold=True)
        if sub:
            txt(c, cx, y_pos-eh/2-3.5, sub,   size=6)
        return y_pos - eh

    # ── INBOUND ───────────────────────────────────────────────────────────────
    section_band(c, y, "INBOUND — Meta Cloud API → FastAPI Webhook", fill=LBLUE, stroke=BLUE)
    y -= 8*mm
    y = step("Worker sends WhatsApp message",
             "Text / Voice Note (Whisper) / Photo (GPT-4o Vision)", LBLUE, BLUE, y)
    arrow_v(c, cx, y, y-6*mm)
    y -= 6*mm
    y = step("POST /webhook",
             "HMAC-SHA256 verified  ·  Deduplicated by whatsapp_message_id  ·  Mark as READ", LBLUE, BLUE, y)
    arrow_v(c, cx, y, y-6*mm)
    y -= 6*mm

    # ── RATING GATE ───────────────────────────────────────────────────────────
    section_band(c, y, "RATING GATE CHECK", fill=YELLOW, stroke=ORANGE)
    y -= 8*mm
    diamond(c, cx, y-dh, 50*mm, dh, fill=YELLOW, stroke=ORANGE)
    txt(c, cx, y-dh, "Pending unrated\nwork orders?", size=7.5, bold=True)
    y -= 2*dh

    # BLOCKED branch (right)
    bk_y = y + dh
    arrow_h(c, cx+50*mm, cx+80*mm, bk_y, "YES — BLOCKED")
    box(c, cx+80*mm, bk_y-bhs, bws, bhs, fill=PINK, stroke=RED)
    txt(c, cx+80*mm+bws/2, bk_y-bhs/2+1, "Send rating request", size=7.5, bold=True)
    txt(c, cx+80*mm+bws/2, bk_y-bhs/2-4, '⭐ "Rate WO-X before new request"', size=6)

    arrow_v(c, cx, y, y-6*mm, "NO — proceed")
    y -= 6*mm

    # ── INTAKE AGENT ─────────────────────────────────────────────────────────
    section_band(c, y, "INTAKE AGENT  (GPT-4o + Whisper + Vision)", fill=LORANGE, stroke=ORANGE)
    y -= 8*mm
    y = step("Transcribe audio / Analyse photo / Translate text",
             "Whisper API  ·  GPT-4o Vision  ·  EN / FR / HI / BN", LORANGE, ORANGE, y)
    arrow_v(c, cx, y, y-6*mm)
    y -= 6*mm

    diamond(c, cx, y-dh, 48*mm, dh, fill=YELLOW, stroke=ORANGE)
    txt(c, cx, y-dh, "Fault details\ncomplete?", size=7.5, bold=True)
    y -= 2*dh

    cl_y = y + dh
    arrow_h(c, cx+48*mm, cx+76*mm, cl_y, "NO")
    box(c, cx+76*mm, cl_y-bhs, bws, bhs, fill=LORANGE, stroke=ORANGE)
    txt(c, cx+76*mm+bws/2, cl_y-bhs/2+1, "Ask clarification", size=7.5, bold=True)
    txt(c, cx+76*mm+bws/2, cl_y-bhs/2-4, '"Which machine is affected?"', size=6)

    arrow_v(c, cx, y, y-6*mm, "YES")
    y -= 6*mm

    # ── KNOWLEDGE + TRIAGE ───────────────────────────────────────────────────
    section_band(c, y, "KNOWLEDGE AGENT → TRIAGE AGENT", fill=LPURPLE, stroke=PURPLE)
    y -= 8*mm
    y = step("Knowledge Agent — ChromaDB vector search",
             "Embed query  ·  Cosine similarity  ·  Top-3 SOP/manual snippets", LPURPLE, PURPLE, y)
    arrow_v(c, cx, y, y-6*mm)
    y -= 6*mm
    y = step("Triage Agent — Rule-based + LLM validation",
             "P0 keywords: stopped/fire/sparks  ·  P1: leak/overheat  ·  P2: default  ·  SLA stamped", LPURPLE, PURPLE, y)
    arrow_v(c, cx, y, y-6*mm)
    y -= 6*mm

    # Priority split
    p_y = y
    for i, (px, lbl, fill, stroke) in enumerate([
        (cx-55*mm, "P0\nImmediate", PINK, RED),
        (cx,       "P1\nScheduled", LORANGE, ORANGE),
        (cx+55*mm, "P2\nAnytime",   LGREEN,  GREEN),
    ]):
        box(c, px-22*mm, p_y-bh, 44*mm, bh, fill=fill, stroke=stroke, lw=1.4)
        txt(c, px, p_y-bh/2+1, lbl, size=8, bold=True)
    arrow_v(c, cx-55*mm, y, y-6*mm)
    arrow_v(c, cx,       y, y-6*mm)
    arrow_v(c, cx+55*mm, y, y-6*mm)
    y -= bh + 6*mm

    # ── DISPATCH ─────────────────────────────────────────────────────────────
    section_band(c, y, "DISPATCH AGENT — Technician Assignment", fill=LGREEN, stroke=GREEN)
    y -= 8*mm
    y = step("find_technician()  — SQL query",
             "trade match  ·  fewest active jobs  ·  highest reward_score  ·  on_shift=TRUE", LGREEN, GREEN, y)
    arrow_v(c, cx, y, y-6*mm)
    y -= 6*mm

    diamond(c, cx, y-dh, 46*mm, dh, fill=YELLOW, stroke=ORANGE)
    txt(c, cx, y-dh, "Priority\n= P0?", size=7.5, bold=True)
    y -= 2*dh

    p0_y = y + dh
    arrow_h(c, cx+46*mm, cx+72*mm, p0_y, "YES — P0 preempt")
    box(c, cx+72*mm, p0_y-bhs, bws, bhs, fill=PINK, stroke=RED)
    txt(c, cx+72*mm+bws/2, p0_y-bhs/2+1, "pause_active_job()", size=7.5, bold=True)
    txt(c, cx+72*mm+bws/2, p0_y-bhs/2-4, "assignment.paused_at = NOW()", size=6)

    arrow_v(c, cx, y, y-6*mm, "Create assignment")
    y -= 6*mm
    y = step("INSERT assignment  +  UPDATE work_order status=Assigned",
             "Send WA to tech:  🚨 NEW WORK ORDER  [✅ ACKNOWLEDGE]  [📍 ON SITE]", LGREEN, GREEN, y)

    # ── P0 ESCALATION ────────────────────────────────────────────────────────
    y -= 8*mm
    section_band(c, y, "P0 ESCALATION LADDER  (APScheduler one-shot, 5-min countdown)", fill=PINK, stroke=RED)
    y -= 8*mm

    diamond(c, cx, y-dh, 52*mm, dh, fill=YELLOW, stroke=ORANGE)
    txt(c, cx, y-dh, "Acknowledged\nwithin 5 min?", size=7.5, bold=True)
    y -= 2*dh

    ack_y = y + dh
    arrow_h(c, cx-52*mm, cx-82*mm, ack_y, "YES", right=False)
    box(c, cx-82*mm-bws, ack_y-bhs, bws, bhs, fill=LGREEN, stroke=GREEN)
    txt(c, cx-82*mm-bws/2, ack_y-bhs/2+1, "assignment.acknowledged_at = NOW()", size=6.5, bold=True)
    txt(c, cx-82*mm-bws/2, ack_y-bhs/2-4, "Continue job lifecycle →", size=6)

    arrow_v(c, cx, y, y-6*mm, "NO — re-route")
    y -= 6*mm
    y = step("Mark assignment abandoned  →  find_next_technician()",
             "⚡ ESCALATED P0 dispatched to next tech  ·  Restart 5-min countdown", PINK, RED, y)
    arrow_v(c, cx, y, y-6*mm)
    y -= 6*mm

    # ── COMPLETION & REWARD ───────────────────────────────────────────────────
    section_band(c, y, "JOB LIFECYCLE  →  REWARD LOOP", fill=LGREEN, stroke=GREEN)
    y -= 8*mm
    y = step("Tech taps ON SITE → DONE  (WhatsApp buttons)",
             "arrived_at  ·  completed_at  ·  work_order.status = Completed", LGREEN, GREEN, y)
    arrow_v(c, cx, y, y-6*mm)
    y -= 6*mm
    y = step("Reward score delta: base(3) + urgency + quality + speed + volume  →  clamped [0,10]",
             "UPDATE technician SET reward_score += delta", LGREEN, GREEN, y, w=bw+20*mm)
    arrow_v(c, cx, y, y-6*mm)
    y -= 6*mm
    y = step('Notify requester: "Rate 1-5: WO-XXX 5"  →  INSERT feedback  →  UPDATE reward',
             "Rating Gate clears  ·  Next request allowed", LBLUE, BLUE, y, w=bw+20*mm)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def generate():
    path = OUTPUT / "flow_map.pdf"
    c = canvas.Canvas(str(path), pagesize=A3)
    c.setTitle("RT Knits CMMS — Flow Map")

    # Page 1
    c.setFillColor(LGREY)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    page1(c)
    c.showPage()

    # Page 2
    c.setFillColor(LGREY)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    page2(c)

    c.save()
    print(f"  ✓  flow_map.pdf  →  {path}")
    return path


if __name__ == "__main__":
    generate()
