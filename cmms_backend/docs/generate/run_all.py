"""
Master diagram runner — generates all RT Knits CMMS PDFs in one shot.

Usage (from repo root):
    python cmms_backend/docs/generate/run_all.py

Or from the generate/ directory:
    python run_all.py

Outputs (all in docs/output/):
    architecture.pdf   — 5-layer system architecture   (landscape A3)
    data_model.pdf     — 10-table ERD                  (landscape A2)
    agent_flow.pdf     — LangGraph StateGraph flow      (landscape A3)
    api_map.pdf        — REST API map, 27 endpoints     (portrait A3)
    data_flow.pdf      — Pydantic schema data-flow      (landscape A3)
    flow_map.pdf       — Loop 1 + Loop 2 flowcharts     (portrait A3, 2 pages)
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

# Make sure imports resolve whether run from repo root or generate/ dir
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

GENERATORS = [
    ("architecture.pdf",  "arch_diagram",       "generate"),
    ("data_model.pdf",    "erd_diagram",         "generate"),
    ("agent_flow.pdf",    "agent_flow_diagram",  "generate"),
    ("api_map.pdf",       "api_map_diagram",     "generate"),
    ("data_flow.pdf",     "data_flow_diagram",   "generate"),
    ("flow_map.pdf",      "flow_diagram",        "generate"),
]

OUTPUT_DIR = HERE.parent / "output"


def run_all() -> None:
    print()
    print("=" * 62)
    print("  RT Knits Agentic CMMS — Diagram Generator")
    print("  CBBR-NATEC Innovation Cup 2026")
    print("=" * 62)
    print(f"  Output directory: {OUTPUT_DIR}")
    print()

    results: list[tuple[str, bool, float, str]] = []

    for pdf_name, module_name, _pkg in GENERATORS:
        t0 = time.perf_counter()
        try:
            import importlib
            mod = importlib.import_module(module_name)
            importlib.reload(mod)          # force re-run if already imported
            mod.generate()
            elapsed = time.perf_counter() - t0
            results.append((pdf_name, True, elapsed, ""))
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            tb = traceback.format_exc()
            results.append((pdf_name, False, elapsed, tb))
            print(f"  ✗  {pdf_name}  [{elapsed:.2f}s]")
            print(tb)

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("=" * 62)
    print("  SUMMARY")
    print("=" * 62)

    ok  = [r for r in results if r[1]]
    err = [r for r in results if not r[1]]

    for pdf_name, success, elapsed, _ in results:
        status = "✓" if success else "✗"
        size   = ""
        pdf_path = OUTPUT_DIR / pdf_name
        if success and pdf_path.exists():
            kb = pdf_path.stat().st_size / 1024
            size = f"  ({kb:.1f} KB)"
        print(f"  {status}  {pdf_name:<26}  [{elapsed:.2f}s]{size}")

    print()
    print(f"  Generated : {len(ok)}/{len(results)} diagrams")

    if err:
        print(f"  Failed    : {len(err)} — see errors above")
        sys.exit(1)
    else:
        print(f"  All diagrams written to: {OUTPUT_DIR}")
        print()


if __name__ == "__main__":
    run_all()
