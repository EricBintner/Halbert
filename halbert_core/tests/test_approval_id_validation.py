# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""F-C: approval request ids must not reach the filesystem unvalidated.

``request_id`` arrives from a URL and used to reach
``requests_dir / f"{request_id}.json"`` raw — an id carrying ``../`` read
and wrote outside the requests directory. ``validate_approval_id`` is the
refusal; these tests pin the accepted shape and the traversal rejections.
"""
import uuid

import pytest

from halbert_core.approval.engine import (
    ApprovalDecision,
    ApprovalEngine,
    ApprovalRequest,
    InvalidApprovalId,
    validate_approval_id,
)


def test_uuid_shaped_id_accepted():
    rid = str(uuid.uuid4())
    assert validate_approval_id(rid) == rid


def test_urlsafe_token_id_accepted():
    assert validate_approval_id("req_abc-123_XYZ") == "req_abc-123_XYZ"


@pytest.mark.parametrize("bad", [
    "../escape",
    "../../etc/passwd",
    "..",
    "a/b",
    "/absolute",
    "a\\b",
    "with space",
    "with.dot",
    "",
    None,
    "x" * 129,
])
def test_hostile_id_rejected(bad):
    with pytest.raises(InvalidApprovalId):
        validate_approval_id(bad)


def test_get_request_refuses_traversal(tmp_path):
    engine = ApprovalEngine(storage_dir=str(tmp_path))
    with pytest.raises(InvalidApprovalId):
        engine.get_request("../../etc/passwd")


def _request(rid: str) -> ApprovalRequest:
    return ApprovalRequest(
        id=rid, task="t", action="a", reasoning="r", confidence=0.5,
        risk_level="low", system_state={}, affected_resources=[],
    )


def test_save_request_refuses_traversal(tmp_path):
    engine = ApprovalEngine(storage_dir=str(tmp_path))
    with pytest.raises(InvalidApprovalId):
        engine._save_request(_request("../outside"))
    assert not (tmp_path.parent / "outside.json").exists()


def test_save_decision_refuses_traversal(tmp_path):
    engine = ApprovalEngine(storage_dir=str(tmp_path))
    decision = ApprovalDecision(request_id="../outside", approved=True)
    with pytest.raises(InvalidApprovalId):
        engine._save_decision(decision)
    assert not any(p.name.startswith("outside") for p in tmp_path.parent.iterdir())


def test_valid_request_roundtrips(tmp_path):
    engine = ApprovalEngine(storage_dir=str(tmp_path))
    rid = str(uuid.uuid4())
    engine._save_request(_request(rid))
    assert engine.get_request(rid) is not None
