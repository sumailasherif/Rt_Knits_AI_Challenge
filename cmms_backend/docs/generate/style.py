"""
Shared premium style constants and drawing helpers.

Design language:
  - Deep navy canvas (#0B1929) — premium dark background
  - Crisp white cards with coloured accent border (3pt left stripe)
  - ALL body text: pure black #000000 for maximum legibility
  - Headers: white text on solid accent-colour banner
  - Accent palette: one colour per layer/section
  - Drop shadows on every card for depth
  - Thick solid connector lines with filled arrowheads
"""
from __future__ import annotations
import math
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, Color

# ── Canvas background ──────────────────────────────────────────────────────────
BG          = HexColor("#0B1929")   # deep navy
BG_ALT      = HexColor("#0F2236")   # slightly lighter navy for alternating bands
CARD_BG     = HexColor("#FFFFFF")   # white card fill
CARD_BORDER = HexColor("#DEE3EA")   # light card stroke

# ── Typography ────────────────────────────────────────────────────────────────
BLACK  = HexColor("#000000")   # ALL body / label text
WHITE  = HexColor("#FFFFFF")   # text on dark header bars
GREY   = HexColor("#4A4A4A")   # secondary body text (still very readable)
LGREY  = HexColor("#888888")   # tertiary / caption

# ── Accent palette (vibrant, clearly distinct) ────────────────────────────────
A_BLUE   = HexColor("#2980F5")   # Layer 1 / Entry
A_GREEN  = HexColor("#27AE60")   # Layer 2 / API
A_ORANGE = HexColor("#F39C12")   # Layer 3 / Orchestrator
A_RED    = HexColor("#E74C3C")   # Layer 4 / Agents
A_PURPLE = HexColor("#8E44AD")   # Layer 5 / Data
A_TEAL   = HexColor("#16A085")   # Supplementary
A_GOLD   = HexColor("#F1C40F")   # PK badge
A_STEEL  = HexColor("#3498DB")   # FK badge

# ── Shadow ────────────────────────────────────────────────────────────────────
SHADOW = HexColor("#000000")


# ── Low-level drawing helpers ─────────────────────────────────────────────────

def fill_background(c: rl_canvas.Canvas, w: float, h: float) -> None:
    """Fill the whole page with BG colour."""
    c.setFillColor(BG)
    c.rect(0, 0, w, h, fill=1, stroke=0)


def title_bar(c: rl_canvas.Canvas, w: float, h: float,
              title: str, subtitle: str,
              accent: "Color" = A_BLUE,
              bar_h: float = 22*mm) -> None:
    """Draw a premium two-tone title bar at the top of the page."""
    # Dark navy backing strip
    c.setFillColor(HexColor("#060F1A"))
    c.rect(0, h - bar_h, w, bar_h, fill=1, stroke=0)

    # Accent left stripe
    c.setFillColor(accent)
    c.rect(0, h - bar_h, 6*mm, bar_h, fill=1, stroke=0)

    # Accent bottom line
    c.setStrokeColor(accent)
    c.setLineWidth(2)
    c.line(0, h - bar_h, w, h - bar_h)

    # Title text
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(10*mm, h - 12*mm, title)

    # Subtitle / badge
    c.setFillColor(accent)
    badge_w = len(subtitle) * 4.5 + 8
    c.roundRect(w - badge_w - 10*mm, h - bar_h + 5*mm, badge_w, 10*mm,
                2*mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(w - badge_w/2 - 10*mm, h - bar_h + 9*mm, subtitle)


def drop_shadow(c: rl_canvas.Canvas, x: float, y: float,
                w: float, h: float, r: float = 3*mm) -> None:
    """Paint a blurred-style drop shadow (layered semi-transparent rects)."""
    for offset, alpha in [(4, 0.08), (3, 0.10), (2, 0.12)]:
        c.saveState()
        c.setFillColor(HexColor("#000000"))
        # ReportLab doesn't do true alpha fills; fake it with dark grey shades
        shade = HexColor(f"#{offset*25:02X}{offset*25:02X}{offset*25:02X}")
        c.setFillColor(shade)
        c.roundRect(x + offset, y - offset, w, h, r, fill=1, stroke=0)
        c.restoreState()


def card(c: rl_canvas.Canvas, x: float, y: float, w: float, h: float,
         accent: "Color" = A_BLUE,
         header_text: str = "",
         header_h: float = 9*mm,
         r: float = 3*mm) -> None:
    """
    Draw a premium card:
      - drop shadow
      - white fill with rounded corners
      - solid accent header band
      - thick left accent stripe
    """
    drop_shadow(c, x, y, w, h, r)

    # White body
    c.setFillColor(CARD_BG)
    c.setStrokeColor(CARD_BORDER)
    c.setLineWidth(0.8)
    c.roundRect(x, y, w, h, r, fill=1, stroke=1)

    # Left accent stripe (3 pt wide)
    c.setFillColor(accent)
    # Draw as a narrow rounded rect to match card corners on left only
    c.rect(x, y, 4, h, fill=1, stroke=0)
    # Re-round the two left corners by drawing BG colour triangles in corners
    c.setFillColor(CARD_BG)
    c.rect(x, y, r, r, fill=1, stroke=0)
    c.rect(x, y + h - r, r, r, fill=1, stroke=0)
    c.setFillColor(accent)
    c.circle(x + r, y + r, r, fill=1, stroke=0)
    c.circle(x + r, y + h - r, r, fill=1, stroke=0)
    c.rect(x, y, r + 4, h, fill=1, stroke=0)

    if header_text:
        # Solid accent header band
        c.setFillColor(accent)
        # Rounded top, flat bottom
        c.roundRect(x, y + h - header_h, w, header_h, r, fill=1, stroke=0)
        c.rect(x, y + h - header_h, w, header_h / 2, fill=1, stroke=0)

        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(x + w / 2, y + h - header_h + 3*mm, header_text)


def connector(c: rl_canvas.Canvas,
              x1: float, y1: float, x2: float, y2: float,
              color: "Color" = A_BLUE,
              dashed: bool = False,
              label: str = "",
              arrow_size: float = 7) -> None:
    """Draw a connector line with arrowhead."""
    c.saveState()
    c.setStrokeColor(color)
    c.setLineWidth(1.8)
    if dashed:
        c.setDash(6, 4)
    c.line(x1, y1, x2, y2)
    c.setDash()

    # Filled arrowhead at (x2, y2)
    dx, dy = x2 - x1, y2 - y1
    length = math.sqrt(dx * dx + dy * dy) or 1
    ux, uy = dx / length, dy / length
    px, py = -uy * arrow_size * 0.45, ux * arrow_size * 0.45
    path = c.beginPath()
    path.moveTo(x2, y2)
    path.lineTo(x2 - ux * arrow_size + px, y2 - uy * arrow_size + py)
    path.lineTo(x2 - ux * arrow_size - px, y2 - uy * arrow_size - py)
    path.close()
    c.setFillColor(color)
    c.drawPath(path, fill=1, stroke=0)

    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        c.setFillColor(color)
        c.setFont("Helvetica-Bold", 6.5)
        c.drawCentredString(mx, my + 3, label)

    c.restoreState()


def legend_bar(c: rl_canvas.Canvas,
               lx: float, ly: float,
               items: list[tuple["Color", str]]) -> None:
    """Draw a horizontal legend row."""
    # Background pill
    total_w = len(items) * 45*mm + 20*mm
    c.setFillColor(HexColor("#111E2E"))
    c.roundRect(lx - 5*mm, ly - 2*mm, total_w, 12*mm, 3*mm, fill=1, stroke=0)

    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(lx, ly + 4*mm, "LEGEND")

    for i, (col, lbl) in enumerate(items):
        ix = lx + 20*mm + i * 45*mm
        c.setFillColor(col)
        c.roundRect(ix, ly + 1.5*mm, 12*mm, 6*mm, 1.5*mm, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica", 7)
        c.drawString(ix + 14*mm, ly + 4*mm, lbl)
