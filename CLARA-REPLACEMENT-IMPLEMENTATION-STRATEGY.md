# CLARA Replacement — Implementation Strategy

**Date:** 2026-08-23
**Plan:** See CLARA-REPLACEMENT-PLAN.md for full research and rationale
**This document:** Step-by-step execution guide with exact file paths, line numbers, and verification gates

---

## Execution Order

```
Phase 1 (Additive)  →  Phase 2 (Wiring)  →  Phase 3 (Switchover)  →  Phase 4 (Subtractive)
    ↓                      ↓                      ↓                       ↓
 0 risk                 low risk              medium risk              low risk
 new files only         parallel code         one commit               deletions
 + tests                + config              UI switchover            + summarization
```

Each phase ends with a commit and a verification gate. Do not proceed to the next phase until the gate passes.

---

## Phase 1: Create Compression Package + Tests

### Step 1.1: Create the compression package directory

```
halbert_core/halbert_core/compression/
├── __init__.py
├── compressor.py
├── semantic_compressor.py
├── lingua_compressor.py
├── memory_lod.py
└── factory.py
```

### Step 1.2: Port `compressor.py` (ABC + CompressResult + NoopCompressor)

**Source:** `/Volumes/4TB-BAD/HumanAI/LinuxBrain/halley_core/compression/compressor.py` (90 lines)
**Target:** `halbert_core/halbert_core/compression/compressor.py`
**Changes:** None needed — no `halley_core` imports in this file (it's the base ABC)

### Step 1.3: Port `semantic_compressor.py` (rule-based, zero deps)

**Source:** `/Volumes/4TB-BAD/HumanAI/LinuxBrain/halley_core/compression/semantic_compressor.py` (203 lines)
**Target:** `halbert_core/halbert_core/compression/semantic_compressor.py`
**Changes:**
- Import: `halley_core.compression.compressor` → `halbert_core.compression.compressor`
- `infer_category()`: Replace persona categories with sysadmin categories:
  - `background` → `service` (matches: service, daemon, systemd, running, stopped)
  - `personality` → `network` (matches: network, interface, ip, dns, routing)
  - `relationship` → `storage` (matches: disk, mount, partition, filesystem, lvm)
  - `interest` → `security` (matches: firewall, ssh, cert, ssl, permissions)
  - `secret` → `package` (matches: package, apt, dpkg, rpm, installed, version)
  - `quirk` → `kernel` (matches: kernel, module, driver, boot, grub)
  - Default: `config` (was `background`)

### Step 1.4: Port `lingua_compressor.py` (LLMLingua-2 neural)

**Source:** `/Volumes/4TB-BAD/HumanAI/LinuxBrain/halley_core/compression/lingua_compressor.py` (178 lines)
**Target:** `halbert_core/halbert_core/compression/lingua_compressor.py`
**Changes:**
- Import: `halley_core.compression.compressor` → `halbert_core.compression.compressor`
- `FORCE_TOKENS`: Add sysadmin tokens to the existing list:
  ```python
  FORCE_TOKENS = [
      # Sentence structure (keep from LinuxBrain)
      "\n", ".", "?", "!",
      # Dialogue markers (keep)
      '"', "'",
      # Narrative markers (keep)
      "—", "...",
      # Clause separation (keep)
      ",",
      # Names and identity markers (keep)
      ":",
      # Sysadmin tokens (NEW for Halbert)
      "/",    # file paths
      "=",    # config assignments
      "|",    # pipes
      ">",    # redirects
      "<",    # redirects
      "$",    # variables
      "`",    # inline code
      "#",    # comments, shebangs
  ]
  ```

### Step 1.5: Port `memory_lod.py` (6-level structural LOD)

**Source:** `/Volumes/4TB-BAD/HumanAI/LinuxBrain/halley_core/compression/memory_lod.py` (270 lines)
**Target:** `halbert_core/halbert_core/compression/memory_lod.py`
**Changes:**
- No `halley_core` imports (self-contained)
- `_FACT_INDICATORS`: Add sysadmin fact verbs:
  ```python
  _FACT_INDICATORS = re.compile(
      r"\b(is|are|was|were|lives?|works?|grew up|born|from|named?|called|"
      # Sysadmin facts (NEW)
      r"configured|enabled|disabled|installed|running|failed|"
      r"error|version|path|mounted|loaded|started|stopped|"
      r"set to|defined as|located at|points to)\b",
      re.IGNORECASE,
  )
  ```
- `assign_memory_lod()`: Add epistemic floor:
  ```python
  def assign_memory_lod(relevance: float, epistemic: float = 1.0) -> int:
      combined = 0.6 * relevance + 0.4 * epistemic
      # Epistemic floor: high-confidence memories never go below LOD 2
      # (prevents "lost along the way" failure from gist token research)
      if combined >= 0.70:
          return 0
      if combined >= 0.50:
          return 1
      if combined >= 0.35:
          return 2
      if epistemic >= 0.8:
          return 2  # FLOOR: don't compress high-confidence below LOD 2
      if combined >= 0.20:
          return 3
      if combined >= 0.10:
          return 4
      return 5
  ```

### Step 1.6: Port `factory.py` (create_compressor priority chain)

**Source:** `/Volumes/4TB-BAD/HumanAI/LinuxBrain/halley_core/compression/factory.py` (63 lines)
**Target:** `halbert_core/halbert_core/compression/factory.py`
**Changes:**
- Imports: `halley_core.compression.*` → `halbert_core.compression.*`

### Step 1.7: Port `__init__.py` (package exports)

**Source:** `/Volumes/4TB-BAD/HumanAI/LinuxBrain/halley_core/compression/__init__.py` (41 lines)
**Target:** `halbert_core/halbert_core/compression/__init__.py`
**Changes:**
- Imports: `halley_core.compression.*` → `halbert_core.compression.*`
- Update docstring: "Halbert Compression Package" instead of "Halley"

### Step 1.8: Write tests

**Target:** `halbert_core/tests/test_compression.py` (~200 lines)

```python
# Test structure:
# class TestCompressResult: field defaults, frozen immutability
# class TestNoopCompressor: pass-through, is_available=True
# class TestSemanticCompressor:
#   - test_light_level: filler removal only
#   - test_standard_level: + adjective trimming + clause pruning
#   - test_aggressive_level: + abbreviations + budget truncation
#   - test_extract_keywords: stopword filtering, dedup, max_keywords
#   - test_infer_category_service: "systemd service is running"
#   - test_infer_category_network: "network interface eth0"
#   - test_infer_category_storage: "disk mounted at /mnt"
#   - test_infer_category_security: "firewall enabled ssh"
#   - test_infer_category_package: "apt package version 1.2"
#   - test_infer_category_kernel: "kernel module loaded"
#   - test_infer_category_config_default: fallback
# class TestLinguaCompressor:
#   - test_is_available_false: llmlingua not installed
#   - test_compress_fallback: returns text unchanged if model unavailable
#   - test_compress_with_mock: mock PromptCompressor, verify rate/force_tokens
#   - test_status: returns dict with available/loaded/downloaded
# class TestMemoryLOD:
#   - test_lod0_full: no compression
#   - test_lod1_filler_removed: filler words stripped
#   - test_lod2_key_facts: fact extraction + emotional marker
#   - test_lod3_one_liner: category + one-line summary
#   - test_lod4_keywords: keywords + timestamp
#   - test_lod5_id_tag: ID + category only
#   - test_assign_lod_high_relevance: returns 0
#   - test_assign_lod_low_relevance: returns 5
#   - test_assign_lod_epistemic_floor: epistemic=0.9, relevance=0.1 → returns 2 (not 4/5)
#   - test_compress_batch_budget: fits within target_chars
#   - test_compress_batch_empty: returns ""
#   - test_compress_batch_promotes_lod: if exceeds budget, tries higher LOD
# class TestFactory:
#   - test_auto_detect_semantic: llmlingua not installed → SemanticCompressor
#   - test_explicit_lingua: backend="lingua" → LinguaCompressor (or fallback)
#   - test_explicit_semantic: backend="semantic" → SemanticCompressor
#   - test_explicit_noop: backend="noop" → NoopCompressor
```

### Step 1.9: Add optional dependency to pyproject.toml

**File:** `halbert_core/pyproject.toml`
**Change:** Add to `[project.optional-dependencies]`:
```toml
compression = [
  "llmlingua>=0.2",
  "huggingface-hub>=0.20",
]
```

### Phase 1 Verification Gate
```bash
# Run new tests
cd /Volumes/4TB-BAD/Halbert/halbert_core
arch -arm64 .venv/bin/python -m pytest tests/test_compression.py -v

# Verify no existing tests broken
arch -arm64 .venv/bin/python -m pytest tests/ -q --tb=short

# Verify package imports
arch -arm64 .venv/bin/python -c "from halbert_core.compression import create_compressor; c = create_compressor(); print(type(c).__name__)"
```

**Commit:** `Add compression package (ported from LinuxBrain Phase 72)`

---

## Phase 2: Wire Cascade into Assembler + API Routes + Summarization

### Step 2.1: Port conversation/summarization.py

**Source:** `/Volumes/4TB-BAD/HumanAI/LinuxBrain/halley_core/conversation/summarization.py` (~463 lines)
**Target:** `halbert_core/halbert_core/conversation/summarization.py`
**Changes:**
- Create `halbert_core/halbert_core/conversation/__init__.py`
- No `halley_core` imports in summarization.py (self-contained)
- Review `create_simple_summary()` — adapt for sysadmin context (extract commands, config changes, error messages instead of dialogue)

### Step 2.2: Add `_compress_with_cascade()` to assembler.py

**File:** `halbert_core/halbert_core/context/assembler.py`
**Location:** After `_compress_with_clara()` (line 630)
**New method:**

```python
async def _compress_with_cascade(
    self,
    content: str,
    query: str,
    sources: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Source-aware compression cascade.

    Applies different strategies per source type:
    - memories → LOD batch compression
    - rag/SourcePrep → skip or light (already compressed by SourcePrep LOD)
    - conversation → semantic compression (standard level)
    - observations → semantic compression (standard level)
    - other → semantic compression (standard level)

    Returns same shape as _compress_with_clara for drop-in replacement:
        {'content': str, 'tokens': int, 'original_tokens': int, 'ratio': float}
    """
    try:
        from ..compression.factory import create_compressor
        from ..compression.memory_lod import compress_batch
    except ImportError:
        return None

    compressor = create_compressor()
    original_tokens = self.tokens.count(content)

    # Split content by source type for targeted compression
    parts = []
    total_compressed_chars = 0

    for source in sources:
        source_type = source.get("type", "unknown")
        source_content = source.get("content", "")
        if not source_content:
            continue

        if source_type == "memory":
            # LOD batch compression for memories
            # (would need memory dicts with relevance/epistemic — use source metadata)
            result = compressor.compress(source_content, level="standard")
            parts.append(result.compressed)
        elif source_type == "rag":
            # SourcePrep already compressed — skip or light only
            result = compressor.compress(source_content, level="light")
            parts.append(result.compressed)
        elif source_type in ("conversation", "observations"):
            # Semantic compression for prose
            result = compressor.compress(source_content, level="standard")
            parts.append(result.compressed)
        else:
            # Default: standard compression
            result = compressor.compress(source_content, level="standard")
            parts.append(result.compressed)

    combined = "\n\n".join(parts)
    combined_tokens = self.tokens.count(combined)

    if combined_tokens >= original_tokens:
        # No compression achieved — return None to signal no change
        return None

    return {
        "content": combined,
        "tokens": combined_tokens,
        "original_tokens": original_tokens,
        "ratio": round(original_tokens / max(combined_tokens, 1), 2),
    }
```

### Step 2.3: Add cascade call to assembler's assemble() method

**File:** `halbert_core/halbert_core/context/assembler.py`
**Location:** Lines 209-222 (the compression block)
**Change:** Add cascade attempt before CLARA:

```python
# Optional compression for large contexts
compressed = False
if use_compression and combined_tokens > self._clara_threshold:
    # Try new cascade first (Phase 2)
    compress_result = await self._compress_with_cascade(combined, query, sources)
    if not compress_result:
        # Fall back to CLARA if cascade unavailable
        compress_result = await self._compress_with_clara(combined, query)
    if compress_result:
        combined = compress_result["content"]
        combined_tokens = compress_result["tokens"]
        compressed = True
        sources.append({
            "type": "compression",
            "original_tokens": compress_result["original_tokens"],
            "compressed_tokens": compress_result["tokens"],
            "ratio": compress_result.get("ratio", 1.0),
        })
```

### Step 2.4: Create compression API routes

**Target:** `halbert_core/halbert_core/dashboard/routes/compression.py` (~120 lines)
**Pattern:** Mirror `clara.py` structure but for the new compression system

Routes:
- `GET /api/compression/status` — active backend, model loaded, compression stats
- `GET /api/compression/config` — current config from models.yml
- `POST /api/compression/config` — update config
- `POST /api/compression/compress` — manual compress (text + query → compressed)
- `POST /api/compression/test` — run test compression, return before/after stats

### Step 2.5: Register compression router in app.py

**File:** `halbert_core/halbert_core/dashboard/app.py`
**Change:** Add import + include_router for compression (keep CLARA router)

### Step 2.6: Add compression config to models.yml

**File:** `config/models.yml`
**Change:** Add after the `clara:` block (keep `clara:` block for now):

```yaml
# Compression system (replaces CLaRa — Phase 72 port from LinuxBrain)
compression:
  enabled: true
  backend: auto  # auto | lingua | semantic | noop
  threshold: 4000  # Compress when context > this many tokens
  level: standard  # light | standard | aggressive
  lod_epistemic_floor: 0.8  # Never compress high-confidence memories below LOD 2
```

### Phase 2 Verification Gate
```bash
# Run all tests
arch -arm64 .venv/bin/python -m pytest tests/ -q --tb=short

# Start dashboard
arch -arm64 .venv/bin/uvicorn halbert_core.dashboard.app:app --host 127.0.0.1 --port 8000 &

# Test compression API
curl http://127.0.0.1:8000/api/compression/status
curl http://127.0.0.1:8000/api/compression/config

# Verify CLARA routes still work
curl http://127.0.0.1:8000/api/clara/status
```

**Commit:** `Wire compression cascade into assembler + add compression API routes`

---

## Phase 3: Switchover — Prefer Cascade Over CLARA

### Step 3.1: Update assembler to prefer cascade

**File:** `halbert_core/halbert_core/context/assembler.py`
**Change:** The cascade-first logic was already added in Phase 2 Step 2.3. In Phase 3, we just verify it's the preferred path. No code change needed if Phase 2 was done correctly.

### Step 3.2: Create CompressionSettings.tsx

**Target:** `halbert_core/halbert_core/dashboard/frontend/src/components/CompressionSettings.tsx` (~200 lines)
**Content:** React component showing:
- Active backend badge (Lingua/Semantic/Noop) with color indicator
- Compression level selector (light/standard/aggressive) — dropdown
- Threshold input (number, tokens)
- Epistemic floor input (0.0-1.0 slider)
- "Test Compression" button → calls `/api/compression/test`, shows before/after stats
- "Download Model" button (for Lingua, if not downloaded)
- Status display: model loaded, model size, last compression stats

### Step 3.3: Update Settings.tsx

**File:** `halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx`
**Changes (7 refs at lines 106, 107, 1309, 1310, 1315, 1316, 1792):**
- Replace `ClaraSettings` import with `CompressionSettings` import
- Replace `<ClaraSettings />` component with `<CompressionSettings />`
- Remove CLARA-related state variables
- Add compression-related state variables

### Step 3.4: Update settings.py routes

**File:** `halbert_core/halbert_core/dashboard/routes/settings.py`
**Changes (29 refs at lines 267-432):**
- Replace CLARA config GET/POST endpoints with compression config endpoints
- Map to the new `compression:` block in models.yml
- Keep CLARA endpoints as deprecated aliases that redirect to compression endpoints

### Step 3.5: Update tauri.ts

**File:** `halbert_core/halbert_core/dashboard/frontend/src/lib/tauri.ts`
**Add:**
```typescript
export async function getCompressionStatus() { ... }
export async function getCompressionConfig() { ... }
export async function updateCompressionConfig(config: CompressionConfig) { ... }
export async function testCompression(text: string, query: string) { ... }
```

### Step 3.6: Rebuild frontend

```bash
cd halbert_core/halbert_core/dashboard/frontend
npm run build
```

### Phase 3 Verification Gate
```bash
# Run all tests
arch -arm64 .venv/bin/python -m pytest tests/ -q --tb=short

# Start dashboard and verify Settings page
arch -arm64 .venv/bin/uvicorn halbert_core.dashboard.app:app --host 127.0.0.1 --port 8000 &

# Open browser to Settings page — verify compression panel shows
# Verify compression status endpoint
curl http://127.0.0.1:8000/api/compression/status

# Test manual compression
curl -X POST http://127.0.0.1:8000/api/compression/test \
  -H "Content-Type: application/json" \
  -d '{"text": "The systemd service nginx is configured to start at boot and is currently running with PID 1234. The configuration file is located at /etc/nginx/nginx.conf and the error log shows a warning about worker_connections being set to 1024 which may be too low for high traffic loads.", "query": "nginx status"}'
```

**Commit:** `Switchover: prefer compression cascade over CLARA in UI and settings`

---

## Phase 4: Remove CLARA + Wire Summarization + Cleanup

### Step 4.1: Delete CLARA files

```bash
rm halbert_core/halbert_core/model/clara_provider.py
rm halbert_core/halbert_core/dashboard/routes/clara.py
rm halbert_core/halbert_core/dashboard/frontend/src/components/ClaraSettings.tsx
rm halbert_core/tests/test_clara_integration.py
```

### Step 4.2: Remove CLARA from assembler.py

**File:** `halbert_core/halbert_core/context/assembler.py`
**Changes:**
- Delete `_compress_with_clara()` method (lines 570-630)
- Remove `clara_provider` import attempt (lines 588-594)
- Remove `_clara` constructor parameter (line 68)
- Remove `self._clara = clara_provider` (line 90)
- Remove `self._clara_threshold = 4000` → rename to `self._compressor_threshold = 4000`
- Remove CLARA fallback in `assemble()` — cascade is the only path now
- Wire `conversation/summarization.py` into `_format_conversation()`:
  - If `len(conversation) > 10`: use `create_simple_summary()` for older messages
  - Keep last 6 messages as raw text
  - Replace current end-truncation (lines 290-326)

### Step 4.3: Remove CLARA from app.py

**File:** `halbert_core/halbert_core/dashboard/app.py`
**Changes (lines 165, 189):**
- Remove `from .routes.clara import router as clara_router`
- Remove `app.include_router(clara_router)`

### Step 4.4: Remove CLARA from settings.py

**File:** `halbert_core/halbert_core/dashboard/routes/settings.py`
**Changes (29 refs at lines 267-432):**
- Remove all CLARA config endpoints
- Remove CLARA-related imports
- Keep compression endpoints (added in Phase 3)

### Step 4.5: Remove CLARA from Settings.tsx

**File:** `halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx`
**Changes (7 refs):**
- Remove any remaining CLARA imports or references
- Ensure only CompressionSettings is used

### Step 4.6: Remove CLARA from config/models.yml

**File:** `config/models.yml`
**Changes:**
- Remove `clara:` block (lines 40-47)
- Update tier comments (lines 10-12): remove CLARA references
  - Tier 1: "remote CLaRa" → "local compression (Semantic)"
  - Tier 2: "local CLaRa" → "local compression (Lingua)"
  - Tier 3: "local CLaRa" → "local compression (Lingua)"

### Step 4.7: Update handoff docs

**Files:**
- `.handoff/RQ-D-SCRUTINY-2026-08-22.md` (2 refs at lines 284, 293)
- `.handoff/RQ-D-CHAT-AUDIT-2026-08-22.md` (3 refs at lines 7, 30, 237)

**Changes:** Replace "CLaRa compression" references with "compression cascade (LOD + LLMLingua-2 + Semantic)"

### Step 4.8: Rebuild frontend

```bash
cd halbert_core/halbert_core/dashboard/frontend
npm run build
```

### Phase 4 Verification Gate
```bash
# Verify no CLARA references remain in Python code
grep -ri 'clara' halbert_core/halbert_core/ --include="*.py"
# Expected: 0 results

# Verify no CLARA references remain in frontend
grep -ri 'clara' halbert_core/halbert_core/dashboard/frontend/src/
# Expected: 0 results

# Verify no CLARA references in config
grep -ri 'clara' config/
# Expected: 0 results (except maybe historical comments)

# Run all tests
arch -arm64 .venv/bin/python -m pytest tests/ -q --tb=short

# Start dashboard and verify everything works
arch -arm64 .venv/bin/uvicorn halbert_core.dashboard.app:app --host 127.0.0.1 --port 8000 &

# Verify Settings page loads
# Verify compression panel works
# Verify chat path works (send a test message)
```

**Commit:** `Remove CLARA, wire conversation summarization, cleanup references`

---

## Post-Implementation Checklist

- [ ] `grep -ri 'clara' halbert_core/` returns 0 results (excluding handoff docs)
- [ ] `pytest tests/ -q` passes with 0 failures
- [ ] Dashboard starts and Settings page shows compression panel
- [ ] Compression status endpoint returns active backend info
- [ ] Test compression endpoint returns before/after stats
- [ ] Chat path works end-to-end (assembler uses cascade, not CLARA)
- [ ] Conversation summarization works for long conversations (>10 messages)
- [ ] `config/models.yml` has `compression:` block, no `clara:` block
- [ ] `pyproject.toml` has `compression` optional dependency group
- [ ] All 4 commits are clean (no Co-Authored-By trailers)
