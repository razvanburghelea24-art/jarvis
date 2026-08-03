"""Intent Engine — structured Intent objects via detector registry (not ad-hoc if/else trees)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Callable

from .types import Intent, NormalizedCommand, RiskLevel, SourceChannel


@dataclass(frozen=True)
class IntentMatch:
    type: str
    confidence: float
    required_capabilities: tuple[str, ...]
    risk_level: RiskLevel
    estimated_cost: float = 0.0
    params: dict | None = None


Detector = Callable[[NormalizedCommand], IntentMatch | None]


def _match(pattern: str, text: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _det_whoami(cmd: NormalizedCommand) -> IntentMatch | None:
    if _match(r"\b(who\s*am\s*i|cine\s+sunt|whoami)\b", cmd.text):
        return IntentMatch(
            type="identity.whoami",
            confidence=0.95,
            required_capabilities=("Identity.whoami",),
            risk_level=RiskLevel.READ,
            estimated_cost=0.0,
        )
    return None


def _det_memory_read(cmd: NormalizedCommand) -> IntentMatch | None:
    if _match(r"\b(memory\s+status|list\s+tasks|what\s+do\s+you\s+remember)\b", cmd.text):
        return IntentMatch(
            type="memory.read",
            confidence=0.9,
            required_capabilities=("Memory.read",),
            risk_level=RiskLevel.READ,
            estimated_cost=0.0,
        )
    return None


def _det_overlay_refresh(cmd: NormalizedCommand) -> IntentMatch | None:
    if _match(r"\b(refresh\s+overlay|overlay\s+refresh)\b", cmd.text):
        return IntentMatch(
            type="overlay.refresh",
            confidence=0.9,
            required_capabilities=("Overlay.refresh",),
            risk_level=RiskLevel.SAFE_LOCAL,
            estimated_cost=0.01,
        )
    return None


def _det_discord_send(cmd: NormalizedCommand) -> IntentMatch | None:
    if _match(r"\b(send\s+discord|discord\s+send|posteaz[aă]\s+pe\s+discord)\b", cmd.text):
        return IntentMatch(
            type="discord.send",
            confidence=0.85,
            required_capabilities=("Discord.send",),
            risk_level=RiskLevel.OWNER_CONFIRM,
            estimated_cost=0.05,
            params={"channel": "unspecified"},
        )
    return None


def _det_github_pr(cmd: NormalizedCommand) -> IntentMatch | None:
    if _match(r"\b(create\s+pr|open\s+pull\s+request|github\s+pr)\b", cmd.text):
        return IntentMatch(
            type="github.create_pr",
            confidence=0.88,
            required_capabilities=("GitHub.create_pr",),
            risk_level=RiskLevel.CRITICAL,
            estimated_cost=0.2,
        )
    return None


def _det_railway_deploy(cmd: NormalizedCommand) -> IntentMatch | None:
    if _match(r"\b(railway\s+deploy|deploy\s+railway|deploy\s+to\s+prod)\b", cmd.text):
        return IntentMatch(
            type="railway.deploy",
            confidence=0.9,
            required_capabilities=("Railway.deploy",),
            risk_level=RiskLevel.CRITICAL,
            estimated_cost=0.5,
        )
    return None


def _det_server_restart(cmd: NormalizedCommand) -> IntentMatch | None:
    if _match(r"\b(restart\s+server|server\s+restart)\b", cmd.text):
        return IntentMatch(
            type="server.restart",
            confidence=0.9,
            required_capabilities=("Server.restart",),
            risk_level=RiskLevel.CRITICAL,
            estimated_cost=1.0,
        )
    return None


def _det_unknown(cmd: NormalizedCommand) -> IntentMatch | None:
    if not cmd.text:
        return IntentMatch(
            type="noop.empty",
            confidence=1.0,
            required_capabilities=(),
            risk_level=RiskLevel.READ,
        )
    return IntentMatch(
        type="unknown",
        confidence=0.2,
        required_capabilities=(),
        risk_level=RiskLevel.READ,
        estimated_cost=0.0,
        params={"raw": cmd.text},
    )


DEFAULT_DETECTORS: tuple[Detector, ...] = (
    _det_whoami,
    _det_memory_read,
    _det_overlay_refresh,
    _det_discord_send,
    _det_github_pr,
    _det_railway_deploy,
    _det_server_restart,
)


class IntentEngine:
    """Registry of detectors — first confident match wins; unknown fallback last."""

    def __init__(self, detectors: tuple[Detector, ...] | list[Detector] | None = None) -> None:
        self._detectors = tuple(detectors) if detectors is not None else DEFAULT_DETECTORS

    def detect(
        self,
        cmd: NormalizedCommand,
        *,
        owner_id: str | None,
        workspace_id: str | None,
        session_id: str | None,
    ) -> Intent:
        match: IntentMatch | None = None
        for det in self._detectors:
            hit = det(cmd)
            if hit is not None and hit.type != "unknown":
                match = hit
                break
        if match is None:
            match = _det_unknown(cmd)
            assert match is not None
        return Intent(
            intent_id=f"int_{uuid.uuid4().hex}",
            type=match.type,
            confidence=float(match.confidence),
            source=cmd.source if isinstance(cmd.source, SourceChannel) else SourceChannel.UNKNOWN,
            owner_id=owner_id,
            workspace_id=workspace_id,
            session_id=session_id,
            required_capabilities=tuple(match.required_capabilities),
            risk_level=match.risk_level,
            estimated_cost=float(match.estimated_cost),
            params=dict(match.params or {}),
        )
