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

## License

By contributing, you agree that your contributions will be licensed under the GPL-3.0 license.

---

## Code of Conduct

Be respectful. Be constructive. Be patient.

We're all here to build something useful.
