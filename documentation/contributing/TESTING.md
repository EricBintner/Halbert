# Testing

Test conventions for Cerebric.

---

## Running Tests

```bash
# All tests
pytest tests/

# Specific file
pytest tests/test_memory.py

# With coverage
pytest tests/ --cov=cerebric_core --cov-report=html

# Verbose
pytest tests/ -v
```

---

## Test Structure

```
tests/
├── test_*.py           # Unit tests
├── platform/           # Platform-specific
│   └── test_linux_*.py
├── rag/                # RAG pipeline
│   └── test_rag_*.py
└── fixtures/           # Test data
    └── etc/
```

---

## Writing Tests

```python
import pytest
from cerebric_core.cerebric_core.memory.retrieval import MemoryRetrieval

def test_retrieval_returns_list():
    """Test that retrieval returns a list."""
    mem = MemoryRetrieval()
    results = mem.retrieve_from("core", "test", k=5)
    
    assert isinstance(results, list)
    assert len(results) <= 5

def test_retrieval_empty_query_raises():
    """Test that empty query raises ValueError."""
    mem = MemoryRetrieval()
    
    with pytest.raises(ValueError):
        mem.retrieve_from("core", "", k=5)
```

---

## Fixtures

```python
import pytest

@pytest.fixture
def temp_config(tmp_path):
    """Create temporary config directory."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir
```

---

## Markers

```python
@pytest.mark.slow
def test_large_index():
    ...

@pytest.mark.integration
def test_ollama_connection():
    ...
```

Run specific markers:
```bash
pytest -m "not slow"
pytest -m integration
```

---

## CI

Tests run on GitHub Actions. See `.github/workflows/ci.yml`.
