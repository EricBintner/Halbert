# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Host-side RPC seam for ``execute_code`` scripts (Packet 06, Task A2).

The ONLY place a stub call is served. A stub's ``_call(name, args)`` funnels
here, and the host runs the fixed Hermes enforcement order:

    token -> allow-list -> budget -> dispatch -> log

The token is a per-run ``secrets.token_hex(32)`` compared with
``secrets.compare_digest`` (fail closed on empty or non-string). The
allow-list is the caller's decision — the ``execute_code`` handler derives
it per run (read-only stubs for the owner; the executor's own per-call
policy while a guest fronts). Budget is a mutable single-slot counter
consumed only by a *dispatched* call: every refusal (bad token, not
allowed, exhausted) is free, so a script cannot burn its budget probing
the boundary.

``dispatch_hook`` is the integration seam: Phase B wires it to
``ToolExecutor.execute()`` so every existing gate (RoleGate, guest
allowlist, safety classify, audit) runs per call unchanged. ``handle()``
never raises into the script — every failure is an ``{"error": ...}``
dict the script can branch on.

Every handled call logs one structured line: tool name, verdict, budget.
Never the arguments.
"""
from __future__ import annotations

import logging
import secrets
from typing import Callable, Dict, FrozenSet, Iterable, Optional

logger = logging.getLogger("halbert.tools.script_rpc_host")

#: dispatch_hook(name, args) -> result-dict; wired by the execute_code host.
DispatchHook = Callable[[str, Dict], Dict]


class ScriptRpcHost:
    """Per-run gatekeeper between a script's stub calls and the dispatcher."""

    def __init__(self, allowed_tools: Iterable[str], budget: int):
        self._token = secrets.token_hex(32)
        self.allowed_tools: FrozenSet[str] = frozenset(allowed_tools)
        self._budget: list[int] = [max(0, int(budget))]
        self.dispatch_hook: Optional[DispatchHook] = None
        self.calls_dispatched: int = 0

    # -- token ---------------------------------------------------------------

    @property
    def budget_remaining(self) -> int:
        return self._budget[0]

    def issue_token(self) -> str:
        """The run token — but only under an explicit test flag.

        Production never needs the token back: ``bind_call()`` closes over
        it on the host's side of the seam, and the script only ever sees
        ``_call``. Making the read loud keeps a future caller from handing
        the token to script code.
        """
        if not getattr(self, "reveal_token_for_test", False):
            raise RuntimeError(
                "the script token never leaves the host; wire scripts with "
                "bind_call(), not the token"
            )
        return self._token

    def issue_token_for_test(self) -> str:
        """Test convenience: issue_token() with the flag set for you."""
        self.reveal_token_for_test = True
        return self._token

    def bind_call(self) -> Callable[[str, Dict], Dict]:
        """The ``_call`` the generated stub module gets: name + args, sealed
        to this host's token without exposing it."""
        token = self._token

        def _call(name: str, args: Optional[Dict] = None) -> Dict:
            return self.handle(token, name, args or {})

        return _call

    # -- the one serve path ----------------------------------------------------

    def _token_ok(self, token: object) -> bool:
        if not isinstance(token, str) or not token:
            return False
        return secrets.compare_digest(token, self._token)

    def handle(self, token: object, name: str, args: Optional[Dict]) -> Dict:
        """Serve one stub call. Order is fixed; refusals are free and
        structured; the script never sees an exception from here."""
        args = dict(args or {})
        if not self._token_ok(token):
            logger.info("script_rpc refusal=bad_token tool=%s", name)
            return {"error": "invalid script token"}

        if name not in self.allowed_tools:
            logger.info("script_rpc refusal=not_allowed tool=%s", name)
            return {"error": f"{name} is not available in scripts"}

        if self._budget[0] <= 0:
            logger.info(
                "script_rpc refusal=budget tool=%s remaining=%d",
                name, self._budget[0],
            )
            return {
                "error": (
                    f"script tool-call budget is exhausted; {name} was not "
                    f"dispatched — finish with what you have and say so"
                ),
            }

        if self.dispatch_hook is None:
            logger.info("script_rpc refusal=no_hook tool=%s", name)
            return {"error": "script RPC host has no dispatch hook wired"}

        self._budget[0] -= 1
        self.calls_dispatched += 1
        try:
            result = self.dispatch_hook(name, args)
        except Exception as e:  # never raise into the script
            logger.warning("script_rpc dispatch_error tool=%s error=%s", name, e)
            return {"error": f"{name} could not be dispatched: {e}"}
        logger.info(
            "script_rpc dispatched tool=%s budget_delta=-1 remaining=%d",
            name, self._budget[0],
        )
        return result if isinstance(result, Dict) else {"result": result}