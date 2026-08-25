"""
JSONL to Grouped Markdown Converter for SourcePrep.

Transforms canonical JSONL records into grouped Markdown files with H2 headings
per document and HTML comment metadata headers. Large files are split (e.g. max 500 docs
or 500KB per file) to prevent SourcePrep's large-file truncation at 8000 characters.

Part of Phase 0 RAG Corpus implementation (T0d.1).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..utils.paths import data_subdir

logger = logging.getLogger("halbert.rag.jsonl_to_markdown")

# T-H1.1: unified SourcePrep knowledge corpus root. convert_corpus mirrors
# the data/{linux,macos,bsd,common} hierarchy under staging_dir, so the
# default output lands at sourceprep/knowledge/{linux,macos,bsd,common}/.
DEFAULT_STAGING_DIR = Path(data_subdir("sourceprep", "knowledge"))

DEFAULT_MAX_DOCS = 500
DEFAULT_MAX_BYTES = 500_000  # 500 KB threshold


def sanitize_heading(text: str) -> str:
    """Sanitize title for Markdown H2 heading."""
    text = re.sub(r"[\r\n]+", " ", str(text)).strip()
    # Strip any leading '#' to avoid header confusion
    text = re.sub(r"^#+\s*", "", text).strip()
    return text or "Untitled Document"


def format_meta_comment(doc: Dict[str, Any]) -> str:
    """Format document metadata into a structured HTML comment line."""
    doc_id = doc.get("id", "")
    url = doc.get("url", "")
    source = doc.get("source", "")
    category = doc.get("category", "")
    tags = doc.get("tags", [])
    if isinstance(tags, list):
        tags_str = ",".join(str(t) for t in tags)
    else:
        tags_str = str(tags)

    parts = [
        f"id: {doc_id}",
        f"url: {url}",
        f"source: {source}",
        f"category: {category}",
        f"tags: {tags_str}",
    ]
    return f"<!-- { ' | '.join(parts)} -->"


def format_doc_to_markdown(doc: Dict[str, Any]) -> str:
    """Format a single JSONL document into an H2 markdown section."""
    title = sanitize_heading(doc.get("title", "Untitled"))
    meta_line = format_meta_comment(doc)
    content = str(doc.get("content", "")).strip()

    return f"## {title}\n{meta_line}\n\n{content}\n\n"


def chunk_large_doc(doc: Dict[str, Any], max_bytes: int) -> List[str]:
    """Split an oversized document into multiple markdown sections.

    If the document's markdown fits within *max_bytes*, a single-element list
    is returned (identical to ``format_doc_to_markdown``).

    Otherwise the content is split at paragraph boundaries (double newlines).
    Each resulting section carries the same metadata header and an H2 heading
    suffixed with ``(continued, part N)`` so SourcePrep's 8000-char truncation
    does not clip the tail.  Paragraphs that individually exceed *max_bytes*
    are further split at line boundaries.
    """
    doc_md = format_doc_to_markdown(doc)
    if len(doc_md.encode("utf-8")) <= max_bytes:
        return [doc_md]

    title = sanitize_heading(doc.get("title", "Untitled"))
    meta_line = format_meta_comment(doc)
    content = str(doc.get("content", "")).strip()

    header = f"## {title}\n{meta_line}\n\n"
    header_bytes = len(header.encode("utf-8"))

    # Split into paragraphs, then further split oversized paragraphs at line breaks
    paragraphs: List[str] = []
    for para in re.split(r"\n\s*\n", content):
        if len(para.encode("utf-8")) + header_bytes <= max_bytes:
            paragraphs.append(para)
        else:
            # Paragraph itself too large — split at line boundaries
            for line in para.split("\n"):
                paragraphs.append(line)

    sections: List[str] = []
    current: List[str] = []
    current_bytes = header_bytes

    for para in paragraphs:
        chunk = para + "\n\n"
        chunk_bytes = len(chunk.encode("utf-8"))
        if current and current_bytes + chunk_bytes > max_bytes:
            sections.append(header + "".join(current))
            current = []
            current_bytes = header_bytes
        current.append(chunk)
        current_bytes += chunk_bytes

    if current:
        sections.append(header + "".join(current))

    # Rename headings: first keeps original, rest get "(continued, part N)"
    if len(sections) > 1:
        for i in range(1, len(sections)):
            old_heading = f"## {title}\n"
            new_heading = f"## {title} (continued, part {i + 1})\n"
            sections[i] = sections[i].replace(old_heading, new_heading, 1)

    return sections


def convert_jsonl_file(
    jsonl_path: Path,
    output_dir: Path,
    max_docs_per_file: int = DEFAULT_MAX_DOCS,
    max_bytes_per_file: int = DEFAULT_MAX_BYTES,
) -> List[Path]:
    """
    Convert a single JSONL file into one or more grouped Markdown files.
    Splits when doc count exceeds max_docs_per_file OR cumulative bytes exceed max_bytes_per_file.
    
    Returns list of generated markdown file paths.
    """
    if not jsonl_path.exists():
        return []

    docs: List[Dict[str, Any]] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                docs.append(json.loads(line))
            except Exception as e:
                logger.warning(f"Skipping malformed line in {jsonl_path}: {e}")

    if not docs:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    stem_name = jsonl_path.stem
    source_name = docs[0].get("source", stem_name)

    created_files: List[Path] = []
    part_num = 1
    current_docs = 0
    current_bytes = 0
    current_buffer: List[str] = []

    def flush_part():
        nonlocal part_num, current_docs, current_bytes, current_buffer
        if not current_buffer:
            return

        # Determine filename: stem_01.md if multiple parts or stem.md if single part
        # To ensure consistency for split sources, use 2-digit padding if multiple parts
        suffix = f"_{part_num:02d}.md"
        out_file = output_dir / f"{stem_name}{suffix}"

        header = f"# Source: {source_name} (Part {part_num})\n\n"
        full_content = header + "".join(current_buffer)

        with open(out_file, "w", encoding="utf-8") as out_f:
            out_f.write(full_content)

        created_files.append(out_file)
        part_num += 1
        current_docs = 0
        current_bytes = 0
        current_buffer = []

    for doc in docs:
        # Split oversized docs into multiple sections that each fit within max_bytes
        doc_sections = chunk_large_doc(doc, max_bytes_per_file)

        for doc_md in doc_sections:
            doc_size = len(doc_md.encode("utf-8"))

            # Check if adding this section would exceed limits
            if current_docs > 0 and (
                (current_docs + 1 > max_docs_per_file) or (current_bytes + doc_size > max_bytes_per_file)
            ):
                flush_part()

            current_buffer.append(doc_md)
            current_docs += 1
            current_bytes += doc_size

    # Flush remaining
    flush_part()

    # If only 1 part was created and stem_01.md exists, rename to stem.md if desired or keep numbered
    # Numbered is safer for uniform indexing
    return created_files


def convert_corpus(
    data_dir: Path,
    staging_dir: Path,
    max_docs_per_file: int = DEFAULT_MAX_DOCS,
    max_bytes_per_file: int = DEFAULT_MAX_BYTES,
) -> Dict[str, Any]:
    """
    Convert the entire JSONL corpus into grouped Markdown files in staging_dir.
    Mirrors the data/{linux,macos,bsd,common} directory hierarchy.
    """
    data_dir = data_dir.resolve()
    staging_dir = staging_dir.resolve()

    jsonl_files = sorted(list(data_dir.rglob("*.jsonl")))
    jsonl_files = [f for f in jsonl_files if "staging" not in f.parts]

    total_jsonl_files = len(jsonl_files)
    total_docs = 0
    total_md_files = 0
    output_files: List[Path] = []

    for jpath in jsonl_files:
        rel_parent = jpath.relative_to(data_dir).parent
        target_dir = staging_dir / rel_parent
        created = convert_jsonl_file(
            jpath,
            target_dir,
            max_docs_per_file=max_docs_per_file,
            max_bytes_per_file=max_bytes_per_file,
        )
        total_md_files += len(created)
        output_files.extend(created)

        # Count docs in jpath
        with open(jpath, "r", encoding="utf-8") as f:
            total_docs += sum(1 for line in f if line.strip())

    return {
        "jsonl_sources_processed": total_jsonl_files,
        "total_documents_converted": total_docs,
        "markdown_files_generated": total_md_files,
        "output_directory": str(staging_dir),
        "files": [str(p.relative_to(staging_dir)) for p in output_files],
    }


def main():
    parser = argparse.ArgumentParser(description="Convert JSONL corpus to grouped Markdown for SourcePrep")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="Path to input data directory")
    parser.add_argument(
        "--staging-dir",
        type=Path,
        default=DEFAULT_STAGING_DIR,
        help="Path to staging output directory (default: the unified "
             "~/.local/share/halbert/sourceprep/knowledge/ root; convert_corpus "
             "mirrors the per-platform data subdirs under it)",
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        default=DEFAULT_MAX_DOCS,
        help=f"Max documents per Markdown file (default: {DEFAULT_MAX_DOCS})",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        help=f"Max bytes per Markdown file (default: {DEFAULT_MAX_BYTES})",
    )

    args = parser.parse_args()

    print(f"Converting JSONL corpus from {args.data_dir} to {args.staging_dir}...")
    res = convert_corpus(
        args.data_dir,
        args.staging_dir,
        max_docs_per_file=args.max_docs,
        max_bytes_per_file=args.max_bytes,
    )

    print("\n--- Markdown Conversion Complete ---")
    print(f"JSONL sources processed:  {res['jsonl_sources_processed']}")
    print(f"Documents converted:      {res['total_documents_converted']}")
    print(f"Markdown files generated: {res['markdown_files_generated']}")
    print(f"Output directory:         {res['output_directory']}")


if __name__ == "__main__":
    main()
