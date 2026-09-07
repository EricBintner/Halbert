# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Generate the per-run ``halbert_tools.py`` stub module (Hermes
code_execution_tool pattern).

Plain-source Python, zero dependencies, written to a per-run temp dir and
put on ``sys.path`` for the run. One def per tool in ``tool_names`` — the
intersection decides what exists; a tool not in the set physically does not
exist in the module, so the model cannot keep trying it. Every stub routes
through ``_call(name, args)``, the host-side RPC seam
(``tools/script_rpc_host.py``), which dispatches into
``ToolExecutor.execute()`` — the same policy pipeline an interactive tool
call takes (guest allowlist, RoleGate, safety classify, audit; Packet 06's
one non-negotiable).

The seam is injected, not imported: a host that executes the module with
``_call`` already in the namespace keeps its binding (tests use this), and
a module loaded fresh defines a refusing placeholder that the host
overwrites after import. Either way a stub never calls a tool handler
directly.
"""
from __future__ import annotations

from typing import Iterable, Sequence

# F-1(b) ratified: the default stub set is read-only. Write-plane stubs stay
# deferred behind the PACKET-02 lattice gate; extend this only with tools a
# script may call with no side effects beyond the read itself.
DEFAULT_STUB_TOOLS: Sequence[str] = ("recall_memory",)

_TEMPLATE = '''\
"""Halbert agent tools. Generated per run — do not edit.
Every tool call returns dicts (structured results); do not json.loads() them.
Call tools by keyword arguments matching the tool schema.
"""
if "_call" not in globals():
    def _call(name, args):
        raise NotImplementedError("wired by the host at run time")

{defs}
'''

_DEF = '''\


def {name}(**kwargs):
    """Halbert tool `{name}` — returns a structured dict."""
    return _call({name!r}, kwargs)
'''


def generate_stub_module(tool_names: Iterable[str]) -> str:
    """Render the stub module source for exactly the tools named.

    Keyword-only stubs on purpose: the RPC seam takes an args dict, and a
    positional parameter would let a script hand it anything else.
    """
    defs = "".join(_DEF.format(name=t) for t in tool_names)
    return _TEMPLATE.format(defs=defs)