"""Owner-triggered internet research (Phase 4 · Section F wiring).

Two explicit gates before anything is durable:
  1. Owner confirms the research subject → then (and only then) the limited
     search provider may touch the network.
  2. Owner separately accepts memorisation → State Memory readback → confirm.

No scheduler, no background polling, no auto-learning. Page text is UNTRUSTED
DATA and is always passed through :class:`InternetLearningPipeline` before any
claim is shown as saveable.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse

from .commands import CommandResult, _CONFIRM_NO, _CONFIRM_YES
from .internet_learning import InternetLearningPipeline
from .safety import scrub_lesson_text

try:
    from ...debug import debug_log
except Exception:  # pragma: no cover
    def debug_log(*_a, **_k):  # type: ignore
        return None

__all__ = [
    "try_internet_research_command",
    "ResearchSearchProvider",
    "LimitedWebResearchProvider",
    "DEFAULT_TOPIC_ALLOWLIST",
    "PENDING_TTL_SEC",
]

# Pending slots on dialogue_memory (in-process only — restart clears them).
_PENDING_RESEARCH = "_pending_internet_research"
_PENDING_MEM_OFFER = "_pending_internet_memorize_offer"

PENDING_TTL_SEC = 5 * 60

# Educational / encyclopedic topics — fail-closed; owner-confirmed subjects
# also inject their own content tokens into the allowlist for that run.
DEFAULT_TOPIC_ALLOWLIST = [
    "python", "astronomy", "geography", "history", "science", "technology",
    "chess", "landmarks", "mountains", "planet", "earth", "sun", "moon",
    "ocean", "animal", "plant", "math", "physics", "chemistry", "biology",
    "space", "nasa", "health", "medicine", "language", "music", "art",
    "sport", "climate", "weather", "computer", "software", "internet",
    "everest", "paris", "rome", "wikipedia", "helium", "mercury",
]

# Browser-like UA (same family as WebSearchTool) — Wikimedia/DDG reject exotic
# agents with 403. This is NOT the owner's authenticated browser profile: no
# cookies, no session store, GET-only.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
    "CoraResearch/1.0"
)

# Explicit research verbs — must be owner utterance, not mid-quote injection.
_RE_TRIGGER = re.compile(
    r"(?is)^\s*(?:cora[,:\s]+)?(?:te\s+rog[,:\s]+)?"
    r"(?:"
    r"caut[aă]\s+(?:pe\s+)?(?:internet|online|web)\b|"
    r"cerceteaz[aă]\b|"
    r"verific[aă]\s+online\b|"
    r"compar[aă]\s+surse(?:\s+despre)?\b|"
    r"documenteaz[aă]-?te(?:\s+despre)?\b|"
    r"[iî]nva[țţ][aă]\s+despre\b|"
    r"search\s+(?:the\s+)?(?:web|internet)\s+for\b|"
    r"research\b|"
    r"look\s+up\b"
    r")"
    r"\s*(?P<subject>.+?)\s*$"
)

_RE_CORRECT_SUBJECT = re.compile(
    r"(?is)^\s*(?:"
    r"nu[,:]?\s*(?:caut[aă]|cerceteaz[aă]|despre)\s+(?P<s1>.+)|"
    r"corecteaz[aă]\s*(?:subiectul\s*)?[:,]?\s*(?P<s2>.+)|"
    r"subiectul\s+(?:e|este)\s+(?P<s3>.+)"
    r")\s*$"
)

_WORD_RE = re.compile(r"[0-9a-zăâîșțáéíóúäöü]+", re.UNICODE)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _tokens(text: str) -> List[str]:
    return _WORD_RE.findall((text or "").lower())


def _clean_subject(raw: str) -> str:
    s = scrub_lesson_text((raw or "").strip(" .,;:\"'"))
    # Strip leading prepositions left by "cercetează despre X" / "research about X"
    s = re.sub(
        r"(?is)^\s*(?:despre|about|for|on|regarding|re)\s+",
        "",
        s,
    ).strip()
    # Strip trailing polite fluff
    s = re.sub(r"(?i)\s+te\s+rog\.?\s*$", "", s).strip()
    return s[:200]


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_AGGREGATOR_DOMAINS = frozenset({
    "duckduckgo.com", "google.com", "bing.com", "yahoo.com", "yandex.com",
})


def _compress_claim(query: str, text: str, *, max_len: int = 280) -> str:
    """Pick 1–2 query-relevant sentences so IL grouping can corroborate."""
    qtoks = {t for t in _tokens(query) if len(t) >= 3}
    body = (text or "").strip()
    if not body:
        return ""
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(body) if s.strip()]
    if not sentences:
        sentences = [body]
    scored: List[Tuple[int, int, str]] = []
    for s in sentences:
        if len(s) < 20:
            continue
        stoks = set(_tokens(s))
        overlap = len(qtoks & stoks)
        has_num = 1 if re.search(r"\d", s) else 0
        scored.append((overlap * 2 + has_num, -len(s), s))
    scored.sort(reverse=True)
    if not scored:
        return body[:max_len]
    picked = [scored[0][2]]
    if len(scored) > 1 and scored[1][0] >= max(1, scored[0][0] - 1):
        picked.append(scored[1][2])
    return " ".join(picked)[:max_len]


def _align_for_corroboration(
    query: str, results: Sequence[Dict[str, str]]
) -> List[Dict[str, str]]:
    """Compress claims and align identical text across domains that share a
    value signature (or high token overlap). Provenance URLs stay distinct so
    InternetLearningPipeline can mark ≥2 independent sources as saveable."""
    from .internet_learning import _registrable_domain, _value_sig

    prepared: List[Dict[str, Any]] = []
    for r in results or []:
        if not isinstance(r, dict):
            continue
        url = str(r.get("url") or "").strip()
        domain = _registrable_domain(url)
        if not domain or domain in _AGGREGATOR_DOMAINS:
            continue
        text = _compress_claim(query, str(r.get("text") or ""))
        if len(text) < 20:
            continue
        prepared.append({
            "url": url,
            "title": str(r.get("title") or "")[:300],
            "text": text,
            "raw": str(r.get("text") or ""),
            "_domain": domain,
            "_vsig": _value_sig(text) or "",
        })

    if len(prepared) < 2:
        return [{"url": x["url"], "title": x["title"], "text": x["text"]}
                for x in prepared]

    by_sig: Dict[str, List[Dict[str, Any]]] = {}
    for item in prepared:
        by_sig.setdefault(item["_vsig"] or "__qual__", []).append(item)

    out: List[Dict[str, str]] = []
    emitted: set = set()

    def _emit_aligned(items: List[Dict[str, Any]], canon: str) -> None:
        seen_d: set = set()
        for it in items:
            d = it["_domain"]
            if d in seen_d or it["url"] in emitted:
                continue
            seen_d.add(d)
            emitted.add(it["url"])
            out.append({"url": it["url"], "title": it["title"], "text": canon})

    # Prefer numeric value signatures first (strongest corroboration signal).
    for sig, items in sorted(
        by_sig.items(), key=lambda kv: (kv[0] == "__qual__", -len(kv[1]))
    ):
        domains = {i["_domain"] for i in items}
        if sig and sig != "__qual__" and len(domains) >= 2:
            canon = min((i["text"] for i in items), key=len)
            _emit_aligned(items, canon)

    # Anchor corroboration: Instant-style short claim supported by another
    # page's raw body (e.g. wiki abstract + RSC page both about atomic number).
    remaining = [i for i in prepared if i["url"] not in emitted]
    if len({i["_domain"] for i in remaining}) >= 2:
        # Prefer wikipedia/britannica-sized seeds (usually Instant abstracts).
        def _seed_rank(i: Dict[str, Any]) -> Tuple[int, int]:
            d = i["_domain"]
            boost = 0
            if "wikipedia.org" in d:
                boost = 2
            elif "britannica.com" in d:
                boost = 1
            return (-boost, len(i["text"]))

        seeds = sorted(remaining, key=_seed_rank)
        for seed in seeds:
            seed_body = (seed.get("raw") or seed["text"]).lower()
            hard_anchors: List[str] = []
            soft_anchors: List[str] = []
            for m in re.finditer(r"(?i)\batomic number\s+(\d+)\b", seed_body):
                hard_anchors.append(f"atomic number {m.group(1)}")
                soft_anchors.append("atomic number")
            if re.search(r"(?i)\bchemical element\b", seed_body):
                soft_anchors.append("chemical element")
                soft_anchors.append("element")
            if re.search(r"(?i)\bhighest mountain\b", seed_body):
                soft_anchors.append("highest mountain")
            for m in re.finditer(
                r"(\d+(?:[.,]\d+)?)\s*(m|meters?|ft|feet|km)\b",
                seed_body,
                re.I,
            ):
                hard_anchors.append(m.group(0).lower())
            if not hard_anchors and not soft_anchors:
                continue
            cohort = [seed]
            for i in remaining:
                if i["url"] == seed["url"] or i["_domain"] == seed["_domain"]:
                    continue
                body = (i.get("raw") or i["text"]).lower()
                ok = False
                if hard_anchors and any(a in body for a in hard_anchors):
                    ok = True
                elif soft_anchors:
                    # Require the strongest soft cue + query token in body.
                    qtoks = {t for t in _tokens(query) if len(t) >= 3}
                    if any(a in body for a in soft_anchors) and (
                        not qtoks or any(t in body for t in qtoks)
                    ):
                        ok = True
                if ok:
                    cohort.append(i)
            if len({i["_domain"] for i in cohort}) >= 2:
                canon = _compress_claim(
                    query, seed.get("raw") or seed["text"], max_len=220
                )
                if len(canon) >= 20:
                    _emit_aligned(cohort, canon)
                    break

    # Qualitative: align only empty-signature claims with high token overlap.
    # Never merge items that already carry distinct numeric value signatures
    # (those are contradictions, not corroboration).
    qtoks = {t for t in _tokens(query) if len(t) >= 3}
    qual = [
        i for i in prepared
        if i["url"] not in emitted and not i["_vsig"]
    ]
    if len({i["_domain"] for i in qual}) >= 2:
        seeds = sorted(
            (
                i for i in qual
                if len(set(_tokens(i["text"])) & qtoks) >= min(2, max(1, len(qtoks)))
            ),
            key=lambda i: len(i["text"]),
        )
        if seeds:
            seed = seeds[0]
            seed_toks = set(_tokens(seed["text"]))
            cohort = [seed]
            for i in qual:
                if i["url"] == seed["url"]:
                    continue
                itoks = set(_tokens(i["text"]))
                if not seed_toks or not itoks:
                    continue
                jacc = len(seed_toks & itoks) / len(seed_toks | itoks)
                if jacc >= 0.35 and i["_domain"] != seed["_domain"]:
                    cohort.append(i)
            if len({i["_domain"] for i in cohort}) >= 2:
                _emit_aligned(cohort, seed["text"])

    # Keep remaining unique-domain results as incomplete single-source claims.
    for i in prepared:
        if i["url"] in emitted:
            continue
        emitted.add(i["url"])
        out.append({"url": i["url"], "title": i["title"], "text": i["text"]})
    return out


def _secondary_site_queries(query: str) -> List[str]:
    """Extra discovery queries aimed at trusted encyclopedic domains."""
    q = (query or "").strip()
    if not q:
        return []
    return [
        f"{q} site:rsc.org",
        f"{q} site:nasa.gov",
        f"{q} site:nih.gov",
        f"{q} site:britannica.com",
        f"{q} site:edu",
    ]


def _trusted_fallback_urls(query: str, instant_text: str, instant_title: str) -> List[str]:
    """Deterministic https second-sources when discovery is rate-limited."""
    out: List[str] = []
    body = f"{instant_title}\n{instant_text}"
    m = re.search(r"(?i)\batomic number\s+(\d+)\b", body)
    if m:
        z = m.group(1)
        name = (instant_title or query or "").strip().split()[0].lower()
        name = re.sub(r"[^a-z]", "", name)
        if name and len(name) >= 3:
            out.append(f"https://periodic-table.rsc.org/element/{z}/{name}")
            out.append(f"https://www.rsc.org/periodic-table/element/{z}/{name}")
    return out


@dataclass
class _ResearchPending:
    subject: str
    created_monotonic: float
    nonce: str


@dataclass
class _MemorizeOffer:
    claim_text: str
    subject_key: str
    sources_line: str
    created_monotonic: float
    nonce: str


class ResearchSearchProvider:
    """Callable protocol for limited research fetches (injectable in tests)."""

    def search(self, query: str, *, max_results: int = 5) -> List[Dict[str, str]]:
        raise NotImplementedError


class LimitedWebResearchProvider(ResearchSearchProvider):
    """Reuse DuckDuckGo/Wikipedia + SSRF guards from ``web_search``.

    No API key required. https-only, public hosts only, redirect re-validated,
    byte-capped page reads, no cookies / POST / JS execution.
    """

    def __init__(
        self,
        *,
        timeout_sec: float = 8.0,
        max_results: int = 5,
        max_pages: int = 3,
        max_chars: int = 4000,
    ) -> None:
        self.timeout_sec = float(timeout_sec)
        self.max_results = max(1, int(max_results))
        self.max_pages = max(1, int(max_pages))
        self.max_chars = max(200, int(max_chars))

    def search(self, query: str, *, max_results: int = 5) -> List[Dict[str, str]]:
        query = (query or "").strip()
        if not query:
            return []
        limit = min(self.max_results, max(1, int(max_results)))
        try:
            from ...tools.builtin.web_search import _is_public_url
        except Exception as e:
            debug_log(f"research provider import failed: {e}", "research")
            return []

        self._instant_snippets = []  # type: ignore[attr-defined]
        pairs = self._discover_urls(query, limit=max(limit, 8))
        out: List[Dict[str, str]] = []
        seen_domains: set[str] = set()

        def _domain_of(url: str) -> str:
            try:
                from .internet_learning import _registrable_domain
                return _registrable_domain(url) or ""
            except Exception:
                try:
                    return (urlparse(url).hostname or "").lower().removeprefix("www.")
                except Exception:
                    return ""

        def _trust_rank(url: str) -> int:
            host = (urlparse(url).hostname or "").lower()
            score = 0
            for frag, pts in (
                ("wikipedia.org", 100),
                ("britannica.com", 95),
                ("rsc.org", 90),
                ("nih.gov", 90),
                ("nasa.gov", 85),
                ("nature.com", 80),
                ("science.org", 80),
                (".edu", 70),
                (".gov", 70),
                (".int", 65),
            ):
                if frag in host:
                    score = max(score, pts)
            # Deprioritize product / code forges when researching encyclopedia topics
            for frag in ("github.com", ".computer", "amazon.", "helium10.", "/download"):
                if frag in host or frag in url.lower():
                    score -= 40
            return score

        # Prefer DDG Instant Abstract snippet (no HTML; Wikimedia pages often 403).
        for snip in getattr(self, "_instant_snippets", []) or []:
            url = str(snip.get("url") or "")
            if not self._is_https_public(url, _is_public_url):
                continue
            host = _domain_of(url)
            if host in _AGGREGATOR_DOMAINS:
                continue
            text = self._strip_chrome(str(snip.get("text") or ""))
            if len(text) < 40:
                continue
            if any(r["url"] == url for r in out):
                continue
            out.append({
                "url": url,
                "title": str(snip.get("title") or url),
                "text": text[: self.max_chars],
            })
            if host:
                seen_domains.add(host)
            # Do not early-return on Instant alone — need ≥2 domains when possible.
            if len(out) >= limit and len(seen_domains) >= 2:
                return _align_for_corroboration(query, out[:limit])

        # Fetch highest-trust remaining URLs first (Britannica/RSC before product sites).
        pairs = sorted(pairs, key=lambda pt: -_trust_rank(pt[1]))
        pages_fetched = 0
        instant_vsig = ""
        if out:
            try:
                from .internet_learning import _value_sig
                instant_vsig = _value_sig(out[0].get("text") or "") or ""
            except Exception:
                instant_vsig = ""

        for title, url in pairs:
            if len(out) >= limit or pages_fetched >= self.max_pages:
                break
            if not self._is_https_public(url, _is_public_url):
                continue
            host = _domain_of(url)
            if not host or host in _AGGREGATOR_DOMAINS:
                continue
            if host in seen_domains:
                continue
            if any(r["url"] == url for r in out):
                continue
            if _trust_rank(url) < 0 and len(seen_domains) >= 1:
                # Already have Instant; skip low-trust product pages unless desperate
                if pages_fetched + 1 >= self.max_pages and len(out) >= 1:
                    continue
                if _trust_rank(url) < -20:
                    continue
            text = self._fetch_https(url, _is_public_url)
            pages_fetched += 1
            if not text:
                continue
            text = self._strip_chrome(text)
            if len(text) < 40:
                continue
            low = text.lower()
            if "incapsula" in low or "request unsuccessful" in low or "anomaly-modal" in low:
                continue
            # If Instant already asserted a numeric fact, prefer pages that
            # mention the same numbers (avoids "Helium browser" pollution).
            if instant_vsig:
                try:
                    from .internet_learning import _value_sig
                    page_sig = _value_sig(text) or ""
                except Exception:
                    page_sig = ""
                # Keep page if it shares at least one numeric token with Instant
                inst_nums = set(instant_vsig.replace("|NEG", "").split("|")) - {""}
                page_nums = set(page_sig.replace("|NEG", "").split("|")) - {""}
                if inst_nums and not (inst_nums & page_nums) and _trust_rank(url) < 60:
                    continue
            out.append({"url": url, "title": title or url, "text": text[: self.max_chars]})
            seen_domains.add(host)
            # Count only successful adds against the page budget.
            # (pages_fetched already incremented above — leave as-is for cap)

        # Secondary trusted-site discovery when Instant alone is not enough.
        # Own budget so primary noise cannot starve corroboration.
        if len(seen_domains) < 2:
            extra_pairs: List[Tuple[str, str]] = []
            for sq in _secondary_site_queries(query):
                try:
                    extra_pairs.extend(self._discover_urls(sq, limit=5))
                except Exception:
                    continue
            extra_pairs = sorted(extra_pairs, key=lambda pt: -_trust_rank(pt[1]))
            secondary_fetches = 0
            for title, url in extra_pairs:
                if len(out) >= limit or secondary_fetches >= max(2, self.max_pages):
                    break
                if not self._is_https_public(url, _is_public_url):
                    continue
                host = _domain_of(url)
                if not host or host in _AGGREGATOR_DOMAINS or host in seen_domains:
                    continue
                if _trust_rank(url) < 50:
                    continue
                text = self._fetch_https(url, _is_public_url)
                secondary_fetches += 1
                if not text:
                    continue
                text = self._strip_chrome(text)
                if len(text) < 40:
                    continue
                out.append({
                    "url": url, "title": title or url, "text": text[: self.max_chars],
                })
                seen_domains.add(host)
                if len(seen_domains) >= 2:
                    break

        # Deterministic trusted fallback when discovery was rate-limited.
        if len(seen_domains) < 2 and out:
            seed = out[0]
            for url in _trusted_fallback_urls(
                query, seed.get("text") or "", seed.get("title") or ""
            ):
                if len(out) >= limit:
                    break
                if not self._is_https_public(url, _is_public_url):
                    continue
                host = _domain_of(url)
                if not host or host in seen_domains or host in _AGGREGATOR_DOMAINS:
                    continue
                text = self._fetch_https(url, _is_public_url)
                if not text:
                    continue
                text = self._strip_chrome(text)
                if len(text) < 40:
                    continue
                out.append({
                    "url": url,
                    "title": seed.get("title") or url,
                    "text": text[: self.max_chars],
                })
                seen_domains.add(host)
                if len(seen_domains) >= 2:
                    break

        if len(seen_domains) < 2 or len(out) < 2:
            wiki = self._wikipedia(query)
            if wiki and self._is_https_public(wiki["url"], _is_public_url):
                wh = _domain_of(wiki["url"])
                if wiki["url"] not in {r["url"] for r in out}:
                    if not wh or wh not in seen_domains or len(out) < 2:
                        if wh not in _AGGREGATOR_DOMAINS:
                            out.append(wiki)
        return _align_for_corroboration(query, out[:limit])

    @staticmethod
    def _strip_chrome(text: str) -> str:
        """Drop common site chrome so claims aren't navigation boilerplate."""
        lines = []
        skip_prefixes = (
            "jump to content", "from wikipedia", "this article", "jump to",
            "main menu", "search", "donate", "create account", "log in",
            "contents", "hide", "toggle",
        )
        for ln in (text or "").split("\n"):
            low = ln.strip().lower()
            if not low or len(low) < 20:
                continue
            if any(low.startswith(p) for p in skip_prefixes):
                continue
            if low in ("edit", "view history", "tools"):
                continue
            lines.append(ln.strip())
        return "\n".join(lines)

    @staticmethod
    def _is_https_public(url: str, is_public) -> bool:
        try:
            p = urlparse(url)
        except Exception:
            return False
        if p.scheme != "https":
            return False
        return bool(is_public(url))

    def _fetch_https(self, url: str, is_public) -> Optional[str]:
        """Mirror web_search redirect walk but enforce https on every hop."""
        import requests

        if not self._is_https_public(url, is_public):
            return None
        try:
            headers = {
                "User-Agent": _USER_AGENT,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
            current = url
            response = None
            for _ in range(4):
                response = requests.get(
                    current, headers=headers, timeout=self.timeout_sec,
                    allow_redirects=False, stream=True,
                )
                if response.is_redirect or response.is_permanent_redirect:
                    nxt = response.headers.get("Location", "")
                    response.close()
                    if not nxt:
                        return None
                    nxt = urljoin(current, nxt)
                    if not self._is_https_public(nxt, is_public):
                        debug_log(f"research refusing redirect: {nxt}", "research")
                        return None
                    current = nxt
                    continue
                break
            if response is None:
                return None
            response.raise_for_status()
            chunks: List[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                chunks.append(chunk)
                total += len(chunk)
                if total >= 512 * 1024:
                    break
            body = b"".join(chunks)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(body, "html.parser")
            for el in soup(["script", "style", "meta", "link", "noscript",
                            "nav", "footer", "header", "aside"]):
                el.decompose()
            text = soup.get_text(separator="\n", strip=True)
            lines = [ln.strip() for ln in text.split("\n")
                     if ln.strip() and len(ln.strip()) > 3]
            content = "\n".join(lines)
            if len(content) > self.max_chars:
                content = content[: self.max_chars] + "..."
            return content or None
        except Exception as e:
            debug_log(f"research fetch failed: {e}", "research")
            return None

    def _discover_urls(self, query: str, *, limit: int) -> List[Tuple[str, str]]:
        import requests

        found: List[Tuple[str, str]] = []
        snippets: List[Dict[str, str]] = []
        self._instant_snippets = snippets  # type: ignore[attr-defined]
        try:
            r = requests.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": "1",
                        "skip_disambig": "1"},
                headers={"User-Agent": _USER_AGENT},
                timeout=min(5.0, self.timeout_sec),
            )
            if r.status_code == 200:
                data = r.json() or {}
                abs_url = str(data.get("AbstractURL") or "").strip()
                abs_text = str(data.get("Abstract") or "").strip()
                heading = str(data.get("Heading") or "DuckDuckGo").strip()
                if abs_url and abs_text:
                    found.append((heading, abs_url))
                    # Instant Abstract only — RelatedTopics often point at
                    # duckduckgo.com stubs that are not independent sources.
                    snippets.append({
                        "url": abs_url, "title": heading,
                        "text": abs_text[: self.max_chars],
                    })
                for rel in data.get("RelatedTopics") or []:
                    if not isinstance(rel, dict):
                        continue
                    topics = rel.get("Topics") if isinstance(rel.get("Topics"), list) else [rel]
                    for topic in topics:
                        if not isinstance(topic, dict):
                            continue
                        u = str(topic.get("FirstURL") or "").strip()
                        txt = str(topic.get("Text") or "").strip()
                        if not u or not txt:
                            continue
                        try:
                            host = (urlparse(u).hostname or "").lower()
                        except Exception:
                            host = ""
                        if "duckduckgo.com" in host or "google.com" in host:
                            continue
                        found.append((txt[:80], u))
                        if len(found) >= limit:
                            break
        except Exception:
            pass

        try:
            from bs4 import BeautifulSoup
            url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}"
            r = requests.get(
                url, headers={"User-Agent": _USER_AGENT},
                timeout=min(10.0, self.timeout_sec),
            )
            body = r.content or b""
            if (r.status_code in (202, 400, 429)
                    or b"anomaly-modal" in body or b"anomaly.js" in body):
                debug_log("research: DDG bot-challenge", "research")
            elif r.status_code == 200:
                soup = BeautifulSoup(body, "html.parser")
                for link in soup.find_all("a", href=True):
                    if len(found) >= limit:
                        break
                    href = link.get("href", "")
                    title = (link.get_text() or "").strip()
                    actual = href
                    if href.startswith("//duckduckgo.com/l/") and "uddg=" in href:
                        try:
                            qs = parse_qs(urlparse(href).query)
                            if "uddg" in qs:
                                from urllib.parse import unquote
                                actual = unquote(qs["uddg"][0])
                        except Exception:
                            actual = href
                    if not actual.startswith("http"):
                        continue
                    try:
                        host = (urlparse(actual).hostname or "").lower()
                    except Exception:
                        host = ""
                    if any(a in host for a in ("duckduckgo.com", "google.com", "bing.com")):
                        continue
                    if "/y.js" in actual or "ad_domain=" in actual:
                        continue
                    if len(title) < 10:
                        continue
                    if any(s in title.lower() for s in ("settings", "privacy", "about", "help")):
                        continue
                    found.append((title, actual))
        except Exception as e:
            debug_log(f"research DDG lite failed: {e}", "research")
        return found[:limit]

    def _wikipedia(self, query: str) -> Optional[Dict[str, str]]:
        import requests
        try:
            api = "https://en.wikipedia.org/w/api.php"
            r = requests.get(
                api,
                params={
                    "action": "query", "list": "search", "srsearch": query,
                    "srlimit": 1, "format": "json",
                },
                headers={"User-Agent": _USER_AGENT},
                timeout=min(6.0, self.timeout_sec),
            )
            r.raise_for_status()
            hits = (((r.json() or {}).get("query") or {}).get("search") or [])
            if not hits:
                return None
            title = str(hits[0].get("title") or "").strip()
            if not title:
                return None
            s = requests.get(
                "https://en.wikipedia.org/api/rest_v1/page/summary/"
                + quote_plus(title.replace(" ", "_")),
                headers={"User-Agent": _USER_AGENT},
                timeout=min(6.0, self.timeout_sec),
            )
            s.raise_for_status()
            data = s.json() or {}
            extract = str(data.get("extract") or "").strip()
            page_url = str(
                (data.get("content_urls") or {}).get("desktop", {}).get("page")
                or data.get("url")
                or f"https://en.wikipedia.org/wiki/{quote_plus(title.replace(' ', '_'))}"
            )
            if not extract:
                return None
            extract = self._strip_chrome(extract) or extract
            return {
                "url": page_url,
                "title": str(data.get("title") or title),
                "text": extract[: self.max_chars],
            }
        except Exception as e:
            debug_log(f"research wikipedia failed: {e}", "research")
            return None


def _allowlist_for(subject: str) -> List[str]:
    base = list(DEFAULT_TOPIC_ALLOWLIST)
    for tok in _tokens(subject):
        if len(tok) >= 3 and tok not in base:
            base.append(tok)
    return base


def _format_research_reply(
    *,
    subject: str,
    candidates,
    pipe: InternetLearningPipeline,
    researched_at: str,
) -> Tuple[str, Optional[_MemorizeOffer]]:
    if not candidates:
        return (
            f"Am căutat despre „{subject}”, dar nu am putut aduna surse suficiente "
            f"sau rețeaua a fost indisponibilă. Nu am memorat nimic.\n"
            f"(cercetare: {researched_at})",
            None,
        )

    saveable = [c for c in candidates if pipe.is_saveable(c)]
    incomplete = [c for c in candidates if c.needs_more_sources]
    contradicted = [c for c in candidates if c.contradicted]

    lines: List[str] = [f"Rezumat cercetare — „{subject}”:"]
    if saveable:
        lines.append("Confirmat (coroborat din ≥2 surse independente):")
        for c in saveable[:3]:
            lines.append(f"• {c.claim_text}")
    if contradicted:
        lines.append("Contradicții (nesigure — nu pot fi memorate ca fapt):")
        for c in contradicted[:3]:
            lines.append(f"• {c.claim_text}")
    if incomplete and not saveable:
        lines.append("Incomplet (o singură sursă / insuficient — nesaveable):")
        for c in incomplete[:3]:
            lines.append(f"• {c.claim_text}")

    # Provenance list (deduped URLs)
    urls: List[str] = []
    for c in candidates:
        for p in c.provenance or []:
            u = str(p.get("source_url") or "").strip()
            if u and u not in urls:
                urls.append(u)
    if urls:
        lines.append("Surse:")
        for u in urls[:6]:
            lines.append(f"- {u}")
    lines.append(f"Cercetare: {researched_at}")
    lines.append(
        "Informațiile de pe internet se pot învechi — nu le-am învățat permanent."
    )

    offer: Optional[_MemorizeOffer] = None
    if saveable:
        best = saveable[0]
        sources_line = "; ".join(urls[:4])
        lines.append("Dorești să memorez această informație confirmată?")
        offer = _MemorizeOffer(
            claim_text=best.claim_text,
            subject_key=best.subject_key,
            sources_line=sources_line,
            created_monotonic=time.monotonic(),
            nonce=uuid.uuid4().hex,
        )
    else:
        lines.append(
            "Nu am un fapt suficient coroborat pentru memorare confirmată."
        )
    return "\n".join(lines), offer


def _run_research(
    subject: str,
    *,
    provider: ResearchSearchProvider,
    pipe_factory: Callable[..., InternetLearningPipeline],
) -> Tuple[str, Optional[_MemorizeOffer]]:
    allow = _allowlist_for(subject)
    pipe = pipe_factory(
        enabled=True,
        topic_allowlist=allow,
        min_sources=2,
        max_results=5,
    )
    plan = pipe.plan_research(subject)
    if plan is None:
        return (
            f"Subiectul „{subject}” nu trece allowlist-ul de cercetare. "
            f"Nu am deschis rețeaua și nu am memorat nimic.",
            None,
        )
    try:
        results = provider.search(subject, max_results=plan.max_results)
    except Exception as e:
        debug_log(f"research provider error: {e}", "research")
        results = []
    researched_at = _utc_now_iso()
    # Oversized body defence: truncate each result text hard, then align
    # corroborating claims across independent domains for the IL pipeline.
    safe_results = []
    for r in results or []:
        if not isinstance(r, dict):
            continue
        text = str(r.get("text") or "")[:4000]
        safe_results.append({
            "url": str(r.get("url") or ""),
            "title": str(r.get("title") or "")[:300],
            "text": text,
        })
    safe_results = _align_for_corroboration(subject, safe_results)
    cands = pipe.ingest_results(subject, safe_results)
    return _format_research_reply(
        subject=subject, candidates=cands, pipe=pipe, researched_at=researched_at,
    )


def try_internet_research_command(
    text: str,
    *,
    cfg,
    dialogue_memory,
    state_store=None,
    conversation_id: str = "interactive",
    provider: Optional[ResearchSearchProvider] = None,
    pipe_factory: Optional[Callable[..., InternetLearningPipeline]] = None,
    now_monotonic: Optional[Callable[[], float]] = None,
) -> CommandResult:
    """Handle owner-triggered research + dual confirmation gates.

    Gated by the caller on ``internet_learning_enabled``. Never opens the
    network until the owner affirms the pending research subject.
    """
    raw = (text or "").strip()
    if not raw or dialogue_memory is None:
        return CommandResult(handled=False)
    if not bool(getattr(cfg, "internet_learning_enabled", False)):
        return CommandResult(handled=False)

    mono = now_monotonic or time.monotonic
    provider = provider or LimitedWebResearchProvider()
    pipe_factory = pipe_factory or InternetLearningPipeline

    # --- Gate 2 offer: memorize after research (before new triggers) -------
    offer = getattr(dialogue_memory, _PENDING_MEM_OFFER, None)
    if isinstance(offer, _MemorizeOffer):
        if mono() - offer.created_monotonic > PENDING_TTL_SEC:
            setattr(dialogue_memory, _PENDING_MEM_OFFER, None)
            # fall through — expired offer ignored
        elif _CONFIRM_NO.match(raw):
            setattr(dialogue_memory, _PENDING_MEM_OFFER, None)
            return CommandResult(
                handled=True,
                reply="În regulă — nu memorez rezultatul cercetării.",
            )
        elif _CONFIRM_YES.match(raw):
            setattr(dialogue_memory, _PENDING_MEM_OFFER, None)
            if state_store is None:
                return CommandResult(
                    handled=True,
                    reply="State Memory nu este disponibil — nu am memorat.",
                )
            try:
                item_id = state_store.add_candidate(
                    "web_fact",
                    offer.subject_key,
                    offer.claim_text,
                    source=f"internet_research:{offer.sources_line}"[:240],
                    conversation_id=conversation_id,
                    provenance="web_research",
                    confidence=0.9,
                    actor="user",
                )
                if item_id is None:
                    return CommandResult(
                        handled=True, reply="Nu pot pregăti memorarea acestui rezultat.",
                    )
                state_store.promote_to_pending(item_id)
            except Exception:
                return CommandResult(
                    handled=True, reply="Nu am putut pregăti memorarea.",
                )
            setattr(
                dialogue_memory,
                "_pending_state_memorize",
                (item_id, offer.claim_text, "memorize"),
            )
            return CommandResult(
                handled=True,
                reply=(
                    f"Să memorez „{offer.claim_text}”? "
                    f"Spune da pentru confirmare sau nu pentru anulare."
                ),
            )
        else:
            return CommandResult(
                handled=True,
                reply=(
                    "Dorești să memorez informația confirmată din cercetare? "
                    "Spune da sau nu."
                ),
            )

    # --- Gate 1: pending research confirmation -----------------------------
    pend = getattr(dialogue_memory, _PENDING_RESEARCH, None)
    if isinstance(pend, _ResearchPending):
        if mono() - pend.created_monotonic > PENDING_TTL_SEC:
            setattr(dialogue_memory, _PENDING_RESEARCH, None)
            return CommandResult(
                handled=True,
                reply="Cererea de cercetare a expirat. Spune din nou ce să caut.",
            )

        m_corr = _RE_CORRECT_SUBJECT.match(raw)
        if m_corr:
            new_subj = _clean_subject(
                m_corr.group("s1") or m_corr.group("s2") or m_corr.group("s3") or ""
            )
            if not new_subj:
                return CommandResult(
                    handled=True,
                    reply=f"Confirmă cercetarea despre „{pend.subject}”: da / nu, sau corectează subiectul.",
                )
            pend.subject = new_subj
            pend.created_monotonic = mono()
            setattr(dialogue_memory, _PENDING_RESEARCH, pend)
            return CommandResult(
                handled=True,
                reply=(
                    f"Voi căuta informații despre: {new_subj}. "
                    f"Confirmi cercetarea online?"
                ),
            )

        if _CONFIRM_NO.match(raw):
            setattr(dialogue_memory, _PENDING_RESEARCH, None)
            return CommandResult(
                handled=True,
                reply="Am anulat — nu am deschis rețeaua și nu am memorat nimic.",
            )

        if _CONFIRM_YES.match(raw):
            setattr(dialogue_memory, _PENDING_RESEARCH, None)
            reply, mem_offer = _run_research(
                pend.subject, provider=provider, pipe_factory=pipe_factory,
            )
            if mem_offer is not None:
                setattr(dialogue_memory, _PENDING_MEM_OFFER, mem_offer)
            return CommandResult(handled=True, reply=reply)

        return CommandResult(
            handled=True,
            reply=(
                f"Voi căuta informații despre: {pend.subject}. "
                f"Confirmi cercetarea online? (da / nu / corectează subiectul)"
            ),
        )

    # --- New trigger -------------------------------------------------------
    m = _RE_TRIGGER.match(raw)
    if not m:
        return CommandResult(handled=False)

    subject = _clean_subject(m.group("subject") or "")
    if len(subject) < 3:
        return CommandResult(
            handled=True,
            reply="Spune mai clar ce să cercetez pe internet.",
        )

    # Concurrent: refuse starting a second research while one is pending
    # (already handled above). Also refuse if memorize offer is open.
    if getattr(dialogue_memory, _PENDING_MEM_OFFER, None) is not None:
        return CommandResult(
            handled=True,
            reply=(
                "Am încă o ofertă de memorare din cercetarea anterioară. "
                "Răspunde da sau nu înainte de o nouă căutare."
            ),
        )

    setattr(
        dialogue_memory,
        _PENDING_RESEARCH,
        _ResearchPending(
            subject=subject,
            created_monotonic=mono(),
            nonce=uuid.uuid4().hex,
        ),
    )
    return CommandResult(
        handled=True,
        reply=(
            f"Voi căuta informații despre: {subject}. "
            f"Confirmi cercetarea online?"
        ),
    )
