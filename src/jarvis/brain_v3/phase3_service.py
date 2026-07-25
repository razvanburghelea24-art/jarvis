"""Brain V3 Phase 3: conversational intelligence + contextual recall."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

from .conversation import build_conversation
from .conversational_intelligence import (
    AnswerSupport,
    MemoryPolicy,
    Phase3Diagnostics,
    build_answer_support,
    parse_recall_request,
)
from .errors import ValidationError
from .extraction import extract_candidates
from .extraction.models import MemoryCandidate
from .models import normalize_key, utc_now_iso
from .phase2_service import BrainV3Phase2Service, create_brain_v3_phase2
from .project_intelligence import ProjectSnapshot
from .recall import (
    ContextBundle,
    RecallCache,
    RecallLimits,
    RecallRequest,
    build_conversation_context,
    explain_bundle,
    retrieve_approved_context,
)
from .service import BrainV3Service, _resolve_root, create_brain_v3

_PathLike = Union[str, Path]


def _candidate_to_phase2_dict(cand: MemoryCandidate) -> Dict[str, Any]:
    """Adapt extraction MemoryCandidate into Phase 2 proposal-oriented dict."""
    base = cand.to_dict()
    if cand.candidate_type == "event":
        base.update(
            {
                "kind": "timeline_event",
                "event_type": "conversation_note",
                "title": cand.display_value[:120],
                "description": cand.display_value[:500],
                "confidence_category": "user_stated"
                if cand.confidence >= 0.5
                else "inferred",
                "source_reference": "conversation",
            }
        )
    else:
        entity_type = cand.candidate_type
        if entity_type in {"preference", "constraint"}:
            entity_type = "concept"
        if entity_type not in {
            "person",
            "project",
            "component",
            "decision",
            "goal",
            "task",
            "repository",
            "branch",
            "commit",
            "document",
            "system",
            "feature",
            "environment",
            "event",
            "concept",
        }:
            entity_type = "concept"
        base.update(
            {
                "kind": "entity",
                "entity_type": entity_type,
                "canonical_name": normalize_key(cand.normalized_value or cand.display_value),
                "display_name": cand.display_value[:120] or "unnamed",
                "description": cand.display_value[:500],
                "confidence_category": "user_stated"
                if cand.confidence >= 0.5
                else "inferred",
                "source_reference": "conversation",
                "attributes": {
                    "is_preference": cand.candidate_type == "preference",
                    "sensitivity": cand.sensitivity,
                    "extraction_candidate_id": cand.candidate_id,
                },
            }
        )
    return base


class BrainV3Phase3Service:
    """Phase 3 facade: wired conversation/extraction + approved contextual recall."""

    def __init__(
        self,
        *,
        brain_v3: BrainV3Service,
        phase2: Optional[BrainV3Phase2Service] = None,
        root_dir: Optional[_PathLike] = None,
        policy: Optional[MemoryPolicy] = None,
        limits: Optional[RecallLimits] = None,
        contextual_recall_enabled: bool = True,
        cache_enabled: bool = False,
    ) -> None:
        self._brain_v3 = brain_v3
        self._phase2 = phase2
        self._root_dir = _resolve_root(root_dir) if root_dir is not None else None
        self.policy = policy or MemoryPolicy()
        self.limits = limits or RecallLimits()
        self.contextual_recall_enabled = contextual_recall_enabled
        self.read_only = True
        self._cache = RecallCache(enabled=cache_enabled)
        self._diag = Phase3Diagnostics(
            phase3_enabled=True,
            contextual_recall_enabled=contextual_recall_enabled,
            read_only=True,
            approved_only=self.policy.approved_only,
            include_inferences=self.policy.include_inferences,
            cache_enabled=cache_enabled,
        )
        self._memory_revision = "0"
        self.last_error: Optional[str] = None

    @property
    def brain_v3(self) -> BrainV3Service:
        return self._brain_v3

    @property
    def phase2(self) -> Optional[BrainV3Phase2Service]:
        return self._phase2

    def _note_error(self, exc: BaseException) -> None:
        self.last_error = str(exc)
        self._diag.last_error = str(exc)

    def bump_memory_revision(self) -> None:
        self._memory_revision = str(int(self._memory_revision) + 1)
        self._cache.invalidate()

    # ── Conversation / extraction wiring ──────────────────────────────────

    def analyze_conversation(self, conv: Mapping[str, Any]) -> Dict[str, Any]:
        if self._phase2 is not None:
            return self._phase2.analyze_conversation(conv)
        if not isinstance(conv, Mapping):
            raise ValidationError("conversation must be a mapping")
        messages = conv.get("messages") or conv.get("turns") or []
        if not isinstance(messages, list):
            raise ValidationError("messages must be a list")
        candidates = self.extract_memory_candidates(
            {"messages": messages, "conversation_id": conv.get("conversation_id") or conv.get("id")}
        )
        return {
            "conversation_id": conv.get("id") or conv.get("conversation_id"),
            "candidate_count": len(candidates),
            "candidates": candidates,
            "dry_run": True,
            "approval_required": True,
            "phase": 3,
        }

    def extract_memory_candidates(self, conv_or_messages: Any) -> List[Dict[str, Any]]:
        """Wire conversation.build_conversation + extraction.extract_candidates."""
        if isinstance(conv_or_messages, list):
            raw = {"messages": conv_or_messages}
        elif isinstance(conv_or_messages, Mapping):
            raw = dict(conv_or_messages)
            if "messages" not in raw and "turns" in raw:
                raw["messages"] = raw["turns"]
        else:
            raise ValidationError("conversation payload required")
        conversation = build_conversation(raw)
        candidates = extract_candidates(conversation)
        return [_candidate_to_phase2_dict(c) for c in candidates]

    def generate_memory_proposals(self, candidates: List[Mapping[str, Any]]):
        if self._phase2 is None:
            raise ValidationError("phase2 service required for proposals")
        return self._phase2.generate_memory_proposals(candidates)

    def build_project_snapshot(self, project_name_or_id: str) -> ProjectSnapshot:
        if self._phase2 is not None:
            return self._phase2.build_project_snapshot(project_name_or_id)
        raise ValidationError("phase2 service required for project snapshot")

    def build_project_timeline(self, project_name_or_id: str) -> Dict[str, Any]:
        snap = self.build_project_snapshot(project_name_or_id)
        data = snap.to_dict() if hasattr(snap, "to_dict") else dict(snap.__dict__)
        return {
            "project": project_name_or_id,
            "timeline": data.get("timeline") or data.get("events") or [],
            "milestones": data.get("milestones") or [],
            "execution_forbidden": True,
        }

    # ── Contextual recall ─────────────────────────────────────────────────

    def retrieve_context(self, request: Mapping[str, Any] | RecallRequest) -> ContextBundle:
        if not self.contextual_recall_enabled:
            raise ValidationError("contextual recall disabled")
        req = parse_recall_request(request)
        req.approved_only = self.policy.approved_only if req.approved_only else False
        if not self.policy.include_inferences:
            req.include_inferences = False

        cache_key = self._cache.make_key(
            req.query,
            self._memory_revision,
            approved_only=req.approved_only,
            inferences=req.include_inferences,
            project=req.project_scope,
            max_results=req.maximum_results,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._diag.cache_hits = self._cache.hits
            self._diag.cache_misses = self._cache.misses
            return cached

        started = time.perf_counter()
        try:
            bundle = retrieve_approved_context(
                self._brain_v3,
                req,
                limits=self.limits,
                include_sensitive=self.policy.include_sensitive,
            )
        except Exception as exc:  # noqa: BLE001 — surface via diagnostics
            self._note_error(exc)
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self._diag.recall_requests += 1
        self._diag.selected_items += len(bundle.items)
        self._diag.excluded_items += len(bundle.excluded_items)
        if bundle.truncated:
            self._diag.truncated_requests += 1
            if (bundle.limits_applied or {}).get("limit_hit") == "timeout_ms":
                self._diag.timeouts += 1
        self._diag.record_latency(elapsed_ms)
        self._diag.last_recall_at = utc_now_iso()
        self._diag.cache_hits = self._cache.hits
        self._diag.cache_misses = self._cache.misses
        self._cache.set(cache_key, bundle)
        return bundle

    def build_conversation_context(
        self,
        *,
        current_message: Mapping[str, Any] | str,
        recent_messages: Optional[List[Any]] = None,
        recall_request: Optional[Mapping[str, Any] | RecallRequest] = None,
        project_scope: str = "",
    ) -> Dict[str, Any]:
        bundle = None
        if recall_request is not None:
            bundle = self.retrieve_context(recall_request)
        elif isinstance(current_message, str) or (
            isinstance(current_message, Mapping) and current_message.get("content")
        ):
            query = (
                current_message
                if isinstance(current_message, str)
                else str(current_message.get("content") or "")
            )
            bundle = self.retrieve_context(
                {
                    "query": query,
                    "project_scope": project_scope,
                    "approved_only": self.policy.approved_only,
                    "include_inferences": self.policy.include_inferences,
                }
            )
        snapshot = None
        if project_scope and self._phase2 is not None:
            try:
                snap = self._phase2.build_project_snapshot(project_scope)
                snapshot = snap.to_dict() if hasattr(snap, "to_dict") else {"name": project_scope}
            except Exception:  # noqa: BLE001
                snapshot = {"name": project_scope, "unknown": True}
        return build_conversation_context(
            current_message=current_message,
            recent_messages=recent_messages,
            recall_bundle=bundle,
            project_snapshot=snapshot,
            limits=self.limits,
        )

    def build_answer_support(
        self,
        bundle_or_request: ContextBundle | Mapping[str, Any] | RecallRequest,
        *,
        project_scope: str = "",
    ) -> AnswerSupport:
        if isinstance(bundle_or_request, ContextBundle):
            bundle = bundle_or_request
        else:
            bundle = self.retrieve_context(bundle_or_request)
        snapshot = None
        if project_scope and self._phase2 is not None:
            try:
                snap = self._phase2.build_project_snapshot(project_scope)
                snapshot = snap.to_dict() if hasattr(snap, "to_dict") else {"name": project_scope}
            except Exception:  # noqa: BLE001
                snapshot = {"name": project_scope, "unknown": True}
        return build_answer_support(bundle, project_snapshot=snapshot)

    def explain_context_selection(
        self, bundle_or_request: ContextBundle | Mapping[str, Any] | RecallRequest
    ) -> Dict[str, Any]:
        if isinstance(bundle_or_request, ContextBundle):
            bundle = bundle_or_request
        else:
            bundle = self.retrieve_context(bundle_or_request)
        return explain_bundle(bundle)

    def list_excluded_context_items(
        self, bundle_or_request: ContextBundle | Mapping[str, Any] | RecallRequest
    ) -> List[Dict[str, Any]]:
        if isinstance(bundle_or_request, ContextBundle):
            bundle = bundle_or_request
        else:
            bundle = self.retrieve_context(bundle_or_request)
        return list(bundle.excluded_items)

    def get_recall_diagnostics(self) -> Dict[str, Any]:
        self._diag.cache_hits = self._cache.hits
        self._diag.cache_misses = self._cache.misses
        return self._diag.to_dict()

    def close(self) -> None:
        self._cache.clear()
        # Do not close shared brain_v3 unless we own it — factory tracks ownership.


def create_brain_v3_phase3(
    *,
    enabled: bool = False,
    root_dir: Optional[_PathLike] = None,
    brain_v3: Optional[BrainV3Service] = None,
    phase2: Optional[BrainV3Phase2Service] = None,
    contextual_recall_enabled: bool = True,
    approved_only: bool = True,
    include_inferences: bool = False,
    include_sensitive: bool = False,
    cache_enabled: bool = False,
    limits: Optional[RecallLimits] = None,
) -> Optional[BrainV3Phase3Service]:
    """Return Phase 3 service when enabled; otherwise None with zero I/O."""
    if not enabled:
        return None

    resolved = _resolve_root(root_dir)
    service_brain = brain_v3
    owns_brain = False
    if service_brain is None:
        service_brain = create_brain_v3(enabled=True, root_dir=resolved)
        owns_brain = True
    assert service_brain is not None

    service_phase2 = phase2
    if service_phase2 is None:
        service_phase2 = create_brain_v3_phase2(
            enabled=True,
            root_dir=resolved,
            brain_v3=service_brain,
            dry_run=True,
            approval_required=True,
        )

    svc = BrainV3Phase3Service(
        brain_v3=service_brain,
        phase2=service_phase2,
        root_dir=resolved,
        policy=MemoryPolicy(
            approved_only=approved_only,
            include_inferences=include_inferences,
            include_sensitive=include_sensitive,
            read_only=True,
        ),
        limits=limits or RecallLimits(),
        contextual_recall_enabled=contextual_recall_enabled,
        cache_enabled=cache_enabled,
    )
    svc._owns_brain = owns_brain  # type: ignore[attr-defined]
    return svc
