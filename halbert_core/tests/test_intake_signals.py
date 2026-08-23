"""
Tests for intake/signals.py — zero-LLM signal detection.
"""

from __future__ import annotations

import pytest

from halbert_core.intake.signals import MessageSignals, analyze_message


# ── Acceptance cases from the implementation plan ────────────────

class TestGreeting:
    def test_hi(self):
        s = analyze_message("hi")
        assert s.intent == "greeting"
        assert s.is_greeting is True
        assert s.message_length == "short"

    def test_hello(self):
        s = analyze_message("hello")
        assert s.is_greeting is True
        assert s.intent == "greeting"

    def test_hey_halbert(self):
        s = analyze_message("hey Halbert")
        assert s.is_greeting is True
        assert s.message_length == "short"

    def test_good_morning(self):
        s = analyze_message("good morning")
        assert s.is_greeting is True

    def test_whats_up(self):
        s = analyze_message("what's up")
        assert s.is_greeting is True


class TestFarewell:
    def test_bye(self):
        s = analyze_message("bye")
        assert s.intent == "farewell"
        assert s.is_farewell is True
        assert s.message_length == "short"

    def test_goodnight(self):
        s = analyze_message("goodnight")
        assert s.is_farewell is True

    def test_talk_later(self):
        s = analyze_message("talk to you later")
        assert s.is_farewell is True


class TestTroubleshooting:
    def test_nginx_failing(self):
        s = analyze_message("why is nginx failing after the update?")
        assert s.intent == "troubleshooting"
        assert s.is_troubleshooting is True
        assert s.detected_domains == ["service"]
        assert s.has_error_indicators is True
        assert s.is_question is True

    def test_traceback(self):
        s = analyze_message("I got this traceback when running the script")
        assert s.has_error_indicators is True
        assert s.is_troubleshooting is True
        assert s.intent == "troubleshooting"

    def test_segfault(self):
        s = analyze_message("the process segfaults on startup")
        assert s.has_error_indicators is True
        assert s.is_troubleshooting is True


class TestCommand:
    def test_show_disk_usage(self):
        s = analyze_message("show me disk usage")
        assert s.intent == "command"
        assert "storage" in s.detected_domains

    def test_check_nginx_conf(self):
        s = analyze_message("check /etc/nginx/nginx.conf")
        assert s.has_file_paths is True
        assert "service" in s.detected_domains

    def test_restart_service(self):
        s = analyze_message("restart the docker service")
        assert s.intent == "command"
        assert "service" in s.detected_domains

    def test_install_package(self):
        s = analyze_message("install htop")
        assert s.intent == "command"


class TestQuestion:
    def test_latest_version(self):
        s = analyze_message("what's the latest version of nginx")
        assert s.is_question is True
        assert "service" in s.detected_domains

    def test_how_to(self):
        s = analyze_message("how do I configure ssh keys?")
        assert s.is_question is True
        assert "security" in s.detected_domains


# ── Edge cases ───────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_string(self):
        s = analyze_message("")
        assert s.intent == "informational"
        assert s.is_greeting is False
        assert s.is_farewell is False
        assert s.is_question is False
        assert s.is_troubleshooting is False
        assert s.detected_domains == []
        assert s.has_error_indicators is False
        assert s.has_code_blocks is False
        assert s.has_file_paths is False

    def test_whitespace_only(self):
        s = analyze_message("   \n\t  ")
        assert s.intent == "informational"
        assert s.is_greeting is False

    def test_multi_domain(self):
        s = analyze_message("check ssh config and disk space")
        assert "security" in s.detected_domains
        assert "storage" in s.detected_domains
        assert "config" in s.detected_domains

    def test_code_block_fenced(self):
        msg = "Here's my config:\n```yaml\nport: 8080\n```"
        s = analyze_message(msg)
        assert s.has_code_blocks is True

    def test_code_block_indented(self):
        msg = "My script:\n    print('hello')\n    exit(0)"
        s = analyze_message(msg)
        assert s.has_code_blocks is True

    def test_stack_trace(self):
        msg = (
            "I'm getting this error:\n"
            "Traceback (most recent call last):\n"
            "  File 'main.py', line 10, in <module>\n"
            "    raise ValueError('bad input')\n"
            "ValueError: bad input"
        )
        s = analyze_message(msg)
        assert s.has_error_indicators is True
        assert s.is_troubleshooting is True
        assert s.has_code_blocks is True  # indented traceback

    def test_long_message(self):
        words = "word " * 60
        s = analyze_message(words.strip())
        assert s.message_length == "long"

    def test_normal_length(self):
        s = analyze_message("can you check if nginx is running properly?")
        assert s.message_length == "normal"

    def test_file_path(self):
        s = analyze_message("look at ~/.config/halbert/config.yml")
        assert s.has_file_paths is True

    def test_absolute_path(self):
        s = analyze_message("check /var/log/syslog")
        assert s.has_file_paths is True

    def test_informational_default(self):
        s = analyze_message("the weather is nice today")
        assert s.intent == "informational"
        assert s.is_question is False
        assert s.is_greeting is False


# ── Performance ──────────────────────────────────────────────────

class TestPerformance:
    def test_runs_under_1ms(self):
        import time
        msg = "why is nginx failing after the update? Check /etc/nginx/nginx.conf"
        # Warm up
        analyze_message(msg)
        start = time.perf_counter()
        for _ in range(1000):
            analyze_message(msg)
        elapsed = time.perf_counter() - start
        per_call_ms = (elapsed / 1000) * 1000
        assert per_call_ms < 1.0, f"analyze_message took {per_call_ms:.3f}ms per call"
