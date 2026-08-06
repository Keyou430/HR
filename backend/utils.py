"""Shared utility helpers used across the backend."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# Legacy alias — prefer utc_now_iso for new code
_ts = utc_now_iso
