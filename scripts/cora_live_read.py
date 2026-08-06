"""Cora Live READ CLI — Gateway-gated · phase 1 only · JSON out.

Whitelist ops only. Never writes. Token never printed.
Usage:
  python scripts/cora_live_read.py '{"adapter":"github","op":"read_repo","payload":{"repo":"owner/repo"}}'
  python scripts/cora_live_read.py '{"adapter":"n8n","op":"list_workflows","payload":{}}'
  echo '{...}' | python scripts/cora_live_read.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.jarvis.cora_foundation.adapters.discord.live_transport import LiveDiscordTransport
from src.jarvis.cora_foundation.adapters.discord.path import execute_discord_gated
from src.jarvis.cora_foundation.adapters.github.live_transport import LiveGitHubTransport
from src.jarvis.cora_foundation.adapters.github.path import execute_github_gated
from src.jarvis.cora_foundation.adapters.n8n.flags import n8n_api_base
from src.jarvis.cora_foundation.adapters.n8n.live_transport import LiveN8NTransport
from src.jarvis.cora_foundation.adapters.n8n.path import execute_n8n_gated
from src.jarvis.cora_foundation.dispatcher import (
    ApprovalState,
    DispatchExecutionMode,
    DispatchRequest,
)
from src.jarvis.cora_foundation.live_gateway import (
    ExecutionMode,
    GatewayContext,
    LiveExecutionGateway,
)

GITHUB_OPS = frozenset({"read_repo", "list_branches", "read_pr"})
DISCORD_OPS = frozenset({"list_channels", "read_channel", "read_message"})
N8N_OPS = frozenset(
    {
        "list_workflows",
        "workflow_status",
        "workflow_info",
        "inspect_workflow",
        "execution_status",
        "execution_logs",
    }
)

TOOL = {
    "read_repo": "GitHub.read_repo",
    "list_branches": "GitHub.list_branches",
    "read_pr": "GitHub.read_pr",
    "list_channels": "Discord.list_channels",
    "read_channel": "Discord.read_channel",
    "read_message": "Discord.read_message",
    "list_workflows": "n8n.list_workflows",
    "workflow_status": "n8n.workflow_status",
    "workflow_info": "n8n.workflow_info",
    "inspect_workflow": "n8n.workflow_info",
    "execution_status": "n8n.execution_status",
    "execution_logs": "n8n.execution_logs",
}

CAPABILITY = {
    "github": "github.read",
    "discord": "discord.read",
    "n8n": "n8n.read",
}


def _slim_data(adapter: str, op: str, data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    if adapter == "github" and op == "read_repo":
        keys = ("full_name", "private", "default_branch", "html_url", "description", "live")
        return {k: data[k] for k in keys if k in data}
    if adapter == "github" and op == "list_branches":
        items = data.get("branches") or data.get("items") or []
        names = [
            (b.get("name") if isinstance(b, dict) else str(b)) for b in items[:20]
        ]
        return {"branches": names, "count": len(items), "live": data.get("live")}
    if adapter == "discord" and op == "list_channels":
        items = data.get("channels") or data.get("items") or []
        slim = [
            {"id": c.get("id"), "name": c.get("name")}
            for c in items[:30]
            if isinstance(c, dict)
        ]
        return {"channels": slim, "count": len(items), "live": data.get("live")}
    if adapter == "discord" and op == "read_channel":
        keys = ("id", "name", "type", "guild_id", "live")
        return {k: data[k] for k in keys if k in data}
    if adapter == "n8n" and op == "list_workflows":
        items = data.get("data") or data.get("items") or data.get("workflows") or []
        if isinstance(data.get("data"), dict) and isinstance(data["data"].get("workflows"), list):
            items = data["data"]["workflows"]
        slim = []
        for w in items[:40]:
            if not isinstance(w, dict):
                continue
            slim.append(
                {
                    "id": w.get("id"),
                    "name": w.get("name"),
                    "active": w.get("active"),
                    "updatedAt": w.get("updatedAt") or w.get("updated_at"),
                }
            )
        return {"workflows": slim, "count": len(items), "live": data.get("live")}
    if adapter == "n8n" and op in {"workflow_status", "workflow_info", "inspect_workflow"}:
        wf = data
        if isinstance(data.get("data"), dict) and (
            "nodes" in data["data"] or "name" in data["data"]
        ):
            wf = {**data, **data["data"]}
        return _workflow_intelligence(wf)
    if adapter == "n8n" and op in {"execution_status", "execution_logs"}:
        items = data.get("data") or data.get("items") or data.get("results") or []
        if isinstance(items, list):
            slim = []
            for ex in items[:15]:
                if not isinstance(ex, dict):
                    continue
                slim.append(
                    {
                        "id": ex.get("id"),
                        "workflowId": ex.get("workflowId") or ex.get("workflow_id"),
                        "status": ex.get("status") or ex.get("finished"),
                        "mode": ex.get("mode"),
                        "startedAt": ex.get("startedAt") or ex.get("started_at"),
                        "stoppedAt": ex.get("stoppedAt") or ex.get("stopped_at"),
                    }
                )
            return {"executions": slim, "count": len(items), "live": data.get("live")}
        keys = (
            "id",
            "workflowId",
            "status",
            "mode",
            "startedAt",
            "stoppedAt",
            "finished",
            "live",
            "operation",
        )
        return {k: data[k] for k in keys if k in data}
    return data


_TRIGGER_HINTS = (
    "webhook",
    "cron",
    "schedule",
    "manualtrigger",
    "interval",
    "emailtrigger",
    "chattrigger",
)


def _node_service(node_type: str) -> str | None:
    t = (node_type or "").lower()
    for key, label in (
        ("github", "GitHub"),
        ("discord", "Discord"),
        ("slack", "Slack"),
        ("openai", "OpenAI"),
        ("http", "HTTP"),
        ("railway", "Railway"),
        ("postgres", "Postgres"),
        ("mysql", "MySQL"),
        ("redis", "Redis"),
        ("webhook", "Webhook"),
    ):
        if key in t:
            return label
    return None


def _approx_chain(nodes: list[dict[str, Any]], connections: dict[str, Any]) -> list[str]:
    by_name = {
        str(n.get("name") or ""): n for n in nodes if isinstance(n, dict) and n.get("name")
    }
    # Build adjacency from connections: { fromName: { main: [[{node, type, index}]] } }
    outs: dict[str, list[str]] = {}
    for src, buckets in (connections or {}).items():
        if not isinstance(buckets, dict):
            continue
        dests: list[str] = []
        for _port, groups in buckets.items():
            if not isinstance(groups, list):
                continue
            for group in groups:
                if not isinstance(group, list):
                    continue
                for edge in group:
                    if isinstance(edge, dict) and edge.get("node"):
                        dests.append(str(edge["node"]))
        if dests:
            outs[str(src)] = dests

    starts = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        ntype = str(n.get("type") or "").lower()
        if any(h in ntype for h in _TRIGGER_HINTS):
            starts.append(str(n.get("name") or ntype))
    if not starts and nodes:
        starts = [str(nodes[0].get("name") or "start")]

    chain: list[str] = []
    seen: set[str] = set()
    queue = list(starts)
    while queue and len(chain) < 24:
        cur = queue.pop(0)
        if cur in seen:
            continue
        seen.add(cur)
        node = by_name.get(cur)
        label = cur
        if node:
            short = str(node.get("type") or "").split(".")[-1]
            label = f"{cur} ({short})" if short else cur
        chain.append(label)
        for nxt in outs.get(cur, []):
            if nxt not in seen:
                queue.append(nxt)
    return chain


def _workflow_intelligence(wf: dict[str, Any]) -> dict[str, Any]:
    """Summarize real n8n definition — not name-guess."""
    nodes_raw = wf.get("nodes") if isinstance(wf.get("nodes"), list) else []
    connections = wf.get("connections") if isinstance(wf.get("connections"), dict) else {}
    settings = wf.get("settings") if isinstance(wf.get("settings"), dict) else {}
    meta = wf.get("meta") if isinstance(wf.get("meta"), dict) else {}

    nodes_slim = []
    triggers = []
    external: list[str] = []
    for n in nodes_raw[:60]:
        if not isinstance(n, dict):
            continue
        name = str(n.get("name") or "node")
        ntype = str(n.get("type") or "")
        nodes_slim.append({"name": name, "type": ntype})
        if any(h in ntype.lower() for h in _TRIGGER_HINTS):
            triggers.append({"name": name, "type": ntype})
        svc = _node_service(ntype)
        if svc and svc not in external:
            external.append(svc)

    return {
        "id": wf.get("id"),
        "name": wf.get("name"),
        "active": wf.get("active"),
        "updatedAt": wf.get("updatedAt") or wf.get("updated_at"),
        "live": wf.get("live", True),
        "source": "definition",
        "description": settings.get("notes") or meta.get("description"),
        "triggers": triggers,
        "nodes": nodes_slim,
        "node_count": len(nodes_raw),
        "chain": _approx_chain(
            [n for n in nodes_raw if isinstance(n, dict)], connections
        ),
        "external": external,
        "operation": "inspect_workflow",
    }


def _match_workflow_id(items: list[Any], query: str) -> str | None:
    q = (query or "").strip().lower()
    if not q:
        return None
    scored: list[tuple[int, str]] = []
    for w in items:
        if not isinstance(w, dict):
            continue
        name = str(w.get("name") or "")
        wid = str(w.get("id") or "")
        nl = name.lower()
        score = 0
        if nl == q:
            score = 100
        elif q in nl:
            score = 80
        else:
            tokens = [t for t in q.replace("—", " ").replace("-", " ").split() if len(t) > 2]
            hits = sum(1 for t in tokens if t in nl)
            if hits:
                score = 40 + hits * 10
        if score:
            scored.append((score, wid))
    scored.sort(key=lambda x: -x[0])
    return scored[0][1] if scored else None


def _out(payload: dict[str, Any], code: int = 0) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    print(json.dumps(payload, ensure_ascii=False))
    return code


def _token_github() -> str:
    for key in ("CORA_GITHUB_TOKEN", "GITHUB_TOKEN"):
        v = os.environ.get(key, "").strip()
        if v:
            return v
    try:
        raw = subprocess.check_output(
            ["gh", "auth", "token"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
        return raw.strip()
    except Exception:
        return ""


def _railway_vars() -> dict[str, Any]:
    railway = (
        shutil.which("railway.cmd")
        or shutil.which("railway")
        or r"C:\Users\Administrator\AppData\Roaming\npm\railway.cmd"
    )
    cwd = os.environ.get("CORA_RAILWAY_CWD") or r"C:\Users\Administrator\NyMods_Project-live"
    try:
        raw = subprocess.check_output(
            [railway, "variables", "--json"],
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=cwd,
            timeout=30,
        )
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _token_discord() -> tuple[str, str]:
    tok = (
        os.environ.get("CORA_DISCORD_TOKEN", "").strip()
        or os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    )
    guild = os.environ.get("DISCORD_GUILD_ID", "").strip()
    if tok:
        return tok, guild
    vars_ = _railway_vars()
    return (
        str(vars_.get("DISCORD_BOT_TOKEN") or "").strip(),
        str(vars_.get("DISCORD_GUILD_ID") or guild or "").strip(),
    )


def _token_n8n() -> tuple[str, str]:
    tok = (
        os.environ.get("CORA_N8N_TOKEN", "").strip()
        or os.environ.get("N8N_API_KEY", "").strip()
    )
    base = (
        os.environ.get("CORA_N8N_API_BASE", "").strip()
        or os.environ.get("OWNER_BRIEF_N8N_BASE", "").strip()
        or "https://nymodsbot.app.n8n.cloud/api/v1"
    )
    if tok:
        return tok, base.rstrip("/")
    vars_ = _railway_vars()
    tok = str(vars_.get("N8N_API_KEY") or vars_.get("CORA_N8N_TOKEN") or "").strip()
    base = (
        str(vars_.get("CORA_N8N_API_BASE") or vars_.get("N8N_API_BASE") or base)
        .strip()
        .rstrip("/")
    )
    return tok, base


def _req(tool: str, capability: str, payload: dict[str, Any]) -> DispatchRequest:
    return DispatchRequest(
        dispatch_id=DispatchRequest.new_id(),
        plan_id="live_read_cli",
        tool=tool,
        capability=capability,
        execution_mode=DispatchExecutionMode.NONE,
        approval_state=ApprovalState.NOT_REQUIRED,
        payload=payload,
        metadata={"live_read": True, "phase": 1},
    )


def _ctx() -> GatewayContext:
    return GatewayContext(
        session_id="live_read",
        workspace_id="ws_live_read",
        session_valid=True,
        workspace_active=True,
        mode=ExecutionMode.LIVE,
        rate_limit_ok=True,
        audit_available=True,
    )


def _load_input() -> dict[str, Any]:
    if len(sys.argv) > 1 and sys.argv[1].strip().startswith("{"):
        return json.loads(sys.argv[1])
    raw = sys.stdin.read().strip()
    if not raw:
        raise SystemExit(_out({"ok": False, "error": "missing_json_input"}, 2))
    return json.loads(raw)


def main() -> int:
    try:
        inp = _load_input()
    except json.JSONDecodeError:
        return _out({"ok": False, "error": "invalid_json"}, 2)

    adapter = str(inp.get("adapter") or "").strip().lower()
    op = str(inp.get("op") or "").strip().lower()
    payload = inp.get("payload") if isinstance(inp.get("payload"), dict) else {}

    if adapter == "github":
        if op not in GITHUB_OPS:
            return _out(
                {"ok": False, "error": "OP_NOT_ALLOWED", "allowed": sorted(GITHUB_OPS)},
                3,
            )
        tok = _token_github()
        if not tok:
            return _out({"ok": False, "error": "GITHUB_TOKEN_MISSING"}, 4)
        audits: list = []
        transport = LiveGitHubTransport(token=tok, phase=1)
        result = execute_github_gated(
            _req(TOOL[op], CAPABILITY["github"], dict(payload)),
            _ctx(),
            gateway=LiveExecutionGateway(on_audit=lambda d: audits.append(d.reason) or True),
            transport=transport,
        )
    elif adapter == "discord":
        if op not in DISCORD_OPS:
            return _out(
                {"ok": False, "error": "OP_NOT_ALLOWED", "allowed": sorted(DISCORD_OPS)},
                3,
            )
        tok, guild = _token_discord()
        if not tok:
            return _out({"ok": False, "error": "DISCORD_TOKEN_MISSING"}, 4)
        pl = dict(payload)
        if op == "list_channels" and not pl.get("guild_id") and guild:
            pl["guild_id"] = guild
        audits = []
        transport = LiveDiscordTransport(token=tok, phase=1)
        result = execute_discord_gated(
            _req(TOOL[op], CAPABILITY["discord"], pl),
            _ctx(),
            gateway=LiveExecutionGateway(on_audit=lambda d: audits.append(d.reason) or True),
            transport=transport,
        )
    elif adapter == "n8n":
        if op not in N8N_OPS:
            return _out(
                {"ok": False, "error": "OP_NOT_ALLOWED", "allowed": sorted(N8N_OPS)},
                3,
            )
        tok, api_base = _token_n8n()
        if not tok:
            return _out({"ok": False, "error": "N8N_TOKEN_MISSING"}, 4)
        os.environ.setdefault("CORA_N8N_API_BASE", api_base)
        audits = []
        transport = LiveN8NTransport(
            token=tok, phase=1, api_base=api_base or n8n_api_base()
        )
        pl = dict(payload)
        # Resolve name → id for inspect / info / status
        if op in {"inspect_workflow", "workflow_info", "workflow_status"} and not str(
            pl.get("workflow_id") or ""
        ).strip():
            q = str(
                pl.get("name_query")
                or pl.get("name")
                or pl.get("query")
                or pl.get("workflow_name")
                or ""
            ).strip()
            if q:
                listed = transport.list_workflows(payload={})
                items: list[Any] = []
                if listed.ok and isinstance(listed.data, dict):
                    raw_items = (
                        listed.data.get("data")
                        or listed.data.get("items")
                        or listed.data.get("workflows")
                        or []
                    )
                    if isinstance(listed.data.get("data"), dict):
                        inner = listed.data["data"]
                        if isinstance(inner.get("workflows"), list):
                            raw_items = inner["workflows"]
                    if isinstance(raw_items, list):
                        items = raw_items
                wid = _match_workflow_id(items, q)
                if not wid:
                    return _out(
                        {
                            "ok": False,
                            "error": "WORKFLOW_NOT_FOUND",
                            "query": q,
                            "write": False,
                        },
                        5,
                    )
                pl["workflow_id"] = wid
        # inspect_workflow uses same READ tool as workflow_info
        tool_key = "workflow_info" if op == "inspect_workflow" else op
        result = execute_n8n_gated(
            _req(TOOL[tool_key], CAPABILITY["n8n"], pl),
            _ctx(),
            gateway=LiveExecutionGateway(on_audit=lambda d: audits.append(d.reason) or True),
            transport=transport,
        )
    else:
        return _out(
            {
                "ok": False,
                "error": "ADAPTER_NOT_ALLOWED",
                "allowed": ["github", "discord", "n8n"],
            },
            3,
        )

    adapter_payload = None
    if result.adapter is not None:
        raw_data = result.adapter.metadata.get("data")
        adapter_payload = {
            "status": result.adapter.status.value,
            "operation": result.adapter.operation,
            "external_id": result.adapter.external_id,
            "error": result.adapter.error,
            "live": bool(result.adapter.metadata.get("live")),
            "data": _slim_data(adapter, op, raw_data),
            "duration": result.adapter.duration,
        }

    return _out(
        {
            "ok": result.allowed
            and result.adapter is not None
            and result.adapter.error is None,
            "adapter": adapter,
            "op": op,
            "phase": 1,
            "gateway": {
                "decision": result.gateway.decision.value,
                "reason": result.gateway.reason,
                "mode": result.gateway.mode.value,
            },
            "audits": audits,
            "result": adapter_payload,
            "write": False,
        },
        0 if result.allowed else 1,
    )


if __name__ == "__main__":
    raise SystemExit(main())
