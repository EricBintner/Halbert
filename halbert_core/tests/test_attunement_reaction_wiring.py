# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The surfaces where a person reacts call the ledger (A-HB-26, §2.2).

Three routes carry a human's answer to something Halbert said: snooze,
dismiss, and asking for the fix. These tests pin that each one labels the
attempt, that the reaction kinds stay distinct, and — the part that matters
most — that a ledger which is unavailable never costs the user their
dismissal.
"""

import pytest

import halbert_core.dashboard.routes.being as being_routes
import halbert_core.dashboard.routes.findings as findings_routes


class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, reaction, finding_id):
        self.calls.append((reaction, finding_id))
        return True


@pytest.fixture
def noted(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(being_routes, "note", rec)
    monkeypatch.setattr(findings_routes, "note", rec)
    return rec


@pytest.fixture
def findings(tmp_path, monkeypatch):
    from halbert_core.findings.store import Finding, FindingStore

    store = FindingStore(db_path=str(tmp_path / "findings.db"))
    store.add(Finding(
        id="f-1", detector="d", severity="warning", title="t", description="d",
        why_now="n", why_care="c", why_so="s",
    ))
    monkeypatch.setattr(being_routes, "FindingStore", lambda *a, **kw: store)
    monkeypatch.setattr(findings_routes, "_finding_store", lambda: store)
    return store


@pytest.mark.asyncio
async def test_snoozing_records_not_now(noted, findings):
    await being_routes.snooze_event("f-1", being_routes.SnoozeRequest(days=3))

    assert noted.calls == [("not_now", "f-1")]


@pytest.mark.asyncio
async def test_dismissing_records_dismissed(noted, findings):
    await being_routes.dismiss_event(
        "f-1", being_routes.DismissRequest(reason="not relevant")
    )

    assert noted.calls == [("dismissed", "f-1")]


def test_asking_for_the_fix_records_engaged(noted, findings, monkeypatch):
    class _Generator:
        def generate_for_finding(self, finding_id):
            return "p-1"

    class _Proposals:
        def get(self, proposal_id):
            return None

    monkeypatch.setattr(findings_routes, "_proposal_store", lambda: _Proposals())
    monkeypatch.setattr(
        findings_routes, "_proposal_generator", lambda fs, ps: _Generator()
    )

    findings_routes.propose_fix("f-1")

    assert noted.calls == [("engaged", "f-1")]


@pytest.mark.asyncio
async def test_a_ledger_that_is_down_does_not_cost_the_user_the_dismissal(
    monkeypatch, findings
):
    """The reaction is the secondary effect here. Losing it is a gap in the
    evidence; losing the dismissal is a bug the person sees.

    Guarded at the call site rather than only inside `note`, so the safety
    is structural and does not rest on a downstream contract holding.
    """
    def _explode(*a, **kw):
        raise RuntimeError("ledger gone")

    monkeypatch.setattr(being_routes, "note", _explode)

    result = await being_routes.dismiss_event(
        "f-1", being_routes.DismissRequest(reason="x")
    )

    assert result["dismissed"] is True
    assert findings.get("f-1").status == "dismissed"


def test_note_swallows_a_broken_ledger(monkeypatch):
    """`note` is the seam the routes call, and it is the one that must not
    raise — the test above shows what it would cost if it did."""
    import halbert_core.attunement.reactions as reactions

    monkeypatch.setattr(reactions, "default_reactions", lambda: None)
    assert reactions.note("dismissed", "f-1") is False
