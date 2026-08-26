# Contributing to Halbert

Thank you for your interest in contributing to Halbert! This document provides guidelines for contributing.

---

## Getting Started

### 1. Fork and Clone

```bash
git clone https://github.com/EricBintner/Halbert.git
cd Halbert
```

### 2. Set Up Development Environment

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e halbert_core/

# Install dev dependencies
pip install pytest pytest-cov black ruff mypy
```

### 3. Verify Setup

```bash
# Run tests
pytest tests/

# Check CLI works
python Halbert/main.py info
```

---

## Development Workflow

### Branch Naming

- `feature/description` — New features
- `fix/description` — Bug fixes
- `docs/description` — Documentation
- `refactor/description` — Code refactoring

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add disk space analyzer tool
fix: correct journald timestamp parsing
docs: update CLI reference
refactor: extract common tool patterns
```

### Pull Request Process

1. Create a feature branch from `main`
2. Make your changes
3. Run tests: `pytest tests/`
4. Run linting: `ruff check .`
5. Run formatting: `black .`
6. Submit PR with clear description

---

## Code Style

### Python Style

- Use [Black](https://github.com/psf/black) for formatting
- Use [Ruff](https://github.com/charliermarsh/ruff) for linting
- Use type hints for function signatures
- Follow [PEP 8](https://pep8.org/)

```bash
# Format code
black halbert_core/ Halbert/ tests/

# Check linting
ruff check halbert_core/ Halbert/ tests/
```

### Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Files | snake_case | `memory_retrieval.py` |
| Classes | PascalCase | `MemoryRetrieval` |
| Functions | snake_case | `retrieve_from()` |
| Constants | UPPER_SNAKE | `MAX_RETRIES` |
| Private | _prefix | `_internal_method()` |

### Imports

```python
# Standard library
import os
import json
from pathlib import Path

# Third-party
import yaml
from pydantic import BaseModel

# Local
from halbert_core.halbert_core.utils.paths import data_subdir
```

---

## Architecture Guidelines

### Adding a New Tool

1. Create `halbert_core/halbert_core/tools/my_tool.py`:

```python
from .base import BaseTool, ToolResult

class MyTool(BaseTool):
    """One-line description."""
    
    name = "my_tool"
    description = "What this tool does"
    
    def execute(self, inputs: dict, dry_run: bool = True) -> ToolResult:
        """Execute the tool."""
        if dry_run:
            return ToolResult(
                success=True,
                output=f"Would do: {inputs}",
                dry_run=True
            )
        
        # Actual execution
        result = self._do_thing(inputs)
        
        return ToolResult(
            success=True,
            output=result,
            dry_run=False
        )
```

2. Add CLI command in `Halbert/main.py`
3. Add tests in `tests/test_my_tool.py`
4. Update documentation

### Adding a New Ingestion Source

1. Create `halbert_core/halbert_core/ingestion/my_source.py`
2. Implement the standard event schema
3. Add to ingestion runner
4. Update `ingestion.yml` schema

### Adding a Dashboard Feature

1. Add API route in `halbert_core/halbert_core/dashboard/routes/`
2. Add React component in `dashboard/frontend/src/`
3. Update API documentation

---

## Testing

### Running Tests

```bash
# All tests
pytest tests/

# Specific test file
pytest tests/test_memory.py

# With coverage
pytest tests/ --cov=halbert_core --cov-report=html
```

### Writing Tests

```python
import pytest
from halbert_core.halbert_core.memory.retrieval import MemoryRetrieval

def test_memory_retrieval_basic():
    """Test basic memory retrieval."""
    mem = MemoryRetrieval()
    results = mem.retrieve_from("core", "test query", k=5)
    
    assert isinstance(results, list)
    assert len(results) <= 5

def test_memory_retrieval_empty_query():
    """Test handling of empty query."""
    mem = MemoryRetrieval()
    
    with pytest.raises(ValueError):
        mem.retrieve_from("core", "", k=5)
```

### Test Categories

| Directory | Purpose |
|-----------|---------|
| `tests/` | Unit tests |
| `tests/platform/` | Platform-specific tests |
| `tests/rag/` | RAG pipeline tests |
| `tests/fixtures/` | Test data |

---

## Documentation

### Updating Documentation

1. Edit files in `documentation/`
2. Ensure code examples work
3. Update cross-references
4. Verify links

### Documentation Style

- Use present tense ("Runs" not "Will run")
- Use second person ("You can" not "Users can")
- Include code examples
- Keep paragraphs short

---

## Issue Guidelines

### Reporting Bugs

Include:
- Halbert version (from `git log -1`)
- Python version
- OS and version
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs

### Requesting Features

Include:
- Use case description
- Proposed solution (if any)
- Alternatives considered

---

## What We're Looking For

### High-Value Contributions

- **Bug fixes** — Especially with tests
- **Documentation** — Clarifications, examples, corrections
- **Test coverage** — Expanding test suite
- **Performance** — Profiling and optimization
- **New tools** — Following the established patterns

### Lower Priority

- Large architectural changes (discuss first)
- New dependencies (discuss first)
- Cosmetic changes without functional improvement

---

## Questions?

- Open an issue for questions
- Check existing issues first
- Be patient — maintainers are volunteers

---

## Contributor Licensing & Intellectual Property Agreement

Halbert Core is, and will always remain, Free and Open Source Software licensed under the **GNU General Public License v3.0 (or later)** (GPL-3.0-or-later).

To enable the project maintainers to distribute Halbert across diverse platforms—including sandboxed marketplace environments such as the Apple Mac App Store and direct commercial releases (Halbert Pro)—all contributors agree to the licensing terms below.

### 1. Developer Certificate of Origin (DCO) 1.1

By contributing to this project, you certify that:

a) The contribution was created in whole or in part by you and you have the right to submit it under the open source license indicated in the file; or
b) The contribution is based upon previous work that, to the best of your knowledge, is covered under an appropriate open source license and you have the right under that license to submit that work with modifications, whether created in whole or in part by you, under the same open source license; or
c) The contribution was provided directly to you by some other person who certified (a), (b) or (c) and you have not modified it; and
d) You understand and agree that this project and the contribution are public and that a record of the contribution (including all personal information you submit with it, including your sign-off) is maintained indefinitely and may be redistributed consistent with this project or the open source license(s) involved.

All pull requests require signed-off commits (`git commit -s` / `Signed-off-by: Full Name <email@example.com>`).

### 2. Dual-Licensing & Commercial Permission Grant

By submitting a Pull Request with a `Signed-off-by:` commit trailer, you grant the project maintainer (**Eric Bintner**) a perpetual, worldwide, non-exclusive, royalty-free, irrevocable license to:

1. **Distribute via App Stores under GPLv3 Section 7 Exceptions**: Convey and distribute binaries of the work, including your contributions, through digital application stores (including the Apple Mac App Store) subject to the GPLv3 Section 7 Additional Permission set forth below.
2. **Commercial Distribution**: Convey, package, and distribute binary and source distributions of Halbert (including Halbert Pro editions) under commercial, enterprise, or multi-seat licensing models.
3. **Open Source Upstream Parity**: The project maintainers guarantee that all contributions accepted into the core repository will perpetually remain available in source form under the GNU General Public License v3.0 (or later).

### 3. Apple Mac App Store GPLv3 Section 7 Exception Clause

Distributions of Halbert conveyed through the Apple Mac App Store carry the following additional permission pursuant to Section 7 of the GNU General Public License Version 3:

> **Additional Permission under GNU GPLv3 Section 7 (Apple Mac App Store Exception):**
> 
> *"As a special exception, the copyright holders of Halbert grant permission to convey the object code of this work through the Apple Mac App Store or other digital distribution platforms that impose usage rules, DRM, or application sandboxing, notwithstanding Sections 6 and 10 of the GNU GPLv3, provided that the complete corresponding source code for the GPLv3-covered components remains freely available under the terms of the GNU General Public License v3.0 (or later)."*

---

## Code of Conduct

Be respectful. Be constructive. Be patient.

We're all here to build something useful.
