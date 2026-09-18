#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Assemble sites/shared/researchCitations.json from verified records.

One-shot builder used 2026-09-15 to land the v10 dossier citation dictionary
from the 38-agent verification/grounding workflow (run wf_2fd19a21-682).
Kept in scripts/ so the provenance of every field is reconstructable: all
bibliographic fields come from the per-citation web-verification agents, all
`applied` statuses and prose from the per-stop codebase-grounding agents,
with the editorial deltas recorded in plan §7. Re-run only if the dictionary
is deliberately revised.

Usage: python3 scripts/build_research_citations.py   (writes the JSON, no args)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "sites" / "shared" / "researchCitations.json"

SCHEMA_NOTE = (
    "Halbert research citation dictionary. Schema, join rules and copy "
    "directives: .handoff/PLAN-MARKETING-V10-TECHNICAL-DOSSIER-AND-RESEARCH-"
    "CITATIONS-2026-09-15.md §3.1. Gate: scripts/check_research_citations.py "
    "(must pass before any deploy). Voice: third person, academic register "
    "(founder ruling 2026-09-15). Every entry web-verified and codebase-"
    "grounded 2026-09-15; see plan §7 for the verification methodology. "
    "No relatedFeatureIds here — features in catalog.json carry citationIds; "
    "the reverse join is derived at load."
)

REQUIRED = (
    "id", "stopId", "title", "authors", "venue", "year",
    "url", "identifier", "type", "peerReviewed", "category",
    "applied", "takeaway", "howHalbertApplies",
)

SHIPPED_PATH_RE = re.compile(r"halbert_core/[A-Za-z0-9_/.-]+")


def C(
    cid, stopId, title, authors, venue, year, url, identifier,
    typ, peerReviewed, category, applied, takeaway, how,
    **extra,
):
    c = {
        "id": cid, "stopId": stopId, "title": title, "authors": authors,
        "venue": venue, "year": year, "url": url, "identifier": identifier,
        "type": typ, "peerReviewed": peerReviewed, "category": category,
        "applied": applied, "takeaway": takeaway, "howHalbertApplies": how,
    }
    c.update(extra)
    return c


CITATIONS = [
    C(
        "mcp-specification-2024-11-05", "intro",
        "Model Context Protocol Specification",
        "Anthropic",
        "modelcontextprotocol.io (announced in “Introducing the Model Context Protocol”, anthropic.com, Nov 25 2024)",
        2024,
        "https://modelcontextprotocol.io/specification/2024-11-05",
        "MCP Specification 2024-11-05",
        "spec", False, "systems", "shipped",
        "The specification defines MCP as an open protocol that uses JSON-RPC 2.0 messages between hosts, clients, and servers to give LLM applications a standardized way to connect to external data sources and tools, with servers exposing resources, prompts, and tools.",
        "Halbert ships a native MCP server (halbert_core/halbert_core/mcp/server.py, entry point halbert-mcp-serve) that answers the initialize handshake with protocol version 2024-11-05 and dispatches a registered tool set spanning host management (vitals, scanner findings, config queries and diffs, knowledge search) and home automation (Home Assistant entity state and service calls), each routed through a fail-closed tool-classification gate and the redaction boundary before anything leaves the machine. Halbert also consumes external MCP servers as a client (halbert_core/halbert_core/mcp/client.py), making it both host and consumer of the protocol.",
    ),
    C(
        "rfc-9383-spake2", "intro",
        "SPAKE2+, an Augmented Password-Authenticated Key Exchange (PAKE) Protocol",
        "T. Taubert & C. A. Wood, IETF",
        "IETF RFC 9383 (Informational, Independent Submissions stream)",
        2023,
        "https://datatracker.ietf.org/doc/rfc9383/",
        "RFC 9383",
        "rfc", False, "security", "deferred",
        "The RFC specifies SPAKE2+, an augmented password-authenticated key exchange protocol in which only one party has knowledge of the password, enabling two parties to derive a strong shared key with no risk of disclosing the password, and which is simple to implement, compatible with any prime-order group, and computationally efficient.",
        "SPAKE2+ was evaluated in Halbert's inter-node pairing research (.handoff/research/multi-node-systems/01-AUTH-AND-ZERO-TRUST-CLUSTERING.md), which rated it the gold standard for zero-config device pairing, and was explicitly deferred (DECISIONS.md, SEC-TLS) in favour of TLS with self-signed certificates and SHA-256 fingerprint pinning plus the existing operator approval gate — on the grounds that no maintained augmented-PAKE library fits Halbert's two-hard-dependency contract and a 2–3 node home cluster does not demand active-MITM resistance inside the initial exchange window. The shipped alternative lives in halbert_core/halbert_core/federation/tls.py.",
    ),
    C(
        "wyoming-protocol", "intro",
        "Wyoming Protocol",
        "M. Hansen / Open Home Foundation",
        "Open Home Foundation (github.com/OHF-Voice/wyoming; originally Rhasspy)",
        2023,
        "https://github.com/OHF-Voice/wyoming",
        "OHF-Voice/wyoming",
        "spec", False, "systems", "shipped",
        "Wyoming defines a peer-to-peer TCP protocol for voice assistants — a JSON header line plus optional binary PCM audio payload — with event flows for wake-word detection, speech-to-text, text-to-speech, and intent recognition, deliberately carrying no authentication or encryption because it is intended only for trusted local networks.",
        "Halbert speaks the Wyoming voice-satellite protocol natively: halbert_core/halbert_core/integrations/wyoming_agent.py implements the Wyoming JSONL TCP protocol so that Home Assistant's voice pipeline can route transcripts through Halbert's agent turn, halbert_core/halbert_core/audio/ingress/wyoming_ingress.py implements the canonical hybrid framing (JSON header plus binary PCM payload) for satellite audio capture, and halbert_core/halbert_core/audio/egress/wyoming_egress.py streams synthesized speech back to thin satellites over the same connection. The listener binds loopback by default and requires a shared token for any off-loopback satellite (DECISIONS.md, Wyoming defaults).",
    ),
    C(
        "swim-protocol", "open",
        "SWIM: Scalable Weakly-consistent Infection-style Process Group Membership Protocol",
        "A. Das, I. Gupta & A. Motivala",
        "Proceedings of the International Conference on Dependable Systems and Networks (DSN 2002), pp. 303–312, IEEE Computer Society",
        2002,
        "https://doi.org/10.1109/DSN.2002.1028914",
        "DOI: 10.1109/DSN.2002.1028914",
        "paper", True, "distributed", "deferred",
        "SWIM decouples process group membership into a failure-detection component — each member directly pings one randomly chosen peer per protocol round, escalating to indirect probes via other members before declaring failure — and an infection-style (gossip) dissemination component that piggybacks membership updates on ping messages, yielding complete failure detection and eventually consistent membership lists with low, constant per-member message load and no central server.",
        "SWIM's gossip-based membership was evaluated in Halbert's multi-node resilience research and explicitly deferred as over-engineering at the two-to-three-node scale Halbert targets; the review judged the existing hysteresis detector adequate and SWIM's indirect probing worthwhile only at roughly ten-plus nodes. What ships in its place is a hysteresis failure detector — consecutive failed health probes before a peer is marked offline, one success to restore it — in halbert_core/halbert_core/federation/compute_router.py.",
    ),
    C(
        "log-anomaly", "open",
        "LogAnomaly: Unsupervised Detection of Sequential and Quantitative Anomalies in Unstructured Logs",
        "W. Meng et al.",
        "IJCAI 2019 (Proceedings of the Twenty-Eighth International Joint Conference on Artificial Intelligence, pp. 4739–4745)",
        2019,
        "https://www.ijcai.org/proceedings/2019/658",
        "DOI 10.24963/ijcai.2019/658",
        "paper", True, "systems", "design",
        "LogAnomaly detects both sequential (workflow-order) and quantitative (count-based) anomalies in unstructured system logs without labels by representing log templates with a template2vec semantic embedding, cutting false alarms caused by previously unseen log templates.",
        "The log-anomaly tradition frames the problem domain of Halbert's proactive log triage — reading machine logs for signals before they become a person's problem — but Halbert implements the deterministic subset of it. Journald streams are collected continuously into the retrieval store (halbert_core/halbert_core/ingestion/journald.py), while anomaly triage runs on threshold rules (halbert_core/halbert_core/autonomy/anomaly_detector.py) and rule-based detectors (halbert_core/halbert_core/findings/detectors/) rather than learned models; no model is trained on or applied to Halbert's log streams.",
        replacementNote="Replacement for the planned “Log-Based Anomaly (Lin et al. 2020)”, which verification confirmed does not exist (plan §7).",
    ),
    C(
        "donut-telemetry-anomaly", "open",
        "Unsupervised Anomaly Detection via Variational Auto-Encoder for Seasonal KPIs in Web Applications",
        "H. Xu et al. (13 authors)",
        "WWW 2018 (Proceedings of the 2018 World Wide Web Conference)",
        2018,
        "https://dl.acm.org/doi/10.1145/3178876.3185996",
        "DOI 10.1145/3178876.3185996",
        "paper", True, "systems", "design",
        "Donut, an unsupervised anomaly-detection algorithm based on a variational auto-encoder, detects anomalies on seasonal KPI telemetry streams without labels, using MCMC-imputation-based training and ensemble inference to work around missing data and adapt to varied KPI patterns.",
        "Donut represents the learned-model end of telemetry anomaly detection, and Halbert deliberately implements the deterministic subset instead: continuous telemetry ingestion (journald and hardware-sensor streams, halbert_core/halbert_core/ingestion/journald.py and halbert_core/halbert_core/ingestion/hwmon.py) feeds threshold-rule anomaly triage (halbert_core/halbert_core/autonomy/anomaly_detector.py) and scheduled detector sweeps, gated before anything reaches the user (halbert_core/halbert_core/proactive/gate.py). No model is trained on or applied to Halbert's telemetry streams.",
        replacementNote="Replacement for the planned “Proactive Telemetry (Poskitt 2018)”, which verification confirmed does not exist (plan §7).",
    ),
    C(
        "matter-core-specification", "apex",
        "Matter Core Specification",
        "Connectivity Standards Alliance",
        "Connectivity Standards Alliance (csa-iot.org)",
        2022,
        "https://csa-iot.org/all-solutions/matter/",
        "Matter 1.0",
        "spec", False, "systems", "deferred",
        "Matter is an open-source, royalty-free, citedIP-based application-layer connectivity standard that unifies smart-home device communication across vendors and ecosystems, with its first (1.0) release running over Wi-Fi and Thread network layers and using Bluetooth Low Energy for commissioning.",
        "Halbert evaluated a native Matter controller during its 2026-08-31 home-automation strategy review and explicitly deferred it: the Rust stack was judged not production-ready for controller use, and the ratified three-layer strategy keeps Home Assistant as the path through which Matter devices are reached. No Matter protocol code exists in the tree today; device control instead flows through the shipped Home Assistant REST client (halbert_core/halbert_core/integrations/home_assistant/ha_client.py) and the MQTT subscriber infrastructure reused from the Frigate integration.",
    ),
    C(
        "mdns-dns-sd", "apex",
        "Multicast DNS (RFC 6762) and DNS-Based Service Discovery (RFC 6763)",
        "S. Cheshire & M. Krochmal, IETF",
        "IETF RFC 6762 & RFC 6763",
        2013,
        "https://datatracker.ietf.org/doc/rfc6762/",
        "RFC 6762; RFC 6763",
        "rfc", False, "distributed", "design",
        "The two RFCs together define zero-configuration networking on a local link: multicast DNS resolves hostnames and service instances in the absence of unicast DNS, and DNS-SD describes how services advertise themselves as named resource records so clients can enumerate them without configuration.",
        "Halbert's federation design adopts DNS-SD service advertisement in full — a _halbert._tcp service type whose TXT record carries node id, role, capabilities, and offered compute backends — but the multicast mechanism itself remains fenced scaffold: the beacon and listener classes in halbert_core/halbert_core/federation/peer_discovery.py raise NotImplementedError pending wiring, so manual-IP pairing is the deliberate fallback (mDNS link-local multicast does not cross Tailscale tunnels, per the module's design notes). What ships today is the surrounding surface — the PIN/token pairing handshake — plus hostname resolution that strips mDNS/DHCP suffixes in halbert_core/halbert_core/identity.py.",
    ),
    C(
        "lamport-clocks", "apex",
        "Time, Clocks, and the Ordering of Events in a Distributed System",
        "L. Lamport",
        "Communications of the ACM, 21(7), pp. 558–565",
        1978,
        "https://dl.acm.org/doi/10.1145/359545.359563",
        "DOI 10.1145/359545.359563",
        "paper", True, "distributed", "design",
        "Distributed systems have no single notion of “now”: Lamport defines the happens-before relation and logical clocks so that a system of communicating sequential processes can order its events without synchronized physical clocks, and can derive a total ordering when needed.",
        "Halbert's event ordering today is single-node and wall-clock: the persistent event ledger in halbert_core/halbert_core/continuity/timeline.py stamps every home and host event with a Unix timestamp and answers “what happened before X?” by timestamp-window correlation. Lamport's insight — that independently writing nodes share no usable clock and need logical ordering — appears in Halbert's design record as an open question rather than code: the dual-memory review (.handoff/FABLE-HANDOFF-DUAL-MEMORY-SECOND-OPINION-2026-09-10.md) asks whether observation time, write time, or a per-claim version vector governs causal ordering between Halbert's store and a second memory source, and no logical-clock mechanism exists in the tree.",
    ),
    C(
        "apple-sandbox", "diagonal",
        "The Apple Sandbox",
        "D. Blazakis",
        "Black Hat DC 2011",
        2011,
        "https://dl.packetstormsecurity.net/papers/general/apple-sandbox.pdf",
        "",
        "engineering-report", False, "security", "shipped",
        "Documents the design and implementation of Apple's XNU Sandbox — previously codenamed Seatbelt — a fine-grained, user-configurable, per-process access-control system defined by Scheme-based policy profiles and enforced in the kernel as a policy module for the TrustedBSD mandatory access control (MAC) framework.",
        "Halbert wraps agent-issued shell commands in a seatbelt profile generated by halbert_core/halbert_core/streaming/sandbox.py, applied at the terminal execution routes and covered by halbert_core/tests/test_sandbox.py. The hardened deny-by-default profile Halbert researched — including the measured finding that seatbelt matches resolved vnodes, so an unresolved path rule grants nothing — lives in .handoff/research/sec-2-3/seatbelt.md and was deliberately held back after adversarial review found it fails silently on some diagnostics; that research directory's own README states plainly that none of it is wired in.",
        identifierNote="Industry-conference paper; no DOI is registered in OpenAlex or Crossref, and no canonical host survives (semantiscope.com is dead, Black Hat archives 403). The open mirror recorded as the work's landing page by OpenAlex is used.",
        profileOf="The macOS mechanism the plan's “Seatbelt / TrustedBSD MAC” label points at; the canonical published description of that mechanism.",
    ),
    C(
        "tls13-rfc9846", "diagonal",
        "The Transport Layer Security (TLS) Protocol Version 1.3",
        "E. Rescorla, IETF",
        "IETF RFC 9846 (Proposed Standard)",
        2026,
        "https://datatracker.ietf.org/doc/rfc9846/",
        "RFC 9846",
        "rfc", False, "security", "shipped",
        "The current specification of TLS 1.3: a redesigned secure-channel protocol giving two peers authentication, confidentiality, and integrity even against an attacker who fully controls the network, via forward-secret-only key exchange, AEAD-only cipher suites, an encrypted handshake, and HKDF-based key derivation.",
        "Halbert encrypts inter-node daemon-to-daemon traffic through halbert_core/halbert_core/federation/tls.py: each node generates a long-lived self-signed certificate, peers pin SHA-256 fingerprints rather than trusting a CA, and a dedicated HTTPS listener serves only the peer-facing routes. The implementation floors the protocol at TLS 1.2 rather than requiring TLS 1.3, and authentication rides the existing per-peer bearer token rather than mutual TLS; the DECISIONS.md SEC-TLS row records both the shipped design and the deliberate deferral of a PAKE upgrade for a 2–3 node home cluster.",
        appliedNote="Cites the current TLS 1.3 specification: the original 2018 document (RFC 8446) is formally obsoleted by RFC 9846 (July 2026), a backward-compatible revision by the same author with the same title.",
    ),
    C(
        "nist-sp-800-207", "diagonal",
        "Zero Trust Architecture",
        "R. K. Rose, S. Borchert, results Mitchell & S. Connerly (NIST)",
        "NIST Special Publication 800-207",
        2020,
        "https://doi.org/10.6028/NIST.SP.800-207",
        "NIST SP 800-207 (DOI: 10.6028/NIST.SP.800-207)",
        "spec", False, "security", "design",
        "An enterprise's attack surface shrinks when no implicit trust is granted to any network position: NIST SP 800-207 describes zero trust as eliminating implicit trust in network location, applying per-request authentication and authorization with least privilege, and relying on dynamic, continuously evaluated access policies.",
        "Zero-trust doctrine shapes Halbert's federation architecture rather than appearing as a named subsystem: the multi-node research (.handoff/research/multi-node-systems/01-AUTH-AND-ZERO-TRUST-CLUSTERING.md) rejects the trusted-LAN assumption outright and drives the per-request token validation, constant-time comparison and surgical revocation now shipped in halbert_core/halbert_core/federation/peer_middleware.py and halbert_core/halbert_core/federation/peers_config.py. The same fail-closed posture governs the secure-turn gate in halbert_core/halbert_core/dashboard/routes/agent.py, which refuses a turn carrying secrets rather than downgrading it to a cloud endpoint. The full scheme the research recommended — mutual TLS everywhere and PAKE pairing — was scaled down in the SEC-TLS decision to TLS with fingerprint pinning, on the measured grounds of a 2–3 node cluster.",
    ),
    C(
        "osv-vulnerability-database", "diagonal",
        "OSV: A distributed vulnerability database for Open Source",
        "Google / OpenSSF",
        "osv.dev (Google; OSV schema stewarded by OpenSSF)",
        2021,
        "https://osv.dev/",
        "",
        "spec", False, "security", "shipped",
        "OSV is an open, distributed vulnerability database that aggregates open-source advisory data across ecosystems and serves precise, machine-readable records — including where each vulnerability was introduced and where it was fixed — queryable by package version or commit hash.",
        "Halbert ships an opt-in, off-by-default preflight that asks OSV about the exact package an MCP config entry would install, before that server is ever spawned: halbert_core/halbert_core/mcp/package_preflight.py, run from MCPClient._ensure at the launch point in halbert_core/halbert_core/mcp/client.py. Only package coordinates leave the machine — not the file entry, command line or environment — and a refusal stops that one server, never the daemon. The DECISIONS.md FD-10 row records the build, the founder ratification, and the wire contract verified against the real OSV endpoint on 2026-09-10.",
        identifierNote="A living database and schema, not a static publication; the site itself is the canonical identifier.",
    ),
    C(
        "dynamo-store", "rise",
        "Dynamo: Amazon's Highly Available Key-Value Store",
        "G. DeCandia et al.",
        "SOSP 2007 — Proceedings of the 21st ACM Symposium on Operating Systems Principles (Stevenson, WA)",
        2007,
        "https://dl.acm.org/doi/10.1145/1294261.1294281",
        "DOI:10.1145/1294261.1294281",
        "paper", True, "distributed", "design",
        "Dynamo is a decentralized, eventually-consistent replicated key-value store that some of Amazon's core services rely on for an “always-on” experience, deliberately sacrificing consistency under certain failure scenarios and instead using consistent hashing, object versioning with vector clocks, sloppy quorums with hinted handoff, and Merkle-tree-based anti-entropy so that all updates reach all replicas eventually.",
        "Halbert's state vault is not a replicated store: the ledger in halbert_core/halbert_core/continuity/state_store.py is single-host SQLite, and the vault in halbert_core/halbert_core/continuity/vault.py is a deterministic projection of it that carries no authority. The eventually-consistent replicated-storage literature shaped the multi-node design research instead — .handoff/research/multi-node-systems/02-SHARED-REDUNDANT-DATABASES-AND-STATE.md surveys replication engines, rejects quorum consensus for the two-node home topology, and earmarks the ledger for grow-only-set union — while its one shipped descendant, halbert_core/halbert_core/agents/resilient_peer_store.py, stages satellite writes for convergence on reconnect; full ledger replication is explicitly deferred (DECISIONS.md, REPL-CACHE).",
    ),
    C(
        "concurrency-recovery", "rise",
        "Concurrency Control and Recovery in Database Systems",
        "P. A. Bernstein, V. Hadzilacos & N. Goodman",
        "Addison-Wesley Publishing Company (Addison-Wesley Series in Computer Science), Reading, Massachusetts; out of print, freely hosted by Microsoft Research",
        1987,
        "https://www.microsoft.com/en-us/research/people/philbe/book/",
        "ISBN 0-201-10715-5",
        "survey", False, "systems", "shipped",
        "The book establishes the transaction as the atomic unit of reliable program execution, and presents the concurrency-control techniques (serializability theory, two-phase locking, timestamp and multiversion methods) and recovery techniques — emphasizing undo-redo (write-ahead) logging, whose rules ensure that partially completed transactions leave no effect on the database while the results of committed transactions are never lost.",
        "Halbert's state ledger runs SQLite with write-ahead logging enabled at every open (halbert_core/halbert_core/continuity/state_store.py), and the log is load-bearing rather than incidental: after a reason-redaction the store folds the WAL back in or raises rather than let forgotten text survive readable in it. Superseding one fact with another — closing the previous triple and inserting its replacement — is a single BEGIN IMMEDIATE transaction, with a partial unique index and one retry keeping exactly one open row per key under concurrent writers. Rollback of a config change is snapshot-restore rather than log replay (halbert_core/halbert_core/tools/write_config.py restores the .bak and records the restore through the ledger), so the ledger's history is superseded rather than undone.",
    ),
    C(
        "linearizability", "rise",
        "Linearizability: A Correctness Condition for Concurrent Objects",
        "M. P. Herlihy & J. M. Wing",
        "ACM Transactions on Programming Languages and Systems (TOPLAS), 12(3), pp. 463–492",
        1990,
        "https://dl.acm.org/doi/10.1145/78969.78972",
        "DOI:10.1145/78969.78972",
        "paper", True, "distributed", "design",
        "Linearizability is a correctness condition for concurrent objects under which each operation applied by concurrent processes appears to take effect instantaneously at some point between its invocation and its response, permitting a high degree of concurrency while letting programmers specify and reason about concurrent objects using known sequential-domain techniques.",
        "Linearizability was weighed and designed around rather than implemented: the multi-node research corpus (.handoff/research/multi-node-systems/02 and 05) works through the consistency-model spectrum and rejects quorum-based strict serializability because a two-node home cluster loses quorum the moment the workstation sleeps. The shipped architecture keeps a single canonical host as the authority for shared state — halbert_core/halbert_core/agents/peer_conversation_store.py is a thin proxy to it — so no cross-node consistency model is ever required, and the satellite's local mirror (halbert_core/halbert_core/agents/resilient_peer_store.py) converges eventually under explicit FIFO and idempotency rules, with full replication deferred (DECISIONS.md, REPL-CACHE).",
    ),
    C(
        "lost-in-the-middle", "hop",
        "Lost in the Middle: How Language Models Use Long Contexts",
        "N. F. Liu, K. Lin, J. Hewitt, A. Paranjape, M. Bevilacqua, F. Petroni & P. Liang",
        "Transactions of the Association for Computational Linguistics (TACL), Vol. 12, pp. 157–173",
        2024,
        "https://aclanthology.org/2024.tacl-1.9/",
        "DOI:10.1162/tacl_a_00638",
        "paper", True, "retrieval", "shipped",
        "Evaluating language models on multi-document question answering and key-value retrieval, the authors find performance is highest when relevant information occurs at the very beginning or end of the input context and degrades significantly when models must use relevant information in the middle of long contexts — even for models explicitly designed for long contexts.",
        "Halbert's context assembler orders assembled material positionally rather than concatenating it in arrival order: top retrieval results and memory facts occupy the start of the prompt, lower-priority discovery material the middle, and the recent conversation and observations the end, mirroring the edge-attention structure the paper measures (halbert_core/halbert_core/context/assembler.py). Retrieval is further held to a tier-derived token budget so the grounded context stays small rather than stuffed.",
    ),
    C(
        "context-length-hurts", "hop",
        "Context Length Alone Hurts LLM Performance Despite Perfect Retrieval",
        "Y. Du et al. (10 authors)",
        "Findings of EMNLP 2025",
        2025,
        "https://arxiv.org/abs/2510.05381",
        "arXiv:2510.05381",
        "paper", True, "retrieval", "shipped",
        "Across five open- and closed-source LLMs on math, QA, and coding tasks, performance drops 13.9%–85% as input length grows even when all relevant evidence is perfectly retrieved and irrelevant tokens are masked as whitespace, showing that the sheer length of the input itself degrades LLM performance.",
        "Halbert deliberately caps retrieved volume instead of maximizing context: default retrieval returns a handful of top-ranked chunks, the retrieval backend enforces a per-source chunk cap and a character budget, and the assembler truncates to a tier-derived token budget with a compression cascade above a threshold (halbert_core/halbert_core/rag/retriever.py, halbert_core/halbert_core/context/assembler.py). The design reasoning that additional retrieved documents add noise rather than signal is recorded in the RAG optimization plan that set these defaults.",
    ),
    C(
        "context-rot", "hop",
        "Context Rot: How Increasing Input Tokens Impacts LLM Performance",
        "K. Hong, A. Troynikov & J. Huber, Chroma",
        "Chroma technical report (trychroma.com)",
        2025,
        "https://www.trychroma.com/research/context-rot",
        "",
        "engineering-report", False, "retrieval", "design",
        "Evaluating 18 frontier LLMs on simple controlled tasks (repeated-word counting, needle-in-a-haystack variants, LongMemEval), Chroma found that models do not use their context uniformly — performance grows increasingly unreliable as input length grows, degrading non-uniformly well before advertised context limits.",
        "Chroma's context-rot measurement anchors the memory-boundary design argument that superseded values should stay out of context entirely rather than be shown alongside current ones; the reasoning is recorded in the memory-boundary design document's counter-case section. The specific current-only filter it argues for has not landed in Halbert code — the shipped analogues are the token-budgeted, per-source-capped context assembly that keeps distractor material out of prompts (halbert_core/halbert_core/context/assembler.py).",
        identifierNote="Engineering report self-published on the vendor's research site; carries no arXiv/DOI identifier.",
    ),
    C(
        "contextual-retrieval", "hop",
        "Introducing Contextual Retrieval",
        "D. Ford, Anthropic",
        "Anthropic engineering post (anthropic.com)",
        2024,
        "https://www.anthropic.com/news/contextual-retrieval",
        "",
        "engineering-report", False, "retrieval", "design",
        "Prepending chunk-specific explanatory context (generated by a prompt-guided model) to each RAG chunk before embedding (Contextual Embeddings) and before BM25 indexing (Contextual BM25) reduces the top-20 failed-retrieval rate by 49% (5.7% to 2.9%), rising to 67% (5.7% to 1.9%) when a reranker is added.",
        "Halbert does not generate per-chunk context with a model; its corpus pipeline instead carries structural context into every chunk, repeating each large document's heading and metadata across its chunks and indexing title and source alongside every chunk. The underlying premise — that a bare chunk loses the document context it came from — shaped the corpus format through the heading-based chunking design recorded in the RAG optimization plan, while the specific enrichment technique remains unimplemented.",
        identifierNote="Engineering blog post; carries no arXiv/DOI identifier.",
    ),
    C(
        "rag-vs-graphrag", "hop",
        "RAG vs. GraphRAG: A Systematic Evaluation and Key Insights",
        "H. Han et al. (11 authors)",
        "arXiv preprint (cs.IR)",
        2025,
        "https://arxiv.org/abs/2502.11371",
        "arXiv:2502.11371",
        "paper", False, "retrieval", "shipped",
        "A systematic evaluation across four benchmark datasets finds RAG and GraphRAG have distinct, task-dependent strengths (RAG cheaper for semantic-similarity retrieval, GraphRAG stronger for global comprehension of large corpora), with combining or selecting between the two paradigms yielding consistent performance improvements over either alone.",
        "Halbert implemented both sides of the trade-off: flat hybrid retrieval for corpus search, and a graph-enhanced path that extracts commands, services, config files and their relationships into an entity graph and injects relationship context alongside vector results (halbert_core/halbert_core/rag/graphrag.py). In practice the graph path is an auxiliary index rather than the default — the live agent conversation retrieves through the SourcePrep backend — so graph context supplements vector retrieval where multi-hop relationships matter instead of replacing it.",
        peerNote="arXiv preprint; the canonical page listed no journal/conference venue as of v3 (Mar 2026).",
    ),
    C(
        "bm25-beyond", "hop",
        "The Probabilistic Relevance Framework: BM25 and Beyond",
        "S. Robertson & H. Zaragoza",
        "Foundations and Trends in Information Retrieval, Vol. 4, No. 1-2, pp. 1-174 (now Publishers; now hosted by Emerald)",
        2009,
        "https://doi.org/10.1561/1500000019",
        "DOI 10.1561/1500000019",
        "survey", False, "retrieval", "shipped",
        "Presents the probabilistic relevance framework from a conceptual point of view, tracing how 1970s–80s probabilistic retrieval work led to BM25 — one of the most successful text-retrieval algorithms, whose term-frequency saturation and document-length normalization derive from the 2-Poisson model — and extends it to BM25F for structured web/corporate documents.",
        "Halbert builds a BM25 sparse index over the tokenized documentation corpus as the exact-match half of its hybrid retrieval, with tokenization tuned for command-line vocabulary — hyphenated terms preserved, stopwords stripped, common suffixes stemmed (halbert_core/halbert_core/rag/retriever.py). Sparse scoring is the half that finds specific flag names and error codes that dense similarity misses, and it is fused with the dense half at query time.",
    ),
    C(
        "reciprocal-rank-fusion", "hop",
        "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods in High-dimensional Data",
        "G. V. Cormack, C. L. A. Clarke & S. Büttcher",
        "Proceedings of the 32nd International ACM SIGIR Conference on Research and Development in Information Retrieval, pp. 758–759",
        2009,
        "https://dl.acm.org/doi/10.1145/1571941.1572114",
        "DOI:10.1145/1571941.1572114",
        "paper", True, "retrieval", "shipped",
        "Combining result lists by scoring each document with the sum of 1/(k + rank) across all retrievers — reciprocal rank fusion — empirically outperforms Condorcet fusion and individual rank-learning methods on high-dimensional retrieval tasks, at trivial cost.",
        "Halbert fuses its sparse and dense result lists with weighted reciprocal rank fusion at the standard k=60 constant, summing each retriever's reciprocal-rank contribution per document before cutting to the requested top-k (halbert_core/halbert_core/rag/retriever.py). Fused candidates can then be reranked by a cross-encoder for final precision before entering the assembled context.",
    ),
    C(
        "splitwise", "cap",
        "Splitwise: Efficient generative LLM inference using phase splitting",
        "P. Patel, E. Choukse, C. Zhang, A. Shah, Í. Goiri, S. Maleki & R. Bianchini",
        "ISCA 2024 (ACM/IEEE 51st Annual International Symposium on Computer Architecture)",
        2024,
        "https://arxiv.org/abs/2311.18677",
        "DOI:10.1109/isca59077.2024.00019",
        "paper", True, "compute", "design",
        "Characterizing LLM inference as two phases with distinct resource profiles — compute-intensive prompt (prefill) computation and memory-intensive token (decode) generation — Splitwise shows that running the phases on separate, hardware-matched machines achieves 1.4x higher throughput at 20% lower cost, or 2.35x throughput at equal cost and power, versus baseline designs.",
        "Splitwise and DistServe informed Halbert's multi-node compute dispatch as surveyed research rather than as adopted mechanism: the multi-node research package (.handoff/research/multi-node-systems/03-SHARED-COMPUTE-AND-INFERENCE-DISPATCH.md) evaluates their disaggregated prefill/decode pattern against home-LAN bandwidth physics and rejects phase splitting in favour of request-level offloading, where an entire turn is routed to the node that holds the model in local RAM. That conclusion is implemented in halbert_core/halbert_core/federation/compute_router.py and halbert_core/halbert_core/federation/compute_endpoint.py, which dispatch whole prompts over HTTP with deadline-aware priorities — no prefill/decode phase separation exists in the codebase.",
    ),
    C(
        "distserve", "cap",
        "DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving",
        "Y. Zhong et al.",
        "USENIX Symposium on Operating Systems Design and Implementation (OSDI 2024)",
        2024,
        "https://arxiv.org/abs/2401.09670",
        "arXiv:2401.09670",
        "paper", True, "compute", "design",
        "Disaggregating LLM prefill and decoding onto separate GPUs with independently co-optimized resource allocation and parallelism plans eliminates prefill-decoding interference, letting DistServe serve up to 7.4x more requests or meet 12.6x tighter SLOs than state-of-the-art colocated serving systems.",
        "DistServe's goodput-oriented separation of latency classes shaped Halbert's deadline-aware dispatch design: the multi-node research survey (.handoff/research/multi-node-systems/03-SHARED-COMPUTE-AND-INFERENCE-DISPATCH.md) took its priority-queue insight and scoped it to a home cluster as a four-tier turn classification with a strict interactive deadline. Halbert implements that priority scaffolding in halbert_core/halbert_core/federation/compute_broker.py and halbert_core/halbert_core/federation/compute_router.py, though the broker's queue loop is still an explicit TODO and turns are served directly today; DistServe's prefill/decode disaggregation itself was evaluated and not adopted, as home-LAN bandwidth cannot carry KV-cache transfers.",
    ),
    C(
        "petals-collaborative-inference", "cap",
        "Petals: Collaborative Inference and Fine-tuning of Large Models",
        "A. Borzunov et al.",
        "Proceedings of the 61st Annual Meeting of the Association for Computational Linguistics (Volume 3: System Demonstrations), ACL 2023, Toronto, Canada, pp. 558-568",
        2023,
        "https://aclanthology.org/2023.acl-demo.54/",
        "DOI 10.18653/v1/2023.acl-demo.54 (arXiv:2209.01188)",
        "paper", True, "compute", "design",
        "Petals lets multiple parties pool consumer-grade GPUs to serve a 100B+ parameter model collaboratively layer-by-layer over a network — running inference of a very large open model at roughly  venue1 step per second on consumer hardware, outperforming RAM offloading for interactive use — while natively exposing hidden states so users can train and share custom fine-tuned extensions.",
        "Petals was surveyed as the layer-distributed extreme of collaborative inference, and Halbert adopted the failure-tolerance lesson rather than the layer-splitting mechanism: the multi-node research (.handoff/research/multi-node-systems/03-SHARED-COMPUTE-AND-INFERENCE-DISPATCH.md) concluded that splitting model layers across consumer hardware is dominated on a home LAN by keeping each model whole on one node. What carried over is dynamic rerouting around failed nodes, implemented as the peer-health hysteresis and multi-tier fallback chain in halbert_core/halbert_core/federation/compute_router.py, so a satellite re-routes around a sleeping or flapping workstation instead of stalling mid-generation.",
    ),
    C(
        "ray-osdi-2018", "cap",
        "Ray: A Distributed Framework for Emerging AI Applications",
        "P. Moritz, R. Nishihara, S. Wang, A. Tumanov, R. Liaw, E. Liang, M. Elibol, Z. Yang, W. Paul, M. I. Jordan & I. Stoica",
        "OSDI 2018 (13th USENIX Symposium on Operating Systems Design and Implementation)",
        2018,
        "https://arxiv.org/abs/1712.05889",
        "arXiv:1712.05889",
        "paper", True, "compute", "design",
        "Ray provides a unified interface that expresses both task-parallel and actor-based computations and a dynamic execution engine that scales beyond 1.8 million tasks per second, meeting the performance and flexibility demands of emerging AI workloads.",
        "Ray stands in the dossier's bibliography as the canonical distributed-AI compute framework against which Halbert's multi-node design was scoped: the research survey cites it as the task-parallel reference point, then the scoping doc rejects framework-class infrastructure in favour of stdlib-only federation primitives, per the two-hard-dependency subtractive contract. Halbert's shipped equivalent of distributed task execution is deliberately thinner — request-level HTTP offload and MCP tool proxying across paired nodes (halbert_core/halbert_core/federation/), not a cluster runtime.",
    ),
    C(
        "gplv3-section-7", "reveal",
        "GNU General Public License Version 3",
        "Free Software Foundation, Inc.",
        "gnu.org/licenses (Free Software Foundation — canonical licence text)",
        2007,
        "https://www.gnu.org/licenses/gpl-3.0.en.html",
        "GPL-3.0-or-later (SPDX)",
        "licence", False, "licensing", "shipped",
        "A free copyleft licence, copyright 2007 Free Software Foundation, Inc., whose Section 7 defines “additional permissions” as terms that supplement the licence by making exceptions from one or more of its conditions, grantable by anyone who has or can give appropriate copyright permission for material added to a covered work.",
        "Halbert's core ships under the GNU GPL v3 with a single operative Section 7 additional permission, held verbatim at LICENSE-EXCEPTION-APPSTORE and scoped to conveyance through the Apple App Store (macOS, iOS, iPadOS, and visionOS), with a third-party carve-out and a downstream fork-freedom clause (FDR-02/FDR-02b in DECISIONS.md). The remaining distribution-side obligations — copying both licence texts into a built application bundle and completing the wider header rewrite — are recorded as open work in the roadmap (DIST-1) rather than done.",
    ),
    C(
        "ed25519", "reveal",
        "High-speed high-security signatures",
        "D. J. Bernstein, N. Duif, T. Lange, P. Schwabe & B.-Y. Yang",
        "Journal of Cryptographic Engineering, vol. 2, no. 2, pp. 77–89",
        2012,
        "https://doi.org/10.1007/s13389-012-0027-1",
        "DOI:10.1007/s13389-012-0027-1",
        "paper", True, "security", "design",
        "Introduces the Ed25519 signature scheme, showing that a mass-market quad-core 2.4GHz Intel Westmere CPU can create over 100,000 signatures per second and verify tens of thousands per second at a 2^128 security level, with 32-byte public keys and 64-byte signatures, and defenses against software side-channel attacks (no data flow from secret keys to array indices or branch conditions).",
        "Ed25519 is Halbert's ratified mechanism for offline licence verification: DECISIONS.md FDR-04 specifies licence keys as offline certificates signed by the maintainer's master key and verified with zero phone-home, with the design elaborated in the 2026-09-14 monetization plan review and the Pro commercial terms. No licence-signing or verification code exists in halbert_core today — that build (Phase B: keys, verification, the signed update stream, the store integration) was gated on the ratification and has not been written. The signature scheme itself already ships in a different role, where halbert_core/halbert_core/federation/tls.py issues long-lived Ed25519 self-signed certificates as inter-node transport identities, deliberately kept separate from the key that signs the audit chain.",
    ),
    C(
        "saltzer-schroeder", "reveal",
        "The Protection of Information in Computer Systems",
        "J. H. Saltzer & M. D. Schroeder",
        "Proceedings of the IEEE, vol. 63, no. 9, pp. 1278–1308",
        1975,
        "https://doi.org/10.1109/PROC.1975.9939",
        "DOI:10.1109/PROC.1975.9939",
        "paper", True, "security", "shipped",
        "A tutorial paper exploring the mechanics of protecting computer-stored information from unauthorized use or modification, concentrating on the architectural structures — hardware or software — necessary to support information protection, and setting out desired functions and design principles for elementary protection and authentication mechanisms.",
        "Halbert's protection posture instantiates the classic principles without citing them by name: complete mediation at a single redaction seam that withholds output when its check cannot run (halbert_core/halbert_core/security/display_transport.py), fail-safe defaults in a secure-turn gate that refuses rather than silently downgrading to a remote endpoint (halbert_core/halbert_core/dashboard/routes/agent.py), least-privilege command confinement with only designated paths writable (halbert_core/halbert_core/streaming/sandbox.py), and separation of transport identity from audit identity (halbert_core/halbert_core/federation/tls.py). The 2026-09-07 security-remediation research applied the same discipline as method — choke-point mapping, sandbox fail-direction analysis, TOCTOU-safe path resolution — and landed its two cheap findings. That pass also measured the posture's gaps honestly: its larger hardening proposals remain unlanded, including flipping the sandbox's fail-open fallback when no platform sandbox binary is available.",
    ),
]


def main() -> None:
    assert len(CITATIONS) == 30, f"expected 30 citations, got {len(CITATIONS)}"

    seen_ids: set[str] = set()
    stop_ids = {"intro", "open", "apex", "diagonal", "rise", "hop", "cap", "reveal"}
    for c in CITATIONS:
        assert isinstance(c, dict), c
        for field in REQUIRED:
            assert field in c, f"{c.get('id')}: missing {field}"
        assert c["id"] not in seen_ids, f"duplicate id {c['id']}"
        seen_ids.add(c["id"])
        assert c["stopId"] in stop_ids, f"{c['id']}: bad stopId {c['stopId']}"
        assert isinstance(c["year"], int), f"{c['id']}: year not int"
        assert c["url"].startswith("https://"), f"{c['id']}: non-https url {c['url']}"
        assert c["type"] in {"paper", "rfc", "spec", "benchmark", "survey", "engineering-report", "licence"}, c["id"]
        assert c["category"] in {"retrieval", "compute", "security", "distributed", "systems", "licensing"}, c["id"]
        assert c["applied"] in {"shipped", "design", "deferred"}, c["id"]
        if c["applied"] == "shipped" and c["type"] != "licence":
            assert SHIPPED_PATH_RE.search(c["howHalbertApplies"]), f"{c['id']}: shipped prose names no halbert_core/ file"
        if c["peerReviewed"] and c["type"] not in {"paper", "survey", "benchmark"}:
            raise AssertionError(f"{c['id']}: peerReviewed=true on non-reviewable type {c['type']}")
        for m in SHIPPED_PATH_RE.finditer(c["howHalbertApplies"]):
            path = m.group(0).rstrip(".,;:)—")
            if not (REPO_ROOT / path).exists():
                raise AssertionError(f"{c['id']}: shipped prose cites nonexistent path {path}")

    per_stop = {}
    for c in CITATIONS:
        per_stop[c["stopId"]] = per_stop.get(c["stopId"], 0) + 1
    print(f"assembling {len(CITATIONS)} citations")
    for sid in ["intro", "open", "apex", "diagonal", "rise", "hop", "cap", "reveal"]:
        print(f"  {sid:10s} {per_stop.get(sid, 0)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"$schema-note": SCHEMA_NOTE, "citations": CITATIONS}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()