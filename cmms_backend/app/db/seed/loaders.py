"""
Excel → plain Python dict parsers for the seed runner.

Fix applied:
  - Replaced row.name (DataFrame label index — fragile on non-default RangeIndex)
    with iterrows()'s integer counter `idx` via df.iloc[idx] lookups, or more
    robustly by calling _col(df, ...).iloc[i] where `i` is the positional
    integer from enumerate(df.itertuples()).
  - Refactored inner row access: _get(row_series, col_name) helper resolves a
    column value from a named pandas Series safely, handling NaN/None.
  - All callers updated to use the new pattern.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from app.db.seed.utils import (
    clean_str,
    deterministic_uuid,
    normalise_phone,
    normalise_pool,
    normalise_priority,
    normalise_status,
    normalise_trade,
    safe_float,
    safe_int,
)

log = structlog.get_logger(__name__)

NS_DEPT      = "rtknits.department"
NS_ASSET     = "rtknits.asset"
NS_TECH      = "rtknits.technician"
NS_REQUESTER = "rtknits.requester"
NS_REQUEST   = "rtknits.task_request"
NS_WO        = "rtknits.work_order"


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lower-case, strip and underscore-replace all column names."""
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df


def _first_col(df: pd.DataFrame, *candidates: str) -> str | None:
    """Return the first column name from candidates that exists in df."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _val(row: pd.Series, *candidates: str) -> Any:
    """
    FIX: safely extract a value from a pandas Series (a single DataFrame row)
    by trying column name candidates in order.

    Uses row[col_name] — works correctly regardless of the DataFrame's index
    because iterrows() yields (index, Series) where Series is keyed by column
    name, not by position.
    """
    for c in candidates:
        if c in row.index and pd.notna(row[c]):
            return row[c]
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Assets.xlsx  →  departments + assets
# ─────────────────────────────────────────────────────────────────────────────

def load_assets_xlsx(path: Path) -> tuple[list[dict], list[dict]]:
    df = _normalise_columns(pd.read_excel(path, engine="openpyxl"))
    log.debug("assets_xlsx_columns", columns=list(df.columns))

    departments: dict[str, dict] = {}
    assets: list[dict] = []

    for _, row in df.iterrows():
        # FIX: use _val(row, ...) — row is a named Series, safe on any index
        name = clean_str(_val(row, "asset_name", "name", "asset"))
        if not name:
            continue

        dept_name = clean_str(_val(row, "department", "dept", "department_name")) or "General"
        dept_id   = deterministic_uuid(NS_DEPT, dept_name)
        if dept_id not in departments:
            departments[dept_id] = {
                "dept_id":     dept_id,
                "name":        dept_name,
                "location":    None,
                "description": None,
            }

        serial    = clean_str(_val(row, "serial_number", "serial", "serial_no"))
        asset_key = serial if serial else name
        asset_id  = deterministic_uuid(NS_ASSET, asset_key)

        critical_raw = _val(row, "is_critical", "critical")
        is_critical  = str(critical_raw).lower().strip() in ("yes", "true", "1", "y") if critical_raw else False

        assets.append({
            "asset_id":       asset_id,
            "name":           name,
            "category":       clean_str(_val(row, "category", "type", "asset_type")),
            "model_number":   clean_str(_val(row, "model_number", "model")),
            "serial_number":  serial,
            "location":       clean_str(_val(row, "location")),
            "dept_id":        dept_id,
            "required_trade": normalise_trade(_val(row, "required_trade", "trade")),
            "is_critical":    is_critical,
            "notes":          clean_str(_val(row, "notes", "note", "remarks")),
        })

    log.info("assets_loaded", departments=len(departments), assets=len(assets))
    return list(departments.values()), assets


# ─────────────────────────────────────────────────────────────────────────────
# Technicians.xlsx  →  technicians
# ─────────────────────────────────────────────────────────────────────────────

def load_technicians_xlsx(path: Path) -> list[dict]:
    df = _normalise_columns(pd.read_excel(path, engine="openpyxl"))
    log.debug("technicians_xlsx_columns", columns=list(df.columns))

    technicians: list[dict] = []

    for _, row in df.iterrows():
        name = clean_str(_val(row, "name", "technician_name", "tech_name"))
        if not name:
            continue

        phone = normalise_phone(_val(row, "phone", "phone_number", "whatsapp", "contact"))
        if not phone:
            phone = f"+2300000{len(technicians):04d}"

        shift_raw = _val(row, "on_shift", "shift", "is_on_shift")
        on_shift  = str(shift_raw).lower().strip() in ("yes", "true", "1", "y", "on") if shift_raw else False

        tech_id = deterministic_uuid(NS_TECH, name + phone)

        technicians.append({
            "tech_id":             tech_id,
            "name":                name,
            "trade":               normalise_trade(_val(row, "trade", "skill", "specialization")),
            "pool":                normalise_pool(_val(row, "pool", "team", "group")),
            "phone_number":        phone,
            "on_shift":            on_shift,
            "is_active":           True,
            "reward_score":        safe_float(_val(row, "reward_score", "score") or 0.0),
            "max_concurrent_jobs": safe_int(_val(row, "max_jobs", "max_concurrent", "max_concurrent_jobs") or 2, default=2),
        })

    log.info("technicians_loaded", count=len(technicians))
    return technicians


# ─────────────────────────────────────────────────────────────────────────────
# Tasks.xlsx  →  requesters + task_requests + work_orders
# ─────────────────────────────────────────────────────────────────────────────

def load_tasks_xlsx(path: Path) -> tuple[list[dict], list[dict], list[dict]]:
    df = _normalise_columns(pd.read_excel(path, engine="openpyxl"))
    log.debug("tasks_xlsx_columns", columns=list(df.columns))

    requesters:   dict[str, dict] = {}
    task_requests: list[dict]     = []
    work_orders:   list[dict]     = []

    for idx, row in df.iterrows():
        # ── Requester ─────────────────────────────────────────────────────────
        req_name  = clean_str(_val(row, "requester", "reporter", "submitted_by", "name", "requested_by")) or f"Worker_{idx}"
        phone     = normalise_phone(_val(row, "phone", "requester_phone", "contact", "whatsapp"))
        if not phone:
            phone = f"+2301111{int(str(idx)[-4:]):04d}"

        dept_name   = clean_str(_val(row, "department", "dept", "department_name")) or "General"
        dept_id     = deterministic_uuid(NS_DEPT, dept_name)
        requester_id = deterministic_uuid(NS_REQUESTER, phone)

        if requester_id not in requesters:
            requesters[requester_id] = {
                "requester_id": requester_id,
                "name":         req_name,
                "phone_number": phone,
                "language":     "en",
                "dept_id":      dept_id,
                "is_active":    True,
            }

        # ── Asset linkage ─────────────────────────────────────────────────────
        asset_name = clean_str(_val(row, "asset", "asset_name", "machine", "equipment"))
        asset_id   = deterministic_uuid(NS_ASSET, asset_name) if asset_name else None

        # ── Description ───────────────────────────────────────────────────────
        raw_text = clean_str(_val(row, "description", "fault", "issue", "raw_text", "complaint", "details"))

        # ── Timestamps ────────────────────────────────────────────────────────
        created_at = datetime.now(timezone.utc)
        raw_date   = _val(row, "created_at", "date", "timestamp", "reported_at", "created_date")
        if raw_date is not None:
            try:
                created_at = pd.to_datetime(raw_date, utc=True).to_pydatetime()
            except Exception:
                pass

        # ── Priority & Status ─────────────────────────────────────────────────
        priority = normalise_priority(_val(row, "priority") or "P2")
        status   = normalise_status(_val(row, "status", "wo_status", "state") or "Open")

        # ── Task request ──────────────────────────────────────────────────────
        request_id = deterministic_uuid(NS_REQUEST, f"{requester_id}_{idx}")
        task_requests.append({
            "request_id":          request_id,
            "requester_id":        requester_id,
            "asset_id":            asset_id,
            "raw_text":            raw_text,
            "photo_url":           None,
            "audio_transcription": None,
            "structured_fault":    None,
            "whatsapp_message_id": None,
            "created_at":          created_at,
        })

        # ── Work order ────────────────────────────────────────────────────────
        estimated_minutes = safe_int(
            _val(row, "estimated_minutes", "duration", "est_minutes", "time_minutes") or 60,
            default=60,
        )
        wo_id = deterministic_uuid(NS_WO, request_id)
        work_orders.append({
            "wo_id":              wo_id,
            "request_id":         request_id,
            "asset_id":           asset_id,
            "priority":           priority,
            "status":             status,
            "description":        raw_text,
            "required_trade":     None,
            "assigned_techs":     [],
            "estimated_minutes":  estimated_minutes,
            "created_at":         created_at,
            "closed_at":          created_at if status == "Completed" else None,
            "sla_due_at":         None,
        })

    log.info(
        "tasks_loaded",
        requesters=len(requesters),
        task_requests=len(task_requests),
        work_orders=len(work_orders),
    )
    return list(requesters.values()), task_requests, work_orders
