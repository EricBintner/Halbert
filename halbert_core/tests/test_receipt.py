# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for agents/receipt.py — deterministic thread receipts and titles."""

from datetime import datetime

from halbert_core.agents.receipt import (
    build_receipt, first_sentence, provisional_title, receipt_one_liner, refined_title,
)

T0 = datetime(2026, 7, 14, 12, 0).timestamp()


def _thread(**kw):
    base = {"thread_id": "t1", "title": "Samba media share", "topic_domains": ["network", "config"],
            "entities_json": ["samba", "/etc/samba/smb.conf", "share"], "turn_count": 2}
    base.update(kw)
    return base


def _messages():
    return [
        {"message_id": 1, "role": "user", "origin": "human", "turn_id": "turn-1", "timestamp": T0,
         "content": "add a samba share for the media folder\nsecond line", "blocks": [], "diff_proposals": []},
        {"message_id": 2, "role": "assistant", "origin": "assistant", "turn_id": "turn-1", "timestamp": T0 + 60,
         "content": "Added [media] to smb.conf. Restarting smbd now.",
         "blocks": [{"tool": "run_command", "args": {"command": "testparm"}, "exit": 0},
                    {"tool": "write_file", "args": {"path": "/etc/samba/smb.conf"}, "exit": 0},
                    {"tool": "run_command", "args": {"command": "systemctl restart smbd"}, "result": {"exit_code": 0}}],
         "diff_proposals": []},
        {"message_id": 3, "role": "user", "origin": "human", "turn_id": "turn-2", "timestamp": T0 + 3600,
         "content": "did it mount?", "blocks": [], "diff_proposals": []},
        {"message_id": 4, "role": "assistant", "origin": "assistant", "turn_id": "turn-2", "timestamp": T0 + 3660,
         "content": "The share mounts from the laptop at //nas/media (v3.1 client). Next, verify guest access is off once the config reloads.",
         "blocks": [], "diff_proposals": [{"id": "d1", "path": "/etc/fstab"}]},
    ]


class TestBuildReceipt:
    def test_sections_in_order(self):
        r = build_receipt(_thread(), _messages())
        assert [line.split(":")[0] for line in r.splitlines()] == [
            "Title", "When", "Domains", "Entities", "Started with", "Last said",
            "Commands", "Files written", "Open loop"]

    def test_lines(self):
        lines = build_receipt(_thread(), _messages()).splitlines()
        assert lines[0] == "Title: Samba media share"
        assert lines[1] == "When: 2026-07-14..2026-07-14 · 2 turns"
        assert lines[2] == "Domains: network, config"
        assert lines[3] == "Entities: samba, /etc/samba/smb.conf, share"
        assert lines[4] == "Started with: add a samba share for the media folder second line"
        assert lines[5] == "Last said: The share mounts from the laptop at //nas/media (v3.1 client)."
        assert lines[6] == "Commands: testparm (exit 0); systemctl restart smbd (exit 0)"
        assert lines[7] == "Files written: /etc/samba/smb.conf; /etc/fstab"
        assert lines[8] == "Open loop: Next, verify guest access is off once the config reloads."

    def test_open_loop_none_recorded(self):
        msgs = _messages()
        msgs[-1]["content"] = "All done. Nothing else pending."
        assert build_receipt(_thread(), msgs).splitlines()[-1] == "Open loop: none recorded"

    def test_commands_capped_at_eight_and_unknown_exit(self):
        msgs = _messages()
        msgs[1]["blocks"] = [{"tool": "run_command", "args": {"command": f"cmd{i}"}} for i in range(10)]
        line = build_receipt(_thread(), msgs).splitlines()[6]
        assert line.startswith("Commands: cmd2 (exit ?); ") and line.count("(exit ?)") == 8

    def test_max_chars(self):
        msgs = _messages()
        msgs[0]["content"] = "x" * 400
        msgs[-1]["content"] = "y" * 900 + ". Then " + "z" * 900
        r = build_receipt(_thread(), msgs, max_chars=600)
        assert len(r) == 600 and r.endswith("…")

    def test_empty_thread(self):
        r = build_receipt(_thread(turn_count=0, topic_domains=[], entities_json=[]), [])
        assert "When: unknown" in r and "Domains: none" in r and "Started with: none" in r and "Last said: none" in r
        assert r.endswith("Commands: none\nFiles written: none\nOpen loop: none recorded")

    def test_first_sentence_never_splits_on_bare_dot(self):
        assert first_sentence("Edited smb.conf and fstab. Done.") == "Edited smb.conf and fstab."


class TestTitles:
    def test_provisional(self):
        assert provisional_title("  Add a Samba share for the media folder!!\nmore") == "Add a Samba share for the media folder"
        assert provisional_title("") == "New subject"
        assert provisional_title("x" * 80) == "x" * 60
        t = provisional_title("please configure the wireguard vpn tunnel for the laptop and phone so both work")
        assert t == "please configure the wireguard vpn tunnel for the laptop"

    def test_refined(self):
        assert refined_title(["samba", "share"], "add a samba share for the media folder") == "Add samba"
        assert refined_title(["/etc/fstab", "nfs"], "mount the nfs export") == "Mount nfs"
        assert refined_title(["zfs"], "why is this slow") == "Zfs"
        assert refined_title([], "hello there") == "hello there"

    def test_one_liner(self):
        r = build_receipt(_thread(), _messages())
        assert receipt_one_liner(r) == (
            "Started with: add a samba share for the media folder second line "
            "Last said: The share mounts from the laptop at //nas/media (v3.1 client). "
            "Open loop: Next, verify guest access is off once the config reloads.")
