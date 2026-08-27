# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Tests for intake/signals.py — zero-LLM signal detection.
"""

from __future__ import annotations

import pytest

from halbert_core.intake.signals import (
    ENTITY_ALIASES, MessageSignals, analyze_message, canonical_entities,
)


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


# ── Image detection ──────────────────────────────────────────────

class TestImageDetection:
    def test_markdown_image_syntax(self):
        s = analyze_message("Here's a screenshot: ![error](screenshot.png)")
        assert s.has_images is True

    def test_data_uri_image(self):
        s = analyze_message("Check this: data:image/png;base64,iVBORw0KGgo=")
        assert s.has_images is True

    def test_html_img_tag(self):
        s = analyze_message("Look at <img src='chart.jpg' /> for details")
        assert s.has_images is True

    def test_image_file_extension(self):
        s = analyze_message("Please review the diagram.png I attached")
        assert s.has_images is True

    def test_jpeg_extension(self):
        s = analyze_message("See photo.jpeg for the error")
        assert s.has_images is True

    def test_no_image_in_plain_text(self):
        s = analyze_message("why is nginx failing after the update?")
        assert s.has_images is False

    def test_no_false_positive_on_word_png(self):
        s = analyze_message("I pinged the server but got no response")
        assert s.has_images is False


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



# ── Entities + thread cues (Plan A, A4) ──────────────────────────

class TestCanonicalEntities:
    def test_cifs_maps_to_samba(self):
        ents = canonical_entities("the cifs mount is broken")
        assert "samba" in ents and "cifs" not in ents and "mount" in ents

    def test_phrase_alias(self):
        ents = canonical_entities("set up a windows share for the scanner")
        assert {"samba", "share", "scanner"} <= ents

    def test_smb_conf_token_and_path(self):
        assert {"samba", "/etc/samba/smb.conf"} <= canonical_entities("edit /etc/samba/smb.conf please.")
        assert "samba" in canonical_entities("look in smb.conf.")

    def test_generic_keywords_excluded(self):
        assert canonical_entities("check the status of the service") == set()

    def test_vpn_maps_to_wireguard(self):
        assert canonical_entities("is the vpn up?") == {"wireguard"}

    def test_empty(self):
        assert canonical_entities("") == set()

    def test_alias_table_shape(self):
        assert ENTITY_ALIASES["zpool"] == "zfs" and ENTITY_ALIASES["letsencrypt"] == "tls"


class TestThreadCues:
    def test_past_reference(self):
        assert analyze_message("same as we did for the media share last week").past_reference is True
        assert analyze_message("remember when the pool degraded?").past_reference is True
        assert analyze_message("add a share").past_reference is False

    def test_anaphora_phrases(self):
        assert analyze_message("so, did that work?").anaphora is True
        assert analyze_message("any luck?").anaphora is True
        assert analyze_message("ok is it working now?").anaphora is True

    def test_bare_it_without_signals(self):
        assert analyze_message("it still fails").anaphora is True
        assert analyze_message("that again please").anaphora is True

    def test_bare_it_with_entity_is_not_anaphora(self):
        assert analyze_message("it is the samba share again").anaphora is False
        assert analyze_message("it won't mount the disk").anaphora is False

    def test_signals_carry_entities(self):
        s = analyze_message("mount the cifs share")
        assert {"samba", "share", "mount"} <= s.entities and "network" in s.detected_domains

    def test_new_domain_keywords(self):
        assert "network" in analyze_message("restart samba").detected_domains
        assert "storage" in analyze_message("zpool status").detected_domains
        assert "service" in analyze_message("edit the crontab").detected_domains
        assert "network" in analyze_message("is the vpn up").detected_domains
        s = analyze_message("the scanner is offline")
        assert "network" in s.detected_domains and "scanner" in s.entities

    def test_defaults(self):
        s = MessageSignals()
        assert s.entities == set() and s.past_reference is False and s.anaphora is False


# ── Review-fix regressions (Plan A, A4 quality-fix round) ─────────
#
# These pin the behaviours corrected after code review found the first
# fix pass (a5421126) changed three things with zero new test coverage:
# the anaphora gate, the qualified-"share" regex, and the _scan bounding/
# capping. Each assertion below fails on the pre-fix code.

class TestAnaphoraGateOnGenericDomainWords:
    """Bare "it"/"that" must not be suppressed by a *generic* domain hit
    (e.g. "failed", "running", "start", "status") — only a real entity or
    a non-generic domain keyword should suppress it."""

    def test_generic_service_word_does_not_suppress_bare_it(self):
        assert analyze_message("it failed again").anaphora is True
        assert analyze_message("it won't start").anaphora is True
        assert analyze_message("it is still running").anaphora is True
        assert analyze_message("that status is still bad").anaphora is True

    def test_real_entity_still_suppresses_bare_it(self):
        assert analyze_message("it is the samba share again").anaphora is False
        assert analyze_message("it won't mount the disk").anaphora is False


class TestQualifiedShareRegex:
    """The qualifier before "share" (samba/nfs/windows/file/smb/cifs/
    network) must not be consumed into a single two-word match — the
    qualifier is itself a real entity and must survive alongside
    "share"."""

    def test_samba_share_keeps_both_entities(self):
        ents = analyze_message("add a samba share for the media folder").entities
        assert {"samba", "share"} <= ents

    def test_nfs_share_keeps_both_entities(self):
        assert canonical_entities("set up an nfs share") == {"nfs", "share"}

    def test_unqualified_nfs_mount_unaffected(self):
        # No "share" qualifier in play here — sanity check the fix didn't
        # change plain single-word keyword matching.
        assert canonical_entities("the nfs mount is down") == {"nfs", "mount"}

    def test_windows_share_still_aliases_to_samba_plus_share(self):
        ents = canonical_entities("set up a windows share for the scanner")
        assert {"samba", "share", "scanner"} <= ents


class TestAmbiguousKeywordsExcluded:
    """"share", "smart", "cups" alone (unqualified) must not trigger a
    domain — only "smartctl"/"smartd", "cupsd"/"printer", and a
    network-qualified "share" should."""

    def test_bare_share_no_network_domain(self):
        s = analyze_message("can you share that document with me?")
        assert "network" not in s.detected_domains
        assert "share" not in s.entities

    def test_bare_share_verb_no_network_domain(self):
        s = analyze_message("summarize the report and share it")
        assert "network" not in s.detected_domains

    def test_bare_smart_no_domain(self):
        assert analyze_message("hey, that was smart").detected_domains == []

    def test_bare_cups_no_domain(self):
        assert analyze_message("two cups of tea").detected_domains == []


class TestEntityScanBoundsAndPathFiltering:
    """`_scan`'s bounded, single-pass extraction: degenerate file-path
    noise is dropped, the path-entity count is capped, and
    `canonical_entities`/`analyze_message().entities` stay consistent
    with each other on the same input."""

    def test_degenerate_paths_dropped(self):
        s = analyze_message("an I/O error happened, check N/A too and R/W issue")
        assert not any(e in s.entities for e in ("/O", "/A", "/W"))
        # The false-positive matches don't count, but a real path still does.
        s2 = analyze_message("an I/O error in /var/log/syslog again")
        assert "/var/log/syslog" in s2.entities

    def test_path_entity_count_is_capped(self):
        from halbert_core.intake.signals import _MAX_PATH_ENTITIES

        text = " ".join(f"/path/number/{i}" for i in range(_MAX_PATH_ENTITIES + 30))
        ents = canonical_entities(text)
        path_like = {e for e in ents if e.startswith("/")}
        assert len(path_like) <= _MAX_PATH_ENTITIES

    def test_canonical_entities_matches_analyze_message_entities(self):
        for msg in (
            "the cifs mount is broken",
            "add a samba share for the media folder",
            "set up an nfs share",
            "is the vpn up?",
            "edit /etc/samba/smb.conf please.",
        ):
            assert canonical_entities(msg) == analyze_message(msg).entities


class TestLargeInputPerformance:
    """A large pasted message (e.g. a log dump) must not scale linearly
    with entity/path/alias extraction — that work is bounded to a
    prefix, unlike domain-boolean detection which still scans the full
    text (review: Plan A / A4)."""

    def test_large_paste_stays_bounded(self):
        import time

        msg = ("nginx failed to start, check /var/log/nginx/error.log. " * 4000)
        analyze_message(msg)  # warm up (regex module cache, etc.)
        start = time.perf_counter()
        analyze_message(msg)
        elapsed_ms = (time.perf_counter() - start) * 1000
        # Generous bound: this is a ~220KB adversarial paste, not the
        # module's <1ms normal-message budget — it only guards against
        # the entity-extraction passes (token/alias/path scans) scaling
        # unboundedly with input size the way the pre-fix code did.
        assert elapsed_ms < 250, f"analyze_message took {elapsed_ms:.1f}ms on a large paste"
