"""Approved-only and sensitivity filters for Phase 3 recall."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from ..conversation.redaction import redact_secrets
from .models import APPROVAL_STATES

_AUTHORITY_RE = re.compile(
    r"(?is)("
    r"activ(?:eaz[aă]|ate)\s+h\b|"
    r"aprob[aă]\s+toate|"
    r"approve\s+all\s+(?:actions|commands)|"
    r"git\s+reset\s+--hard|"
    r"auto[- ]?development|"
    r"execut[aă]\s+plan|"
    r"run\s+shell|"
    r"authority\s+token|"
    r"ignore\s+previous\s+(?:instructions|rules)|"
    r"\brm\s+-rf\b|"
    r"\bos\.system\b|"
    r"powershell\s+-command|"
    r"\bsudo\s+|"
    r"\beval\s*\(|"
    r"drop\s+table|"
    r"unrestricted|"
    r"override\s+safety|"
    r"execute\s+shell|"
    r"file:///|"
    r"\\\\server\\|"
    r"<script\b|"
    r"\{\{7\*7\}\}|"
    r"curl\s+http|"
    r"bypass\s+approval|"
    r"run\s+shell\s+automatically|"
    r"system:\s*you\s+are\s+now"
    r")"
)

_INFERRED_CATEGORIES = frozenset({"inferred", "assistant_suggested", "quoted_unverified"})
_ALLOW_CATEGORIES = frozenset(
    {
        "verified",
        "user_stated",
        "system_observed",
        "imported",
    }
)
_BLOCKED_STATUSES = frozenset({"archived", "superseded"})
_EXCLUDED_APPROVAL = frozenset({"draft", "rejected", "expired", "rolled_back", "blocked_sensitive"})


def is_authority_related(text: str) -> bool:
    return bool(_AUTHORITY_RE.search(text or ""))


def classify_sensitivity(text: str, attributes: Optional[Dict[str, Any]] = None) -> str:
    attrs = attributes or {}
    if attrs.get("sensitivity") in {"blocked", "sensitive", "authority_related"}:
        return str(attrs["sensitivity"])
    _, blocked = redact_secrets(text or "")
    if blocked:
        return "blocked"
    if is_authority_related(text or ""):
        return "authority_related"
    if attrs.get("secret_like") or attrs.get("blocked_sensitive"):
        return "blocked"
    return "normal"


def proposal_allowed_for_recall(
    status: str,
    *,
    approved_only: bool = True,
) -> Tuple[bool, str]:
    status = (status or "unknown").lower()
    if status not in APPROVAL_STATES and status != "approved":
        # committed graph rows use approval_state=committed
        pass
    if approved_only and status in _EXCLUDED_APPROVAL:
        return False, f"excluded_approval:{status}"
    if approved_only and status not in {"committed", "unknown"}:
        if status == "approved":
            return False, "excluded_approval:approved_not_committed"
        return False, f"excluded_approval:{status}"
    return True, "ok"


def entity_allowed_for_recall(
    entity: Any,
    *,
    approved_only: bool = True,
    include_inferences: bool = False,
    include_sensitive: bool = False,
    min_confidence: float = 0.0,
) -> Tuple[bool, str]:
    """Return (allowed, reason). Entity is a Brain V3 Entity model."""
    status = getattr(entity, "status", "active")
    if status in _BLOCKED_STATUSES:
        return False, f"excluded_status:{status}"

    confidence = float(getattr(entity, "confidence", 0.0) or 0.0)
    if confidence < min_confidence:
        return False, "below_min_confidence"

    category = str(getattr(entity, "confidence_category", "") or "")
    attrs = dict(getattr(entity, "attributes", {}) or {})
    text = " ".join(
        [
            str(getattr(entity, "display_name", "") or ""),
            str(getattr(entity, "description", "") or ""),
            str(attrs),
        ]
    )
    sensitivity = classify_sensitivity(text, attrs)

    if approved_only:
        approval = str(attrs.get("approval_state") or attrs.get("proposal_state") or "committed")
        ok, reason = proposal_allowed_for_recall(approval, approved_only=True)
        if not ok:
            return False, reason
        if attrs.get("rolled_back") or attrs.get("rejected") or attrs.get("expired"):
            return False, "excluded_proposal_flag"

    if not include_inferences and category in _INFERRED_CATEGORIES:
        return False, "excluded_inference"
    if approved_only and category and category not in _ALLOW_CATEGORIES | ({"inferred"} if include_inferences else set()) | {"conflicting", "stale"}:
        if category == "inferred" and not include_inferences:
            return False, "excluded_inference"

    if sensitivity in {"blocked", "sensitive"} and not include_sensitive:
        return False, f"excluded_sensitivity:{sensitivity}"
    if sensitivity == "authority_related":
        return False, "excluded_authority"

    return True, "approved"


def filter_excluded_record(
    *,
    item_id: str,
    item_type: str,
    reason: str,
    title: str = "",
) -> Dict[str, Any]:
    return {
        "item_id": item_id,
        "item_type": item_type,
        "reason": reason,
        "title": title[:120],
    }


def redact_for_output(text: str) -> str:
    redacted, _ = redact_secrets(text or "")
    return redacted
