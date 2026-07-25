"""Temporal relevance helpers for Phase 3 recall."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def temporal_state_for(
    *,
    status: str = "active",
    valid_from: Optional[str] = None,
    valid_until: Optional[str] = None,
    occurred_at: Optional[str] = None,
    observed_at: Optional[str] = None,
    recorded_at: Optional[str] = None,
    superseded: bool = False,
    as_of: Optional[str] = None,
) -> str:
    if superseded or status == "superseded":
        return "superseded"
    if status == "archived":
        return "historical"
    now = _parse_ts(as_of) or datetime.now(timezone.utc).replace(tzinfo=None)
    until = _parse_ts(valid_until)
    start = _parse_ts(valid_from) or _parse_ts(occurred_at) or _parse_ts(observed_at) or _parse_ts(recorded_at)
    if until and until < now:
        return "stale"
    if start and until and start <= now <= until:
        return "valid_interval"
    if start and not until:
        return "current"
    if occurred_at and not valid_until:
        # historical if as_of range asked for past
        return "historical" if as_of and _parse_ts(as_of) and start and start < (_parse_ts(as_of) or now) else "current"
    return "unspecified"


def pick_most_recent(
    candidates: list[Dict[str, Any]],
    *,
    time_keys: Tuple[str, ...] = ("valid_from", "occurred_at", "observed_at", "recorded_at", "updated_at", "created_at"),
) -> Optional[Dict[str, Any]]:
    best = None
    best_ts: Optional[datetime] = None
    for item in candidates:
        for key in time_keys:
            ts = _parse_ts(item.get(key))
            if ts is None:
                continue
            if best_ts is None or ts > best_ts:
                best_ts = ts
                best = item
            break
    return best


def in_time_range(
    stamp: Optional[str],
    time_range: Optional[Dict[str, str]],
) -> bool:
    if not time_range:
        return True
    ts = _parse_ts(stamp)
    if ts is None:
        return True
    start = _parse_ts(time_range.get("from") or time_range.get("time_from"))
    end = _parse_ts(time_range.get("to") or time_range.get("time_to"))
    if start and ts < start:
        return False
    if end and ts > end:
        return False
    return True
