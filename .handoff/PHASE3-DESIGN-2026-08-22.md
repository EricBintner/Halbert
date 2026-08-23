# Phase 3 Design — Config Dependency Edges & Blast-Radius

**Created:** 2026-08-22
**Status:** Design document (awaiting review before implementation)
**Scope:** Config-physiology brain — "what breaks if I edit /etc/fstab?"

---

## 1. Problem Statement

Halbert needs to answer "what depends on this config file?" — the blast-radius
question. If an admin edits `/etc/fstab`, Halbert should know which systemd
mount units, services, and other configs are affected.

SourcePrep has a trace graph with `get_impact_graph()` (BFS reverse traversal
over in-edges), but it only extracts edges for code languages (Python, TS, Go,
Rust, etc.). Config files (`.conf`, `.service`, `.timer`, `fstab`, YAML) get
file-level nodes but **zero edges** — the analyzer returns `None` for unknown
languages.

**The gap:** No mechanism to populate config dependency edges into SourcePrep's
trace graph so that `get_impact_graph()` works over config files.

---

## 2. Research Findings

### 2.1 SourcePrep Edge Ingestion — Three Existing Patterns

SourcePrep already has three edge sources, all loaded by `TraceIndex._load_python()`:

| Source | File | How edges get there |
|--------|------|-------------------|
| **Static** (tree-sitter) | `trace_edges.jsonl` | `TraceBuilder.build()` — Rust or Python analyzers |
| **Inferred** (LLM) | `trace_inferred_edges.jsonl` | `InferredEdgesAnalyzer.run()` — LLM-powered Stage 1.5 |
| **LSP** (IDE) | `trace_lsp_edges.jsonl` | `POST /projects/{id}/trace/lsp-edges` — external push |

All three use the same edge schema:
```json
{"id": "...", "kind": "...", "source": "file:path", "target": "file:path", "metadata": {...}}
```

`TraceIndex._load_python()` at `@/src/prep/core/trace/index.py:111-141` loads
all three JSONL files into `_edges`, `_edges_by_source`, `_edges_by_target`.
The `get_impact_graph()` BFS at `:405-493` traverses in-edges regardless of
origin. **Any new edge source that writes a JSONL file in the same format and
gets loaded by `_load_python()` will automatically work with blast-radius
queries.**

### 2.2 LSP Edge Ingestion Endpoint (the template)

`POST /projects/{id}/trace/lsp-edges` at `@/src/prep/api/routers/trace_routes/query.py:523`:

1. Validates source/target are known nodes in the trace graph
2. Deduplicates against existing edges
3. Appends to `trace_lsp_edges.jsonl`
4. Returns accepted/rejected counts

Request schema (`@/src/prep/api/routers/trace_routes/shared.py:166`):
```python
class LSPEdge(BaseModel):
    source: str       # node ID like "file:/etc/systemd/system/nginx.service"
    target: str       # node ID like "file:/etc/default/nginx"
    kind: str = "calls"
    metadata: Optional[Dict[str, Any]] = None
```

### 2.3 Rust Engine Behavior for Config Files

`@/engine/crates/prep-graph/src/lib.rs:1018-1070`:
- Creates a `file` node for EVERY walked file (including configs)
- Only calls `prep_parser::parse_file()` for files with a detected language
- Config files (`language=None`) get a file node but no symbol nodes or edges
- **This means config files ARE in the trace graph as nodes** — they just have
  no edges. External edge ingestion can connect them.

### 2.4 Halbert Config Parser Output

`@/halbert_core/halbert_core/config/parser.py` produces structured output:

**INI/systemd** (`.conf`, `.ini`, `.service`, `.timer`):
```python
{
    "path": "/etc/systemd/system/nginx.service",
    "hash": "...",
    "kind": "ini",
    "sections": {
        "Unit": {"Description": "...", "Requires": "network.target"},
        "Service": {"ExecStart": "/usr/sbin/nginx -g 'daemon off;'", "EnvironmentFile": "/etc/default/nginx"},
    },
    "lines": [{"n": 1, "text": "..."}, ...]
}
```

**YAML/JSON**: `{"path": "...", "kind": "yaml"|"json", "tree": {...}, "lines": [...]}`
**Text**: `{"path": "...", "kind": "text", "lines": [...]}`

The structured `sections` output for INI/systemd files contains all the key-value
pairs needed to extract dependency edges deterministically.

### 2.5 Config Manifest

`@/config/config-registry.yml`:
```yaml
include:
  - /etc/**/*.conf
  - /etc/systemd/*.service
  - /etc/default/*
exclude:
  - /etc/ssl/**
  - /etc/shadow
```

---

## 3. Config Edge Types — Taxonomy

Six deterministic edge types extractable from parsed configs:

### 3.1 systemd unit dependencies (highest value)

| Directive | Section | Edge kind | Example |
|-----------|---------|-----------|---------|
| `Requires=` | Unit | `requires` | nginx.service → network.target |
| `Wants=` | Unit | `wants` | nginx.service → network.target |
| `After=` | Unit | `after` | nginx.service → network.target |
| `Before=` | Unit | `before` | nginx.service → foo.service |
| `ExecStart=` | Service | `executes` | nginx.service → /usr/sbin/nginx |
| `ExecStartPre=` | Service | `executes` | nginx.service → /usr/bin/mkdir |
| `ExecStop=` | Service | `executes` | nginx.service → /usr/sbin/nginx -s stop |
| `EnvironmentFile=` | Service | `configures` | nginx.service → /etc/default/nginx |
| `PIDFile=` | Service | `references` | nginx.service → /run/nginx.pid |
| `WorkingDirectory=` | Service | `references` | nginx.service → /var/www |
| `BindPaths=` | Service | `references` | nginx.service → /data |
| `RequiresMountsFor=` | Unit | `requires_mount` | nginx.service → /mnt/data |

**Extraction:** Parse `sections["Unit"]` and `sections["Service"]` for these keys.
Values may be space-separated lists. Map unit names to file paths:
`network.target` → `/etc/systemd/system/network.target` or
`/lib/systemd/system/network.target` (search both).

### 3.2 Include directives (high value)

| Config type | Directive pattern | Edge kind |
|-------------|-------------------|-----------|
| nginx | `include /path;` | `includes` |
| apache | `Include /path` | `includes` |
| sysctl | `/etc/sysctl.d/*.conf` (drop-in) | `includes` |
| generic | `include /path` or `.include /path` | `includes` |
| sudoers | `@include /path` | `includes` |

**Extraction:** Regex scan of raw text lines for include directives. Resolve
glob patterns against the filesystem to produce concrete file-to-file edges.

### 3.3 fstab → mount unit correspondence (medium value)

fstab entries correspond 1:1 with systemd `.mount` units:
```
/dev/sda1  /mnt/data  ext4  defaults  0  2
```
→ edge: `/etc/fstab` → `mnt-data.mount` (systemd encodes mount path as unit name)

**Extraction:** Parse fstab lines (skip comments), extract mount point,
generate systemd mount unit name (`/mnt/data` → `mnt-data.mount`).

### 3.4 File-reference co-occurrence (medium value)

Any config file that references another file by path:
- `ssl_certificate /etc/letsencrypt/live/example.com/fullchain.pem;`
- `password_file /etc/dovecot/users`
- `include /etc/foo.conf`

**Extraction:** Regex scan for absolute path references (`/[a-zA-Z0-9_/.-]+`)
in config file content. Filter against known config files to avoid noise.
Edge kind: `references`.

### 3.5 Drop-in directory semantics (lower value, complex)

`/etc/foo.conf` + `/etc/foo.conf.d/*.conf` — the main config includes the
drop-in directory. This is a special case of include directives but with
override-order semantics.

**Extraction:** For each config file, check if a `.d` directory exists with
the same base name. If so, create `includes` edges to each file in the
drop-in directory.

### 3.6 Config → service mapping (lower value, heuristic)

A config file at `/etc/nginx/nginx.conf` configures the `nginx` service.
This is a heuristic mapping based on path naming conventions.

**Extraction:** Match config file paths to systemd unit names by prefix.
Edge kind: `configures`. Low confidence, may produce false positives.

---

## 4. Architecture — Hybrid Approach

### 4.1 Design Principles

1. **Domain knowledge lives in Halbert** — Halbert knows what config formats
   look like, which directives create dependencies, and how to resolve unit
   names to file paths. SourcePrep should not need to understand systemd.

2. **Graph storage and traversal lives in SourcePrep** — SourcePrep already
   has the trace graph, BFS traversal, and the HTTP API. No reason to
   duplicate this in Halbert.

3. **Minimal SourcePrep changes** — Generalize the existing LSP edge
   ingestion pattern. One new endpoint, one new JSONL file, ~50 lines.

4. **Path to graduation** — The Halbert extractor can later be contributed
   as a native `ConfigAnalyzer` in SourcePrep's Rust engine. The external
   edges endpoint remains for other external edge sources.

### 4.2 SourcePrep Side — Generalized External Edges

**New endpoint:** `POST /projects/{id}/trace/external-edges`

Generalizes the LSP edge pattern to accept any external edge source:

```python
class ExternalEdge(BaseModel):
    source: str           # node ID: "file:/etc/systemd/system/nginx.service"
    target: str           # node ID: "file:/etc/default/nginx"
    kind: str             # "requires", "includes", "configures", etc.
    origin: str = "external"  # "config", "lsp", "custom", etc.
    metadata: Optional[Dict[str, Any]] = None

class ExternalEdgesRequest(BaseModel):
    edges: List[ExternalEdge]
    replace_origin: Optional[str] = None  # If set, clear existing edges with this origin before appending
```

**Storage:** `trace_external_edges.jsonl` in the project's index directory.

**Loading:** Add to `TraceIndex._load_python()` after LSP edges:
```python
# Load external edges (posted by external tools like Halbert's config extractor)
self.external_edges_path = self.index_dir / "trace_external_edges.jsonl"
if self.external_edges_path.exists():
    # same pattern as LSP/inferred edges
```

**Dedup:** Same (source, target, kind) dedup as LSP edges.

**Replace semantics:** `replace_origin` parameter allows Halbert to push a
fresh set of config edges (e.g., after a config change) without accumulating
stale edges. The endpoint clears all edges with matching origin from the
JSONL file before appending new ones.

**Validation:** Same as LSP — source/target must be known file nodes. This
ensures edges only connect files that exist in the project.

**Total SourcePrep changes:** ~60 lines (1 endpoint, 1 model, 1 JSONL load
block in `TraceIndex`).

### 4.3 Halbert Side — ConfigEdgeExtractor

New module: `halbert_core/halbert_core/config/edge_extractor.py`

```
ConfigEdgeExtractor
├── extract_all() → List[ConfigEdge]
│   ├── extract_systemd_edges(parsed) → List[ConfigEdge]
│   ├── extract_include_edges(parsed) → List[ConfigEdge]
│   ├── extract_fstab_edges(parsed) → List[ConfigEdge]
│   ├── extract_reference_edges(parsed) → List[ConfigEdge]
│   ├── extract_dropin_edges(parsed) → List[ConfigEdge]
│   └── extract_service_mapping_edges(parsed) → List[ConfigEdge]
├── push_to_sourceprep(edges) → dict  # POST to SourcePrep API
└── sync() → dict  # extract_all + push_to_sourceprep (called on config change)
```

**Input:** Reads from Halbert's existing config snapshot system
(`config/snapshot.py` output — canonical JSON files in `data/config/canon/`).

**Output:** Edges in SourcePrep node ID format:
```python
{
    "source": "file:/etc/systemd/system/nginx.service",
    "target": "file:/etc/default/nginx",
    "kind": "configures",
    "origin": "config",
    "metadata": {
        "directive": "EnvironmentFile",
        "line": 12,
        "section": "Service",
        "extractor": "systemd",
    }
}
```

**Wiring:** Called by `ConfigWatcher` on snapshot changes. Also callable
manually (CLI/dashboard) for initial population.

**SourcePrepClient extension:** Add `push_external_edges()` method to the
existing `SourcePrepClient` class.

### 4.4 End-to-End Flow

```
1. Halbert registers OS config tree as SourcePrep project (Phase 2, done)
2. SourcePrep builds trace graph → file nodes for all configs, no edges
3. Halbert ConfigEdgeExtractor.extract_all()
   ├── Reads canonical JSON from data/config/canon/
   ├── Parses systemd directives, include patterns, fstab, references
   └── Produces List[ConfigEdge]
4. Halbert pushes edges: POST /projects/{id}/trace/external-edges
   ├── SourcePrep validates source/target are known file nodes
   ├── SourcePrep deduplicates against existing edges
   └── SourcePrep appends to trace_external_edges.jsonl
5. SourcePrep TraceIndex.load() picks up external edges
6. User asks: "what breaks if I edit /etc/fstab?"
7. Halbert calls: GET /projects/{id}/trace/impact/file:/etc/fstab
8. SourcePrep BFS traversal follows in-edges → returns dependents
9. Halbert renders blast-radius in response
```

### 4.5 Future Graduation — SourcePrep ConfigAnalyzer

Once the edge extraction rules are proven in Halbert, they can be ported to
SourcePrep as a native analyzer:

1. Add `ConfigAnalyzer` to `engine/crates/prep-parser/src/config.rs`
2. Register config extensions in `prep-walker` language detection
3. `prep_parser::parse_file()` dispatches to `ConfigAnalyzer` for `.conf`,
   `.service`, `.timer`, `fstab`, etc.
4. Edges extracted during `build_trace()` — no external push needed
5. Halbert's `ConfigEdgeExtractor` retired for configs (kept for custom edges)

The external edges endpoint remains valuable for:
- Rapid prototyping of new edge types
- Domain-specific edges that don't belong in SourcePrep core
- Edges from external tools (monitoring, CMDB, etc.)

---

## 5. Implementation Plan

### Phase 3a: SourcePrep external edges endpoint (small)

| Task | File | Effort |
|------|------|--------|
| Add `ExternalEdge` + `ExternalEdgesRequest` models | `trace_routes/shared.py` | 10 lines |
| Add `POST /projects/{id}/trace/external-edges` endpoint | `trace_routes/query.py` | 40 lines |
| Load `trace_external_edges.jsonl` in `TraceIndex._load_python()` | `trace/index.py` | 15 lines |
| Add `external_edges_path` to `TraceIndex.__init__` | `trace/index.py` | 1 line |

### Phase 3b: Halbert ConfigEdgeExtractor (main work)

| Task | File | Effort |
|------|------|--------|
| `ConfigEdge` dataclass + `ConfigEdgeExtractor` class | `config/edge_extractor.py` (new) | ~300 lines |
| systemd directive extraction | `config/edge_extractor.py` | ~80 lines |
| include directive extraction (nginx, apache, generic) | `config/edge_extractor.py` | ~60 lines |
| fstab → mount unit extraction | `config/edge_extractor.py` | ~40 lines |
| file-reference extraction | `config/edge_extractor.py` | ~50 lines |
| drop-in directory extraction | `config/edge_extractor.py` | ~30 lines |
| service mapping extraction | `config/edge_extractor.py` | ~30 lines |
| `push_external_edges()` in `SourcePrepClient` | `integrations/sourceprep_client.py` | ~20 lines |
| Wire into `ConfigWatcher` callback | `config/watcher.py` | ~10 lines |
| CLI command for manual sync | `main.py` or dashboard route | ~20 lines |

### Phase 3c: Blast-radius query in Halbert (small)

| Task | File | Effort |
|------|------|--------|
| `get_impact(file_path)` in `SourcePrepClient` | `integrations/sourceprep_client.py` | ~15 lines |
| Wire into agent tool executor | `tools/` | ~30 lines |
| Add "blast-radius" tool to agent prompt | `prompts/` | ~10 lines |

### Phase 3d: Tests

| Task | File | Effort |
|------|------|--------|
| Unit tests for each edge extractor | `tests/test_config_edges.py` | ~200 lines |
| Integration test: extract → push → impact query | `tests/test_phase3_integration.py` | ~100 lines |

---

## 6. Edge Kind Vocabulary

New edge kinds for config dependencies (added to SourcePrep's vocabulary):

| Kind | Direction | Meaning | Example |
|------|-----------|---------|---------|
| `requires` | unit → unit | Hard dependency | nginx.service → network.target |
| `wants` | unit → unit | Soft dependency | nginx.service → network.target |
| `after` | unit → unit | Ordering constraint | nginx.service → network.target |
| `before` | unit → unit | Ordering constraint | foo.service → nginx.service |
| `executes` | unit → binary | ExecStart/ExecStop | nginx.service → /usr/sbin/nginx |
| `configures` | unit → config | EnvironmentFile | nginx.service → /etc/default/nginx |
| `includes` | config → config | Include directive | nginx.conf → conf.d/*.conf |
| `references` | config → file | Path reference | nginx.conf → /etc/ssl/cert.pem |
| `requires_mount` | unit → mount | RequiresMountsFor | nginx.service → /mnt/data |
| `mounts` | fstab → device | fstab entry | /etc/fstab → /dev/sda1 |
| `corresponds_to` | fstab → unit | fstab ↔ systemd mount | /etc/fstab → mnt-data.mount |

All edges are **directed**: source depends on target (or source includes/references target).
`get_impact_graph()` follows **in-edges** (reverse), so querying the impact of
`/etc/default/nginx` would find `nginx.service` (which configures it).

---

## 7. Unit Name Resolution

systemd directives reference units by name (`network.target`), not file path.
The extractor must resolve names to file paths:

```python
SYSTEMD_PATHS = [
    "/etc/systemd/system/",
    "/lib/systemd/system/",
    "/usr/lib/systemd/system/",
    "/run/systemd/system/",
]

def resolve_unit_path(unit_name: str) -> Optional[str]:
    for base in SYSTEMD_PATHS:
        path = f"{base}{unit_name}"
        if os.path.exists(path):
            return path
    return None
```

For targets like `network.target` that may not have a file, we create a
**phantom node** — an external_module node in the trace graph. This allows
edges to targets that don't exist as files but are known systemd concepts.

Actually, the LSP edge endpoint validates that source/target are known nodes.
Phantom nodes would be rejected. Two options:
1. **Skip unresolvable targets** — only create edges for units that have files
2. **Pre-create phantom nodes** — add a separate endpoint or use the existing
   node creation mechanism

For MVP, option 1 is simpler. Most real dependencies have files. Targets like
`network.target` are usually satisfied by a `.target` unit file in
`/lib/systemd/system/`.

---

## 8. Glob Resolution for Includes

Include directives often use globs:
```
include /etc/nginx/conf.d/*.conf;
```

The extractor must:
1. Detect glob patterns in include directives
2. Expand against the filesystem
3. Create one edge per matched file

If no files match, no edge is created (the glob may match in the future when
new configs are dropped in).

---

## 9. Secrets & Safety

- The extractor reads from Halbert's **redacted** canonical JSON files
  (snapshot.py already runs `redact_text()` on raw content)
- Edge metadata includes only directive names and line numbers, not values
- No file content is sent to SourcePrep — only edge relationships
- The extractor does NOT read files directly — it works from the snapshot
  system's output, which has already been redacted

---

## 10. Open Questions

1. **Phantom nodes for abstract targets** — Should we create nodes for
   systemd targets like `network.target` that may not have files? Or skip
   edges to unresolvable targets? (Recommendation: skip for MVP, add later)

2. **Edge freshness** — When a config file changes, old edges may be stale.
   The `replace_origin` parameter handles this: Halbert pushes a full
   replacement set on each config change. But what about edges for files
   that no longer exist? (Recommendation: `replace_origin` clears all
   config-origin edges, so stale edges are automatically removed)

3. **Cross-project edges** — If Halbert has multiple SourcePrep projects
   (e.g., `host-os` and `user-dotfiles`), edges between configs in different
   projects can't be created (source/target must be in the same project).
   (Recommendation: one project per host for MVP)

4. **Config files outside the SourcePrep project** — Some referenced paths
   (e.g., `/usr/sbin/nginx`) are not config files and won't be in the trace
   graph. Edges to them will be rejected. (Recommendation: skip rejected
   edges silently, log at debug level)

5. **Rust engine support** — The Rust engine's `TraceIndex._load_rust()`
   doesn't load external edge JSONL files. Only `_load_python()` does.
   (Recommendation: for Phase 3, require Python engine fallback for external
   edges. Add Rust support in the graduation phase)

---

## 11. Success Criteria

1. **ConfigEdgeExtractor extracts edges from systemd units** — Given a
   parsed `.service` file with `Requires=network.target`, produces an edge
   from the service file to the network.target file.

2. **Edges are pushed to SourcePrep** — `POST /trace/external-edges`
   accepts and stores config edges in `trace_external_edges.jsonl`.

3. **Blast-radius query works** — `GET /trace/impact/{node_id}` returns
   config dependents. Querying `/etc/default/nginx` returns `nginx.service`.

4. **Config changes trigger edge refresh** — When `ConfigWatcher` detects
   a change, edges are re-extracted and pushed with `replace_origin=config`.

5. **Agent can use blast-radius** — The agent state machine has a tool to
   query impact, and can answer "what breaks if I edit this file?"

---

## 12. What NOT to Do

- **Do not build a separate graph store in Halbert.** Use SourcePrep's trace
  graph. Duplicating graph storage and traversal is waste.
- **Do not modify SourcePrep's Rust engine for Phase 3.** The Rust engine
  changes are for the graduation phase (3e). Phase 3 uses the external edges
  HTTP endpoint.
- **Do not send file content to SourcePrep.** Only send edge relationships.
  Content stays in Halbert's redacted snapshot store.
- **Do not create edges for non-existent files.** The endpoint validates
  against known nodes. Rejected edges are logged but don't fail the sync.
- **Do not implement all six edge types at once.** Start with systemd
  directives (highest value), then includes, then the rest.
