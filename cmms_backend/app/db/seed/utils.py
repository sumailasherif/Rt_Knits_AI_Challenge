"""
Utility helpers shared by loaders and writers.
"""
import hashlib
import re
import uuid
from typing import Optional


def deterministic_uuid(namespace: str, value: str) -> str:
    """
    Produce a stable UUID v5 from a namespace string + a source value.
    Re-running with the same inputs always produces the same UUID —
    this makes the seed idempotent.
    """
    ns = uuid.UUID(hashlib.md5(namespace.encode()).hexdigest())
    return str(uuid.uuid5(ns, str(value).strip().lower()))


def normalise_phone(raw: Optional[str], default_country: str = "+230") -> Optional[str]:
    """
    Clean a phone number to E.164 format.
    Strips spaces, dashes, parentheses.
    Prepends default_country code if no country code found.
    Returns None if raw is empty/null.
    """
    if not raw:
        return None
    cleaned = re.sub(r"[\s\-\(\)]+", "", str(raw))
    if not cleaned:
        return None
    # Already has a +country prefix
    if cleaned.startswith("+"):
        return cleaned
    # Has country code without +
    if cleaned.startswith("00"):
        return "+" + cleaned[2:]
    # Mauritius local number (7 or 8 digits)
    return default_country + cleaned


def clean_str(val) -> Optional[str]:
    """Return None for NaN/None/empty, otherwise stripped string."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s and s.lower() not in ("nan", "none", "n/a", "-") else None


def safe_int(val, default: int = 0) -> int:
    try:
        return int(float(str(val)))
    except (ValueError, TypeError):
        return default


def safe_float(val, default: float = 0.0) -> float:
    try:
        return float(str(val))
    except (ValueError, TypeError):
        return default


# Trade name normalisation map — maps common Excel values to our enum
TRADE_MAP: dict[str, str] = {
    "mechanical": "Mechanical",
    "mech": "Mechanical",
    "electrical": "Electrical",
    "elec": "Electrical",
    "civil": "Civil",
    "plumbing": "Plumbing",
    "plumb": "Plumbing",
    "it": "IT",
    "information technology": "IT",
    "general": "General",
    "gen": "General",
}

POOL_MAP: dict[str, str] = {
    "ltktech": "LTKTech",
    "ltk": "LTKTech",
    "dyetech": "DyeTech",
    "dye": "DyeTech",
    "general": "General",
}

PRIORITY_MAP: dict[str, str] = {
    "p0": "P0",
    "0": "P0",
    "immediate": "P0",
    "emergency": "P0",
    "p1": "P1",
    "1": "P1",
    "scheduled": "P1",
    "p2": "P2",
    "2": "P2",
    "anytime": "P2",
    "routine": "P2",
}

STATUS_MAP: dict[str, str] = {
    "open": "Open",
    "queued": "Queued",
    "assigned": "Assigned",
    "inprogress": "InProgress",
    "in progress": "InProgress",
    "in_progress": "InProgress",
    "paused": "Paused",
    "completed": "Completed",
    "done": "Completed",
    "closed": "Completed",
    "cancelled": "Cancelled",
    "canceled": "Cancelled",
}


def normalise_trade(val) -> str:
    s = clean_str(val)
    if not s:
        return "General"
    return TRADE_MAP.get(s.lower(), "General")


def normalise_pool(val) -> str:
    s = clean_str(val)
    if not s:
        return "General"
    return POOL_MAP.get(s.lower(), "General")


def normalise_priority(val) -> str:
    s = clean_str(val)
    if not s:
        return "P2"
    return PRIORITY_MAP.get(s.lower(), "P2")


def normalise_status(val) -> str:
    s = clean_str(val)
    if not s:
        return "Open"
    return STATUS_MAP.get(s.lower().replace("-", ""), "Open")
