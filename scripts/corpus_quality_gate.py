#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Corpus Quality Gate (Phase 0 T0e.1).
Executes 20 curated test queries spanning Linux, macOS, BSD, storage, networking,
security, package management, and common dev tools against the SourcePrep index.

Usage:
    python scripts/corpus_quality_gate.py [--project-id ID] [--server-url http://127.0.0.1:8400] [--k 5]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests


TEST_QUERIES = [
    {
        "id": "q01_sshd",
        "query": "how to configure sshd",
        "domain": "remote_access",
        "expected_terms": ["ssh", "sshd", "config", "port"],
    },
    {
        "id": "q02_diskutil_apfs",
        "query": "diskutil apfs resize container",
        "domain": "macos_storage",
        "expected_terms": ["diskutil", "apfs", "volume", "container"],
    },
    {
        "id": "q03_freebsd_net",
        "query": "freebsd network interface configuration",
        "domain": "bsd_networking",
        "expected_terms": ["freebsd", "rc.conf", "ifconfig", "network"],
    },
    {
        "id": "q04_git_rebase",
        "query": "git rebase interactive squash commits",
        "domain": "version_control",
        "expected_terms": ["git", "rebase", "commit", "squash"],
    },
    {
        "id": "q05_systemd_restart",
        "query": "systemd restart failed service",
        "domain": "linux_init",
        "expected_terms": ["systemctl", "systemd", "service", "restart"],
    },
    {
        "id": "q06_iptables_firewall",
        "query": "iptables firewall drop incoming port",
        "domain": "security",
        "expected_terms": ["iptables", "firewall", "port", "rule"],
    },
    {
        "id": "q07_homebrew_cask",
        "query": "homebrew cask install application",
        "domain": "macos_packages",
        "expected_terms": ["brew", "cask", "install", "formula"],
    },
    {
        "id": "q08_docker_compose",
        "query": "docker compose up detached mode",
        "domain": "containers",
        "expected_terms": ["docker", "compose", "container", "service"],
    },
    {
        "id": "q09_find_modified",
        "query": "find files modified in the last 24 hours",
        "domain": "file_ops",
        "expected_terms": ["find", "mtime", "file", "directory"],
    },
    {
        "id": "q10_zfs_dataset",
        "query": "zfs create dataset compression lz4",
        "domain": "storage",
        "expected_terms": ["zfs", "pool", "dataset", "compression"],
    },
    {
        "id": "q11_chmod_permissions",
        "query": "chmod setfacl file permissions recursive",
        "domain": "permissions",
        "expected_terms": ["chmod", "permission", "file", "mode"],
    },
    {
        "id": "q12_awk_column",
        "query": "awk print second column delimiter",
        "domain": "text_processing",
        "expected_terms": ["awk", "print", "column", "field"],
    },
    {
        "id": "q13_curl_json",
        "query": "curl post request json payload",
        "domain": "devtools",
        "expected_terms": ["curl", "post", "header", "http"],
    },
    {
        "id": "q14_macports_install",
        "query": "macports install package variant",
        "domain": "macos_packages",
        "expected_terms": ["port", "macports", "install", "variant"],
    },
    {
        "id": "q15_nvidia_gpu",
        "query": "nvidia-smi monitor gpu temperature memory",
        "domain": "hardware",
        "expected_terms": ["nvidia", "smi", "gpu", "cuda"],
    },
    {
        "id": "q16_tar_extract",
        "query": "tar extract tar.gz archive to directory",
        "domain": "archive_ops",
        "expected_terms": ["tar", "extract", "archive", "gzip"],
    },
    {
        "id": "q17_grep_recursive",
        "query": "grep recursive search ignore case pattern",
        "domain": "text_processing",
        "expected_terms": ["grep", "search", "pattern", "match"],
    },
    {
        "id": "q18_launchctl_plist",
        "query": "launchctl load launchd daemon plist",
        "domain": "macos_services",
        "expected_terms": ["launchctl", "launchd", "plist", "daemon"],
    },
    {
        "id": "q19_nginx_proxy",
        "query": "nginx reverse proxy pass upstream",
        "domain": "webservers",
        "expected_terms": ["nginx", "proxy", "server", "http"],
    },
    {
        "id": "q20_pacman_install",
        "query": "pacman install package arch linux",
        "domain": "linux_packages",
        "expected_terms": ["pacman", "package", "install", "arch"],
    },
]


def extract_chunks(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Chunks from a SourcePrep context response, in this script's own shape.

    The daemon replies with an envelope::

        {"success": true,
         "data": {"chunks": [{"source_path": ..., "text": ..., "score": ...}],
                  "context": "..."},
         "error": null}

    so chunks are nested under ``data``, and each one carries ``text`` and
    ``source_path`` — not ``content`` and ``file_path``. This gate read
    ``resp.json()["chunks"]`` and then ``chunk["content"]`` /
    ``chunk["file_path"]``: four mismatches, and the consequence was total.
    ``chunks`` was always ``[]``, so every query scored as failed and no gate
    was protecting any retrieval work. The scoped runner shared the defect,
    which also means its ``forbidden_path_prefix`` isolation assertion was
    testing an always-empty path list and could never fail.

    Normalising here rather than at each read keeps both runners' scoring
    untouched.
    """
    data = payload.get("data")
    if not isinstance(data, dict):
        data = {}

    chunks = data.get("chunks")
    if isinstance(chunks, list):
        return [
            {
                "content": c.get("text") or c.get("content") or "",
                "file_path": c.get("source_path") or c.get("file_path") or "",
                "score": c.get("score", 0.0),
            }
            for c in chunks
            if isinstance(c, dict)
        ]

    # Ambient mode: prose, no chunks.
    context = data.get("context")
    if isinstance(context, str) and context.strip():
        return [{"content": context, "file_path": "", "score": 1.0}]

    return []


def find_project_id(server_url: str, project_name: str = "halbert") -> Optional[str]:
    """Find project ID by name from the SourcePrep daemon."""
    try:
        r = requests.get(f"{server_url}/projects", timeout=10.0)
        if r.status_code == 200:
            data = r.json()
            projects = data.get("data", {}).get("projects", []) or data.get("projects", [])
            for p in projects:
                if p.get("name") == project_name:
                    return p.get("id")
    except Exception as e:
        print(f"Warning: could not query projects list: {e}", file=sys.stderr)
    return None


def run_quality_gate(server_url: str, project_id: str, k: int = 5, min_score: float = 0.15) -> Dict[str, Any]:
    """Run all 20 quality gate test queries and calculate metrics."""
    results = []
    passed_count = 0

    print(f"Running Corpus Quality Gate on project {project_id} (server: {server_url})...\n")

    for tq in TEST_QUERIES:
        qid = tq["id"]
        query = tq["query"]
        expected_terms = tq["expected_terms"]
        domain = tq["domain"]

        url = f"{server_url}/projects/{project_id}/context"
        body = {
            "query": query,
            "k": k,
            "structured": True,
            "trace_expand": True,
            "min_score": min_score,
            "include_sources": True,
        }

        try:
            resp = requests.post(url, json=body, timeout=30.0)
            resp.raise_for_status()
            envelope = resp.json()
        except Exception as e:
            results.append({
                "id": qid,
                "query": query,
                "domain": domain,
                "passed": False,
                "error": str(e),
                "chunks_returned": 0,
            })
            print(f"✗ [{qid}] {query} -> ERROR: {e}")
            continue

        chunks = extract_chunks(data)

        # Match terms against chunk text only (not path strings).
        # Path strings like "systemd-docs" or "homebrew_18" satisfy terms
        # spuriously — only real chunk text counts.
        chunk_texts = [str(c.get("text", "") or c.get("content", "") or "") for c in chunks]
        combined_text = " ".join(chunk_texts).lower()
        has_results = len(chunks) >= 2  # require at least 2 chunks
        has_non_empty = any(len(t.strip()) > 30 for t in chunk_texts)

        # Check for expected terms in chunk text only
        matched_terms = [t for t in expected_terms if t.lower() in combined_text]
        term_match_ratio = len(matched_terms) / len(expected_terms) if expected_terms else 1.0

        # Query passes if >= 2 chunks, non-empty text, and at least 50% of expected terms matched
        passed = has_results and has_non_empty and term_match_ratio >= 0.5

        if passed:
            passed_count += 1
            print(f"✓ [{qid}] {query} ({len(chunks)} chunks, matched terms: {matched_terms})")
        else:
            reasons = []
            if not has_results: reasons.append(f"chunks={len(chunks)}(<2)")
            if not has_non_empty: reasons.append("empty_text")
            if term_match_ratio < 0.5: reasons.append(f"terms={matched_terms}/{expected_terms}")
            print(f"✗ [{qid}] {query} ({'; '.join(reasons)})")

        top_sources = [c.get("source_path", "") for c in chunks[:3] if c.get("source_path")]
        results.append({
            "id": qid,
            "query": query,
            "domain": domain,
            "passed": passed,
            "chunks_returned": len(chunks),
            "matched_terms": matched_terms,
            "expected_terms": expected_terms,
            "top_sources": top_sources,
        })

    pass_rate = (passed_count / len(TEST_QUERIES)) * 100
    summary = {
        "total_queries": len(TEST_QUERIES),
        "passed_queries": passed_count,
        "failed_queries": len(TEST_QUERIES) - passed_count,
        "pass_rate_pct": pass_rate,
        "gate_passed": pass_rate >= 90.0,
        "details": results,
    }

    print("\n--- Corpus Quality Gate Results ---")
    print(f"Queries Passed: {passed_count}/{len(TEST_QUERIES)} ({pass_rate:.1f}%)")
    print(f"Status:         {'PASSED (Gate Passed)' if summary['gate_passed'] else 'FAILED'}")
    return summary


# ── T-V.2: Scoped retrieval quality gate ────────────────────────────
#
# 20 queries with explicit scope assignments. Each query asserts:
#   - results come back (non-empty)
#   - results are scoped correctly (no cross-platform leakage)
#   - expected terms appear in the returned chunks

SCOPED_QUERIES = [
    # ── host scope (live config) ──
    {"id": "s01_host_sshd", "query": "sshd_config Port directive", "scope": "host",
     "expected_terms": ["ssh", "port"], "forbidden_path_prefix": "knowledge/"},
    {"id": "s02_host_sshd_dropin", "query": "sshd_config drop-in override", "scope": "host",
     "expected_terms": ["ssh"], "forbidden_path_prefix": "knowledge/"},
    # ── knowledge-linux scope ──
    {"id": "s03_linux_systemd", "query": "systemd unit file restart", "scope": "knowledge_linux",
     "expected_terms": ["systemd", "unit", "restart"], "forbidden_path_prefix": "knowledge/macos/"},
    {"id": "s04_linux_pacman", "query": "pacman install package arch", "scope": "knowledge_linux",
     "expected_terms": ["pacman", "package"], "forbidden_path_prefix": "knowledge/macos/"},
    {"id": "s05_linux_iptables", "query": "iptables firewall rule drop", "scope": "knowledge_linux",
     "expected_terms": ["iptables", "firewall"], "forbidden_path_prefix": "knowledge/macos/"},
    {"id": "s06_linux_arch_wiki", "query": "arch linux network configuration", "scope": "knowledge_linux",
     "expected_terms": ["network", "config"], "forbidden_path_prefix": "knowledge/macos/"},
    {"id": "s07_linux_nvidia", "query": "nvidia-smi gpu cuda", "scope": "knowledge_linux",
     "expected_terms": ["nvidia", "gpu"], "forbidden_path_prefix": "knowledge/macos/"},
    # ── knowledge-macos scope ──
    {"id": "s08_macos_diskutil", "query": "diskutil apfs resize container", "scope": "knowledge_macos",
     "expected_terms": ["diskutil", "apfs"], "forbidden_path_prefix": "knowledge/linux/"},
    {"id": "s09_macos_homebrew", "query": "homebrew brew install cask", "scope": "knowledge_macos",
     "expected_terms": ["brew", "install"], "forbidden_path_prefix": "knowledge/linux/"},
    {"id": "s10_macos_launchctl", "query": "launchctl load launchd plist", "scope": "knowledge_macos",
     "expected_terms": ["launchctl", "launchd"], "forbidden_path_prefix": "knowledge/linux/"},
    {"id": "s11_macos_macports", "query": "macports port install variant", "scope": "knowledge_macos",
     "expected_terms": ["macports", "port"], "forbidden_path_prefix": "knowledge/linux/"},
    # ── knowledge-bsd scope ──
    {"id": "s12_bsd_freebsd_net", "query": "freebsd network interface rc.conf", "scope": "knowledge_bsd",
     "expected_terms": ["freebsd", "network"], "forbidden_path_prefix": "knowledge/linux/"},
    {"id": "s13_bsd_freebsd_handbook", "query": "freebsd handbook ports system", "scope": "knowledge_bsd",
     "expected_terms": ["freebsd", "ports"], "forbidden_path_prefix": "knowledge/linux/"},
    # ── knowledge-common scope ──
    {"id": "s14_common_git", "query": "git rebase interactive squash", "scope": "knowledge_common",
     "expected_terms": ["git", "rebase"], "forbidden_path_prefix": "knowledge/linux/"},
    {"id": "s15_common_docker", "query": "docker compose up detached", "scope": "knowledge_common",
     "expected_terms": ["docker", "compose"], "forbidden_path_prefix": "knowledge/linux/"},
    {"id": "s16_common_curl", "query": "curl post json http", "scope": "knowledge_common",
     "expected_terms": ["curl", "http"], "forbidden_path_prefix": "knowledge/linux/"},
    {"id": "s17_common_awk", "query": "awk print column field delimiter", "scope": "knowledge_common",
     "expected_terms": ["awk", "print"], "forbidden_path_prefix": "knowledge/linux/"},
    {"id": "s18_common_tar", "query": "tar extract gzip archive", "scope": "knowledge_common",
     "expected_terms": ["tar", "extract"], "forbidden_path_prefix": "knowledge/linux/"},
    # ── cross-scope isolation: linux query must NOT return macos chunks ──
    {"id": "s19_isolation_linux", "query": "systemctl service enable", "scope": "knowledge_linux",
     "expected_terms": ["systemctl", "service"], "forbidden_path_prefix": "knowledge/macos/"},
    {"id": "s20_isolation_macos", "query": "brew tap homebrew cask", "scope": "knowledge_macos",
     "expected_terms": ["brew", "cask"], "forbidden_path_prefix": "knowledge/linux/"},
    # ── role scopes (wave 1) ──
    # Content queries: each role must return its own subsystem's config.
    #
    # Note on strength: the runner's term haystack is content + file_path
    # (see `combined_text` below), so a term that also occurs in the staged
    # path can be satisfied by the path alone -- "launch" matches
    # host/service/Library/LaunchDaemons/..., "auto" matches
    # host/storage/etc/auto_master. Those entries prove the scope resolves to
    # the right tree rather than that the chunk text is on topic. The
    # forbidden_path_prefix assertion is unaffected and is the load-bearing
    # half of each entry.
    {"id": "r01_network_dns", "query": "DNS resolver configuration",
     "scope": "network_admin", "expected_terms": ["nameserver", "dns"],
     "forbidden_path_prefix": "host/storage/"},
    {"id": "r02_network_iface", "query": "network interface address configuration",
     "scope": "network_admin", "expected_terms": ["interface"],
     "forbidden_path_prefix": "host/storage/"},
    {"id": "r03_service_launch", "query": "program that runs at login",
     "scope": "service_admin", "expected_terms": ["label"],
     "forbidden_path_prefix": "host/network/"},
    # "programarguments" appears only in plist CONTENT, never in a path —
    # unlike "launch", which host/service/Library/LaunchDaemons/... would
    # satisfy on the path alone (the matcher concatenates content + path).
    {"id": "r04_service_manager", "query": "service manager configuration",
     "scope": "service_admin", "expected_terms": ["programarguments"],
     "forbidden_path_prefix": "host/storage/"},
    {"id": "r05_storage_mounts", "query": "persistent filesystem mount options",
     "scope": "storage_admin", "expected_terms": ["mount"],
     "forbidden_path_prefix": "host/network/"},
    # "-hosts" is auto_master CONTENT, not path — the bare term "auto" would
    # be satisfied by host/storage/etc/auto_master on the path alone.
    # Caveat: on a stock macOS host that line is commented out (`#/net
    # -hosts`), so this asserts the file body was indexed including comments.
    # If the chunker strips comments this needs revisiting — macOS
    # storage_admin content is thin enough that no uncommented term is both
    # distinctive and absent from the path.
    {"id": "r06_storage_automount", "query": "automount map configuration",
     "scope": "storage_admin", "expected_terms": ["-hosts"],
     "forbidden_path_prefix": "host/network/"},
    # Isolation probes: a role scope must never surface knowledge/ docs,
    # which belong to the platform axis, not the role axis.
    #
    # Empty expected_terms skips only the term check (term_match_ratio is 1.0
    # for an empty list); has_results, has_non_empty and scope_clean all still
    # apply, so these remain real assertions rather than free passes.
    {"id": "r07_iso_network_no_docs", "query": "network interface configuration",
     "scope": "network_admin", "expected_terms": [],
     "forbidden_path_prefix": "knowledge/"},
    {"id": "r08_iso_service_no_docs", "query": "startup daemon",
     "scope": "service_admin", "expected_terms": [],
     "forbidden_path_prefix": "knowledge/"},
    # ── role scopes (waves 2-3) ──
    # Authored from the wave-2/3 manifests (config/scopes/{security,shell,
    # package,boot,sharing}.yml); NOT yet run against a built index — the
    # r01-r08 caveat applies equally here, plus: package_admin and
    # boot_admin stage nothing on macOS (roles_for_platform gates them to
    # Linux), so r14-r19 pass only on a Linux-built corpus.
    # "root" is sudoers CONTENT ("root ALL=(ALL:ALL) ALL") and never in a
    # staged path; "session"/"pam_" likewise appear only in pam.d file
    # bodies, not their paths.
    {"id": "r09_security_sudoers", "query": "sudo command authorization rules",
     "scope": "security_admin", "expected_terms": ["root"],
     "forbidden_path_prefix": "host/network/"},
    {"id": "r10_security_pam", "query": "pluggable authentication module stack",
     "scope": "security_admin", "expected_terms": ["session"],
     "forbidden_path_prefix": "host/service/"},
    {"id": "r11_security_no_docs", "query": "hardened ssh login policy",
     "scope": "security_admin", "expected_terms": [],
     "forbidden_path_prefix": "knowledge/"},
    # "export" is shell rc CONTENT (export PATH=...) and never in a path;
    # "paths.d" entries themselves are bare paths, hence the /etc/zshrc-
    # satisfied "system" term (zshrc body sources /etc/zshrc_* files).
    {"id": "r12_shell_rc", "query": "shell rc file environment variables",
     "scope": "shell_admin", "expected_terms": ["export"],
     "forbidden_path_prefix": "host/network/"},
    {"id": "r13_shell_no_docs", "query": "login PATH environment",
     "scope": "shell_admin", "expected_terms": [],
     "forbidden_path_prefix": "knowledge/"},
    {"id": "r14_package_repos", "query": "package repository mirror list",
     "scope": "package_admin", "expected_terms": ["server"],
     "forbidden_path_prefix": "host/network/"},
    {"id": "r15_package_no_docs", "query": "automatic package upgrades policy",
     "scope": "package_admin", "expected_terms": [],
     "forbidden_path_prefix": "knowledge/"},
    # grub.cfg is generated shell-like text: "linux" lines carry the kernel
    # path — CONTENT, not path (host/boot/boot/grub/grub.cfg).
    {"id": "r16_boot_kernel_cmdline", "query": "kernel command line boot entry",
     "scope": "boot_admin", "expected_terms": ["linux"],
     "forbidden_path_prefix": "host/storage/"},
    {"id": "r17_boot_no_docs", "query": "initramfs generation configuration",
     "scope": "boot_admin", "expected_terms": [],
     "forbidden_path_prefix": "knowledge/"},
    # smb.conf section headers ("[share]") are CONTENT; "valid users" is a
    # real smb.conf directive.
    {"id": "r18_sharing_exports", "query": "samba share definition",
     "scope": "sharing_admin", "expected_terms": ["valid"],
     "forbidden_path_prefix": "host/storage/"},
    {"id": "r19_sharing_no_docs", "query": "nfs export mount options",
     "scope": "sharing_admin", "expected_terms": [],
     "forbidden_path_prefix": "knowledge/"},
    # ── cross-platform negative probes: wrong-platform query under hard scope ──
    # Pass = 0 chunks or all chunks in-scope (no leakage)
    {"id": "s21_neg_homebrew_linux", "query": "homebrew brew install cask", "scope": "knowledge_linux",
     "expected_terms": [], "forbidden_path_prefix": "knowledge/macos/"},
    {"id": "s22_neg_diskutil_linux", "query": "diskutil apfs resize container", "scope": "knowledge_linux",
     "expected_terms": [], "forbidden_path_prefix": "knowledge/macos/"},
    {"id": "s23_neg_pacman_macos", "query": "pacman install package arch", "scope": "knowledge_macos",
     "expected_terms": [], "forbidden_path_prefix": "knowledge/linux/"},
    {"id": "s24_neg_systemctl_macos", "query": "systemctl service enable", "scope": "knowledge_macos",
     "expected_terms": [], "forbidden_path_prefix": "knowledge/linux/"}
]


def run_scoped_quality_gate(server_url: str, project_id: str, k: int = 5,
                            min_score: float = 0.15) -> Dict[str, Any]:
    """Run scoped queries and assert scope isolation (T-V.2)."""
    results = []
    passed_count = 0

    print(f"\nRunning Scoped Quality Gate on project {project_id}...\n")

    for tq in SCOPED_QUERIES:
        qid = tq["id"]
        query = tq["query"]
        scope = tq["scope"]
        expected_terms = tq["expected_terms"]
        forbidden = tq.get("forbidden_path_prefix", "")
        is_negative = qid.startswith("s2") and "neg" in qid  # s21-s24: cross-platform negatives

        url = f"{server_url}/projects/{project_id}/context"
        body = {
            "query": query,
            "k": k,
            "structured": True,
            "min_score": min_score,
            "include_sources": True,
            "scope": scope,
            "scope_mode": "hard",
            "trace_expand": True,
        }

        try:
            resp = requests.post(url, json=body, timeout=30.0)
            resp.raise_for_status()
            envelope = resp.json()
        except Exception as e:
            results.append({"id": qid, "query": query, "scope": scope,
                            "passed": False, "error": str(e), "chunks_returned": 0})
            print(f"X [{qid}] {query} -> ERROR: {e}")
            continue

        chunks = extract_chunks(data)

        # Match terms against chunk text only (not path strings)
        chunk_texts = [str(c.get("text", "") or c.get("content", "") or "") for c in chunks]
        combined_text = " ".join(chunk_texts).lower()
        all_paths = [c.get("source_path", "") for c in chunks]

        # Scope isolation: no chunk's source_path starts with the forbidden prefix
        leaked = [p for p in all_paths if forbidden and p.startswith(forbidden)]
        scope_clean = len(leaked) == 0

        if is_negative:
            # Negative probes: pass = 0 chunks or all chunks in-scope
            passed = scope_clean
            if passed:
                passed_count += 1
                print(f"+ [{qid}] scope={scope} {query} (clean: {len(chunks)} chunks, leaked={leaked})")
            else:
                print(f"X [{qid}] scope={scope} {query} -> LEAKED={leaked}")
        else:
            has_results = len(chunks) >= 2  # require at least 2 chunks
            has_non_empty = any(len(t.strip()) > 30 for t in chunk_texts)
            matched_terms = [t for t in expected_terms if t.lower() in combined_text]
            term_match_ratio = len(matched_terms) / len(expected_terms) if expected_terms else 1.0

            passed = has_results and has_non_empty and term_match_ratio >= 0.5 and scope_clean

            if passed:
                passed_count += 1
                print(f"+ [{qid}] scope={scope} {query} ({len(chunks)} chunks, terms={matched_terms})")
            else:
                reasons = []
                if not has_results: reasons.append(f"chunks={len(chunks)}(<2)")
                if not has_non_empty: reasons.append("empty_text")
                if term_match_ratio < 0.5: reasons.append(f"terms={matched_terms}/{expected_terms}")
                if not scope_clean: reasons.append(f"LEAKED={leaked}")
                print(f"X [{qid}] scope={scope} {query} -> {'; '.join(reasons)}")

        results.append({
            "id": qid, "query": query, "scope": scope,
            "passed": passed, "chunks_returned": len(chunks),
            "matched_terms": matched_terms if not is_negative else [],
            "expected_terms": expected_terms,
            "scope_leaked": leaked, "top_sources": all_paths[:3],
        })

    pass_rate = (passed_count / len(SCOPED_QUERIES)) * 100
    summary = {
        "total_queries": len(SCOPED_QUERIES),
        "passed_queries": passed_count,
        "failed_queries": len(SCOPED_QUERIES) - passed_count,
        "pass_rate_pct": pass_rate,
        "gate_passed": pass_rate >= 90.0,
        "details": results,
    }
    print(f"\n--- Scoped Quality Gate Results ---")
    print(f"Queries Passed: {passed_count}/{len(SCOPED_QUERIES)} ({pass_rate:.1f}%)")
    print(f"Status:         {'PASSED' if summary['gate_passed'] else 'FAILED'}")
    return summary


# ── LEG-MIN-03: Upstream scraper license verification harness ──────
#
# Documentation URLs can change licensing terms upstream without notice.
# This harness fetches a lightweight license/terms signal from each
# upstream source and verifies that the expected license keywords are
# still present. Run during the monthly CI/CD corpus refresh.
#
# Each probe specifies:
#   - url: the page to fetch (license page, about page, or footer)
#   - expect_any: list of keywords; at least one must appear in the page text
#   - expect_all: list of keywords; all must appear (stricter)
#   - timeout: per-request timeout in seconds
#
# A probe FAILS if:
#   - the page is unreachable (network error, non-200), OR
#   - none of the `expect_any` keywords are found, OR
#   - any of the `expect_all` keywords are missing
#
# A probe WARNS if the page is reachable but the license text has changed
# in a way that suggests a license switch (e.g. CC BY → All Rights Reserved).

LICENSE_PROBES = [
    {
        "source": "arch_wiki",
        "license": "GNU FDL 1.3",
        "url": "https://wiki.archlinux.org/title/ArchWiki:Copyrights",
        "expect_any": ["GNU Free Documentation License", "GFDL", "FDL 1.3"],
        "expect_all": [],
        "timeout": 15.0,
    },
    {
        "source": "tldr_pages",
        "license": "CC BY 4.0",
        "url": "https://github.com/tldr-pages/tldr/blob/main/LICENSE.md",
        "expect_any": ["Creative Commons Attribution 4.0", "CC BY 4.0", "CC-BY-4.0"],
        "expect_all": [],
        "timeout": 15.0,
    },
    {
        "source": "macos_homebrew",
        "license": "BSD-2-Clause",
        "url": "https://github.com/Homebrew/brew/blob/master/LICENSE.txt",
        "expect_any": ["BSD 2-Clause", "BSD-2-Clause", "Redistribution and use in source and binary"],
        "expect_all": [],
        "timeout": 15.0,
    },
    {
        "source": "macos_ask_different",
        "license": "CC BY-SA 4.0",
        "url": "https://stackoverflow.com/legal/terms-of-service/public",
        "expect_any": ["CC BY-SA", "Creative Commons Attribution-ShareAlike", "Attribution-ShareAlike"],
        "expect_all": [],
        "timeout": 15.0,
    },
    {
        "source": "macos_support_ss64",
        "license": "CC BY-NC 4.0",
        "url": "https://ss64.com/",
        "expect_any": ["copyright", "some rights reserved", "creative commons"],
        "expect_all": [],
        "timeout": 15.0,
    },
    {
        "source": "freebsd_handbook",
        "license": "FreeBSD Documentation License",
        "url": "https://www.freebsd.org/copyright/freebsd-doc-license/",
        "expect_any": ["FreeBSD Documentation License", "FreeBSD Project"],
        "expect_all": [],
        "timeout": 15.0,
    },
    {
        "source": "macos_macports_guide",
        "license": "BSD-like (MacPorts)",
        "url": "https://github.com/macports/macports-guide",
        "expect_any": ["BSD", "MacPorts", "license", "copyright"],
        "expect_all": [],
        "timeout": 15.0,
    },
    {
        "source": "linux_man_pages",
        "license": "Various (GPL, BSD, MIT)",
        "url": "https://www.kernel.org/doc/man-pages/",
        "expect_any": ["linux man-pages", "man-pages project", "kernel"],
        "expect_all": [],
        "timeout": 15.0,
        "note": "Per-page licenses; this probe only verifies the project page is live. "
                "Individual man page licenses must be checked at the bottom of each page.",
    },
]


def run_license_verification() -> Dict[str, Any]:
    """LEG-MIN-03: Verify upstream sources still carry their expected license terms.

    Fetches each probe URL and checks for expected license keywords. Returns a
    summary dict with per-source pass/fail status. Designed to run in CI/CD
    during the monthly corpus refresh; a failure means an upstream source may
    have changed its license and the corpus manifest needs review.
    """
    results = []
    passed_count = 0
    warned_count = 0

    print("Running Upstream License Verification (LEG-MIN-03)...\n")

    for probe in LICENSE_PROBES:
        source = probe["source"]
        expected_license = probe["license"]
        url = probe["url"]
        expect_any = probe.get("expect_any", [])
        expect_all = probe.get("expect_all", [])
        timeout = probe.get("timeout", 15.0)

        try:
            resp = requests.get(url, timeout=timeout, headers={
                "User-Agent": "Halbert-License-Check/1.0 (corpus quality gate)"
            })
            resp.raise_for_status()
            page_text = resp.text.lower()
        except Exception as e:
            results.append({
                "source": source,
                "license": expected_license,
                "url": url,
                "status": "FAIL",
                "reason": f"unreachable: {e}",
            })
            print(f"  FAIL [{source}] {url} -> unreachable: {e}")
            continue

        # Check expect_any: at least one keyword must be present
        found_any = [k for k in expect_any if k.lower() in page_text]
        any_ok = len(found_any) > 0 if expect_any else True

        # Check expect_all: all keywords must be present
        missing_all = [k for k in expect_all if k.lower() not in page_text]
        all_ok = len(missing_all) == 0

        # Detect license switch signals (page reachable but no license keywords at all)
        license_switch_signals = ["all rights reserved", "proprietary", "no license granted"]
        switch_detected = any(s in page_text for s in license_switch_signals) and not any_ok

        if any_ok and all_ok and not switch_detected:
            status = "PASS"
            passed_count += 1
            reason = f"found: {found_any}" if found_any else "ok"
        elif switch_detected:
            status = "WARN"
            warned_count += 1
            reason = f"possible license switch (found 'all rights reserved' but no expected keywords)"
        else:
            status = "FAIL"
            missing = [k for k in expect_any if k.lower() not in page_text]
            reason = f"expected keywords not found: {missing}"
            if missing_all:
                reason += f"; missing required: {missing_all}"

        results.append({
            "source": source,
            "license": expected_license,
            "url": url,
            "status": status,
            "reason": reason,
            "found_keywords": found_any,
        })
        print(f"  {status} [{source}] {expected_license} -> {reason}")

    total = len(LICENSE_PROBES)
    pass_rate = (passed_count / total) * 100 if total else 0
    # Gate passes if no FAILs; WARNs are informational (license text may have
    # moved to a different page, not necessarily changed terms)
    failed = total - passed_count - warned_count
    summary = {
        "total_sources": total,
        "passed": passed_count,
        "warned": warned_count,
        "failed": failed,
        "pass_rate_pct": pass_rate,
        "gate_passed": failed == 0,
        "details": results,
        "note": "WARN means the license page was reachable but expected keywords "
                "were not found — review the upstream site. FAIL means the page was "
                "unreachable or a license switch was detected.",
    }

    print(f"\n--- License Verification Results ---")
    print(f"Passed: {passed_count}/{total}  Warned: {warned_count}  Failed: {failed}")
    print(f"Status: {'PASSED' if summary['gate_passed'] else 'FAILED'}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Corpus Quality Gate for SourcePrep RAG")
    parser.add_argument("--project-id", type=str, default=None, help="SourcePrep Project ID")
    parser.add_argument("--project-name", type=str, default="halbert",
                        help="Project name to look up (default: halbert unified project)")
    parser.add_argument("--server-url", type=str, default="http://127.0.0.1:8400", help="SourcePrep Daemon URL")
    parser.add_argument("--k", type=int, default=5, help="Number of retrieved chunks")
    parser.add_argument("--report-file", type=Path, default=Path("data/quality_gate_report.json"))
    parser.add_argument("--scoped", action="store_true",
                        help="Run the T-V.2 scoped quality gate (20 scoped queries with isolation assertions)")
    parser.add_argument("--license-check", action="store_true",
                        help="Run the LEG-MIN-03 upstream license verification harness "
                             "(checks that scraped domains still carry their expected license terms)")

    args = parser.parse_args()

    # LEG-MIN-03: license verification can run standalone (no SourcePrep daemon needed)
    if args.license_check:
        lic_summary = run_license_verification()
        lic_report = Path(str(args.report_file).replace(".json", "_license.json"))
        lic_report.parent.mkdir(parents=True, exist_ok=True)
        with open(lic_report, "w", encoding="utf-8") as f:
            json.dump(lic_summary, f, indent=2)
        print(f"License verification report saved to {lic_report}")
        if not lic_summary["gate_passed"]:
            sys.exit(1)
        return

    project_id = args.project_id
    if not project_id:
        project_id = find_project_id(args.server_url, args.project_name)
        if not project_id:
            project_id = os.environ.get("SOURCEPREP_PROJECT_ID", "")
            if not project_id:
                print("ERROR: could not find project and no SOURCEPREP_PROJECT_ID set", file=sys.stderr)
                sys.exit(2)

    if args.scoped:
        summary = run_scoped_quality_gate(args.server_url, project_id, k=args.k)
        report_file = Path(str(args.report_file).replace(".json", "_scoped.json"))
    else:
        summary = run_quality_gate(args.server_url, project_id, k=args.k)
        report_file = args.report_file

    if report_file:
        report_file.parent.mkdir(parents=True, exist_ok=True)
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"Quality gate report saved to {report_file}")

    if not summary["gate_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
