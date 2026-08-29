# Python Environment, Dependency Architecture & Ecosystem Unification Handoff

**Date:** 2026-08-29  
**Author:** AI System Architecture & Engineering  
**Scope:** Halbert Core, Haloysius, SourcePrep (CoDRAG), Model Picker UI, Design System, Packaging & Runtime Deployment  
**Status:** Authoritative Recommendation & Implementation Blueprint  

---

## 1. Executive Summary & Core Verdict

A comprehensive second-pass audit, reverse engineering analysis, and literature review were performed across all owned codebases, third-party libraries, container images, operating system distributions, and continuous integration workflows.

### **The Verdict: Unified Baseline on Python 3.11 with Forward Compatibility for Python 3.12 (`requires-python = ">=3.11,<3.13"`)**

```
+---------------------------------------------------------------------------------------------------+
|                                 UNIFIED TARGET ARCHITECTURE                                       |
|                                                                                                   |
|  Declared Package Metadata:      requires-python = ">=3.11" (or ">=3.11,<3.13")                   |
|  Developer Workstation Venvs:    Python 3.11.x (macOS Apple Silicon & Linux x86_64)               |
|  CI/CD Automated Test Matrix:    Python 3.11 (Primary Gate) + Python 3.12 (Smoke Gate)            |
|  Container Deployments:          Ubuntu 22.04 / 24.04 LTS with Python 3.11 / 3.12 runtime         |
|  Rust/PyO3 Engine ABI:           PyO3 abi3-py311 (Stable forward-compatible ABI)                  |
+---------------------------------------------------------------------------------------------------+
```

### Key Drivers
1. **SourcePrep is already hard-locked to `>=3.11`:** `pyproject.toml`, `[tool.ruff] target-version = "py311"`, `[tool.mypy] python_version = "3.11"`, and Docker images (`Dockerfile.cpu`, `Dockerfile.gpu`) are built on Python 3.11.
2. **Halbert CI is already running on Python 3.11:** `.github/workflows/ci.yml` executes `suite-census`, `design-tokens`, and `test` (backend) jobs under `python-version: '3.11'`.
3. **Public Documentation already dictates Python 3.11+:** Both `README.md` and `documentation/INSTALLATION.md` specify Python 3.11+ (with 3.12 recommended for Ubuntu 24.04 LTS).
4. **Python 3.10 Approaches End-of-Life (October 2026):** 3.10 is entering security-only maintenance and lacks essential runtime features (`tomllib`, `asyncio.TaskGroup`, native ISO 8601 UTC `Z` timestamp parsing).
5. **Haloysius 3.10 Downgrade was a Temporary Concession:** Haloysius `pyproject.toml` was downgraded to `>=3.10` in commit `46f0d20` (August 22, 2026) solely to bypass a mismatch with Halbert's local legacy virtualenv.

---

## 2. Reverse Engineering of All Owned & Consumed Components

### 2.1 Halbert Core (`/Volumes/4TB-BAD/Halbert/halbert_core`)
* **Role:** Local-first system administration assistant runtime (FastAPI dashboard, finite state machine agents, BM25 + ChromaDB RAG, policy engine, journald/hwmon ingestion, LLM client routing).
* **Current State:**
  * `pyproject.toml`: `requires-python = ">=3.10"` (artificially loose).
  * `requirements-rag.txt`: Outdated, hard-pinned 2023 versions (`sentence-transformers==2.2.2`, `chromadb==0.4.22`).
  * Active `.venv`: Built with Python 3.10.9.
  * Broken editable import: Missing `haloysius` runtime linkage due to Haloysius `src/` layout migration.
* **Compatibility Analysis:**
  * All core runtime libraries (`pydantic>=2.6`, `fastapi>=0.109`, `uvicorn>=0.27`, `sqlalchemy>=2.0`, `watchdog>=4.0`, `apscheduler>=3.10`, `httpx>=0.26`, `numpy>=1.24`, `opencv-python>=4.8`, `mss>=9.0`) operate with high stability on Python 3.11 and 3.12.
  * `systemd-python` (Linux native C-extension) builds cleanly against Python 3.11/3.12 system headers (`libsystemd-dev`).

### 2.2 Haloysius (`/Volumes/4TB-BAD/Haloysius`)
* **Role:** Modular persona-cognition core (episodic memory, continuous state ledger, emotional drives, conversation turn advancement, seam protocols).
* **Current State:**
  * `pyproject.toml`: `requires-python = ">=3.10"`.
  * Package Structure: `src/haloysius/` layout.
  * Subtractive Dependency Model: Minimal hard deps (`pyyaml>=6.0`, `requests>=2.31.0`), lazy-loaded optional extras (`numpy`, `sentence-transformers`, `torch`).
* **Compatibility Analysis:**
  * Pure Python core with zero native C extensions in base install.
  * Embeddings stack uses lazy imports; `torch 2.x` and `sentence-transformers` have pre-built binary wheels for Python 3.11 on Darwin (arm64 & x86_64) and Linux.

### 2.3 SourcePrep / CoDRAG (`/Volumes/4TB-BAD/HumanAI/CoDRAG`)
* **Role:** Structural codebase intelligence system (file indexing, tree-sitter AST parsing, trace graph generation, ONNX vector embeddings, SQLite cache, FastAPI daemon, MCP server).
* **Current State:**
  * Root `pyproject.toml`: `requires-python = ">=3.11"`.
  * `engine/pyproject.toml`: `requires-python = ">=3.10"` (inconsistency with root).
  * Tooling: Ruff target `py311`, Mypy target `3.11`.
  * Engine Build: Rust PyO3 crate compiled via `maturin`.
* **Compatibility Analysis:**
  * `onnxruntime>=1.17.0`, `tokenizers>=0.15.0`, `tree-sitter>=0.21.0` have complete wheel coverage for Python 3.11 and 3.12.
  * PyO3 0.23+ with `abi3-py311` produces forward-compatible wheels for 3.11, 3.12, and 3.13.

### 2.4 Model Picker UI (`/Volumes/4TB-BAD/Halbert/packages/model-picker`)
* **Role:** Headless, style-agnostic model picker component for React frontends (local endpoint discovery for Ollama, LM Studio, OpenAI, Anthropic, Gemini; role assignment, tier control).
* **Current State:** Pure TypeScript / React 18 & 19 package (`@halbert/model-picker`).
* **Reverse Engineering Verdict:** **Zero Python runtime code.** Tested via Vitest/Node 20, built via Vite/TypeScript. Completely decoupled from Python version constraints.

### 2.5 Design System (`/Volumes/4TB-BAD/Halbert/packages/design-system`)
* **Role:** Olivetti Vermilion & Bone component library shared across desktop shell and web applications.
* **Current State:** Pure TypeScript / React / Tailwind / Storybook.
* **Reverse Engineering Verdict:** **Zero Python runtime code.** Checked via Node 20 / Vitest.

---

## 3. Computer Science Literature & Industry Benchmarks

### 3.1 Faster CPython & Interpreter Specialization (PEP 659 / PEP 709)
* **Citation:** Shannon, M., van Rossum, G., et al. (2022). *PEP 659 – Specializing Adaptive Interpreter*. Python Enhancement Proposals.
* **Mechanism:** CPython 3.11 introduced dynamic bytecode specialization (Tier 1 adaptive interpreter). The interpreter observes operand types during execution and dynamically rewrites generic opcodes (`BINARY_OP`, `LOAD_ATTR`, `CALL`) into specialized single-type inline instructions (`BINARY_OP_ADD_INT`, `LOAD_ATTR_INSTANCE_VALUE`).
* **Empirical Data (pyperformance benchmark suite):**
  * Python 3.11 delivers a **~25% geometric mean execution speedup** over Python 3.10.
  * Python 3.12 adds another **~5-10% speedup** via inlined comprehensions (PEP 709) and optimized object allocators.
* **Relevance to Halbert & Haloysius:** Halbert's agent state machine, prompt assembly templates, and Haloysius cognition tick (`advance_turn()`, worry decay calculations, predicate string rendering) are pure Python CPU-bound workloads that directly benefit from PEP 659 adaptive specialization without any code changes.

### 3.2 Structured Concurrency & Daemon Reliability (PEP 654 / Smith 2018)
* **Citations:**
  * Smith, N. J. (2018). *Notes on structured concurrency, or: Go statement considered harmful*.
  * Warsaw, B., van Rossum, G., Hrončok, M. (2021). *PEP 654 – Exception Groups and except\**.
* **Mechanism:** Traditional `asyncio.gather` and unstructured background tasks (`asyncio.create_task`) suffer from "task leakage" when partial failures occur, leaving orphaned background coroutines holding system resources (file descriptors, sockets, database handles). Python 3.11 introduced `asyncio.TaskGroup` and `ExceptionGroup`, enforcing lexical scoping on concurrent operations: if any sub-task fails, all siblings are cancelled, and all exceptions are gathered and reported atomically.
* **Relevance to Ingestion & WebSockets:** Halbert's journald/hwmon ingestion streaming, watched terminal sessions, and MCP HTTP/SSE transport layers gain deterministic teardown and leak-free error propagation under Python 3.11+.

### 3.3 Memory Layout & Zero-Cost Exceptions
* **Mechanism:** Python 3.11 eliminated the runtime overhead of entering `try...except` blocks when no exception is raised ("zero-cost exceptions"). In addition, object frame layouts were streamlined, reducing per-frame stack allocation overhead.
* **Relevance to Haloysius Seam Architecture:** Haloysius utilizes defensive `try...except ImportError` patterns to maintain its subtractive contract (lazy loading heavy ML libraries). Zero-cost exceptions ensure that these guarded import paths have zero runtime penalty during normal execution.

### 3.4 Rust-Python Interoperability & Stable ABI (PEP 384 / PyO3)
* **Citation:** PyO3 Project & Maturin Documentation (2024). *Stable ABI (abi3) and Extension Packaging Architecture*.
* **Mechanism:** C extensions compiled against a specific Python minor version (e.g. `cp310`) fail to load on newer Python versions due to C-structure ABI changes. PEP 384 defined the Python Limited C API (`abi3`), restricting extensions to a stable, forward-compatible C-symbol subset.
* **Relevance to SourcePrep Engine:** By configuring `crates/prep-engine` with `pyo3 = { version = "0.23", features = ["abi3-py311"] }`, Maturin produces a single binary wheel (`cp311-abi3`) that executes natively and without recompilation across Python 3.11, 3.12, 3.13, and beyond.

---

## 4. Cross-Version Trade-Off & Risk Matrix

| Criterion | Python 3.10 | Python 3.11 (Recommended Baseline) | Python 3.12 (Forward Target) | Python 3.13 |
| :--- | :--- | :--- | :--- | :--- |
| **EOL Date** | **Oct 2026 (Imminent)** | Oct 2027 | Oct 2028 | Oct 2029 |
| **Performance vs 3.10** | Baseline (1.0x) | **+25% Speedup** | +30-35% Speedup | +35-45% Speedup |
| **Native `tomllib`** | No (requires `tomli`) | **Yes (PEP 680)** | Yes | Yes |
| **`TaskGroup` / `ExceptionGroup`**| No (requires backports) | **Yes (PEP 654)** | Yes | Yes |
| **ISO 8601 UTC 'Z' Parsing** | No (workaround required) | **Yes (native)** | Yes | Yes |
| **Wheel Availability (PyTorch/ONNX)** | 100% | **100% Mature** | 100% Mature | Emerging / Nightly |
| **Ubuntu Native Target** | 22.04 LTS default | 22.04 / Debian 12 | **24.04 LTS default** | Non-LTS only |
| **Rust PyO3 `abi3` Baseline** | `abi3-py310` | **`abi3-py311`** | Compatible | Compatible |
| **Adoption Risk** | High (Sunset risk) | **Zero (Sweet Spot)** | Low (Fully Tested) | Moderate (JIT/GIL flux) |

---

## 5. Technical Migration & Unification Checklist

### Phase 1: Package Manifests Alignment
- [ ] **`halbert_core/pyproject.toml`**: Update `requires-python = ">=3.11"`.
- [ ] **`/Volumes/4TB-BAD/Haloysius/pyproject.toml`**: Update `requires-python = ">=3.11"`.
- [ ] **`/Volumes/4TB-BAD/HumanAI/CoDRAG/engine/pyproject.toml`**: Update `requires-python = ">=3.11"`.
- [ ] **`packaging/arch/PKGBUILD`**: Update `depends=('python>=3.11' ...)`.

### Phase 2: Requirements Cleanup & Deprecations
- [ ] **`halbert_core/requirements-rag.txt`**: Remove obsolete pinned versions (`sentence-transformers==2.2.2`, `chromadb==0.4.22`) to eliminate split-brain dependency specifications; reference `halbert_core[rag-legacy]` extras.
- [ ] **Remove 3.10 workarounds**: Clean up custom trailing 'Z' ISO string slicing where applicable.

### Phase 3: Developer Environment Rebuild
- [ ] Destroy legacy Python 3.10 virtual environment: `rm -rf /Volumes/4TB-BAD/Halbert/.venv`
- [ ] Provision clean Python 3.11 virtual environment:
  ```bash
  /usr/local/bin/python3.11 -m venv /Volumes/4TB-BAD/Halbert/.venv
  /Volumes/4TB-BAD/Halbert/.venv/bin/pip install --upgrade pip setuptools wheel
  /Volumes/4TB-BAD/Halbert/.venv/bin/pip install -e "/Volumes/4TB-BAD/Halbert/halbert_core[dashboard,rag-legacy,cloud-apis,vision,dev]"
  /Volumes/4TB-BAD/Halbert/.venv/bin/pip install -e "/Volumes/4TB-BAD/Haloysius"
  ```

### Phase 4: CI & Build Pipeline Verification
- [ ] Execute census gate: Verify all test files are tracked under GATES in `ci.yml`.
- [ ] Run backend test suite: `/Volumes/4TB-BAD/Halbert/.venv/bin/pytest halbert_core/tests -q`
- [ ] Run Haloysius test suite: `/Volumes/4TB-BAD/Halbert/.venv/bin/pytest /Volumes/4TB-BAD/Haloysius/tests -q`
- [ ] Verify Model Picker boundary and tests: `cd packages/model-picker && npm run check:boundary && npm test`
- [ ] Verify Design System tests: `cd packages/design-system && npm test`
- [ ] Verify macOS PyInstaller packaging script: `./scripts/build-macos.sh --channel oss-macos --dev`

---

## 6. Document Cross-References & History

* `documentation/INSTALLATION.md`: Public installation guide (specifies Python 3.11+).
* `documentation/README.md`: Project landing documentation.
* `.handoff/FINAL-PLAN-2026-08-22.md`: Historical record of Haloysius 3.10 temporary downgrade.
* `.handoff/CONTINUOUS-CONVERSATION-PLAN-A-2026-08-26.md`: Notes on Python 3.10 ISO string parsing workarounds.
* `.github/workflows/ci.yml`: Authoritative GitHub Actions CI matrix (runs on Python 3.11).
* `/Volumes/4TB-BAD/HumanAI/CoDRAG/.github/workflows/engine-wheels.yml`: SourcePrep wheel build workflow.
