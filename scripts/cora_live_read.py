"""Cora Live READ CLI — Gateway-gated · phase 1 only · JSON out.

Whitelist ops only. Never writes. Token never printed.
Usage:
  python scripts/cora_live_read.py '{"adapter":"github","op":"read_repo","payload":{"repo":"owner/repo"}}'
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

TOOL = {
    "read_repo": "GitHub.read_repo",
    "list_branches": "GitHub.list_branches",
    "read_pr": "GitHub.read_pr",
    "list_channels": "Discord.list_channels",
    "read_channel": "Discord.read_channel",
    "read_message": "Discord.read_message",
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
    return data


def _out(payload: dict[str, Any], code: int = 0) -> int:
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
            _req(TOOL[op], "github.read", dict(payload)),
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
            _req(TOOL[op], "discord.read", pl),
            _ctx(),
            gateway=LiveExecutionGateway(on_audit=lambda d: audits.append(d.reason) or True),
            transport=transport,
        )
    else:
        return _out(
            {"ok": False, "error": "ADAPTER_NOT_ALLOWED", "allowed": ["github", "discord"]},
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
            "ok": result.allowed and result.adapter is not None and result.adapter.error is None,
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
