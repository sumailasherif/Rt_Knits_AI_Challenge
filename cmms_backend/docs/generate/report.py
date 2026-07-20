"""
RT Knits CMMS — Full Judge Competition Report
docs/output/RT_Knits_CMMS_Report.pdf

Run:  python -m docs.generate.report
      (from cmms_backend/ with reportlab installed)

Requires: pip install reportlab pillow
"""
from __future__ import annotations
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib import colors

OUTPUT = Path(__file__).parent.parent / "output"
OUTPUT.mkdir(parents=True, exist_ok=True)
