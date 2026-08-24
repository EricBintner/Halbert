"""
Unit tests for JSONL to Markdown converter (jsonl_to_markdown.py).
"""

import json
import tempfile
from pathlib import Path
import pytest

from halbert_core.rag.jsonl_to_markdown import (
    chunk_large_doc,
    convert_corpus,
    convert_jsonl_file,
    format_doc_to_markdown,
    format_meta_comment,
    sanitize_heading,
)


def test_sanitize_heading():
    assert sanitize_heading("### System Architecture") == "System Architecture"
    assert sanitize_heading("  chmod(1)\n\n") == "chmod(1)"
    assert sanitize_heading("") == "Untitled Document"


def test_format_meta_comment():
    doc = {
        "id": "doc_123",
        "url": "https://example.com/doc",
        "source": "linux-docs",
        "category": "system",
        "tags": ["linux", "kernel"],
    }
    comment = format_meta_comment(doc)
    assert "id: doc_123" in comment
    assert "url: https://example.com/doc" in comment
    assert "source: linux-docs" in comment
    assert "category: system" in comment
    assert "tags: linux,kernel" in comment
    assert comment.startswith("<!-- ") and comment.endswith(" -->")


def test_format_doc_to_markdown():
    doc = {
        "id": "man_ls",
        "title": "ls(1)",
        "content": "List directory contents.",
        "source": "man-pages",
        "category": "commands",
        "tags": ["posix", "files"],
    }
    md = format_doc_to_markdown(doc)
    assert md.startswith("## ls(1)\n")
    assert "<!-- id: man_ls" in md
    assert "List directory contents." in md


def test_convert_jsonl_file_splitting(tmp_path: Path):
    jsonl_file = tmp_path / "sample.jsonl"
    out_dir = tmp_path / "output"

    # Create 10 dummy docs
    docs = []
    for i in range(10):
        docs.append({
            "id": f"doc_{i}",
            "title": f"Doc {i}",
            "content": f"Content for doc {i} with sufficient text length to test splitting behavior.",
            "source": "test-source",
            "category": "test",
            "tags": ["test"],
        })

    with open(jsonl_file, "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d) + "\n")

    # Split with max 3 docs per file
    created = convert_jsonl_file(jsonl_file, out_dir, max_docs_per_file=3, max_bytes_per_file=100_000)
    assert len(created) == 4  # 3 + 3 + 3 + 1 = 10 docs across 4 files

    # Verify each file has proper headers and H2 counts
    total_h2 = 0
    for cf in created:
        content = cf.read_text(encoding="utf-8")
        assert content.startswith("# Source: test-source (Part ")
        total_h2 += content.count("## Doc ")

    assert total_h2 == 10


def test_convert_corpus(tmp_path: Path):
    data_dir = tmp_path / "data"
    staging_dir = tmp_path / "staging"

    (data_dir / "linux" / "src1").mkdir(parents=True)
    (data_dir / "macos" / "src2").mkdir(parents=True)

    d1 = {"id": "1", "title": "Linux Doc", "content": "Linux text", "source": "linux", "category": "os", "tags": []}
    d2 = {"id": "2", "title": "Mac Doc", "content": "Mac text", "source": "macos", "category": "os", "tags": []}

    (data_dir / "linux" / "src1" / "doc.jsonl").write_text(json.dumps(d1) + "\n")
    (data_dir / "macos" / "src2" / "doc.jsonl").write_text(json.dumps(d2) + "\n")

    res = convert_corpus(data_dir, staging_dir)
    assert res["jsonl_sources_processed"] == 2
    assert res["total_documents_converted"] == 2
    assert res["markdown_files_generated"] == 2

    assert (staging_dir / "linux" / "src1" / "doc_01.md").exists()
    assert (staging_dir / "macos" / "src2" / "doc_01.md").exists()


def test_chunk_large_doc_under_limit():
    """Docs under the byte limit should return a single section."""
    doc = {"id": "1", "title": "Small", "content": "Hello world.", "source": "s", "category": "c", "tags": []}
    sections = chunk_large_doc(doc, max_bytes=500_000)
    assert len(sections) == 1
    assert "Hello world." in sections[0]


def test_chunk_large_doc_over_limit():
    """Docs over the byte limit should be split into multiple sections."""
    # Create content that exceeds 1000 bytes
    big_content = "\n\n".join(f"Paragraph {i}. " + "x" * 200 for i in range(20))
    doc = {
        "id": "big1",
        "title": "Big Doc",
        "content": big_content,
        "source": "test",
        "category": "c",
        "tags": [],
    }
    sections = chunk_large_doc(doc, max_bytes=1000)
    assert len(sections) > 1
    # Each section should be under the limit
    for s in sections:
        assert len(s.encode("utf-8")) <= 1000
    # First section keeps original heading
    assert sections[0].startswith("## Big Doc\n")
    # Subsequent sections get continuation suffix
    assert "(continued, part 2)" in sections[1]


def test_chunk_large_doc_preserves_metadata():
    """Each chunk should carry the metadata comment."""
    big_content = "\n\n".join(f"Paragraph {i}. " + "x" * 200 for i in range(20))
    doc = {
        "id": "big2",
        "title": "Big Doc",
        "content": big_content,
        "source": "test-src",
        "category": "cat",
        "tags": ["a", "b"],
    }
    sections = chunk_large_doc(doc, max_bytes=1000)
    for s in sections:
        assert "<!-- id: big2" in s
        assert "source: test-src" in s


def test_convert_jsonl_file_with_oversized_doc(tmp_path: Path):
    """A single oversized doc should produce multiple parts, each under the byte limit."""
    jsonl_file = tmp_path / "big.jsonl"
    out_dir = tmp_path / "output"

    big_content = "\n\n".join(f"Paragraph {i}. " + "x" * 200 for i in range(20))
    doc = {
        "id": "big3",
        "title": "Oversized",
        "content": big_content,
        "source": "test-source",
        "category": "test",
        "tags": ["test"],
    }
    with open(jsonl_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc) + "\n")

    created = convert_jsonl_file(jsonl_file, out_dir, max_docs_per_file=500, max_bytes_per_file=1000)
    assert len(created) > 1
    for cf in created:
        size = cf.stat().st_size
        assert size <= 1000 + 200  # small tolerance for header overhead
