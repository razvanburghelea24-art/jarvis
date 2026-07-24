"""Owner-triggered Development Mode — Phase 1 PLAN_ONLY.

Two gates:
  1) Explicit owner development intent → confirm analysis prompt (no inspect).
  2) Explicit affirmative → read-only inspect via injected backend → DevelopmentPlan.

Never writes files, never shells, never mutates config/DB/KG/State Memory.
Pending lives only on dialogue_memory (restart ⇒ no auto-analysis).
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any, Callable, List, Optional, Sequence

from ..memory.learning.commands import CommandResult, _CONFIRM_NO, _CONFIRM_YES
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

from .models import (
    CANONICAL_BRANCH,
    CANONICAL_WORKSPACE_ROOT,
    DEVELOPMENT_MODE_PHASE,
    DevelopmentPlan,
    DevelopmentVerdict,
    DevPending,
    PlanCandidateFile,
    new_plan_id,
    normalize_workspace_root,
    utc_now_iso,
)
from .read_only_backend import (
    AccessDenied,
    MAX_BYTES_PER_FILE,
    MAX_FILES_READ,
    MAX_TOTAL_BYTES,
    ReadOnlyRepoBackend,
    is_path_allowed,
)

__all__ = [
    "try_owner_development_command",
    "format_development_plan",
    "validate_plan_freshness",
    "consult_g_on_plan",
    "PENDING_TTL_SEC",
    "build_development_plan",
]

_PENDING = "_pending_owner_development"
_LAST_PLAN = "_last_development_plan"
_AUDIT = "_h_dev_audit"
_CONSUMED_NONCES = "_h_consumed_dev_nonces"
PENDING_TTL_SEC = 5 * 60

# Explicit owner-intent development triggers (utterance must MATCH whole line).
_RE_TRIGGER = re.compile(
    r"(?is)^\s*(?:cora[,:\s]+)?(?:te\s+rog[,:\s]+)?"
    r"(?:"
    r"dezvolt[aă]\s+(?:o\s+)?(?:func[țt]ie|modul|feature|component[aă])?\s*(?:pentru\s+)?"
    r"(?P<o1>.+)|"
    r"modific[aă]\s+(?:proiectul|codul|repo(?:zitoriul)?)\s+(?:astfel\s+[iî]nc[aâ]t|ca\s+s[aă]|pentru\s+[aă])\s+"
    r"(?P<o2>.+)|"
    r"preg[aă]te[sș]te\s+(?:un\s+)?plan\s+de\s+implementare\s+(?:pentru\s+)?(?P<o3>.+)|"
    r"repar[aă]\s+[iî]n\s+cod\s+(?P<o4>.+)|"
    r"adaug[aă]\s+[iî]n\s+proiect\s+(?P<o5>.+)|"
    r"analizeaz[aă]\s+ce\s+trebuie\s+schimbat\s+[iî]n\s+cod\s+(?:pentru\s+)?(?P<o6>.+)|"
    r"preg[aă]te[sș]te\s+dezvoltarea\s+(?:pentru\s+)?(?P<o7>.+)|"
    # English
    r"develop\s+(?:a\s+)?(?:function|feature|module)\s+(?:for\s+)?(?P<e1>.+)|"
    r"prepare\s+(?:an?\s+)?implementation\s+plan\s+(?:for\s+)?(?P<e2>.+)|"
    r"fix\s+(?:in\s+)?(?:the\s+)?code\s+(?P<e3>.+)|"
    r"add\s+to\s+(?:the\s+)?(?:project|codebase)\s+(?P<e4>.+)|"
    r"change\s+the\s+project\s+so\s+that\s+(?P<e5>.+)|"
    r"analyze\s+what\s+(?:needs|must)\s+(?:to\s+be\s+)?changed\s+in\s+(?:the\s+)?code\s+(?:for\s+)?(?P<e6>.+)"
    r")\s*$"
)

# Direct-apply attempts (still recognized, but Phase 1 refuses execution).
_RE_DIRECT = re.compile(
    r"(?is)^\s*(?:cora[,:\s]+)?(?:te\s+rog[,:\s]+)?"
    r"(?:"
    r"f[aă]\s+direct(?:\s+f[aă]r[aă]\s+plan)?\b|"
    r"aplic[aă]\s+(?:direct\s+)?(?:patch-ul|modific[aă]rile|planul)\b|"
    r"execut[aă]\s+planul\b|"
    r"commit(?:eaz[aă])?\s+(?:acum|direct)\b|"
    r"just\s+(?:do|apply|commit)\s+it\b|"
    r"apply\s+(?:the\s+)?(?:patch|changes)\s+now\b|"
    r"skip\s+the\s+plan\b"
    r").*$"
)

_RE_CORRECT = re.compile(
    r"(?is)^\s*(?:"
    r"nu[,:]?\s*(?:pentru|despre|obiectivul)\s+(?P<c1>.+)|"
    r"corecteaz[aă]\s*(?:obiectivul\s*)?[:,]?\s*(?P<c2>.+)|"
    r"obiectivul\s+(?:e|este)\s+(?P<c3>.+)|"
    r"actually\s+(?:for|about)\s+(?P<c4>.+)"
    r")\s*$"
)

_RE_THEORETICAL = re.compile(
    r"(?i)^\s*(?:cum\s+(?:ai|ai\s+putea)\s+dezvolta|how\s+would\s+you\s+develop|"
    r"ce\s+po[țt]i\s+face\s+[iî]n\s+dezvoltare|what\s+can\s+you\s+develop)\b"
)

_DANGEROUS = re.compile(
    r"(?i)\b("
    r"rm\s+-rf|format\s+c:|drop\s+table|exfiltrat|"
    r"steal\s+(?:keys|secrets)|disable\s+auth|"
    r"push\s+--force|force\s+push|wipe\s+(?:disk|db)|"
    r"install\s+malware|backdoor"
    r")\b"
)

# Authenticated owner only — plain "user" / assistant / guest cannot spoof H.
_OWNER_OK = frozenset({"owner", "local_owner"})


def _safe(text: str, *, limit: int = 400) -> str:
    t = scrub_lesson_text(_scrub(text or ""))
    t = " ".join(t.split())
    if len(t) > limit:
        t = t[: limit - 1].rstrip() + "…"
    return t


def _audit(dialogue_memory, event: str, **fields: Any) -> None:
    if dialogue_memory is None:
        return
    log = getattr(dialogue_memory, _AUDIT, None)
    if not isinstance(log, list):
        log = []
        setattr(dialogue_memory, _AUDIT, log)
    entry = {"event": event, "ts": utc_now_iso()}
    for k, v in fields.items():
        if isinstance(v, str):
            entry[k] = _safe(v, limit=120)
        else:
            entry[k] = v
    log.append(entry)
    # Cap volume — never durable / never State Memory
    if len(log) > 40:
        del log[:-40]


def _extract_objective(match: re.Match) -> str:
    for key, val in match.groupdict().items():
        if val:
            return _safe(val.strip(" .,;:\"'"), limit=240)
    return ""


def _guess_component(objective: str) -> str:
    o = (objective or "").lower()
    mapping = [
        (("evalu", "self.eval", "autoevalu"), "eval"),
        (("memori", "state memory", "state_memory"), "state_memory"),
        (("cercet", "research", "internet"), "internet_research"),
        (("voice", "tts", "piper", "whisper"), "voice_tts"),
        (("identit", "registry"), "identity_registry"),
        (("owner profile", "profil"), "owner_profile"),
        (("chat", "ui", "modern"), "modern_chat"),
        (("engine", "reply"), "reply_engine"),
        (("develop", "plan"), "development"),
    ]
    for keys, comp in mapping:
        if any(k in o for k in keys):
            return comp
    return "general"


def _workspace_blocked(root: str) -> Optional[str]:
    _norm, err = normalize_workspace_root(root)
    return err


def build_development_plan(
    *,
    objective: str,
    component: str,
    desired_outcome: str,
    constraints: Sequence[str],
    ambiguous_or_dangerous: bool,
    backend: ReadOnlyRepoBackend,
    consult_g: bool = False,
    cfg=None,
    now_iso: Optional[Callable[[], str]] = None,
    new_id: Optional[Callable[[], str]] = None,
) -> DevelopmentPlan:
    """Inspect via backend only — never mutates anything."""
    _ts = now_iso or utc_now_iso
    _id = new_id or new_plan_id
    snap = backend.snapshot()
    forbidden = [
        ".env",
        "owner_profile.json",
        "jarvis.db",
        "jarvis.db-wal",
        "jarvis.db-shm",
        ".git/",
        "backups/",
        "~/.config/jarvis/",
        "cora-integration/",
    ]

    def _blocked(verdict: str, risk: str, limitation: str, checks: Optional[List[str]] = None) -> DevelopmentPlan:
        return DevelopmentPlan(
            plan_id=_id(),
            timestamp=_ts(),
            objective=_safe(objective),
            component=component,
            desired_outcome=_safe(desired_outcome),
            constraints=list(constraints),
            workspace_root=snap.root,
            branch=snap.branch,
            head_sha=snap.head_sha,
            working_tree_clean=snap.working_tree_clean,
            state_hash=backend.state_hash(),
            candidate_files=[],
            implementation_steps=[],
            proposed_tests=[],
            risks=[risk],
            security_checks=checks or [],
            rollback_strategy=["N/A — no changes applied"],
            forbidden_files=forbidden,
            future_approval_actions=[
                "Clarify or re-pin workspace, then regenerate the plan."
            ],
            verdict=verdict,
            ambiguous_or_dangerous=ambiguous_or_dangerous,
            limitations=[limitation],
            applied_changes=False,
        )

    block = _workspace_blocked(snap.root)
    if block:
        return _blocked(
            DevelopmentVerdict.BLOCKED_WRONG_WORKSPACE,
            block,
            block,
            ["workspace pinning failed"],
        )

    if getattr(snap, "git_error", None) and not snap.head_sha:
        return _blocked(
            DevelopmentVerdict.INSUFFICIENT_CONTEXT,
            f"Git metadata unavailable: {snap.git_error}",
            "git metadata missing/corrupt",
            ["git read-only snapshot"],
        )

    if not getattr(snap, "git_status_reliable", True):
        return _blocked(
            DevelopmentVerdict.INSUFFICIENT_CONTEXT,
            f"Git status unreliable without shell: {snap.status_summary}",
            "git status unreliable",
            ["no-shell git status"],
        )

    if getattr(snap, "detached_head", False) and snap.branch in ("HEAD", ""):
        return _blocked(
            DevelopmentVerdict.INSUFFICIENT_CONTEXT,
            "Detached HEAD — reattach to the pinned branch before planning.",
            "detached HEAD",
            ["detached HEAD"],
        )

    if snap.branch != CANONICAL_BRANCH:
        return _blocked(
            DevelopmentVerdict.BLOCKED_WRONG_WORKSPACE,
            f"branch {snap.branch!r} ≠ pinned {CANONICAL_BRANCH!r}",
            "wrong branch",
            ["branch pinning failed"],
        )

    if not snap.working_tree_clean:
        return _blocked(
            DevelopmentVerdict.BLOCKED_DIRTY_WORKTREE,
            "Working tree is dirty — planning blocked to avoid mixed scope.",
            "dirty worktree",
            ["dirty worktree gate"],
        )

    if ambiguous_or_dangerous or _DANGEROUS.search(objective or ""):
        return _blocked(
            DevelopmentVerdict.BLOCKED_UNSAFE_SCOPE,
            "Cererea pare ambiguă sau periculoasă — scope refuzat.",
            "unsafe or ambiguous scope",
            ["dangerous-intent heuristic"],
        )

    if not (objective or "").strip():
        return _blocked(
            DevelopmentVerdict.INSUFFICIENT_CONTEXT,
            "Obiectiv lipsă.",
            "missing objective",
            [],
        )

    # Read-only candidate discovery
    pairs = backend.find_candidates(
        objective=objective, component=component, limit=MAX_FILES_READ
    )
    candidates: List[PlanCandidateFile] = []
    total_bytes = 0
    for path, reason in pairs:
        if not is_path_allowed(path):
            continue
        try:
            text = backend.read_text(path, max_bytes=MAX_BYTES_PER_FILE)
        except AccessDenied:
            continue
        except Exception:
            continue
        n = len(text.encode("utf-8", errors="ignore"))
        if total_bytes + n > MAX_TOTAL_BYTES:
            break
        total_bytes += n
        # Never embed file body — path + reason + size only
        candidates.append(
            PlanCandidateFile(path=path, reason=_safe(reason, limit=120), bytes_read=n)
        )

    steps = [
        f"Clarifică obiectivul: {_safe(objective, limit=160)}",
        "Inspectează fișierele candidate (read-only) și dependențele directe.",
        "Propune modificări minime pe componentele vizate (fără aplicare în Phase 1).",
        "Adaugă / actualizează teste unitare pentru comportamentul nou.",
        "Rulează regresia relevantă înainte de orice fază de aplicare viitoare.",
    ]
    tests = [
        f"tests/test_{component}.py — happy path pentru obiectiv",
        "Test negativ: non-owner / flag OFF / scope nesigur",
        "Test zero-mutation: fără write/shell/network pe calea plan-only",
    ]
    if any(c.path.startswith("tests/") for c in candidates):
        tests.append("Extinde testele existente din lista de candidați.")
    risks = [
        "Scope creep dacă obiectivul rămâne vag.",
        "Regresii pe modulele B–G dacă fișierele partajate (engine) sunt atinse.",
        "Phase 1 nu aplică patch — riscul de execuție accidentală trebuie păstrat zero.",
    ]
    security = [
        "Workspace + branch + HEAD pinning obligatorii înainte de orice fază viitoare.",
        "Fără acces la .env / DB / owner_profile / backups.",
        "Fără subprocess / network / package install în Phase 1.",
        "Owner approval explicit necesar înainte de Phase 2 (inexistentă încă).",
    ]
    rollback = [
        "Nicio modificare aplicată în Phase 1 — rollback = N/A.",
        "În faze viitoare: git restore pe fișierele atinse + re-rulare teste.",
        "Planul devine STALE_PLAN dacă HEAD sau worktree se schimbă.",
    ]
    future = [
        "Aprobare owner pentru generarea unui patch (Phase 2 — neimplementat).",
        "Aprobare separată pentru aplicare / commit (Phase 2+).",
        "Opțional: cerere către G Self Evaluation pe plan (consultativ).",
    ]

    verdict = (
        DevelopmentVerdict.PLAN_READY
        if candidates
        else DevelopmentVerdict.INSUFFICIENT_CONTEXT
    )
    limitations: List[str] = []
    if not candidates:
        limitations.append("Nu am găsit fișiere candidate suficiente pentru obiectiv.")
    if getattr(snap, "inventory_truncated", False):
        reasons = list(getattr(snap, "truncation_reasons", ()) or ())
        limitations.append(
            "Inventar trunchiat: " + (", ".join(reasons) if reasons else "limite resurse")
        )

    plan = DevelopmentPlan(
        plan_id=_id(),
        timestamp=_ts(),
        objective=_safe(objective),
        component=component,
        desired_outcome=_safe(desired_outcome or objective),
        constraints=[_safe(c, limit=160) for c in constraints],
        workspace_root=snap.root,
        branch=snap.branch,
        head_sha=snap.head_sha,
        working_tree_clean=snap.working_tree_clean,
        state_hash=backend.state_hash(),
        candidate_files=candidates,
        implementation_steps=steps,
        proposed_tests=tests,
        risks=risks,
        security_checks=security,
        rollback_strategy=rollback,
        forbidden_files=forbidden,
        future_approval_actions=future,
        verdict=verdict,
        limitations=limitations,
        ambiguous_or_dangerous=False,
        applied_changes=False,
    )

    if consult_g:
        notes = consult_g_on_plan(plan, cfg=cfg)
        plan.g_consultative_notes = notes
    return plan


def consult_g_on_plan(plan: DevelopmentPlan, *, cfg=None) -> List[str]:
    """Ask G for a consultative read-only critique. Never approves or executes."""
    notes: List[str] = []
    # Local deterministic critique (no LLM). Optionally mirror module flags via G helpers.
    if not plan.candidate_files:
        notes.append("G: lipsă fișiere candidate — context insuficient.")
    if not plan.proposed_tests:
        notes.append("G: lipsă teste propuse.")
    if len(plan.candidate_files) > 10:
        notes.append("G: scope larg — multe fișiere candidate; îngustează obiectivul.")
    if plan.verdict == DevelopmentVerdict.PLAN_READY and not plan.risks:
        notes.append("G: plan READY fără riscuri listate — incomplet.")
    if plan.applied_changes:
        notes.append("G: applied_changes=True este invalid pentru Phase 1.")
    # Import G module status helpers without executing eval commands on dialogue.
    try:
        from ..eval.owner_eval import _module_flags

        if cfg is not None:
            flags = _module_flags(cfg)
            if flags.get("owner_triggered_development") == "ON":
                notes.append(
                    "G: H live flag este ON în cfg — Phase 1 tests may enable it; "
                    "live owner config should remain OFF until a future activation."
                )
            if flags.get("self_eval") != "ON":
                notes.append("G: self_eval nu e ON în cfg transmis (consultativ).")
    except Exception:
        pass
    notes.append(
        "G: verdict consultativ doar — G nu aprobă și nu execută planul H."
    )
    return notes


def validate_plan_freshness(
    plan: DevelopmentPlan,
    backend: ReadOnlyRepoBackend,
) -> DevelopmentPlan:
    """If HEAD or worktree state diverged, mark STALE_PLAN (copy; no mutate of systems)."""
    snap = backend.snapshot()
    h = backend.state_hash()
    if (
        snap.head_sha != plan.head_sha
        or snap.working_tree_clean != plan.working_tree_clean
        or h != plan.state_hash
        or snap.branch != plan.branch
    ):
        return DevelopmentPlan(
            plan_id=plan.plan_id,
            timestamp=utc_now_iso(),
            objective=plan.objective,
            component=plan.component,
            desired_outcome=plan.desired_outcome,
            constraints=list(plan.constraints),
            workspace_root=snap.root,
            branch=snap.branch,
            head_sha=snap.head_sha,
            working_tree_clean=snap.working_tree_clean,
            state_hash=h,
            candidate_files=list(plan.candidate_files),
            implementation_steps=list(plan.implementation_steps),
            proposed_tests=list(plan.proposed_tests),
            risks=list(plan.risks) + ["Plan stale — HEAD/worktree/branch changed."],
            security_checks=list(plan.security_checks),
            rollback_strategy=list(plan.rollback_strategy),
            forbidden_files=list(plan.forbidden_files),
            future_approval_actions=[
                "Regenerate plan after revalidation — previous plan is not reusable."
            ],
            verdict=DevelopmentVerdict.STALE_PLAN,
            g_consultative_notes=list(plan.g_consultative_notes),
            limitations=list(plan.limitations) + ["STALE_PLAN"],
            ambiguous_or_dangerous=plan.ambiguous_or_dangerous,
        )
    return plan


def format_development_plan(plan: DevelopmentPlan) -> str:
    lines = [
        "### Plan de dezvoltare (H — Phase 1 PLAN_ONLY)",
        f"Plan ID: {plan.plan_id}",
        f"Timp (UTC): {plan.timestamp}",
        f"Verdict: {plan.verdict}",
        f"Fază: {plan.phase}",
        "Nicio modificare nu a fost aplicată.",
        f"Obiectiv: {plan.objective}",
        f"Componentă: {plan.component}",
        f"Rezultat dorit: {plan.desired_outcome}",
        f"Workspace: {plan.workspace_root}",
        f"Branch: {plan.branch}",
        f"HEAD: {plan.head_sha}",
        f"Working tree clean: {'da' if plan.working_tree_clean else 'nu'}",
        f"State hash: {plan.state_hash[:16]}…",
    ]
    if plan.constraints:
        lines.append("Constrângeri:")
        for c in plan.constraints[:6]:
            lines.append(f"• {c}")
    if plan.candidate_files:
        lines.append("Fișiere candidate:")
        for cf in plan.candidate_files[:10]:
            lines.append(f"• {cf.path} — {cf.reason} ({cf.bytes_read} B)")
    if plan.implementation_steps:
        lines.append("Pași propuși (neaplicați):")
        for i, s in enumerate(plan.implementation_steps, 1):
            lines.append(f"{i}. {s}")
    if plan.proposed_tests:
        lines.append("Teste propuse:")
        for t in plan.proposed_tests[:6]:
            lines.append(f"• {t}")
    if plan.risks:
        lines.append("Riscuri:")
        for r in plan.risks[:6]:
            lines.append(f"• {r}")
    if plan.security_checks:
        lines.append("Verificări securitate:")
        for s in plan.security_checks[:6]:
            lines.append(f"• {s}")
    if plan.rollback_strategy:
        lines.append("Rollback:")
        for r in plan.rollback_strategy[:4]:
            lines.append(f"• {r}")
    if plan.forbidden_files:
        lines.append("Fișiere / zone interzise:")
        for f in plan.forbidden_files[:8]:
            lines.append(f"• {f}")
    if plan.future_approval_actions:
        lines.append("Acțiuni care necesită aprobare viitoare:")
        for a in plan.future_approval_actions[:5]:
            lines.append(f"• {a}")
    if plan.g_consultative_notes:
        lines.append("Evaluare G (consultativă, neobligatorie):")
        for n in plan.g_consultative_notes[:6]:
            lines.append(f"• {n}")
    if plan.limitations:
        lines.append("Limitări:")
        for n in plan.limitations[:5]:
            lines.append(f"• {n}")
    lines.append(
        "Phase 1 este doar plan. Pentru aplicare este nevoie de o fază viitoare "
        "și de aprobări separate ale ownerului. Modulul H live rămâne OFF până la activare."
    )
    return "\n".join(lines)


def try_owner_development_command(
    text: str,
    *,
    cfg,
    dialogue_memory,
    backend: Optional[ReadOnlyRepoBackend] = None,
    actor: str = "owner",
    now_monotonic: Optional[Callable[[], float]] = None,
    consult_g: bool = True,
    now_iso: Optional[Callable[[], str]] = None,
    new_id: Optional[Callable[[], str]] = None,
) -> CommandResult:
    """Handle owner development intent. Phase 1 plan-only; flag-gated by caller/engine."""
    raw = (text or "").strip()
    if not raw or dialogue_memory is None:
        return CommandResult(handled=False)
    if not bool(getattr(cfg, "owner_triggered_development_enabled", False)):
        return CommandResult(handled=False)

    act = str(actor if actor is not None else "").strip().lower()
    if act not in _OWNER_OK:
        _audit(dialogue_memory, "trigger_blocked_actor", actor=act or "missing")
        return CommandResult(
            handled=True,
            reply="Modulul de dezvoltare este rezervat ownerului autentificat.",
        )

    mono = now_monotonic or time.monotonic

    # Theoretical / capability questions — never take over
    if _RE_THEORETICAL.match(raw):
        return CommandResult(handled=False)

    consumed = getattr(dialogue_memory, _CONSUMED_NONCES, None)
    if not isinstance(consumed, set):
        consumed = set()
        setattr(dialogue_memory, _CONSUMED_NONCES, consumed)

    # Pending gate handling first
    pend = getattr(dialogue_memory, _PENDING, None)
    if isinstance(pend, DevPending):
        if mono() - pend.created_monotonic > PENDING_TTL_SEC:
            setattr(dialogue_memory, _PENDING, None)
            _audit(dialogue_memory, "pending_expired", objective=pend.objective)
            # fall through — expired pending does not auto-inspect
            pend = None
        else:
            # Cancel / refuse
            if _CONFIRM_NO.match(raw):
                setattr(dialogue_memory, _PENDING, None)
                _audit(dialogue_memory, "request_cancelled", objective=pend.objective)
                return CommandResult(
                    handled=True,
                    reply="Am anulat planul de dezvoltare. Nu am inspectat repository-ul.",
                )
            # Correct objective
            cm = _RE_CORRECT.match(raw)
            if cm:
                new_obj = ""
                for k, v in cm.groupdict().items():
                    if v:
                        new_obj = _safe(v, limit=240)
                        break
                if new_obj:
                    pend.objective = new_obj
                    pend.component = _guess_component(new_obj)
                    pend.desired_outcome = new_obj
                    pend.created_monotonic = mono()
                    # Rotate nonce on correction — old confirm tokens become stale
                    pend.nonce = uuid.uuid4().hex
                    setattr(dialogue_memory, _PENDING, pend)
                    _audit(dialogue_memory, "objective_corrected", objective=new_obj)
                    return CommandResult(
                        handled=True,
                        reply=(
                            f"Am actualizat obiectivul la: {new_obj}. "
                            f"Confirmi analiza read-only a proiectului?"
                        ),
                    )
            # Concurrent new development trigger — do not overwrite unsafely
            if _RE_TRIGGER.match(raw) or _RE_DIRECT.match(raw):
                _audit(dialogue_memory, "concurrent_request_rejected")
                return CommandResult(
                    handled=True,
                    reply=(
                        f"Am deja o cerere de plan în așteptare pentru: {pend.objective}. "
                        f"Spune „da”, „nu”, sau corectează obiectivul — "
                        f"nu pornesc o a doua analiză în paralel."
                    ),
                )
            # Affirm → inspect
            if _CONFIRM_YES.match(raw):
                if pend.nonce in consumed:
                    setattr(dialogue_memory, _PENDING, None)
                    _audit(dialogue_memory, "stale_confirmation_rejected")
                    return CommandResult(
                        handled=True,
                        reply=(
                            "Confirmarea este expirată sau a fost deja folosită. "
                            "Pornește o cerere nouă de plan. "
                            "Nicio modificare nu a fost aplicată."
                        ),
                    )
                # Lazy backend: inject fake in tests; live only after both gates + flag ON
                active_backend = backend
                if active_backend is None:
                    try:
                        from .live_backend import create_live_backend_after_confirm

                        active_backend = create_live_backend_after_confirm(
                            cfg,
                            injected=getattr(cfg, "_h_dev_backend", None),
                        )
                    except Exception as e:
                        setattr(dialogue_memory, _PENDING, None)
                        _audit(dialogue_memory, "plan_blocked", reason=type(e).__name__)
                        return CommandResult(
                            handled=True,
                            reply=(
                                "Nu am putut deschide backend-ul read-only. "
                                "Nicio modificare nu a fost aplicată."
                            ),
                        )
                if active_backend is None:
                    setattr(dialogue_memory, _PENDING, None)
                    _audit(dialogue_memory, "plan_blocked", reason="no_backend")
                    return CommandResult(
                        handled=True,
                        reply=(
                            "Nu am un backend read-only disponibil pentru analiză. "
                            "Nicio modificare nu a fost aplicată."
                        ),
                    )
                pend.inspect_allowed = True
                consumed.add(pend.nonce)
                _audit(dialogue_memory, "request_confirmed", objective=pend.objective)
                try:
                    plan = build_development_plan(
                        objective=pend.objective,
                        component=pend.component,
                        desired_outcome=pend.desired_outcome,
                        constraints=pend.constraints,
                        ambiguous_or_dangerous=pend.ambiguous_or_dangerous,
                        backend=active_backend,
                        consult_g=consult_g,
                        cfg=cfg,
                        now_iso=now_iso,
                        new_id=new_id,
                    )
                except Exception as e:
                    setattr(dialogue_memory, _PENDING, None)
                    _audit(dialogue_memory, "plan_blocked", reason=type(e).__name__)
                    debug_log(f"owner_development plan failed: {e}", "development")
                    return CommandResult(
                        handled=True,
                        reply=(
                            "Nu am putut genera planul (eroare read-only). "
                            "Nicio modificare nu a fost aplicată."
                        ),
                    )
                setattr(dialogue_memory, _PENDING, None)
                setattr(dialogue_memory, _LAST_PLAN, plan)
                if plan.verdict.startswith("BLOCKED") or plan.verdict == DevelopmentVerdict.INSUFFICIENT_CONTEXT:
                    _audit(
                        dialogue_memory,
                        "plan_blocked",
                        verdict=plan.verdict,
                        plan_id=plan.plan_id,
                    )
                else:
                    _audit(
                        dialogue_memory,
                        "plan_generated",
                        verdict=plan.verdict,
                        plan_id=plan.plan_id,
                    )
                if consult_g and plan.g_consultative_notes:
                    _audit(dialogue_memory, "g_consult_requested", plan_id=plan.plan_id)
                return CommandResult(
                    handled=True,
                    reply=format_development_plan(plan),
                )
            # Still waiting for confirm — remind, do not inspect
            return CommandResult(
                handled=True,
                reply=(
                    f"Aștept confirmarea pentru planul: {pend.objective}. "
                    f"Spune „da” pentru analiza read-only, „nu” pentru anulare, "
                    f"sau corectează obiectivul."
                ),
            )

    # Direct apply / skip plan
    if _RE_DIRECT.match(raw):
        _audit(dialogue_memory, "plan_only_refusal")
        return CommandResult(
            handled=True,
            reply=(
                "Phase 1 a modulului H este doar PLAN_ONLY. "
                "Nu pot modifica fișiere, aplica patch-uri, rula shell sau crea commit-uri. "
                "Pot doar pregăti un plan după o cerere explicită de dezvoltare și confirmarea ta. "
                "Nicio modificare nu a fost aplicată."
            ),
        )

    m = _RE_TRIGGER.match(raw)
    if not m:
        return CommandResult(handled=False)

    objective = _extract_objective(m)
    component = _guess_component(objective)
    dangerous = bool(_DANGEROUS.search(objective) or _DANGEROUS.search(raw))
    constraints: List[str] = ["Phase 1 plan-only — zero writes"]
    if "fără rețea" in raw.lower() or "without network" in raw.lower():
        constraints.append("no network")

    setattr(
        dialogue_memory,
        _PENDING,
        DevPending(
            objective=objective,
            component=component,
            desired_outcome=objective,
            constraints=constraints,
            ambiguous_or_dangerous=dangerous or len(objective) < 4,
            created_monotonic=mono(),
        ),
    )
    _audit(dialogue_memory, "trigger_detected", objective=objective, component=component)
    return CommandResult(
        handled=True,
        reply=(
            f"Am înțeles că dorești un plan de dezvoltare pentru: {objective}. "
            f"Confirmi analiza read-only a proiectului?"
        ),
    )
