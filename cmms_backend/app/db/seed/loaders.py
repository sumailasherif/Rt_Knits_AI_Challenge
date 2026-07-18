"""
Excel → plain Python dict parsers.
Each loader returns typed dicts ready to be passed to writers.py.

Column name matching is case-insensitive and whitespace-tolerant to handle
real-world spreadsheet inconsistencies.
"""
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

# Namespace constants for deterministic UUIDs
NS_DEPT = "rtknits.department"
NS_ASSET = "rtknits.asset"
NS_TECH = "rtknits.technician"
NS_REQUESTER = "rtknits.requester"
NS_REQUEST = "rtknits.task_request"
NS_WO = "rtknits.work_order"


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase, strip, and replace spaces with underscores in column names."""
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df


def _col(df: pd.DataFrame, *candidates: str) -> pd.Series | None:
    """Return the first matching column series, or None if none found."""
    for c in candidates:
        if c in df.columns:
            return df[c]
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Assets.xlsx  →  departments + assets
# ─────────────────────────────────────────────────────────────────────────────

def load_assets_xlsx(path: Path) -> tuple[list[dict], list[dict]]:
    """
    Returns (departments, assets).

    Expected columns (flexible matching):
        Asset Name / Name
        Category / Type
        Department / Dept
        Location
        Model Number / Model
        Serial Number / Serial
        Required Trade / Trade
        Is Critical / Critical
        Notes
    """
    df = _normalise_columns(pd.read_excel(path, engine="openpyxl"))
    log.debug("assets_xlsx_columns", columns=list(df.columns))

    departments: dict[str, dict] = {}
    assets: list[dict] = []

    for _, row in df.iterrows():
        name = clean_str(_col(df, "asset_name", "name", "asset").iloc[row.name] if _col(df, "asset_name", "name", "asset") is not None else None)
        if not name:
            continue

        dept_name = clean_str(
            _col(df, "department", "dept", "department_name").iloc[row.name]
            if _col(df, "department", "dept", "department_name") is not None else None
        ) or "General"

        # Build department record (deduplicated by name)
        dept_id = deterministic_uuid(NS_DEPT, dept_name)
        if dept_id not in departments:
            departments[dept_id] = {
                "dept_id": dept_id,
                "name": dept_name,
                "location": None,
                "description": None,
            }

        serial = clean_str(
            _col(df, "serial_number", "serial", "serial_no").iloc[row.name]
            if _col(df, "serial_number", "serial", "serial_no") is not None else None
        )
        asset_key = serial if serial else name
        asset_id = deterministic_uuid(NS_ASSET, asset_key)

        category = clean_str(
            _col(df, "category", "type", "asset_type").iloc[row.name]
            if _col(df, "category", "type", "asset_type") is not None else None
        )
        trade_col = _col(df, "required_trade", "trade", "required_trade")
        required_trade = normalise_trade(trade_col.iloc[row.name] if trade_col is not None else None)

        critical_col = _col(df, "is_critical", "critical")
        is_critical = False
        if critical_col is not None:
            val = str(critical_col.iloc[row.name]).lower().strip()
            is_critical = val in ("yes", "true", "1", "y")

        assets.append({
            "asset_id": asset_id,
            "name": name,
            "category": category,
            "model_number": clean_str(
                _col(df, "model_number", "model").iloc[row.name]
                if _col(df, "model_number", "model") is not None else None
            ),
            "serial_number": serial,
            "location": clean_str(
                _col(df, "location").iloc[row.name]
                if _col(df, "location") is not None else None
            ),
            "dept_id": dept_id,
            "required_trade": required_trade,
            "is_critical": is_critical,
            "notes": clean_str(
                _col(df, "notes", "note", "remarks").iloc[row.name]
                if _col(df, "notes", "note", "remarks") is not None else None
            ),
        })

    log.info("assets_loaded", departments=len(departments), assets=len(assets))
    return list(departments.values()), assets


# ─────────────────────────────────────────────────────────────────────────────
# Technicians.xlsx  →  technicians
# ─────────────────────────────────────────────────────────────────────────────

def load_technicians_xlsx(path: Path) -> list[dict]:
    """
    Expected columns (flexible matching):
        Name / Technician Name
        Trade
        Pool / Team
        Phone / Phone Number / WhatsApp
        On Shift / Shift
        Max Jobs / Max Concurrent
    """
    df = _normalise_columns(pd.read_excel(path, engine="openpyxl"))
    log.debug("technicians_xlsx_columns", columns=list(df.columns))

    technicians: list[dict] = []

    for _, row in df.iterrows():
        name = clean_str(
            _col(df, "name", "technician_name", "tech_name").iloc[row.name]
            if _col(df, "name", "technician_name", "tech_name") is not None else None
        )
        if not name:
            continue

        phone_raw = _col(df, "phone", "phone_number", "whatsapp", "contact")
        phone = normalise_phone(
            phone_raw.iloc[row.name] if phone_raw is not None else None
        )
        # If no real phone, generate a placeholder so uniqueness constraint passes
        if not phone:
            phone = f"+2300000{len(technicians):04d}"

        trade_col = _col(df, "trade", "skill", "specialization")
        pool_col = _col(df, "pool", "team", "group")
        shift_col = _col(df, "on_shift", "shift", "is_on_shift")
        maxjob_col = _col(df, "max_jobs", "max_concurrent", "max_concurrent_jobs")

        on_shift = False
        if shift_col is not None:
            val = str(shift_col.iloc[row.name]).lower().strip()
            on_shift = val in ("yes", "true", "1", "y", "on")

        tech_id = deterministic_uuid(NS_TECH, name + (phone or ""))

        technicians.append({
            "tech_id": tech_id,
            "name": name,
            "trade": normalise_trade(trade_col.iloc[row.name] if trade_col is not None else None),
            "pool": normalise_pool(pool_col.iloc[row.name] if pool_col is not None else None),
            "phone_number": phone,
            "on_shift": on_shift,
            "is_active": True,
            "reward_score": safe_float(
                _col(df, "reward_score", "score").iloc[row.name]
                if _col(df, "reward_score", "score") is not None else 0.0
            ),
            "max_concurrent_jobs": safe_int(
                maxjob_col.iloc[row.name] if maxjob_col is not None else 2, default=2
            ),
        })

    log.info("technicians_loaded", count=len(technicians))
    return technicians


# ─────────────────────────────────────────────────────────────────────────────
# Tasks.xlsx  →  requesters + task_requests + work_orders
# ─────────────────────────────────────────────────────────────────────────────

def load_tasks_xlsx(
    path: Path,
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Expected columns (flexible matching):
        Requester / Reporter / Submitted By / Name
        Phone / Requester Phone
        Department / Dept
        Asset / Asset Name / Machine
        Description / Fault / Issue / Raw Text
        Priority
        Status
        Created At / Date / Timestamp
        Estimated Minutes / Duration
    """
    df = _normalise_columns(pd.read_excel(path, engine="openpyxl"))
    log.debug("tasks_xlsx_columns", columns=list(df.columns))

    requesters: dict[str, dict] = {}
    task_requests: list[dict] = []
    work_orders: list[dict] = []

    for idx, row in df.iterrows():
        # ── Requester ─────────────────────────────────────────────────────────
        req_name_col = _col(df, "requester", "reporter", "submitted_by", "name", "requested_by")
        req_name = clean_str(req_name_col.iloc[row.name] if req_name_col is not None else None) or f"Worker_{idx}"

        phone_col = _col(df, "phone", "requester_phone", "contact", "whatsapp")
        phone = normalise_phone(phone_col.iloc[row.name] if phone_col is not None else None)
        if not phone:
            phone = f"+2301111{idx:04d}"

        dept_col = _col(df, "department", "dept", "department_name")
        dept_name = clean_str(dept_col.iloc[row.name] if dept_col is not None else None) or "General"
        dept_id = deterministic_uuid(NS_DEPT, dept_name)

        requester_id = deterministic_uuid(NS_REQUESTER, phone)
        if requester_id not in requesters:
            requesters[requester_id] = {
                "requester_id": requester_id,
                "name": req_name,
                "phone_number": phone,
                "language": "en",
                "dept_id": dept_id,
                "is_active": True,
            }

        # ── Asset linkage (best-effort by name) ──────────────────────────────
        asset_col = _col(df, "asset", "asset_name", "machine", "equipment")
        asset_name = clean_str(asset_col.iloc[row.name] if asset_col is not None else None)
        asset_id = deterministic_uuid(NS_ASSET, asset_name) if asset_name else None

        # ── Description ───────────────────────────────────────────────────────
        desc_col = _col(df, "description", "fault", "issue", "raw_text", "complaint", "details")
        raw_text = clean_str(desc_col.iloc[row.name] if desc_col is not None else None)

        # ── Timestamps ────────────────────────────────────────────────────────
        date_col = _col(df, "created_at", "date", "timestamp", "reported_at", "created_date")
        created_at = datetime.now(timezone.utc)
        if date_col is not None:
            raw_date = date_col.iloc[row.name]
            if pd.notna(raw_date):
                try:
                    created_at = pd.to_datetime(raw_date, utc=True).to_pydatetime()
                except Exception:
                    pass

        # ── Priority & Status ─────────────────────────────────────────────────
        priority_col = _col(df, "priority")
        status_col = _col(df, "status", "wo_status", "state")
        priority = normalise_priority(priority_col.iloc[row.name] if priority_col is not None else "P2")
        status = normalise_status(status_col.iloc[row.name] if status_col is not None else "Open")

        # ── Task Request ──────────────────────────────────────────────────────
        request_id = deterministic_uuid(NS_REQUEST, f"{requester_id}_{idx}")
        task_requests.append({
            "request_id": request_id,
            "requester_id": requester_id,
            "asset_id": asset_id,
            "raw_text": raw_text,
            "photo_url": None,
            "audio_transcription": None,
            "structured_fault": None,
            "whatsapp_message_id": None,
            "created_at": created_at,
        })

        # ── Work Order ────────────────────────────────────────────────────────
        est_col = _col(df, "estimated_minutes", "duration", "est_minutes", "time_minutes")
        estimated_minutes = safe_int(
            est_col.iloc[row.name] if est_col is not None else 60, default=60
        )

        wo_id = deterministic_uuid(NS_WO, request_id)
        work_orders.append({
            "wo_id": wo_id,
            "request_id": request_id,
            "asset_id": asset_id,
            "priority": priority,
            "status": status,
            "description": raw_text,
            "required_trade": None,  # will be set by Triage Agent on live requests
            "assigned_techs": [],
            "estimated_minutes": estimated_minutes,
            "created_at": created_at,
            "closed_at": created_at if status == "Completed" else None,
            "sla_due_at": None,
        })

    log.info(
        "tasks_loaded",
        requesters=len(requesters),
        task_requests=len(task_requests),
        work_orders=len(work_orders),
    )
    return list(requesters.values()), task_requests, work_orders
