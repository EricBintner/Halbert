#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Enrich catalog.json with citationIds and stopIds (plan Step 1b).

The join direction is one way (plan §3.1): catalog features carry
``citationIds`` referencing entries in marketing/shared/researchCitations.json.
This script inverts the per-stop codebase-grounding pass (workflow run
wf_2fd19a21-682, journal relatedFeatureIds) into those citationIds, derives
``stopIds`` per feature (the stops its citations sit at, optionally widened
with a curated hand-map below for features whose marketing relevance is
broader than their citations), and rewrites catalog.json preserving its exact
2-space-indent + trailing-newline formatting (round-trip verified before the
edit).

Kept in scripts/ for the same provenance reason as the citation builder.
Re-run only if the mapping is deliberately revised.

Usage: python3 scripts/enrich_catalog_citations.py   (writes, no args)
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG = REPO_ROOT / "marketing" / "feature-reference" / "src" / "catalog.json"
CITATIONS = REPO_ROOT / "marketing" / "shared" / "researchCitations.json"

# feature id -> citation ids, inverted from the grounding pass's measured
# relatedFeatureIds (journal, ground:* agents). Every value here came from an
# agent that read catalog.json and measured the citation against the code.
CITATION_IDS = {
    "right-sized-intelligence": ["distserve"],
    "air-gapped-private-execution": ["nist-sp-800-207", "saltzer-schroeder"],
    "hot-swap-providers": [],
    "context-compression": ["lost-in-the-middle", "context-length-hurts", "context-rot"],
    "agent-lifecycle": [],
    "secure-credential-storage": ["saltzer-schroeder"],
    "37-system-scanners": ["donut-telemetry-anomaly"],
    "gpu-accelerator-diagnostics": [],
    "four-whys-findings": ["log-anomaly", "donut-telemetry-anomaly"],
    "notification-attunement": [],
    "somatic-self-management": ["donut-telemetry-anomaly"],
    "morning-reports-reflexes": ["log-anomaly", "donut-telemetry-anomaly"],
    "computer-vision-suite": [],
    "apps-container-management": [],
    "blast-radius": [],
    "diff-proposals-rollback": ["concurrency-recovery"],
    "why-brain": [],
    "memory-vault": ["dynamo-store", "context-rot", "concurrency-recovery"],
    "provenance-tracking": ["concurrency-recovery"],
    "approval-queue": [],
    "hybrid-retrieval": ["lost-in-the-middle", "context-length-hurts", "rag-vs-graphrag", "bm25-beyond", "reciprocal-rank-fusion", "contextual-retrieval"],
    "indexed-documents": ["contextual-retrieval"],
    "cite-verify": [],
    "web-search-fallback": [],
    "three-panel-shell": [],
    "terminal-tiles-sandbox": ["apple-sandbox", "saltzer-schroeder"],
    "at-mentions": [],
    "command-palette": [],
    "shell-integration": [],
    "skill-registry": [],
    "design-language": [],
    "local-voice-pipeline": ["wyoming-protocol"],
    "acoustic-sensing": ["donut-telemetry-anomaly"],
    "screenshot-analysis": [],
    "voice-aura": [],
    "peer-pairing": ["rfc-9383-spake2", "swim-protocol", "mdns-dns-sd", "nist-sp-800-207", "tls13-rfc9846", "ed25519", "splitwise", "distserve", "petals-collaborative-inference", "ray-osdi-2018"],
    "canonical-host-satellites": ["swim-protocol", "mdns-dns-sd", "lamport-clocks", "dynamo-store", "linearizability", "tls13-rfc9846", "ed25519", "splitwise", "distserve", "petals-collaborative-inference", "ray-osdi-2018"],
    "remote-tool-proxy": ["tls13-rfc9846", "petals-collaborative-inference", "ray-osdi-2018"],
    "mcp-server": ["mcp-specification-2024-11-05"],
    "home-assistant-control": ["mcp-specification-2024-11-05", "matter-core-specification"],
    "cognitive-loop": [],
    "occupancy-behavior": ["lamport-clocks"],
    "frigate-nvr": [],
}

# Curated stopIds: the marketing anchor map (plan §3.2). stopIds and
# citationIds are deliberately INDEPENDENT associations — stopIds place a
# feature at the storyboard stops where its marketing story lives; the
# gate checks membership in the storyboard, not coupling to citations.
# The dossier's Section Focus tab shows a stop's features as: features
# whose stopIds include that stop. Features with no marketing stop get no
# stopIds (they remain in the catalog and the All-Research tab).
STOP_IDS = {
    # intro — Meet Halbert: native MCP + ambient sensory
    "mcp-server": ["intro"],
    "local-voice-pipeline": ["intro"],
    "acoustic-sensing": ["intro"],
    "voice-aura": ["intro"],
    # open — Triage: proactive findings
    "four-whys-findings": ["open"],
    "morning-reports-reflexes": ["open"],
    "37-system-scanners": ["open"],
    "somatic-self-management": ["open"],
    "gpu-accelerator-diagnostics": ["open"],
    # apex — Automation: home & host chores
    "home-assistant-control": ["apex"],
    "apps-container-management": ["apex"],
    "occupancy-behavior": ["apex"],
    "frigate-nvr": ["apex"],
    # diagonal — Local: private by construction
    "air-gapped-private-execution": ["diagonal"],
    "secure-credential-storage": ["diagonal"],
    "hot-swap-providers": ["diagonal"],
    "web-search-fallback": ["diagonal"],
    # rise — Rationale: intent beside the change
    "why-brain": ["rise"],
    "provenance-tracking": ["rise"],
    "diff-proposals-rollback": ["rise"],
    "memory-vault": ["rise"],
    "blast-radius": ["rise"],
    "approval-queue": ["rise"],
    # hop — Knowledge: grounded answers
    "hybrid-retrieval": ["hop"],
    "indexed-documents": ["hop"],
    "cite-verify": ["hop"],
    "context-compression": ["hop"],
    # cap — Distributed: nodes of shared intelligence
    "peer-pairing": ["cap"],
    "canonical-host-satellites": ["cap"],
    "remote-tool-proxy": ["cap"],
    # reveal — Get Halbert: open source
    "design-language": ["reveal"],
    "three-panel-shell": ["reveal"],
    "terminal-tiles-sandbox": ["reveal"],
    "command-palette": ["reveal"],
    "skill-registry": ["reveal"],
    "shell-integration": ["reveal"],
}


def main() -> None:
    citations = json.loads(CITATIONS.read_text(encoding="utf-8"))["citations"]
    cit_stops = {c["id"]: c["stopId"] for c in citations}
    cit_ids = set(cit_stops)

    raw = CATALOG.read_text(encoding="utf-8")
    data = json.loads(raw)

    features = data["features"]
    known = {f["id"] for f in features}
    unknown = set(CITATION_IDS) - known
    assert not unknown, f"CITATION_IDS keys not in catalog: {unknown}"
    bad_cit = {cid for ids in CITATION_IDS.values() for cid in ids} - cit_ids
    assert not bad_cit, f"citationIds referencing unknown citations: {bad_cit}"

    touched = 0
    for f in features:
        cids = sorted(set(CITATION_IDS.get(f["id"], [])))
        stops = sorted(set(STOP_IDS.get(f["id"], [])))
        if cids:
            f["citationIds"] = cids
            touched += 1
        else:
            f.pop("citationIds", None)
        if stops:
            f["stopIds"] = stops
        else:
            f.pop("stopIds", None)

    data["version"] = data.get("version", 0) + 1
    CATALOG.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    n_cit = sum(len(v) for v in CITATION_IDS.values())
    print(f"enriched {touched}/{len(features)} features with citation joins; {len(STOP_IDS)} curated stop-anchor sets")
    print(f"catalog version -> {data['version']}")


if __name__ == "__main__":
    main()