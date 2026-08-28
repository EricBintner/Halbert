# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for OSC 133 parser and shell integration (Plan B: B3)."""

import base64

import pytest

from halbert_core.streaming.shell_integration import (
    OSCParser,
    OSCState,
    BlockBoundary,
    ParsedOutput,
    PASSWORD_PROMPT_RE,
    detect_needs_input,
    is_remote_command,
    REMOTE_PREFIXES,
)


# ---------------------------------------------------------------------------
# OSC 133 parser — basic markers
# ---------------------------------------------------------------------------

class TestOSCParserMarkers:
    def test_prompt_start_a(self):
        p = OSCParser()
        out = p.feed(b"\x1b]133;A\x07")
        assert len(out.boundaries) == 1
        assert out.boundaries[0].kind == "A"
        assert out.passthrough == b"\x1b]133;A\x07"

    def test_input_start_b(self):
        p = OSCParser()
        out = p.feed(b"\x1b]133;B\x07")
        assert len(out.boundaries) == 1
        assert out.boundaries[0].kind == "B"

    def test_output_start_c_with_command(self):
        p = OSCParser()
        cmd_b64 = base64.b64encode(b"ls -la").decode()
        out = p.feed(f"\x1b]133;C;id=123;cmd={cmd_b64}\x07".encode())
        assert len(out.boundaries) == 1
        b = out.boundaries[0]
        assert b.kind == "C"
        assert b.block_id == "123"
        assert b.command == "ls -la"

    def test_output_end_d_with_exit_code(self):
        p = OSCParser()
        out = p.feed(b"\x1b]133;D;0\x07")
        assert len(out.boundaries) == 1
        assert out.boundaries[0].kind == "D"
        assert out.boundaries[0].exit_code == 0

    def test_d_with_nonzero_exit(self):
        p = OSCParser()
        out = p.feed(b"\x1b]133;D;127\x07")
        assert out.boundaries[0].exit_code == 127

    def test_d_no_exit_code(self):
        p = OSCParser()
        out = p.feed(b"\x1b]133;D\x07")
        assert out.boundaries[0].kind == "D"
        assert out.boundaries[0].exit_code is None


# ---------------------------------------------------------------------------
# OSC 7 — cwd
# ---------------------------------------------------------------------------

class TestOSC7Cwd:
    def test_osc7_records_cwd(self):
        p = OSCParser()
        out = p.feed(b"\x1b]7;file://myhost/Users/eric\x07")
        assert len(out.boundaries) == 1
        assert out.boundaries[0].kind == "7"
        assert out.boundaries[0].cwd == "/Users/eric"

    def test_osc7_with_host(self):
        p = OSCParser()
        out = p.feed(b"\x1b]7;file://example.com/tmp\x07")
        assert out.boundaries[0].cwd == "/tmp"


# ---------------------------------------------------------------------------
# ST terminator (\x1b\\ instead of \x07)
# ---------------------------------------------------------------------------

class TestSTTerminator:
    def test_st_terminator(self):
        p = OSCParser()
        out = p.feed(b"\x1b]133;A\x1b\\")
        assert len(out.boundaries) == 1
        assert out.boundaries[0].kind == "A"

    def test_st_terminator_with_command(self):
        p = OSCParser()
        cmd_b64 = base64.b64encode(b"echo hi").decode()
        out = p.feed(f"\x1b]133;C;id=42;cmd={cmd_b64}\x1b\\".encode())
        assert out.boundaries[0].command == "echo hi"


# ---------------------------------------------------------------------------
# Block bytes accumulation
# ---------------------------------------------------------------------------

class TestBlockBytes:
    def test_block_bytes_between_c_and_d(self):
        p = OSCParser()
        cmd_b64 = base64.b64encode(b"echo hello").decode()
        out1 = p.feed(f"\x1b]133;C;id=1;cmd={cmd_b64}\x07".encode())
        assert out1.block_bytes == b""
        out2 = p.feed(b"hello\n")
        assert out2.block_bytes == b"hello\n"
        out3 = p.feed(b"\x1b]133;D;0\x07")
        # After D, block_bytes stops accumulating
        assert out3.block_bytes == b""

    def test_block_bytes_excludes_markers(self):
        p = OSCParser()
        cmd_b64 = base64.b64encode(b"pwd").decode()
        p.feed(f"\x1b]133;C;id=1;cmd={cmd_b64}\x07".encode())
        out = p.feed(b"/tmp\n")
        assert out.block_bytes == b"/tmp\n"
        # The marker bytes should not be in block_bytes
        assert b"\x1b]133" not in out.block_bytes


# ---------------------------------------------------------------------------
# Alt-screen detection
# ---------------------------------------------------------------------------

class TestAltScreen:
    def test_alt_enter_1049h(self):
        p = OSCParser()
        out = p.feed(b"\x1b[?1049h")
        assert any(b.kind == "alt_enter" for b in out.boundaries)

    def test_alt_exit_1049l(self):
        p = OSCParser()
        out = p.feed(b"\x1b[?1049l")
        assert any(b.kind == "alt_exit" for b in out.boundaries)

    def test_alt_enter_47h(self):
        p = OSCParser()
        out = p.feed(b"\x1b[?47h")
        assert any(b.kind == "alt_enter" for b in out.boundaries)

    def test_alt_exit_47l(self):
        p = OSCParser()
        out = p.feed(b"\x1b[?47l")
        assert any(b.kind == "alt_exit" for b in out.boundaries)

    def test_alt_screen_stops_block_bytes(self):
        p = OSCParser()
        cmd_b64 = base64.b64encode(b"vim").decode()
        p.feed(f"\x1b]133;C;id=1;cmd={cmd_b64}\x07".encode())
        p.feed(b"\x1b[?1049h")
        out = p.feed(b"some vim output")
        assert out.block_bytes == b""
        p.feed(b"\x1b[?1049l")
        out2 = p.feed(b"back to normal")
        assert out2.block_bytes == b"back to normal"


# ---------------------------------------------------------------------------
# Partial sequences across reads
# ---------------------------------------------------------------------------

class TestPartialSequences:
    def test_split_osc_sequence(self):
        p = OSCParser()
        out1 = p.feed(b"\x1b]133;")
        assert out1.boundaries == []
        out2 = p.feed(b"A\x07")
        assert len(out2.boundaries) == 1
        assert out2.boundaries[0].kind == "A"

    def test_split_st_terminator(self):
        p = OSCParser()
        out1 = p.feed(b"\x1b]133;A\x1b")
        assert out1.boundaries == []
        out2 = p.feed(b"\\")
        assert len(out2.boundaries) == 1

    def test_split_mid_command(self):
        p = OSCParser()
        cmd_b64 = base64.b64encode(b"ls -la").decode()
        half = f"\x1b]133;C;id=1;cmd={cmd_b64}".encode()
        out1 = p.feed(half)
        assert out1.boundaries == []
        out2 = p.feed(b"\x07")
        assert len(out2.boundaries) == 1
        assert out2.boundaries[0].command == "ls -la"

    def test_plain_text_no_boundary(self):
        p = OSCParser()
        out = p.feed(b"just some output\n")
        assert out.boundaries == []
        assert out.passthrough == b"just some output\n"

    def test_escape_not_osc(self):
        p = OSCParser()
        out = p.feed(b"\x1b[0m")
        assert out.boundaries == []
        assert out.passthrough == b"\x1b[0m"


# ---------------------------------------------------------------------------
# Full prompt cycle
# ---------------------------------------------------------------------------

class TestFullCycle:
    def test_prompt_command_output_end(self):
        p = OSCParser()
        cmd_b64 = base64.b64encode(b"echo test").decode()
        chunks = [
            b"\x1b]133;A\x07",                                    # prompt
            f"\x1b]133;C;id=1;cmd={cmd_b64}\x07".encode(),        # command
            b"test\n",                                             # output
            b"\x1b]133;D;0\x07",                                   # end
        ]
        all_boundaries = []
        all_passthrough = b""
        all_block_bytes = b""
        for chunk in chunks:
            out = p.feed(chunk)
            all_boundaries.extend(out.boundaries)
            all_passthrough += out.passthrough
            all_block_bytes += out.block_bytes
        kinds = [b.kind for b in all_boundaries]
        assert kinds == ["A", "C", "D"]
        assert all_block_bytes == b"test\n"
        # passthrough should contain everything
        assert b"test\n" in all_passthrough

    def test_multiple_commands_in_sequence(self):
        p = OSCParser()
        results = []
        for cmd in ["ls", "pwd", "whoami"]:
            cmd_b64 = base64.b64encode(cmd.encode()).decode()
            out = p.feed(f"\x1b]133;C;id=x;cmd={cmd_b64}\x07".encode())
            results.append(out.boundaries[0].command)
            p.feed(b"\x1b]133;D;0\x07")
        assert results == ["ls", "pwd", "whoami"]


# ---------------------------------------------------------------------------
# Password prompt detection
# ---------------------------------------------------------------------------

class TestPasswordPrompt:
    def test_password_prompt_matches(self):
        assert PASSWORD_PROMPT_RE.search(b"Password: ")
        assert PASSWORD_PROMPT_RE.search(b"password: ")
        assert PASSWORD_PROMPT_RE.search(b"Passphrase: ")
        assert PASSWORD_PROMPT_RE.search(b"[sudo] password for eric: ")

    def test_non_prompt_does_not_match(self):
        assert not PASSWORD_PROMPT_RE.search(b"Your password is secret")
        assert not PASSWORD_PROMPT_RE.search(b"Enter your name: ")

    def test_detect_needs_input_with_prompt_and_silence(self):
        assert detect_needs_input(b"Password: ", 5.0) is True
        assert detect_needs_input(b"Password: ", 10.0) is True

    def test_detect_needs_input_prompt_but_no_silence(self):
        assert detect_needs_input(b"Password: ", 4.9) is False
        assert detect_needs_input(b"Password: ", 0.0) is False

    def test_detect_needs_input_no_prompt(self):
        assert detect_needs_input(b"some output", 10.0) is False

    def test_detect_needs_input_empty(self):
        assert detect_needs_input(b"", 10.0) is False


# ---------------------------------------------------------------------------
# Remote command detection
# ---------------------------------------------------------------------------

class TestRemoteCommand:
    def test_ssh(self):
        assert is_remote_command("ssh user@host") is True

    def test_mosh(self):
        assert is_remote_command("mosh user@host") is True

    def test_slogin(self):
        assert is_remote_command("slogin user@host") is True

    def test_local_command(self):
        assert is_remote_command("ls -la") is False

    def test_leading_whitespace(self):
        assert is_remote_command("  ssh user@host") is True

    def test_ssh_in_middle(self):
        assert is_remote_command("echo ssh") is False

    def test_remote_prefixes_exist(self):
        assert "ssh " in REMOTE_PREFIXES
        assert "mosh " in REMOTE_PREFIXES
        assert "slogin " in REMOTE_PREFIXES


# ---------------------------------------------------------------------------
# Passthrough integrity
# ---------------------------------------------------------------------------

class TestPassthrough:
    def test_passthrough_preserves_all_bytes(self):
        p = OSCParser()
        data = b"\x1b]133;A\x07hello world\x1b]133;D;0\x07"
        out1 = p.feed(data)
        assert out1.passthrough == data

    def test_passthrough_with_csi(self):
        p = OSCParser()
        data = b"\x1b[31mred text\x1b[0m"
        out = p.feed(data)
        assert out.passthrough == data
        assert out.boundaries == []

    def test_passthrough_split_preserves(self):
        p = OSCParser()
        out1 = p.feed(b"hello ")
        out2 = p.feed(b"world")
        assert out1.passthrough == b"hello "
        assert out2.passthrough == b"world"
