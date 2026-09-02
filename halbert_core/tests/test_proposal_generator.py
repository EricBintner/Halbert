# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the proposal generator pipeline (T5b.3 gaps).

ApprovalEngine and WriteConfig are MOCKED — no real approval prompts and
no real config writes. chmod changes do touch temp files (by design, with
audit logging patched out).
"""

import os
import shutil
import tempfile
from types import SimpleNamespace
from unittest import mock

import pytest

from halbert_core.findings.store import FindingStore, Finding, FindingStatus
from halbert_core.findings.proposals import ProposalStore, Proposal, ProposalStatus
from halbert_core.findings.proposal_generator import (
    ProposalGenerator,
    handle_approval_decision,
)
from halbert_core.tools.base import ToolRequest


@pytest.fixture
def tmpdir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def db_path(tmpdir):
    return os.path.join(tmpdir, "findings.db")


@pytest.fixture
def fstore(db_path):
    return FindingStore(db_path=db_path)


@pytest.fixture
def pstore(db_path):
    return ProposalStore(db_path=db_path)


@pytest.fixture
def approval_engine():
    engine = mock.MagicMock()
    return engine


@pytest.fixture
def write_config():
    wc = mock.MagicMock()
    wc.execute.return_value = SimpleNamespace(
        request_id="r", ok=True, error=None, outputs={"diff": "", "applied": True}
    )
    return wc


@pytest.fixture
def blast():
    b = mock.MagicMock()
    b.calculate_multi.return_value = ["sshd.service"]
    return b


@pytest.fixture
def generator(fstore, pstore, approval_engine, write_config, blast):
    return ProposalGenerator(
        finding_store=fstore,
        proposal_store=pstore,
        approval_engine=approval_engine,
        write_config=write_config,
        blast_radius=blast,
    )


def _make_finding(fstore, detector="permissions_hygiene", affected_paths=None):
    return fstore.add(Finding(
        id="",
        detector=detector,
        severity="warning",
        title="Test finding",
        description="desc",
        why_now="now",
        why_care="care",
        why_so="evidence",
        affected_paths=affected_paths or [],
    ))


def _ssh_key(tmpdir, name="id_rsa", mode=0o644):
    ssh_dir = os.path.join(tmpdir, ".ssh")
    os.makedirs(ssh_dir, exist_ok=True)
    path = os.path.join(ssh_dir, name)
    with open(path, "w") as f:
        f.write("key\n")
    os.chmod(path, mode)
    return path


class TestGenerate:
    def test_generate_queues_pending_approval(self, generator, pstore, approval_engine, tmpdir):
        key = _ssh_key(tmpdir)
        fid = _make_finding(generator.findings, affected_paths=[key])

        pid = generator.generate_for_finding(fid)
        assert pid is not None

        # Proposal PENDING (never auto-rejected/approved)
        proposal = pstore.get(pid)
        assert proposal.status == ProposalStatus.PENDING.value
        assert proposal.approval_request_id is not None

        # Approval request QUEUED, not decided synchronously
        approval_engine.queue_request.assert_called_once()
        approval_engine.request_approval.assert_not_called()

        queued = approval_engine.queue_request.call_args[0][0]
        assert queued.id == proposal.approval_request_id
        assert queued.status == "pending"
        assert queued.task == "Apply config change"
        assert queued.reasoning == "evidence"
        # affected_resources = blast radius + affected paths
        assert "sshd.service" in queued.affected_resources
        assert key in queued.affected_resources
        assert queued.simulation_result is not None

    def test_dry_run_covers_all_changes(self, generator, pstore, approval_engine, tmpdir):
        k1 = _ssh_key(tmpdir, "id_rsa")
        k2 = _ssh_key(tmpdir, "id_ed25519")
        fid = _make_finding(generator.findings, affected_paths=[k1, k2])

        pid = generator.generate_for_finding(fid)
        proposal = pstore.get(pid)
        assert len(proposal.changes) == 2
        assert len(proposal.dry_run_result["changes"]) == 2

    def test_no_fix_returns_none(self, generator, approval_engine):
        fid = _make_finding(generator.findings, detector="unknown_detector")
        assert generator.generate_for_finding(fid) is None
        approval_engine.queue_request.assert_not_called()

    def test_missing_finding_returns_none(self, generator):
        assert generator.generate_for_finding("nonexistent") is None


class TestHandleApprovalDecision:
    def test_unlinked_request_is_noop(self, generator):
        result = handle_approval_decision("no-such-request", True, generator=generator)
        assert result["linked"] is False

    def test_reject_marks_rejected_with_real_reason(self, generator, pstore, tmpdir):
        key = _ssh_key(tmpdir)
        fid = _make_finding(generator.findings, affected_paths=[key])
        pid = generator.generate_for_finding(fid)
        req_id = pstore.get(pid).approval_request_id

        result = handle_approval_decision(req_id, False, "too risky", generator=generator)
        assert result["status"] == ProposalStatus.REJECTED.value
        assert result["reason"] == "too risky"

        proposal = pstore.get(pid)
        assert proposal.status == ProposalStatus.REJECTED.value
        assert proposal.rejection_reason == "too risky"
        # Nothing executed: file mode untouched
        assert (os.stat(key).st_mode & 0o777) == 0o644

    def test_approve_chmod_applies_and_resolves_finding(self, generator, pstore, fstore, tmpdir):
        key = _ssh_key(tmpdir)
        fid = _make_finding(generator.findings, affected_paths=[key])
        pid = generator.generate_for_finding(fid)
        req_id = pstore.get(pid).approval_request_id

        with mock.patch("halbert_core.obs.audit.write_audit", return_value=""):
            result = handle_approval_decision(req_id, True, generator=generator)

        assert result["status"] == ProposalStatus.APPLIED.value
        assert (os.stat(key).st_mode & 0o777) == 0o600

        proposal = pstore.get(pid)
        assert proposal.status == ProposalStatus.APPLIED.value
        assert fstore.get(fid).status == FindingStatus.RESOLVED.value

    def test_multi_change_applies_all(self, generator, pstore, tmpdir):
        k1 = _ssh_key(tmpdir, "id_rsa")
        k2 = _ssh_key(tmpdir, "id_ed25519")
        fid = _make_finding(generator.findings, affected_paths=[k1, k2])
        pid = generator.generate_for_finding(fid)
        req_id = pstore.get(pid).approval_request_id

        with mock.patch("halbert_core.obs.audit.write_audit", return_value=""):
            result = handle_approval_decision(req_id, True, generator=generator)

        assert result["status"] == ProposalStatus.APPLIED.value
        assert len(result["applied"]) == 2
        assert (os.stat(k1).st_mode & 0o777) == 0o600
        assert (os.stat(k2).st_mode & 0o777) == 0o600

    def test_approve_config_change_uses_write_config(
        self, generator, pstore, fstore, write_config
    ):
        fid = _make_finding(fstore, detector="custom")
        # Craft a config-file change proposal directly
        pid = pstore.add(Proposal(
            id="",
            finding_id=fid,
            action="Set directive",
            changes=[
                {
                    "path": "/etc/ssh/sshd_config.d/10-port.conf",
                    "action": "set_directive",
                    "config_changes": {"SSHD": {"Port": "22"}},
                },
                {
                    "path": "/etc/ssh/sshd_config.d/20-pubkey.conf",
                    "action": "set_directive",
                    "config_changes": {"SSHD": {"PubkeyAuthentication": "yes"}},
                },
            ],
        ))
        pstore.link_approval(pid, "req-cfg-1")

        result = handle_approval_decision("req-cfg-1", True, generator=generator)
        assert result["status"] == ProposalStatus.APPLIED.value

        # WriteConfig.execute called once per change, apply mode + backup
        assert write_config.execute.call_count == 2
        for call in write_config.execute.call_args_list:
            req = call[0][0]
            assert isinstance(req, ToolRequest)
            assert req.dry_run is False
            assert req.confirm is True
            assert req.inputs["backup"] is True

        assert pstore.get(pid).status == ProposalStatus.APPLIED.value
        assert fstore.get(fid).status == FindingStatus.RESOLVED.value

    def test_execution_failure_rolls_back(
        self, generator, pstore, fstore, write_config
    ):
        fid = _make_finding(fstore, detector="custom")
        pid = pstore.add(Proposal(
            id="",
            finding_id=fid,
            action="Set directive",
            changes=[{
                "path": "/etc/ssh/sshd_config.d/10.conf",
                "action": "set_directive",
                "config_changes": {"SSHD": {"Port": "22"}},
            }],
        ))
        pstore.link_approval(pid, "req-fail-1")

        ok_resp = SimpleNamespace(
            request_id="r", ok=True, error=None, outputs={"applied": True}
        )
        fail_resp = SimpleNamespace(
            request_id="r", ok=False, error="disk full", outputs={}
        )
        write_config.execute.side_effect = [fail_resp, ok_resp]  # apply fails, rollback ok

        result = handle_approval_decision("req-fail-1", True, generator=generator)
        assert result["status"] == ProposalStatus.ROLLED_BACK.value
        assert result["error"] == "disk full"

        # Second call was the rollback request
        assert write_config.execute.call_count == 2
        rollback_req = write_config.execute.call_args_list[1][0][0]
        assert rollback_req.inputs["rollback"] is True

        proposal = pstore.get(pid)
        assert proposal.status == ProposalStatus.ROLLED_BACK.value
        assert proposal.execution_result.get("error") == "disk full"
        # Finding NOT resolved on rollback
        assert fstore.get(fid).status != FindingStatus.RESOLVED.value

    def test_chmod_drift_skipped_with_warning(self, generator, pstore, tmpdir, caplog):
        key = _ssh_key(tmpdir, mode=0o644)
        fid = _make_finding(generator.findings, affected_paths=[key])
        pid = generator.generate_for_finding(fid)  # records expected 0o644
        req_id = pstore.get(pid).approval_request_id

        # Drift: someone changes the mode after generation
        os.chmod(key, 0o640)

        with mock.patch("halbert_core.obs.audit.write_audit", return_value=""):
            with caplog.at_level("WARNING"):
                result = handle_approval_decision(req_id, True, generator=generator)

        assert result["skipped"]
        assert "drift" in result["skipped"][0]["message"]
        # Mode left untouched
        assert (os.stat(key).st_mode & 0o777) == 0o640
        assert any("drift" in r.message for r in caplog.records)
        # No failure → proposal still applied
        assert result["status"] == ProposalStatus.APPLIED.value

    def test_chmod_failure_rolls_back_restoring_old_modes(
        self, generator, pstore, tmpdir
    ):
        k1 = _ssh_key(tmpdir, "id_rsa", mode=0o644)
        k2 = os.path.join(tmpdir, ".ssh", "id_gone")  # will vanish before apply
        with open(k2, "w") as f:
            f.write("key\n")
        os.chmod(k2, 0o644)

        fid = _make_finding(generator.findings, affected_paths=[k1, k2])
        pid = generator.generate_for_finding(fid)
        req_id = pstore.get(pid).approval_request_id

        os.unlink(k2)  # second chmod will fail

        with mock.patch("halbert_core.obs.audit.write_audit", return_value=""):
            result = handle_approval_decision(req_id, True, generator=generator)

        assert result["status"] == ProposalStatus.ROLLED_BACK.value
        # First change rolled back: original 0o644 restored
        assert (os.stat(k1).st_mode & 0o777) == 0o644
        assert result["rolled_back"]

    def test_a_failure_after_the_chmod_still_restores_the_mode(
        self, generator, pstore, tmpdir
    ):
        """R06-F4. The undo record must exist from the moment the side effect
        does. The audit write sits after os.chmod inside _apply_chmod, so a
        failing audit used to leave the mode changed on disk while the
        proposal reported ROLLED_BACK — the one state the caller is promised
        cannot happen."""
        key = _ssh_key(tmpdir, "id_rsa", mode=0o644)

        fid = _make_finding(generator.findings, affected_paths=[key])
        pid = generator.generate_for_finding(fid)
        req_id = pstore.get(pid).approval_request_id

        with mock.patch(
            "halbert_core.obs.audit.write_audit",
            side_effect=RuntimeError("audit sink unavailable"),
        ):
            result = handle_approval_decision(req_id, True, generator=generator)

        assert result["status"] == ProposalStatus.ROLLED_BACK.value
        assert (os.stat(key).st_mode & 0o777) == 0o644, (
            "chmod took effect but was not rolled back"
        )
        assert any(rb["kind"] == "chmod" for rb in result["rolled_back"]), (
            result["rolled_back"]
        )

    def test_a_rollback_that_cannot_be_audited_is_still_a_rollback(
        self, generator, pstore, tmpdir
    ):
        """The mirror of the above. On the way back, an audit sink failure
        must not report a completed undo as failed — that would tell the
        operator the machine is still modified when it is not."""
        k1 = _ssh_key(tmpdir, "id_rsa", mode=0o644)
        k2 = os.path.join(tmpdir, ".ssh", "id_gone")
        with open(k2, "w") as f:
            f.write("key\n")
        os.chmod(k2, 0o644)

        fid = _make_finding(generator.findings, affected_paths=[k1, k2])
        pid = generator.generate_for_finding(fid)
        req_id = pstore.get(pid).approval_request_id

        os.unlink(k2)  # the second chmod fails, triggering rollback of the first

        calls = {"n": 0}

        def _audit(*args, **kwargs):
            # Let the apply-side audit through; fail only the rollback's.
            calls["n"] += 1
            if "rollback" in kwargs.get("summary", ""):
                raise RuntimeError("audit sink unavailable")
            return ""

        with mock.patch("halbert_core.obs.audit.write_audit", side_effect=_audit):
            result = handle_approval_decision(req_id, True, generator=generator)

        assert result["status"] == ProposalStatus.ROLLED_BACK.value
        assert (os.stat(k1).st_mode & 0o777) == 0o644
        assert any(rb["kind"] == "chmod" for rb in result["rolled_back"]), (
            "a completed undo was dropped because it could not be audited"
        )


class TestHasExecutableFix:
    """J3-7: which findings get a proposal at detection time.

    Executable = at least one generated change the executor can apply
    without a human editing a file (chmod today). Drop-in / fstab changes
    are prose marked requires_manual_review, so proposing them at
    detection would queue a verified no-op.
    """

    def _finding(self, detector, paths):
        return Finding(
            id="", detector=detector, severity="warning", title="t",
            description="d", why_now="n", why_care="c", why_so="s",
            affected_paths=paths,
        )

    def test_permissions_hygiene_key_is_executable(self, tmpdir):
        from halbert_core.findings.proposal_generator import has_executable_fix
        key = _ssh_key(tmpdir)
        assert has_executable_fix(self._finding("permissions_hygiene", [key])) is True

    def test_permissions_hygiene_without_matching_paths_is_not(self):
        from halbert_core.findings.proposal_generator import has_executable_fix
        assert has_executable_fix(self._finding("permissions_hygiene", ["/etc/motd"])) is False

    def test_dropin_and_fstab_are_manual_review(self):
        from halbert_core.findings.proposal_generator import has_executable_fix
        assert has_executable_fix(
            self._finding("dropin_conflicts", ["/etc/ssh/sshd_config.d/10.conf"])
        ) is False
        assert has_executable_fix(self._finding("fstab_phantom", ["/etc/fstab"])) is False

    def test_unknown_detector_is_not(self):
        from halbert_core.findings.proposal_generator import has_executable_fix
        assert has_executable_fix(self._finding("acoustic_anomaly", [])) is False

    def test_generator_uses_the_same_change_set(self, generator, tmpdir):
        """The method the generator executes against and the module-level
        predicate must not drift apart."""
        from halbert_core.findings.proposal_generator import generate_changes
        key = _ssh_key(tmpdir)
        f = self._finding("permissions_hygiene", [key])
        assert generator._generate_changes(f) == generate_changes(f)
