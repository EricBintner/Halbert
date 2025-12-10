# Code Style

Python code style for Halbert.

---

## Tools

| Tool | Purpose |
|------|---------|
| [Black](https://github.com/psf/black) | Formatting |
| [Ruff](https://github.com/charliermarsh/ruff) | Linting |
| [mypy](https://mypy-lang.org/) | Type checking |

```bash
# Format
black halbert_core/ Halbert/ tests/

# Lint
ruff check halbert_core/ Halbert/ tests/

# Type check
mypy halbert_core/
```

---

## Naming

| Type | Convention | Example |
|------|------------|---------|
| Files | snake_case | `memory_retrieval.py` |
| Classes | PascalCase | `MemoryRetrieval` |
| Functions | snake_case | `retrieve_from()` |
| Constants | UPPER_SNAKE | `MAX_RETRIES` |
| Private | _prefix | `_internal()` |

---

## Imports

```python
# 1. Standard library
import os
from pathlib import Path

# 2. Third-party
import yaml
from pydantic import BaseModel

# 3. Local
from halbert_core.halbert_core.utils.paths import data_subdir
```

---

## Type Hints

Required for public functions:

```python
def retrieve_from(
    self,
    subdir: str,
    query: str,
    k: int = 5
) -> list[dict]:
    """Retrieve documents from memory."""
    ...
```

---

## Docstrings

Google style:

```python
def example(param1: str, param2: int) -> bool:
    """Short description.

    Args:
        param1: Description of param1.
        param2: Description of param2.

    Returns:
        Description of return value.

    Raises:
        ValueError: When param1 is empty.
    """
```

---

## Error Handling

```python
# Specific exceptions
try:
    result = do_thing()
except FileNotFoundError:
    logger.warning("File not found: %s", path)
    return None
except Exception:
    logger.exception("Unexpected error")
    raise
```
