"""Shared HTTP helpers for LLM providers (stdlib only)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable


Opener = Callable[[str, bytes | None, float, dict[str, str]], bytes]


def env_key(*names: str) -> str | None:
    for name in names:
        val = os.environ.get(name, "").strip()
        if val:
            return val
    return None


def post_json(
    url: str,
    body: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_sec: float,
    opener: Opener | None = None,
) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    hdrs = {"Content-Type": "application/json", **headers}
    if opener is not None:
        raw = opener(url, data, timeout_sec, hdrs)
        return json.loads(raw.decode("utf-8"))
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"unreachable {url}: {exc.reason}") from exc
