"""Owner-triggered Self Evaluation (Phase 4 · Section G).

Read-only, proposal-only reports. Never mutates code, config, memory, KG,
prompts, or processes. No scheduler / background loop. LLM is optional and
never the sole authority — deterministic checks always run.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..memory.learning.commands import CommandResult
from ..memory.learning.safety import scrub_lesson_text

try:
    from ..utils.redact import scrub_secrets as _scrub
except Exception:  # pragma: no cover
    def _scrub(text: str) -> str:  # type: ignore
        return text

try:
    from ..debug import debug_log
except Exception:  # pragma: no cover
    def debug_log(*_a, **_k):  # type: ignore
        return None

__all__ = [
    "EvaluationVerdict",
    "EvaluationFinding",
    "EvaluationReport",
    "try_self_eval_command",
    "format_evaluation_report",
    "PENDING_TTL_SEC",
]

_PENDING_EVAL = "_pending_self_eval"
PENDING_TTL_SEC = 5 * 60

# Max recent turns / chars considered for a single eval request.
_MAX_TURNS = 12
_MAX_CHARS_PER_MSG = 1200


class EvaluationVerdict:
    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    FAIL = "FAIL"


_RE_TRIGGER = re.compile(
    r"(?is)^\s*(?:cora[,:\s]+)?(?:te\s+rog[,:\s]+)?"
    r"(?:"
    # Broad but explicit evaluation verbs + required object/focus
    r"evalueaz[aă]\s+(?P<focus1>.+)|"
    r"f[aă]\s+(?:o\s+)?autoevaluare(?:\s+(?P<focus2>.+))?|"
    r"ce\s+ai\s+gre[șs]it\??|"
    r"analizeaz[aă]\s+(?P<focus3>(?:conversa[țt]ia|ultima?\s+\w+|r[aă]spunsul(?:\s+t[aă]u)?|"
    r"cercetarea|memorarea|modulele|starea(?:\s+modulelor)?).*)|"
    r"verific[aă]\s+(?P<focus4>(?:dac[aă]\s+ai\s+r[aă]spuns\s+corect|rezultatul(?:\s+cercet[aă]rii)?|"
    r"dac[aă]\s+ai\s+gre[șs]it|modulele|starea(?:\s+modulelor)?).*)|"
    r"evaluate\s+(?P<focus5>.+)|"
    r"self[- ]?evaluat(?:e|ion)(?:\s+(?P<focus6>.+))?|"
    r"review\s+(?:your\s+)?(?P<focus7>.+)"
    r")\s*$"
)

_RE_SCOPE_LAST_REPLY = re.compile(
    r"(?i)\b(r[aă]spuns|reply|response|answer|ultimul\s+r[aă]spuns)\b"
)
_RE_SCOPE_RESEARCH = re.compile(
    r"(?i)\b(cercet[aă]r\w*|research|internet|surse|web)\b"
)
_RE_SCOPE_MEMORY = re.compile(
    r"(?i)\b(memor\w*|state\s*memory|am\s+memorat)\b"
)
_RE_SCOPE_MODULES = re.compile(
    r"(?i)\b(module\w*|status(?:ul)?\s+module|B.?H|capabilit)\b"
)
_RE_SCOPE_CONVERSATION = re.compile(
    r"(?i)\b(conversa[țt]i\w*|conversation|dialog|ultimele\s+mesaje)\b"
)
_RE_SCOPE_ACTION = re.compile(
    r"(?i)\b(ac[țt]iun\w*|action|audit\s*id|opera[țt]iun\w*)\b"
)

_INJECTION = re.compile(
    r"(?i)\b("
    r"ignore\s+(all\s+)?previous\s+instructions|"
    r"system\s+prompt|jailbreak|developer\s+mode|"
    r"reveal\s+(the\s+)?(api|secret|key|token)|"
    r"execut[aă]\s+(cod|comand[aă]|shell)|"
    r"modific[aă]\s+(config|codul|promptul)"
    r")\b"
)

_SECRETISH = re.compile(
    r"(?i)(sk-[a-z0-9]{16,}|ghp_[a-z0-9]{20,}|Bearer\s+[A-Za-z0-9\-._]{16,}|"
    r"api[_-]?key\s*[:=]\s*\S+|password\s*[:=]\s*\S+)"
)


@dataclass
class EvaluationFinding:
    code: str
    severity: str  # info | warning | error
    message: str


@dataclass
class EvaluationReport:
    object_label: str
    timestamp: str
    operation_type: str
    verdict: str
    confidence: float
    correct: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    unsupported_claims: List[str] = field(default_factory=list)
    contradictions: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    memory_use: str = ""
    internet_use: str = ""
    confirmations: str = ""
    owner_role: str = ""
    hallucination_risk: str = ""
    security_risks: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    findings: List[EvaluationFinding] = field(default_factory=list)
    modules_snapshot: Dict[str, str] = field(default_factory=dict)
    applied_changes: bool = False  # always False by contract
    nonce: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass
class _EvalPending:
    scope: str
    created_monotonic: float
    nonce: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_text(text: str, *, limit: int = _MAX_CHARS_PER_MSG) -> str:
    t = scrub_lesson_text(_scrub(text or ""))
    t = _SECRETISH.sub("[REDACTED]", t)
    t = " ".join(t.split())
    if len(t) > limit:
        t = t[: limit - 1].rstrip() + "…"
    return t


def _module_flags(cfg) -> Dict[str, str]:
    def on(name: str) -> str:
        return "ON" if bool(getattr(cfg, name, False)) else "OFF"

    return {
        "owner_profile": on("owner_profile_enabled"),
        "identity_registry": on("identity_registry_enabled"),
        "state_memory": on("state_memory_enabled"),
        "internet_learning": on("internet_learning_enabled"),
        "self_eval": on("self_eval_enabled"),
        "owner_triggered_development": on("owner_triggered_development_enabled"),
        "legacy_kg_auto_write": on("legacy_knowledge_auto_write_enabled"),
    }


def _detect_scope(raw: str, focus: str) -> str:
    blob = f"{raw} {focus or ''}"
    if _RE_SCOPE_MODULES.search(blob):
        return "modules"
    if _RE_SCOPE_RESEARCH.search(blob):
        return "research"
    if _RE_SCOPE_MEMORY.search(blob):
        return "memory"
    if _RE_SCOPE_CONVERSATION.search(blob):
        return "conversation"
    if _RE_SCOPE_ACTION.search(blob):
        return "action"
    if _RE_SCOPE_LAST_REPLY.search(blob):
        return "last_reply"
    # Default for bare "autoevaluare" / "ce ai greșit"
    return "last_reply"


def _recent_turns(dialogue_memory, *, max_turns: int = _MAX_TURNS) -> List[Dict[str, str]]:
    if dialogue_memory is None:
        return []
    msgs: Sequence[Any] = []
    if hasattr(dialogue_memory, "get_recent_messages"):
        try:
            msgs = dialogue_memory.get_recent_messages() or []
        except Exception:
            msgs = []
    out: List[Dict[str, str]] = []
    for m in list(msgs)[-max_turns:]:
        if isinstance(m, dict):
            role = str(m.get("role") or m.get("speaker") or "")
            content = str(m.get("content") or m.get("text") or "")
        else:
            role = str(getattr(m, "role", "") or "")
            content = str(getattr(m, "content", "") or getattr(m, "text", "") or "")
        if not content:
            continue
        out.append({"role": role.lower(), "content": _safe_text(content)})
    return out


def _last_assistant(turns: List[Dict[str, str]]) -> Optional[str]:
    for t in reversed(turns):
        if t.get("role") in ("assistant", "cora", "bot"):
            return t.get("content") or ""
    return None


def _last_user(turns: List[Dict[str, str]]) -> Optional[str]:
    for t in reversed(turns):
        if t.get("role") in ("user", "owner", "human"):
            return t.get("content") or ""
    return None


def _extract_sources(text: str) -> List[str]:
    urls = re.findall(r"https://[^\s\]\)\"']+", text or "")
    clean = []
    for u in urls:
        u = u.rstrip(".,;)")
        if u not in clean:
            clean.append(u)
    return clean[:8]


def _count_source_domains(urls: Sequence[str]) -> int:
    domains = set()
    for u in urls:
        try:
            host = u.split("/")[2].lower().removeprefix("www.")
            # registrable-ish
            parts = host.split(".")
            if len(parts) >= 2:
                domains.add(".".join(parts[-2:]))
            else:
                domains.add(host)
        except Exception:
            continue
    return len(domains)


def _run_turn_heuristics(user_text: str, assistant_text: str, *, had_sources: bool) -> List[EvaluationFinding]:
    """Reuse Section-G conversation heuristics without persisting anything."""
    findings: List[EvaluationFinding] = []
    try:
        from .self_eval import ConversationEvents, TurnRecord, evaluate_conversation
    except Exception:
        return findings
    ev = ConversationEvents(turns=[
        TurnRecord(
            user_text=user_text or "",
            assistant_text=assistant_text or "",
            had_sources=had_sources,
        ),
    ])
    for c in evaluate_conversation(ev, enabled=True):
        sev = "warning"
        if c.kind in ("tool_selected_not_executed",):
            sev = "error"
        findings.append(EvaluationFinding(
            code=c.kind,
            severity=sev,
            message=_safe_text(c.summary, limit=240),
        ))
    return findings


def _score_verdict(findings: List[EvaluationFinding], *, evidence_ok: bool) -> Tuple[str, float]:
    if not evidence_ok:
        return EvaluationVerdict.INSUFFICIENT_EVIDENCE, 0.35
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    if errors:
        return EvaluationVerdict.FAIL, 0.85
    if warnings:
        return EvaluationVerdict.PASS_WITH_WARNINGS, 0.75
    return EvaluationVerdict.PASS, 0.9


def build_evaluation_report(
    *,
    scope: str,
    cfg,
    dialogue_memory,
    state_store=None,
    audit_id: Optional[str] = None,
    llm_hint: Optional[str] = None,
) -> EvaluationReport:
    """Deterministic report builder. Never writes. Never calls network."""
    ts = _utc_now_iso()
    flags = _module_flags(cfg)
    turns = _recent_turns(dialogue_memory)
    findings: List[EvaluationFinding] = []
    correct: List[str] = []
    errors: List[str] = []
    unsupported: List[str] = []
    contradictions: List[str] = []
    sources: List[str] = []
    limitations: List[str] = []
    recommendations: List[str] = []
    security: List[str] = []
    memory_use = "n/a"
    internet_use = "n/a"
    confirmations = "n/a"
    hallucination = "necunoscut"
    evidence_ok = True
    object_label = scope
    op_type = scope

    # --- modules snapshot (always available) ---------------------------------
    if scope == "modules":
        object_label = "starea modulelor B–H"
        op_type = "module_status"
        correct.append(
            "Flaguri citite din configurația efectivă (determinist, fără LLM)."
        )
        for k, v in flags.items():
            findings.append(EvaluationFinding(
                code=f"flag_{k}",
                severity="info",
                message=f"{k}={v}",
            ))
        if flags.get("owner_triggered_development") == "ON":
            errors.append("H (owner_triggered_development) este ON — neașteptat.")
            findings.append(EvaluationFinding(
                "h_unexpected_on", "error",
                "H ar trebui să rămână OFF.",
            ))
        else:
            correct.append("H (owner_triggered_development) este OFF.")
        if flags.get("self_eval") != "ON":
            limitations.append("self_eval_enabled nu este ON în cfg transmis.")
        # Deterministic correction of a wrong LLM hint about flags
        if llm_hint:
            hint = llm_hint.lower()
            if "h" in hint and ("activ" in hint or "on" in hint or "enabled" in hint):
                if flags.get("owner_triggered_development") == "OFF":
                    findings.append(EvaluationFinding(
                        "llm_flag_corrected", "warning",
                        "Hint LLM a sugerat H activ, dar flagul real este OFF "
                        "(corecție deterministă).",
                    ))
                    recommendations.append(
                        "Nu te baza pe afirmații LLM despre flaguri — verifică config."
                    )
        evidence_ok = True

    # --- last reply ----------------------------------------------------------
    elif scope == "last_reply":
        object_label = "ultimul răspuns"
        op_type = "last_reply"
        asst = _last_assistant(turns)
        user = _last_user(turns)
        if not asst:
            evidence_ok = False
            limitations.append("Nu există un răspuns recent de evaluat.")
        else:
            if _INJECTION.search(asst) or (user and _INJECTION.search(user)):
                security.append(
                    "Conținut cu formă de prompt-injection — tratat ca DATE, "
                    "nu ca instrucțiuni."
                )
                findings.append(EvaluationFinding(
                    "injection_shaped", "warning",
                    "Text evaluat conține pattern de prompt-injection (ignorat ca instrucțiune).",
                ))
            srcs = _extract_sources(asst)
            sources.extend(srcs)
            had_sources = bool(srcs) or ("Surse:" in asst) or ("surse:" in asst.lower())
            for f in _run_turn_heuristics(user or "", asst, had_sources=had_sources):
                findings.append(f)
                if f.code == "unsourced_claim":
                    unsupported.append(f.message)
            if had_sources:
                correct.append("Răspunsul include referințe/surse detectabile.")
            if not findings:
                correct.append("Nicio problemă deterministă detectată pe ultimul răspuns.")
            hallucination = (
                "ridicat" if unsupported else
                ("moderat" if any(f.severity == "warning" for f in findings) else "scăzut")
            )

    # --- research ------------------------------------------------------------
    elif scope == "research":
        object_label = "ultima cercetare web"
        op_type = "internet_research"
        asst = _last_assistant(turns) or ""
        # Also scan recent assistant turns for research summary
        research_text = ""
        for t in reversed(turns):
            c = t.get("content") or ""
            if "Rezumat cercetare" in c or "Confirmi cercetarea online" in c or "Surse:" in c:
                research_text = c
                break
        if not research_text:
            research_text = asst
        if not research_text:
            evidence_ok = False
            limitations.append("Nu am găsit o cercetare recentă în dialog.")
        else:
            if "Confirmi cercetarea online" in research_text and "Rezumat cercetare" not in research_text:
                internet_use = "pending_confirm — network nepornit (corect)"
                confirmations = "confirmare cerută înainte de network"
                correct.append("Cercetarea a așteptat confirmarea ownerului.")
            elif "Am anulat" in research_text or "nu am deschis rețeaua" in research_text.lower():
                internet_use = "anulat — zero network după anulare"
                confirmations = "anulare respectată"
                correct.append("Anularea a prevenit accesul la rețea.")
            elif "Rezumat cercetare" in research_text:
                srcs = _extract_sources(research_text)
                sources.extend(srcs)
                n_dom = _count_source_domains(srcs)
                internet_use = f"executat; domenii independente detectate={n_dom}"
                if "Incomplet" in research_text or "nesaveable" in research_text.lower():
                    findings.append(EvaluationFinding(
                        "research_incomplete", "warning",
                        "Cercetare marcată incompletă / o singură sursă.",
                    ))
                    if n_dom < 2:
                        unsupported.append("Fapt nesaveable — <2 domenii independente.")
                if "Confirmat" in research_text and n_dom >= 2:
                    correct.append("≥2 surse independente raportate.")
                if "Dorești să memorez" in research_text:
                    confirmations = "ofertă memorare separată de aprobarea cercetării"
                    correct.append("Poarta de memorare este distinctă de confirmarea research.")
                if "nu le-am învățat permanent" in research_text.lower():
                    correct.append("Nu s-a declarat învățare permanentă automată.")
            else:
                evidence_ok = False
                limitations.append(
                    "Text recent nu arată clar un flux de cercetare F."
                )
            for f in _run_turn_heuristics("", research_text, had_sources=bool(sources)):
                if f.code not in {x.code for x in findings}:
                    findings.append(f)

    # --- memory --------------------------------------------------------------
    elif scope == "memory":
        object_label = "ultima operațiune State Memory"
        op_type = "state_memory"
        pending = getattr(dialogue_memory, "_pending_state_memorize", None) if dialogue_memory else None
        asst = _last_assistant(turns) or ""
        if pending:
            memory_use = "pending_confirm — scriere nefinalizată"
            confirmations = "așteaptă confirmarea finală State Memory"
            correct.append("Memorarea nu s-a finalizat fără confirmare.")
            evidence_ok = True
        elif any(x in asst for x in ("Am memorat", "Am anulat", "nu memorez", "Să memorez")):
            if "Am memorat" in asst:
                memory_use = "confirmat și scris (conform răspunsului)"
                confirmations = "confirmare finală aparentă"
                correct.append("Fluxul de confirmare State Memory a fost urmat.")
            elif "anulat" in asst.lower() or "nu memorez" in asst.lower():
                memory_use = "anulat — fără scriere confirmată"
                confirmations = "refuz respectat"
                correct.append("Refuzul de memorare a fost respectat.")
            elif "Să memorez" in asst:
                memory_use = "readback — așteaptă da/nu"
                confirmations = "readback activ"
            evidence_ok = True
        else:
            evidence_ok = False
            limitations.append("Nu am dovezi recente de operațiune State Memory.")
        if state_store is not None:
            try:
                n = len(state_store.retrieve_confirmed() or [])
                findings.append(EvaluationFinding(
                    "state_memory_count", "info",
                    f"Fapte confirmate în State Memory (session view): {n}",
                ))
            except Exception:
                limitations.append("StateStore nu a putut fi interogat.")

    # --- conversation window -------------------------------------------------
    elif scope == "conversation":
        object_label = f"ultimele {len(turns)} mesaje"
        op_type = "conversation_window"
        if len(turns) < 2:
            evidence_ok = False
            limitations.append("Fereastră de conversație prea scurtă.")
        else:
            correct.append(f"Am analizat {len(turns)} mesaje recente (limită {_MAX_TURNS}).")
            asst = _last_assistant(turns) or ""
            user = _last_user(turns) or ""
            srcs = _extract_sources(asst)
            sources.extend(srcs)
            for f in _run_turn_heuristics(user, asst, had_sources=bool(srcs)):
                findings.append(f)
                if f.code == "unsourced_claim":
                    unsupported.append(f.message)
            # injection in any turn
            for t in turns:
                if _INJECTION.search(t.get("content") or ""):
                    security.append(
                        "Turn cu pattern injection — tratat ca date."
                    )
                    break

    # --- action / audit id ---------------------------------------------------
    elif scope == "action":
        object_label = f"acțiune{(' ' + audit_id) if audit_id else ''}"
        op_type = "action"
        if audit_id:
            limitations.append(
                "Infrastructura audit ID nu este expusă acestui modul — "
                "evaluez doar semnalele din dialog."
            )
        asst = _last_assistant(turns)
        if not asst:
            evidence_ok = False
            limitations.append("Nu există acțiune recentă observabilă în dialog.")
        else:
            findings.extend(_run_turn_heuristics(
                _last_user(turns) or "", asst, had_sources=bool(_extract_sources(asst)),
            ))

    else:
        evidence_ok = False
        limitations.append(f"Scope necunoscut: {scope}")

    # Global flag consistency notes
    if flags.get("legacy_kg_auto_write") == "ON":
        security.append("legacy_knowledge_auto_write este ON — risc de scriere KG.")
        findings.append(EvaluationFinding(
            "legacy_kg_on", "error",
            "Scrierea automată în KG legacy este activă.",
        ))
    else:
        if scope == "modules":
            correct.append("KG legacy auto-write este OFF.")

    # Owner role
    owner_role = "evaluare cerută pe canalul owner (engine interactiv)"

    # Recommendations (never applied)
    if unsupported:
        recommendations.append(
            "Cere surse sau o cercetare F confirmată înainte de a trata afirmația ca fapt."
        )
    if any(f.code == "research_incomplete" for f in findings):
        recommendations.append(
            "Nu memora ca fapt confirmat rezultate cu o singură sursă."
        )
    if not recommendations and evidence_ok and not findings:
        recommendations.append("Nicio acțiune necesară.")
    recommendations.append(
        "Self Evaluation NU aplică modificări — orice remediere e decizia ownerului "
        "(modulul H rămâne OFF)."
    )

    verdict, confidence = _score_verdict(findings, evidence_ok=evidence_ok)
    for f in findings:
        if f.severity == "error":
            errors.append(f.message)
        elif f.severity == "warning" and f.message not in unsupported:
            if f.message not in errors:
                pass  # warnings stay in findings list

    return EvaluationReport(
        object_label=object_label,
        timestamp=ts,
        operation_type=op_type,
        verdict=verdict,
        confidence=confidence,
        correct=correct,
        errors=errors,
        unsupported_claims=unsupported,
        contradictions=contradictions,
        sources=sources,
        memory_use=memory_use,
        internet_use=internet_use,
        confirmations=confirmations,
        owner_role=owner_role,
        hallucination_risk=hallucination,
        security_risks=security,
        limitations=limitations,
        recommendations=recommendations,
        findings=findings,
        modules_snapshot=flags,
        applied_changes=False,
    )


def format_evaluation_report(report: EvaluationReport) -> str:
    lines: List[str] = [
        "### Autoevaluare (G — doar raport)",
        f"Obiect: {report.object_label}",
        f"Tip: {report.operation_type}",
        f"Timp (UTC): {report.timestamp}",
        f"Verdict: {report.verdict} (încredere {report.confidence:.2f})",
        f"Modificări aplicate: {'DA' if report.applied_changes else 'NU (read-only)'}",
    ]
    if report.modules_snapshot:
        snap = ", ".join(f"{k}={v}" for k, v in report.modules_snapshot.items())
        lines.append(f"Module: {snap}")
    if report.correct:
        lines.append("Corect:")
        for x in report.correct[:6]:
            lines.append(f"• {_safe_text(x, limit=220)}")
    if report.errors:
        lines.append("Erori / probleme:")
        for x in report.errors[:6]:
            lines.append(f"• {_safe_text(x, limit=220)}")
    if report.unsupported_claims:
        lines.append("Afirmații fără suport:")
        for x in report.unsupported_claims[:4]:
            lines.append(f"• {_safe_text(x, limit=220)}")
    if report.contradictions:
        lines.append("Contradicții:")
        for x in report.contradictions[:4]:
            lines.append(f"• {_safe_text(x, limit=220)}")
    if report.sources:
        lines.append("Surse / provenance observate:")
        for u in report.sources[:6]:
            lines.append(f"- {u}")
    if report.memory_use and report.memory_use != "n/a":
        lines.append(f"Memorie: {report.memory_use}")
    if report.internet_use and report.internet_use != "n/a":
        lines.append(f"Internet Learning: {report.internet_use}")
    if report.confirmations and report.confirmations != "n/a":
        lines.append(f"Confirmări: {report.confirmations}")
    lines.append(f"Rol owner: {report.owner_role}")
    if report.hallucination_risk != "necunoscut":
        lines.append(f"Risc hallucination: {report.hallucination_risk}")
    if report.security_risks:
        lines.append("Riscuri securitate:")
        for x in report.security_risks[:4]:
            lines.append(f"• {_safe_text(x, limit=220)}")
    if report.limitations:
        lines.append("Limitări:")
        for x in report.limitations[:5]:
            lines.append(f"• {_safe_text(x, limit=220)}")
    if report.recommendations:
        lines.append("Recomandări (neaplicate):")
        for x in report.recommendations[:5]:
            lines.append(f"• {_safe_text(x, limit=220)}")
    lines.append(
        "Raportul nu a fost memorat permanent. Cere explicit memorarea prin State Memory "
        "dacă vrei să îl păstrezi."
    )
    return "\n".join(lines)


def try_self_eval_command(
    text: str,
    *,
    cfg,
    dialogue_memory,
    state_store=None,
    actor: str = "owner",
    now_monotonic: Optional[Callable[[], float]] = None,
    llm_hint: Optional[str] = None,
) -> CommandResult:
    """Handle owner-only self-evaluation. Read-only; never mutates systems."""
    raw = (text or "").strip()
    if not raw or dialogue_memory is None:
        return CommandResult(handled=False)
    if not bool(getattr(cfg, "self_eval_enabled", False)):
        return CommandResult(handled=False)

    # Non-owner / missing / unknown actor blocked
    act = str(actor if actor is not None else "").strip().lower()
    if act not in ("owner", "user", "local_owner"):
        return CommandResult(
            handled=True,
            reply="Autoevaluarea este rezervată ownerului autentificat.",
        )

    mono = now_monotonic or time.monotonic

    # Concurrent: if a pending confirm-style slot exists, remind (we don't need
    # confirm to *run* eval — eval is immediate — but we keep a slot to detect
    # concurrent re-triggers without mixing scope).
    pend = getattr(dialogue_memory, _PENDING_EVAL, None)
    if isinstance(pend, _EvalPending):
        if mono() - pend.created_monotonic > PENDING_TTL_SEC:
            setattr(dialogue_memory, _PENDING_EVAL, None)
        elif _RE_TRIGGER.match(raw):
            return CommandResult(
                handled=True,
                reply=(
                    f"Am deja o evaluare în curs pentru „{pend.scope}”. "
                    f"Așteaptă raportul sau spune „anulează evaluarea”."
                ),
            )

    if re.match(r"(?i)^\s*anuleaz[aă]\s+evaluarea\s*$", raw):
        setattr(dialogue_memory, _PENDING_EVAL, None)
        return CommandResult(handled=True, reply="Am anulat evaluarea pending.")

    m = _RE_TRIGGER.match(raw)
    if not m:
        return CommandResult(handled=False)

    focus = ""
    for key in ("focus1", "focus2", "focus3", "focus4", "focus5", "focus6", "focus7"):
        if m.groupdict().get(key):
            focus = (m.group(key) or "").strip()
            break
    # Quoted / injection-only payloads: still evaluate as data, never as instructions
    scope = _detect_scope(raw, focus)
    audit_id = None
    id_m = re.search(r"(?i)\baudit\s*id\s*[:=]?\s*([A-Za-z0-9\-_]+)", raw)
    if id_m:
        audit_id = id_m.group(1)
        scope = "action"

    setattr(
        dialogue_memory,
        _PENDING_EVAL,
        _EvalPending(scope=scope, created_monotonic=mono(), nonce=uuid.uuid4().hex),
    )
    try:
        report = build_evaluation_report(
            scope=scope,
            cfg=cfg,
            dialogue_memory=dialogue_memory,
            state_store=state_store,
            audit_id=audit_id,
            llm_hint=llm_hint,
        )
        # Optional LLM narrative — never overrides deterministic verdict.
        # We deliberately do NOT call any model here (DeepSeek/Ollama forbidden
        # for this activation). llm_hint is inject-only for tests.
        reply = format_evaluation_report(report)
    except Exception as e:
        debug_log(f"self_eval failed: {e}", "eval")
        setattr(dialogue_memory, _PENDING_EVAL, None)
        return CommandResult(
            handled=True,
            reply="Nu am putut produce raportul de autoevaluare (eroare internă).",
        )
    # Clear pending after producing report (no auto-exec on restart)
    setattr(dialogue_memory, _PENDING_EVAL, None)
    # Stash last report for tests / follow-ups (in-memory only, not durable)
    setattr(dialogue_memory, "_last_self_eval_report", report)
    return CommandResult(handled=True, reply=reply)
