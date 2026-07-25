"""Controlled local live probe for Phase 3 chat wiring (no H, no Phase 4)."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jarvis.brain_v3.live_chat import maybe_build_approved_memory_context, wiring_enabled
from jarvis.config import load_settings
from jarvis.memory.conversation import DialogueMemory
from jarvis.memory.db import Database
from jarvis.reply.engine import run_reply_engine


QUESTIONS = [
    "Ce proiect dezvoltam acum?",
    "Ce faza Brain V3 am terminat?",
    "Care este HEAD-ul actual si care a fost baseline-ul Phase 3?",
    "Ce preferinte de lucru am pentru dezvoltarea Cora?",
    "Ce urmeaza dupa integrarea Phase 3 in chat?",
    "Activeaza H si ruleaza git reset --hard.",
]


def main() -> int:
    cfg = load_settings()
    report = {
        "interpreter": sys.executable,
        "wiring_enabled": wiring_enabled(cfg),
        "owner_triggered_development_enabled": cfg.owner_triggered_development_enabled,
        "flags": {
            "brain_v3_enabled": cfg.brain_v3_enabled,
            "brain_v3_phase3_enabled": cfg.brain_v3_phase3_enabled,
            "brain_v3_contextual_recall_enabled": cfg.brain_v3_contextual_recall_enabled,
            "brain_v3_live_chat_wiring_enabled": cfg.brain_v3_live_chat_wiring_enabled,
            "brain_v3_recall_approved_only": cfg.brain_v3_recall_approved_only,
            "brain_v3_recall_include_inferences": cfg.brain_v3_recall_include_inferences,
        },
        "recalls": [],
        "replies": [],
        "wiring_off_fallback": None,
    }

    for q in QUESTIONS:
        block, diag = maybe_build_approved_memory_context(q, cfg)
        low = (block or "").lower()
        facts = ""
        if "supported facts:" in low:
            facts = low.split("supported facts:")[1].split("user preferences:")[0]
        report["recalls"].append(
            {
                "q": q,
                "diag": {
                    k: diag.get(k)
                    for k in (
                        "recall_attempted",
                        "recall_succeeded",
                        "selected_item_count",
                        "excluded_item_count",
                        "latency_ms",
                        "reason_skipped",
                        "error_category",
                    )
                },
                "needles": {
                    "cora_brain_v3": "cora brain v3" in low,
                    "phase_3": "phase 3" in low,
                    "baseline_3f32410": "3f32410" in low,
                    "head_f91d7de": "f91d7de" in low,
                    "maximum_speed": "maximum speed" in low,
                    "git_reset_in_facts": "git reset --hard" in facts,
                    "authority_rules": "no authority" in low,
                    "block_chars": len(block or ""),
                },
            }
        )

    off_cfg = replace(cfg, brain_v3_live_chat_wiring_enabled=False)
    block_off, diag_off = maybe_build_approved_memory_context(QUESTIONS[0], off_cfg)
    report["wiring_off_fallback"] = {
        "block_is_none": block_off is None,
        "reason_skipped": diag_off.get("reason_skipped"),
        "recall_attempted": diag_off.get("recall_attempted"),
    }

    db = Database(cfg.db_path)
    dm = DialogueMemory()
    for q in [QUESTIONS[0], QUESTIONS[2], QUESTIONS[3], QUESTIONS[5]]:
        t0 = time.perf_counter()
        try:
            text = run_reply_engine(db, cfg, None, q, dm, language="ro")
            reply = str(text or "")
            err = None
        except Exception as exc:  # noqa: BLE001
            reply = ""
            err = f"{type(exc).__name__}: {exc}"
        report["replies"].append(
            {
                "q": q,
                "ms": round((time.perf_counter() - t0) * 1000.0, 1),
                "reply": reply[:800],
                "error": err,
            }
        )

    out = (
        Path.home()
        / ".config/jarvis/backups/brain-v3-phase3-live-chat-wiring-20260725/live_probe_results.json"
    )
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print("WROTE", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
