"""
API Map Diagram — docs/output/api_map.pdf
All 7 routers, every endpoint, HTTP method badge, path, and description.
Portrait A3, grouped by router with colour-coded method badges.
CBBR-NATEC Innovation Cup 2026
"""
from __future__ import annotations
from pathlib import Path
from reportlab.lib.pagesizes import A3
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor

OUTPUT = Path(__file__).parent.parent / "output"
OUTPUT.mkdir(parents=True, exist_ok=True)

# ── Palette ───────────────────────────────────────────────────────────────────
NAVY    = HexColor("#0D1B2A")
WHITE   = HexColor("#FFFFFF")
BLACK   = HexColor("#000000")
LGREY   = HexColor("#F2F3F4")
MGREY   = HexColor("#BDC3C7")
DGREY   = HexColor("#7F8C8D")

# Method badge colours (matching OpenAPI convention)
M_GET    = HexColor("#27AE60")   # green
M_POST   = HexColor("#2980B9")   # blue
M_PATCH  = HexColor("#E67E22")   # orange
M_DELETE = HexColor("#C0392B")   # red

# Router accent colours
R_WEBHOOK   = HexColor("#1B6CA8")
R_WO        = HexColor("#C0392B")
R_TECH      = HexColor("#1E8449")
R_PLANNING  = HexColor("#7D3C98")
R_ANALYTICS = HexColor("#17A589")
R_KNOWLEDGE = HexColor("#E67E22")
R_ASSETS    = HexColor("#2C3E50")
R_SYSTEM    = HexColor("#626567")

W, H = A3        # portrait 297 × 420 mm
PAD  = 12 * mm
COL_W = (W - 2 * PAD - 6 * mm) / 2   # two-column layout

METHOD_COLORS = {
    "GET":    M_GET,
    "POST":   M_POST,
    "PATCH":  M_PATCH,
    "DELETE": M_DELETE,
}

# ── Router data ───────────────────────────────────────────────────────────────
# Each entry: (accent, router_tag, prefix, description, [endpoints])
# Endpoint: (method, path_suffix, short_description, auth_note)
ROUTERS = [
    (
        R_WEBHOOK,
        "WhatsApp Webhook",
        "/webhook",
        "Meta Cloud API integration — inbound message processing & hub verification",
        [
            ("GET",   "",        "Meta hub verification (one-time setup)",        "hub_verify_token"),
            ("POST",  "",        "Receive & process inbound WhatsApp messages",   "HMAC-SHA256"),
        ],
    ),
    (
        R_WO,
        "Work Orders",
        "/api/v1/work-orders",
        "Full CRUD for work orders and their assignments",
        [
            ("GET",   "",                           "List work orders (filter: status, priority)",  "limit/offset"),
            ("POST",  "",                           "Create a new work order manually",             "WorkOrderCreate"),
            ("GET",   "/{wo_id}",                   "Get work order by ID (incl. feedback rating)", ""),
            ("PATCH", "/{wo_id}",                   "Update work order fields",                     "WorkOrderUpdate"),
            ("GET",   "/{wo_id}/assignments",       "List all assignments for a work order",        ""),
            ("PATCH", "/{wo_id}/assignments/{a_id}","Update assignment (arrived/completed etc.)",   "triggers reward"),
        ],
    ),
    (
        R_TECH,
        "Technicians",
        "/api/v1/technicians",
        "CRUD for technicians, shift management, and reward score tracking",
        [
            ("GET",   "",                   "List active technicians (filter: on_shift, trade)", "active_jobs count"),
            ("POST",  "",                   "Register a new technician",                        "TechnicianCreate"),
            ("GET",   "/{tech_id}",         "Get technician by ID",                             ""),
            ("PATCH", "/{tech_id}",         "Update technician profile",                        "TechnicianUpdate"),
            ("POST",  "/{tech_id}/shift-on","Mark technician as on-shift",                      ""),
            ("POST",  "/{tech_id}/shift-off","Mark technician as off-shift",                    ""),
        ],
    ),
    (
        R_PLANNING,
        "Planning",
        "/api/v1/planning",
        "Nightly batch planning (Loop 1) — trigger, list, and patch daily plans",
        [
            ("POST",  "/trigger",              "Manually trigger nightly planning loop",         "plan_date, force"),
            ("GET",   "/plans",                "List daily plans (filter: plan_date, tech_id)",  ""),
            ("PATCH", "/plans/{plan_id}",      "Update a plan (confirm / conflict note)",        "DailyPlanUpdate"),
            ("POST",  "/technician-reply",     "Record technician conflict note for re-balance", "plan_id, tech_id"),
        ],
    ),
    (
        R_ANALYTICS,
        "Analytics",
        "/api/v1/analytics",
        "KPI reports, technician performance, asset failure patterns, SLA compliance",
        [
            ("GET", "/kpi",         "KPI dashboard summary (totals, avg resolution, SLA)", "date_from/to, dept_id"),
            ("GET", "/technicians", "Per-technician performance (jobs, duration, rating)",  "date_from/to"),
            ("GET", "/assets",      "Asset failure heatmap (count, most common trade)",     "date_from/to, dept_id"),
            ("GET", "/sla",         "SLA compliance report",                                "date_from/to"),
            ("GET", "/summary",     "Natural-language WhatsApp-style summary (GPT-4o)",     "date_from/to"),
        ],
    ),
    (
        R_KNOWLEDGE,
        "Knowledge",
        "/api/v1/knowledge",
        "Semantic document search and ingestion — ChromaDB + OpenAI embeddings",
        [
            ("POST", "/search", "Vector semantic search over SOPs / manuals / history", "KnowledgeInput"),
            ("POST", "/docs",   "Ingest new document: embed → ChromaDB + PostgreSQL",   "KnowledgeDocCreate"),
            ("GET",  "/docs",   "List all knowledge_doc records",                        ""),
        ],
    ),
    (
        R_ASSETS,
        "Assets",
        "/api/v1/assets",
        "Factory asset CRUD — equipment register with trade and criticality",
        [
            ("GET",   "",            "List assets (filter: dept_id, category)", ""),
            ("POST",  "",            "Register a new asset",                    "AssetCreate"),
            ("GET",   "/{asset_id}", "Get asset by ID",                         ""),
            ("PATCH", "/{asset_id}", "Update asset details",                    "AssetUpdate"),
        ],
    ),
    (
        R_SYSTEM,
        "System",
        "/",
        "Health check and root endpoints",
        [
            ("GET", "health", "DB connectivity check + version + env", ""),
            ("GET", "/",      "API name, docs URL, health URL",         ""),
        ],
    ),
]


# ── Drawing helpers ───────────────────────────────────────────────────────────

def rr(c, x, y, w, h, fill=WHITE, stroke=MGREY, lw=0.8, r=2 * mm):
    c.saveState()
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(lw)
    c.roundRect(x, y, w, h, r, fill=1, stroke=1)
    c.restoreState()


def method_badge(c, x, y, method):
    col = METHOD_COLORS.get(method, MGREY)
    bw = 13 * mm
    bh = 4.5 * mm
    c.setFillColor(col)
    c.roundRect(x, y, bw, bh, 1 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(x + bw / 2, y + 1.4 * mm, method)


def draw_router_card(c, x, y_top, w, router_data):
    """Draw one router group card. Returns the y position after the card."""
    accent, tag, prefix, desc, endpoints = router_data

    row_h   = 7 * mm
    hdr_h   = 13 * mm
    total_h = hdr_h + len(endpoints) * row_h + 3 * mm

    # Card shadow
    c.setFillColor(HexColor("#D0D0D0"))
    c.roundRect(x + 1.5, y_top - total_h - 1.5, w, total_h, 2.5 * mm, fill=1, stroke=0)

    # Card body
    rr(c, x, y_top - total_h, w, total_h, fill=WHITE, stroke=accent, lw=1.4)

    # Header band
    c.setFillColor(accent)
    c.roundRect(x, y_top - hdr_h, w, hdr_h, 2.5 * mm, fill=1, stroke=0)
    c.rect(x, y_top - hdr_h, w, hdr_h / 2, fill=1, stroke=0)

    # Tag + prefix
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + 4 * mm, y_top - 6 * mm, tag)
    c.setFont("Helvetica", 7)
    c.drawString(x + 4 * mm, y_top - 10.5 * mm, prefix)
    # Description (right-aligned, truncated)
    desc_display = desc if len(desc) <= 52 else desc[:49] + "…"
    c.setFont("Helvetica", 6.5)
    c.setFillColor(HexColor("#D6EAF8"))
    c.drawRightString(x + w - 4 * mm, y_top - 10 * mm, desc_display)

    # Endpoint rows
    for i, (method, path_sfx, edesc, note) in enumerate(endpoints):
        ry = y_top - hdr_h - (i + 1) * row_h
        # Alternating row background
        bg = HexColor("#FAFAFA") if i % 2 == 0 else WHITE
        c.setFillColor(bg)
        c.rect(x + 1, ry, w - 2, row_h - 0.5, fill=1, stroke=0)
        # Separator
        c.setStrokeColor(HexColor("#ECECEC"))
        c.setLineWidth(0.4)
        c.line(x + 1, ry + row_h - 0.5, x + w - 1, ry + row_h - 0.5)

        # Method badge
        method_badge(c, x + 3 * mm, ry + 1.25 * mm, method)

        # Path suffix
        c.setFillColor(BLACK)
        c.setFont("Helvetica-Bold", 6.8)
        path_display = (prefix + path_sfx) if path_sfx else prefix
        c.drawString(x + 18 * mm, ry + 2.2 * mm, path_display)

        # Description
        c.setFont("Helvetica", 6.2)
        c.setFillColor(HexColor("#2C3E50"))
        c.drawString(x + 18 * mm, ry + row_h - 4.2 * mm, edesc)

        # Note badge (right side)
        if note:
            note_col = HexColor("#1A5276")
            nw = min(len(note) * 3.5 + 6, 55 * mm)
            c.setFillColor(note_col)
            c.roundRect(x + w - nw - 3 * mm, ry + 1.5 * mm, nw, 4 * mm, 0.8 * mm, fill=1, stroke=0)
            c.setFillColor(WHITE)
            c.setFont("Helvetica", 5.2)
            c.drawRightString(x + w - 3 * mm - 1 * mm, ry + 2.5 * mm, note)

    return y_top - total_h - 5 * mm


def generate():
    path = OUTPUT / "api_map.pdf"
    c = canvas.Canvas(str(path), pagesize=A3)
    c.setTitle("RT Knits CMMS — API Map")

    # Background
    c.setFillColor(LGREY)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # ── Title bar ─────────────────────────────────────────────────────────────
    c.setFillColor(NAVY)
    c.rect(0, H - 20 * mm, W, 20 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(PAD, H - 13 * mm, "RT Knits Agentic CMMS — REST API Map")
    c.setFont("Helvetica", 9)
    c.drawRightString(W - PAD, H - 13 * mm, "FastAPI · 7 Routers · 27 Endpoints  ·  CBBR-NATEC 2026")

    # Subtitle
    c.setFillColor(BLACK)
    c.setFont("Helvetica", 8)
    c.drawCentredString(W / 2, H - 23 * mm,
        "All routes use /api/v1 prefix (except /webhook and system). "
        "OpenAPI docs available at /docs and /redoc.")

    # ── Two-column layout ─────────────────────────────────────────────────────
    col_gap = 6 * mm
    col1_x  = PAD
    col2_x  = PAD + COL_W + col_gap
    y1      = H - 27 * mm   # left column current y
    y2      = H - 27 * mm   # right column current y

    # Distribute routers across two columns (balance by endpoint count)
    left_routers  = ROUTERS[::2]    # indices 0,2,4,6
    right_routers = ROUTERS[1::2]   # indices 1,3,5,7  (if present, else leftover)

    # Interleave for better visual balance
    left_routers  = [ROUTERS[0], ROUTERS[2], ROUTERS[4], ROUTERS[6]]
    right_routers = [ROUTERS[1], ROUTERS[3], ROUTERS[5], ROUTERS[7]]

    for rd in left_routers:
        y1 = draw_router_card(c, col1_x, y1, COL_W, rd)

    for rd in right_routers:
        y2 = draw_router_card(c, col2_x, y2, COL_W, rd)

    # ── Legend (method badges) ────────────────────────────────────────────────
    lx = PAD
    ly = PAD + 1 * mm
    c.setFillColor(HexColor("#1A1A2E"))
    c.roundRect(lx, ly, 140 * mm, 9 * mm, 2 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(lx + 3 * mm, ly + 2.8 * mm, "HTTP METHODS:")
    for i, (method, col) in enumerate([
        ("GET", M_GET), ("POST", M_POST), ("PATCH", M_PATCH), ("DELETE", M_DELETE)
    ]):
        mx = lx + 33 * mm + i * 26 * mm
        c.setFillColor(col)
        c.roundRect(mx, ly + 2 * mm, 13 * mm, 5 * mm, 1 * mm, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 6.5)
        c.drawCentredString(mx + 6.5 * mm, ly + 3.5 * mm, method)

    c.save()
    print(f"  ✓  api_map.pdf  →  {path}")
    return path


if __name__ == "__main__":
    generate()
