#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P-05 — the receipt's reserved Open-loop line at the SMALL tier (observational).

The seam (collected empirically 2026-09-07): ``test_conversation_budget_
receipt_slot.py::TestReceiptCut::test_a_real_receipt_keeps_its_open_loop_
at_every_tier`` went red during collection — at ModelTier.SMALL the receipt
is rendered through ``receipt_one_liner``'s space-joined path, so the
producer-reserved ``Open loop:`` line stops being the rendered body's own
last line (it is glued onto the end of the ``Last said:`` sentence).

BUT the red only reproduces under wt_pytest's base interpreter.  Under the
project venv (the canonical environment, 2026-09-07 full-suite run: 0
failed / 6233 passed) the SMALL tier keeps the label and the test is
green — the base interpreter's dependency set (token estimator included)
shapes the SMALL budget differently.  The probe drives the production path
(``AgentStateMachine._begin_turn``) and RECORDS what the venv sees; it
fixes nothing and judges nothing.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import bootstrap  # noqa: E402

bootstrap()

from halbert_core.agents.receipt import OPEN_LOOP_LABEL  # noqa: E402
from halbert_core.agents.threads import RECEIPT_ROW_PREFIX  # noqa: E402
from halbert_core.agents.state_machine import AgentStateMachine  # noqa: E402
from halbert_core.agents.states import StateContext  # noqa: E402
from halbert_core.context.assembler import RECEIPT_HEADER  # noqa: E402
from halbert_core.intake.budget import CONTEXT_BUDGETS, ModelTier  # noqa: E402

PROBE_ID = "P-05"

NINE_LINE_RECEIPT = "\n".join([
    "Title: Samba media share",
    "When: 2026-07-14..2026-07-16 · 7 turns",
    "Domains: file sharing, storage",
    "Entities: smbd, /srv/media, /etc/samba/smb.conf, nas-01, media-rw",
    "Started with: set up a samba share for the media library on the NAS",
    "Last said: The share mounts read-write from the laptop now.",
    "Commands: testparm -s (exit 0); systemctl restart smbd (exit 0); "
    "rm -rf /srv/media/tmp-old-transcodes (exit 0)",
    "Files written: /etc/samba/smb.conf; /etc/fstab; /srv/media/.hidden",
    "Open loop: verify the mount survives a reboot.",
])
RECEIPT_ROW_PREFIX = "[Earlier in this subject:"
NINE_LINE_ROW = {"role": "system", "content": f"{RECEIPT_ROW_PREFIX} {NINE_LINE_RECEIPT}]"}
PAD = "and the samba config " * 18


def _turns(n, pad=""):
    rows = []
    for i in range(n):
        rows.append({"role": "user", "content": f"user message number {i} about the share {pad}".strip()})
        rows.append({"role": "assistant", "content": f"assistant reply number {i} about the share {pad}".strip()})
    return rows


class _StubManager:
    def __init__(self, rows):
        self.rows = rows

    def begin_turn(self, text, signals, session_id):
        return SimpleNamespace(
            thread_id="t1", turn_id="turn-1", hint="", recalled=[],
            history=list(self.rows),
        )


def _shape(rows, budget):
    """Drive the production path: AgentStateMachine._begin_turn, as the test does."""
    class _NullLLM:
        max_tokens = 8192
        temperature = 0.7

    agent = AgentStateMachine(llm_client=_NullLLM())
    agent.ctx = StateContext(
        session_id="s", request_id="r", user_query="continue",
        history_budget=budget, thread_manager=_StubManager(rows),
    )

    async def drive():
        async for _ in agent._begin_turn():
            pass

    asyncio.run(drive())
    return agent.ctx.thread_receipt_block


def _receipt_body(block):
    return block[len(RECEIPT_HEADER):].strip()


def main() -> int:
    budget = CONTEXT_BUDGETS[ModelTier.SMALL].conversation
    block = _shape([NINE_LINE_ROW] + _turns(6, PAD), budget)
    body = _receipt_body(block)
    last_line = body.splitlines()[-1] if body.splitlines() else ""
    keeps_label = last_line.startswith(OPEN_LOOP_LABEL)

    # OBSERVED either way: under the venv the SMALL tier keeps the reserved
    # open loop as the body's own last line; under wt_pytest's base
    # interpreter (a different dependency set, incl. the token estimator) the
    # label is flattened into the one-liner and the seam's test goes red.
    print(
        f"PROBE {PROBE_ID} receipt-small-open-loop: OBSERVED -- "
        f"SMALL-tier body's last line keeps {OPEN_LOOP_LABEL!r}: {keeps_label} "
        f"(last line: {last_line!r})"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"PROBE {PROBE_ID} receipt-small-open-loop: HARNESS-ERROR -- {exc!r}")
        raise SystemExit(3)