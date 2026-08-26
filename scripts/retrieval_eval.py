#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Retrieval Evaluation Suite for Halbert RAG (Phase 0 T0e.2).
Evaluates precision, coverage, and latency across 40+ system administration queries.

Usage:
    python scripts/retrieval_eval.py [--project-id ID] [--server-url http://127.0.0.1:8400] [--k 5] [--report-file path]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests


BENCHMARK_QUERIES = [
    # macOS Specific
    {"query": "macOS APFS volume create container diskutil", "expected_sources": ["macos", "support", "man-pages"], "domain": "macos_storage"},
    {"query": "brew services list and restart service", "expected_sources": ["homebrew", "macos", "tldr"], "domain": "macos_packages"},
    {"query": "launchd daemon start plist configuration", "expected_sources": ["macos", "support", "man-pages"], "domain": "macos_services"},
    {"query": "macports port install build variant", "expected_sources": ["macports", "macos"], "domain": "macos_packages"},
    {"query": "codesign gatekeeper spctl assess app notarization", "expected_sources": ["macos", "support", "man-pages"], "domain": "macos_security"},
    {"query": "scutil network dns configuration macos", "expected_sources": ["macos", "man-pages"], "domain": "macos_network"},
    {"query": "defaults write com.apple screenshot location", "expected_sources": ["macos", "support", "ask-different"], "domain": "macos_config"},
    {"query": "tmutil startbackup time machine destination", "expected_sources": ["macos", "support", "man-pages"], "domain": "macos_backup"},

    # Linux Core & Distros
    {"query": "systemctl mask service prevent startup", "expected_sources": ["systemd", "arch-wiki", "man-pages"], "domain": "linux_init"},
    {"query": "journalctl vacuum-size logs cleanup", "expected_sources": ["systemd", "logging", "man-pages"], "domain": "linux_logging"},
    {"query": "pacman remove orphaned packages arch linux", "expected_sources": ["arch-wiki", "tldr"], "domain": "linux_packages"},
    {"query": "apt-get dist-upgrade ubuntu package repository", "expected_sources": ["ubuntu", "man-pages", "tldr"], "domain": "linux_packages"},
    {"query": "udevadm monitor kernel device events", "expected_sources": ["arch-wiki", "man-pages", "linux-core"], "domain": "linux_kernel"},
    {"query": "sysctl net.ipv4.ip_forward routing", "expected_sources": ["arch-wiki", "network", "man-pages"], "domain": "linux_kernel"},
    {"query": "btrfs subvolume create snapshot rollback", "expected_sources": ["arch-wiki", "filesystem"], "domain": "linux_storage"},
    {"query": "lvm lvextend resize physical volume group", "expected_sources": ["arch-wiki", "linux-utils", "man-pages"], "domain": "linux_storage"},

    # BSD Specific
    {"query": "freebsd handbook jail creation networking", "expected_sources": ["freebsd-handbook", "bsd"], "domain": "bsd_virtualization"},
    {"query": "freebsd pf firewall packet filter rules", "expected_sources": ["freebsd-handbook", "freebsd-man-pages"], "domain": "bsd_security"},
    {"query": "freebsd rc.conf enable sshd service", "expected_sources": ["freebsd-handbook", "freebsd-man-pages"], "domain": "bsd_init"},
    {"query": "zfs snapshot send receive zpool pool", "expected_sources": ["freebsd-handbook", "arch-wiki", "storage"], "domain": "bsd_storage"},

    # Version Control & Common Tools
    {"query": "git cherry-pick commit to another branch", "expected_sources": ["git", "common", "tldr"], "domain": "vcs"},
    {"query": "git bisect bad good find regression", "expected_sources": ["git", "common", "tldr"], "domain": "vcs"},
    {"query": "ssh agent add private key identity file", "expected_sources": ["ssh", "man-pages", "tldr"], "domain": "remote_access"},
    {"query": "rsync over ssh preserve permissions progress", "expected_sources": ["man-pages", "backup", "tldr"], "domain": "file_transfer"},
    {"query": "tmux create detached session attach window", "expected_sources": ["man-pages", "devtools", "tldr"], "domain": "terminal"},
    {"query": "htop sort processes by memory usage", "expected_sources": ["man-pages", "monitoring", "tldr"], "domain": "monitoring"},

    # Containers & Cloud
    {"query": "docker build multi stage dockerfile cache", "expected_sources": ["docker", "containers", "tldr"], "domain": "containers"},
    {"query": "podman run rootless container volume mount", "expected_sources": ["podman", "containers", "arch-wiki"], "domain": "containers"},
    {"query": "kubectl get pods namespace logs tail", "expected_sources": ["kubernetes", "helm-k8s", "tldr"], "domain": "k8s"},
    {"query": "aws s3 sync bucket local directory exclude", "expected_sources": ["aws-cli", "common", "tldr"], "domain": "cloud"},

    # Networking & Security
    {"query": "wireguard wg-quick up interface peer allowed-ips", "expected_sources": ["arch-wiki", "network", "tldr"], "domain": "networking"},
    {"query": "iptables nat prerouting port forwarding", "expected_sources": ["arch-wiki", "security", "man-pages"], "domain": "networking"},
    {"query": "nftables add table inet filter chain", "expected_sources": ["arch-wiki", "network", "man-pages"], "domain": "networking"},
    {"query": "openssl req x509 generate self-signed certificate", "expected_sources": ["ssl-certs", "security", "man-pages"], "domain": "security"},
    {"query": "ss -tulpn listen open ports sockets", "expected_sources": ["man-pages", "network", "tldr"], "domain": "networking"},

    # Text Processing & Scripting
    {"query": "sed replace string regex in file in-place", "expected_sources": ["shell", "man-pages", "tldr"], "domain": "text_processing"},
    {"query": "awk sum integers in column delimiter", "expected_sources": ["shell", "man-pages", "tldr"], "domain": "text_processing"},
    {"query": "jq parse json extract array objects field", "expected_sources": ["devtools", "man-pages", "tldr"], "domain": "text_processing"},
    {"query": "xargs parallel execution multiple processes", "expected_sources": ["shell", "man-pages", "tldr"], "domain": "scripting"},
    {"query": "curl download file follow redirect header auth", "expected_sources": ["devtools", "man-pages", "tldr"], "domain": "networking"},
]


def evaluate_retrieval(server_url: str, project_id: str, k: int = 5) -> Dict[str, Any]:
    """Run benchmark queries and evaluate precision, coverage, and latency."""
    results = []
    total_latency_ms = 0.0
    matched_queries = 0
    non_empty_results = 0

    print(f"Running Retrieval Evaluation on {len(BENCHMARK_QUERIES)} queries (k={k})...\n")

    for idx, bq in enumerate(BENCHMARK_QUERIES, 1):
        query = bq["query"]
        expected = bq["expected_sources"]
        domain = bq["domain"]

        start_time = time.time()
        url = f"{server_url}/projects/{project_id}/context"
        body = {
            "query": query,
            "k": k,
            "structured": True,
            "min_score": 0.10,
            "include_sources": True,
        }

        try:
            resp = requests.post(url, json=body, timeout=30.0)
            elapsed_ms = (time.time() - start_time) * 1000.0
            total_latency_ms += elapsed_ms
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000.0
            total_latency_ms += elapsed_ms
            results.append({
                "query": query,
                "domain": domain,
                "status": "error",
                "error": str(e),
                "latency_ms": elapsed_ms,
                "hit": False,
            })
            print(f"[{idx:02d}/{len(BENCHMARK_QUERIES)}] ✗ {query[:50]}... -> ERROR: {e}")
            continue

        chunks = data.get("chunks", [])
        if chunks:
            non_empty_results += 1

        # Check if any expected source substring is in file_path or content
        sources_found = [c.get("file_path", "") for c in chunks if c.get("file_path")]
        sources_str = " ".join(sources_found).lower()

        hit = any(exp.lower() in sources_str for exp in expected)
        if hit:
            matched_queries += 1
            print(f"[{idx:02d}/{len(BENCHMARK_QUERIES)}] ✓ {query[:50]}... ({elapsed_ms:.1f}ms, top: {sources_found[:2]})")
        else:
            print(f"[{idx:02d}/{len(BENCHMARK_QUERIES)}] ○ {query[:50]}... ({elapsed_ms:.1f}ms, top: {sources_found[:2]})")

        results.append({
            "query": query,
            "domain": domain,
            "status": "ok",
            "latency_ms": round(elapsed_ms, 2),
            "chunks_returned": len(chunks),
            "hit": hit,
            "expected_sources": expected,
            "sources_found": sources_found[:5],
        })

    avg_latency = total_latency_ms / len(BENCHMARK_QUERIES) if BENCHMARK_QUERIES else 0.0
    coverage_pct = (non_empty_results / len(BENCHMARK_QUERIES)) * 100
    precision_pct = (matched_queries / len(BENCHMARK_QUERIES)) * 100

    summary = {
        "total_queries": len(BENCHMARK_QUERIES),
        "coverage_pct": round(coverage_pct, 2),
        "precision_at_k_pct": round(precision_pct, 2),
        "avg_latency_ms": round(avg_latency, 2),
        "k": k,
        "details": results,
    }

    print("\n--- Retrieval Benchmark Results ---")
    print(f"Coverage (Results Returned): {non_empty_results}/{len(BENCHMARK_QUERIES)} ({coverage_pct:.1f}%)")
    print(f"Domain Hit Rate (P@{k}):      {matched_queries}/{len(BENCHMARK_QUERIES)} ({precision_pct:.1f}%)")
    print(f"Average Latency:             {avg_latency:.1f} ms")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Retrieval Evaluation for Halbert RAG")
    parser.add_argument("--project-id", type=str, default="8e34abfa-fa6a-4a63-ae12-8690a8666082")
    parser.add_argument("--server-url", type=str, default="http://127.0.0.1:8400")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--report-file", type=Path, default=Path("data/retrieval_eval_report.json"))

    args = parser.parse_args()

    summary = evaluate_retrieval(args.server_url, args.project_id, k=args.k)

    if args.report_file:
        with open(args.report_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"\nEvaluation report saved to {args.report_file}")


if __name__ == "__main__":
    main()
