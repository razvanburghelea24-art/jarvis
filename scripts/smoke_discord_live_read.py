"""Discord LIVE phase-1 READ-only smoke. Never prints secrets."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.jarvis.cora_foundation.adapters import AdapterStatus, DiscordAdapter
from src.jarvis.cora_foundation.adapters.discord.live_transport import LiveDiscordTransport
from src.jarvis.cora_foundation.adapters.discord.path import execute_discord_gated
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


def _railway_vars() -> dict:
    # Prefer piped JSON (no railway link required in Core cwd).
    if not sys.stdin.isatty():
        raw_in = sys.stdin.read().strip()
        if raw_in.startswith("{"):
            data = json.loads(raw_in)
            if isinstance(data, dict) and data:
                return data

    railway = (
        shutil.which("railway.cmd")
        or shutil.which("railway")
        or r"C:\Users\Administrator\AppData\Roaming\npm\railway.cmd"
    )
    cwd = os.environ.get("CORA_RAILWAY_CWD") or r"C:\Users\Administrator\NyMods_Project-live"
    raw = subprocess.check_output(
        [railway, "variables", "--json"],
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        shell=False,
    )
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise SystemExit("unexpected railway variables shape")
    return data


def _pick_channel(token: str, guild_id: str) -> tuple[str, str]:
    req = urllib.request.Request(
        f"https://discord.com/api/v10/guilds/{guild_id}/channels",
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "Cora-Discord-Smoke/1",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        chans = json.loads(resp.read().decode())
    text = [c for c in chans if isinstance(c, dict) and c.get("type") == 0]
    if not text:
        raise SystemExit("NO_TEXT_CHANNEL")
    pick = text[0]
    for c in text:
        name = c.get("name") or ""
        if name in ("general", "chat", "cora", "bot-logs", "logs"):
            pick = c
            break
    return str(pick["id"]), str(pick.get("name") or "")


def main() -> int:
    vars_ = _railway_vars()
    token = str(vars_.get("DISCORD_BOT_TOKEN") or "").strip()
    guild = str(vars_.get("DISCORD_GUILD_ID") or "").strip()
    if not token or not guild:
        print(json.dumps({"verdict": "FAIL", "reason": "missing_token_or_guild"}))
        return 2

    channel_id, channel_name = _pick_channel(token, guild)
    live = LiveDiscordTransport(token=token, phase=1)
    report: dict = {
        "adapter": "discord",
        "phase": 1,
        "mode": "READ_ONLY_SMOKE",
        "guild_id": guild,
        "channel_id": channel_id,
        "channel_name": channel_name,
        "cases": [],
    }

    def req(tool: str, payload: dict) -> DispatchRequest:
        return DispatchRequest(
            dispatch_id=DispatchRequest.new_id(),
            plan_id="smoke_dc_p1",
            tool=tool,
            capability="discord.read",
            execution_mode=DispatchExecutionMode.NONE,
            approval_state=ApprovalState.NOT_REQUIRED,
            payload=payload,
            metadata={"smoke": True},
        )

    def ctx(**kw) -> GatewayContext:
        base = dict(
            session_id="smoke",
            workspace_id="ws_smoke",
            session_valid=True,
            workspace_active=True,
            mode=ExecutionMode.LIVE,
            rate_limit_ok=True,
            audit_available=True,
        )
        base.update(kw)
        return GatewayContext(**base)

    r = DiscordAdapter(live).execute(
        req("Discord.list_channels", {"guild_id": guild})
    )
    report["cases"].append(
        {
            "case": "list_channels",
            "ok": r.status == AdapterStatus.SUCCESS,
            "live": bool(r.metadata.get("live")),
            "count": len((r.metadata.get("data") or {}).get("channels") or []),
            "error": r.error,
        }
    )

    r2 = DiscordAdapter(live).execute(
        req("Discord.read_channel", {"channel_id": channel_id})
    )
    report["cases"].append(
        {
            "case": "read_channel",
            "ok": r2.status == AdapterStatus.SUCCESS,
            "live": bool(r2.metadata.get("live")),
            "name": (r2.metadata.get("data") or {}).get("name"),
            "error": r2.error,
        }
    )

    audits: list = []
    out = execute_discord_gated(
        req("Discord.read_channel", {"channel_id": channel_id}),
        ctx(),
        gateway=LiveExecutionGateway(on_audit=lambda d: audits.append(d) or True),
        transport=live,
    )
    report["cases"].append(
        {
            "case": "gated_read",
            "ok": out.allowed
            and out.adapter is not None
            and out.adapter.status == AdapterStatus.SUCCESS,
            "audits": len(audits),
        }
    )

    out2 = execute_discord_gated(
        req("Discord.read_channel", {"channel_id": channel_id}),
        ctx(e_stop=True),
        transport=live,
    )
    report["cases"].append(
        {
            "case": "e_stop_deny",
            "ok": out2.gateway.reason == "E_STOP" and out2.adapter is None,
        }
    )

    ok = all(c["ok"] for c in report["cases"])
    report["verdict"] = "PASS" if ok else "FAIL"
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
