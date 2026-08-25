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
    {"id": "s03_linux_systemd", "query": "systemd unit file restart", "scope": "knowledge-linux",
     "expected_terms": ["systemd", "unit", "restart"], "forbidden_path_prefix": "knowledge/macos/"},
    {"id": "s04_linux_pacman", "query": "pacman install package arch", "scope": "knowledge-linux",
     "expected_terms": ["pacman", "package"], "forbidden_path_prefix": "knowledge/macos/"},
    {"id": "s05_linux_iptables", "query": "iptables firewall rule drop", "scope": "knowledge-linux",
     "expected_terms": ["iptables", "firewall"], "forbidden_path_prefix": "knowledge/macos/"},
    {"id": "s06_linux_arch_wiki", "query": "arch linux network configuration", "scope": "knowledge-linux",
     "expected_terms": ["network", "config"], "forbidden_path_prefix": "knowledge/macos/"},
    {"id": "s07_linux_nvidia", "query": "nvidia-smi gpu cuda", "scope": "knowledge-linux",
     "expected_terms": ["nvidia", "gpu"], "forbidden_path_prefix": "knowledge/macos/"},
    # ── knowledge-macos scope ──
    {"id": "s08_macos_diskutil", "query": "diskutil apfs resize container", "scope": "knowledge-macos",
     "expected_terms": ["diskutil", "apfs"], "forbidden_path_prefix": "knowledge/linux/"},
    {"id": "s09_macos_homebrew", "query": "homebrew brew install cask", "scope": "knowledge-macos",
     "expected_terms": ["brew", "install"], "forbidden_path_prefix": "knowledge/linux/"},
    {"id": "s10_macos_launchctl", "query": "launchctl load launchd plist", "scope": "knowledge-macos",
     "expected_terms": ["launchctl", "launchd"], "forbidden_path_prefix": "knowledge/linux/"},
    {"id": "s11_macos_macports", "query": "macports port install variant", "scope": "knowledge-macos",
     "expected_terms": ["macports", "port"], "forbidden_path_prefix": "knowledge/linux/"},
    # ── knowledge-bsd scope ──
    {"id": "s12_bsd_freebsd_net", "query": "freebsd network interface rc.conf", "scope": "knowledge-bsd",
     "expected_terms": ["freebsd", "network"], "forbidden_path_prefix": "knowledge/linux/"},
    {"id": "s13_bsd_freebsd_handbook", "query": "freebsd handbook ports system", "scope": "knowledge-bsd",
     "expected_terms": ["freebsd", "ports"], "forbidden_path_prefix": "knowledge/linux/"},
    # ── knowledge-common scope ──
    {"id": "s14_common_git", "query": "git rebase interactive squash", "scope": "knowledge-common",
     "expected_terms": ["git", "rebase"], "forbidden_path_prefix": "knowledge/linux/"},
    {"id": "s15_common_docker", "query": "docker compose up detached", "scope": "knowledge-common",
     "expected_terms": ["docker", "compose"], "forbidden_path_prefix": "knowledge/linux/"},
    {"id": "s16_common_curl", "query": "curl post json http", "scope": "knowledge-common",
     "expected_terms": ["curl", "http"], "forbidden_path_prefix": "knowledge/linux/"},
    {"id": "s17_common_awk", "query": "awk print column field delimiter", "scope": "knowledge-common",
     "expected_terms": ["awk", "print"], "forbidden_path_prefix": "knowledge/linux/"},
    {"id": "s18_common_tar", "query": "tar extract gzip archive", "scope": "knowledge-common",
     "expected_terms": ["tar", "extract"], "forbidden_path_prefix": "knowledge/linux/"},
    # ── cross-scope isolation: linux query must NOT return macos chunks ──
    {"id": "s19_isolation_linux", "query": "systemctl service enable", "scope": "knowledge-linux",
     "expected_terms": ["systemctl", "service"], "forbidden_path_prefix": "knowledge/macos/"},
    {"id": "s20_isolation_macos", "query": "brew tap homebrew cask", "scope": "knowledge-macos",
     "expected_terms": ["brew", "cask"], "forbidden_path_prefix": "knowledge/linux/"},
]


def run_scoped_quality_gate(server_url: str, project_id: str, k: int = 5,
                            min_score: float = 0.15) -> Dict[str, Any]:
    """Run 20 scoped queries and assert scope isolation (T-V.2)."""
    results = []
    passed_count = 0

    print(f"\nRunning Scoped Quality Gate on project {project_id}...\n")

    for tq in SCOPED_QUERIES:
        qid = tq["id"]
        query = tq["query"]
        scope = tq["scope"]
        expected_terms = tq["expected_terms"]
        forbidden = tq.get("forbidden_path_prefix", "")

        url = f"{server_url}/projects/{project_id}/context"
        body = {
            "query": query,
            "k": k,
            "structured": True,
            "min_score": min_score,
            "include_sources": True,
            "scope": scope,
            "trace_expand": True,
        }

        try:
            resp = requests.post(url, json=body, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            results.append({"id": qid, "query": query, "scope": scope,
                            "passed": False, "error": str(e), "chunks_returned": 0})
            print(f"X [{qid}] {query} -> ERROR: {e}")
            continue

        chunks = data.get("chunks", [])
        if not chunks and "content" in data:
            chunks = [{"content": data.get("content", ""), "score": 1.0, "file_path": ""}]

        has_results = len(chunks) > 0
        has_non_empty = any(len(c.get("content", "").strip()) > 30 for c in chunks)
        combined_text = " ".join(c.get("content", "") + " " + c.get("file_path", "") for c in chunks).lower()
        matched_terms = [t for t in expected_terms if t.lower() in combined_text]
        term_match_ratio = len(matched_terms) / len(expected_terms) if expected_terms else 1.0

        # Scope isolation: no chunk's file_path starts with the forbidden prefix
        all_paths = [c.get("file_path", "") for c in chunks]
        leaked = [p for p in all_paths if forbidden and p.startswith(forbidden)]
        scope_clean = len(leaked) == 0

        passed = has_results and has_non_empty and term_match_ratio >= 0.5 and scope_clean

        if passed:
            passed_count += 1
            print(f"+ [{qid}] scope={scope} {query} ({len(chunks)} chunks, terms={matched_terms})")
        else:
            reasons = []
            if not has_results: reasons.append("no_results")
            if not has_non_empty: reasons.append("empty_chunks")
            if term_match_ratio < 0.5: reasons.append(f"terms={matched_terms}/{expected_terms}")
            if not scope_clean: reasons.append(f"LEAKED={leaked}")
            print(f"X [{qid}] scope={scope} {query} -> {'; '.join(reasons)}")

        results.append({
            "id": qid, "query": query, "scope": scope,
            "passed": passed, "chunks_returned": len(chunks),
            "matched_terms": matched_terms, "expected_terms": expected_terms,
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

    args = parser.parse_args()

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
