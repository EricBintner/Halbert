#!/usr/bin/env python3
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


def find_project_id(server_url: str, project_name: str = "halbert-knowledge") -> Optional[str]:
    """Find project ID by name from the SourcePrep daemon."""
    try:
        r = requests.get(f"{server_url}/projects", timeout=10.0)
        if r.status_code == 200:
            for p in r.json().get("projects", []):
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
            "min_score": min_score,
            "include_sources": True,
        }

        try:
            resp = requests.post(url, json=body, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
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

        chunks = data.get("chunks", [])
        if not chunks and "content" in data:
            # Fallback to search endpoint if context returns raw text
            chunks = [{"content": data.get("content", ""), "score": 1.0, "file_path": ""}]

        # Validate results
        has_results = len(chunks) > 0
        has_non_empty = any(len(c.get("content", "").strip()) > 30 for c in chunks)

        # Check for expected terms
        combined_text = " ".join(c.get("content", "") + " " + c.get("file_path", "") for c in chunks).lower()
        matched_terms = [t for t in expected_terms if t.lower() in combined_text]
        term_match_ratio = len(matched_terms) / len(expected_terms) if expected_terms else 1.0

        # Query passes if results are returned, non-empty, and at least 50% of expected terms matched
        passed = has_results and has_non_empty and term_match_ratio >= 0.5

        if passed:
            passed_count += 1
            print(f"✓ [{qid}] {query} ({len(chunks)} chunks, matched terms: {matched_terms})")
        else:
            print(f"✗ [{qid}] {query} (chunks: {len(chunks)}, non_empty: {has_non_empty}, matched: {matched_terms}/{expected_terms})")

        top_sources = [c.get("file_path", "") for c in chunks[:3] if c.get("file_path")]
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


def main():
    parser = argparse.ArgumentParser(description="Corpus Quality Gate for SourcePrep RAG")
    parser.add_argument("--project-id", type=str, default=None, help="SourcePrep Project ID")
    parser.add_argument("--server-url", type=str, default="http://127.0.0.1:8400", help="SourcePrep Daemon URL")
    parser.add_argument("--k", type=int, default=5, help="Number of retrieved chunks")
    parser.add_argument("--report-file", type=Path, default=Path("data/quality_gate_report.json"))

    args = parser.parse_args()

    project_id = args.project_id
    if not project_id:
        project_id = find_project_id(args.server_url, "halbert-knowledge")
        if not project_id:
            project_id = os.environ.get("SOURCEPREP_PROJECT_ID", "8e34abfa-fa6a-4a63-ae12-8690a8666082")

    summary = run_quality_gate(args.server_url, project_id, k=args.k)

    if args.report_file:
        with open(args.report_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"Quality gate report saved to {args.report_file}")

    if not summary["gate_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
