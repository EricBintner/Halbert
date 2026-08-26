#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Download clean replacement datasets:
1. Arch Linux Wiki documentation (hannah-eee/arch-wiki-docs from HuggingFace)
2. TLDR pages (tldr-pages/tldr release from GitHub)

Converts both into the unified JSONL schema and partitions them into:
- data/linux/arch-wiki/arch_wiki.jsonl
- data/common/tldr/tldr.jsonl
- data/linux/tldr/tldr.jsonl
- data/macos/tldr/tldr.jsonl
- data/bsd/tldr/tldr.jsonl

Usage:
    python scripts/download_replacements.py [--data-dir data] [--verbose]
"""

import argparse
import io
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import requests
from huggingface_hub import hf_hub_download


def slugify(text: str) -> str:
    """Sanitize string for identifier, preserving symbols as words."""
    if not text:
        return "unnamed"
    text = str(text).lower()
    symbol_map = {
        "++": "_plusplus",
        "+": "_plus",
        "[": "_sym_lbracket",
        "]": "_sym_rbracket",
        "(": "_sym_lparen",
        ")": "_sym_rparen",
        "{": "_sym_lbrace",
        "}": "_sym_rbrace",
        "$": "_sym_dollar",
        "%": "_sym_percent",
        ",": "_sym_comma",
        "!": "_sym_exclamation",
        "^": "_sym_caret",
        "~": "_sym_tilde",
        "&": "_sym_amp",
        "=": "_sym_eq",
        ":": "_sym_colon",
        ";": "_sym_semicolon",
        "?": "_sym_question",
        "*": "_sym_star",
    }

    for sym, word in symbol_map.items():
        text = text.replace(sym, word)
    text = re.sub(r"[^\w\-_.]", "_", text)
    slug = re.sub(r"_+", "_", text).strip("_")
    return slug or "symbol_" + "_".join(str(ord(c)) for c in text)



def download_arch_wiki(output_file: Path, verbose: bool = False) -> int:
    """Download Arch Wiki docs from HuggingFace and convert English docs to JSONL."""
    print("Downloading Arch Wiki docs from HuggingFace (hannah-eee/arch-wiki-docs)...")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    hf_path = hf_hub_download(
        repo_id="hannah-eee/arch-wiki-docs",
        filename="arch_wiki.jsonl",
        repo_type="dataset",
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    count = 0

    with open(hf_path, "r", encoding="utf-8") as in_f, open(output_file, "w", encoding="utf-8") as out_f:
        for line in in_f:
            if not line.strip():
                continue
            doc = json.loads(line)
            lang = doc.get("lang", "")
            if lang != "en":
                continue

            title = doc.get("title", "").strip()
            content = doc.get("content", "").strip()
            if len(content) < 50:
                continue

            url_path = doc.get("url_path", "")
            headings = doc.get("headings", [])
            doc_id = f"arch_wiki_{slugify(title)}"
            url = f"https://wiki.archlinux.org/title/{url_path or title.replace(' ', '_')}"

            tag_list = ["arch", "linux", "wiki"]
            for h in headings[:5]:
                clean_h = slugify(re.sub(r"^#+\s*", "", h))
                if clean_h and clean_h not in tag_list:
                    tag_list.append(clean_h)

            record = {
                "id": doc_id,
                "url": url,
                "title": title,
                "content": content,
                "source": "arch-wiki",
                "category": "linux_wiki",
                "tags": tag_list,
                "scraped_at": now_iso,
                "metadata": {
                    "source_type": "arch_wiki",
                    "lang": "en",
                    "url_path": url_path,
                    "headings": headings,
                },
            }
            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

    print(f"Arch Wiki: saved {count} English documents to {output_file}")
    return count


def download_tldr_pages(data_dir: Path, verbose: bool = False) -> Dict[str, int]:
    """Download TLDR pages zip and partition into common, linux, macos, bsd."""
    print("Downloading TLDR pages from GitHub (tldr-pages/tldr release)...")
    url = "https://github.com/tldr-pages/tldr/releases/download/v2.3/tldr-pages.en.zip"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    zip_file = zipfile.ZipFile(io.BytesIO(resp.content))
    now_iso = datetime.now(timezone.utc).isoformat()

    partition_files = {
        "common": data_dir / "common" / "tldr" / "tldr.jsonl",
        "linux": data_dir / "linux" / "tldr" / "tldr.jsonl",
        "osx": data_dir / "macos" / "tldr" / "tldr.jsonl",
        "bsd": data_dir / "bsd" / "tldr" / "tldr.jsonl",
    }

    writers = {}
    counts = {"common": 0, "linux": 0, "osx": 0, "bsd": 0}

    for key, p in partition_files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        writers[key] = open(p, "w", encoding="utf-8")

    try:
        for fname in zip_file.namelist():
            if not fname.endswith(".md") or "/" not in fname:
                continue

            parts = fname.split("/", 1)
            folder = parts[0].lower()
            rel_name = parts[1]
            cmd_name = Path(rel_name).stem

            # Map folder to partition
            if folder == "common":
                target_key = "common"
                platform = "common"
            elif folder == "linux":
                target_key = "linux"
                platform = "linux"
            elif folder in ("osx", "macos"):
                target_key = "osx"
                platform = "macos"
            elif folder in ("freebsd", "openbsd", "netbsd"):
                target_key = "bsd"
                platform = "bsd"
            else:
                continue

            raw_bytes = zip_file.read(fname)
            content = raw_bytes.decode("utf-8", errors="replace").strip()
            if len(content) < 50:
                continue

            # Extract description summary from > lines
            desc_lines = []
            for line in content.splitlines():
                if line.startswith(">"):
                    desc_lines.append(line.lstrip("> ").strip())
            desc_summary = " ".join(desc_lines) if desc_lines else ""

            doc_id = f"tldr_{folder}_{slugify(cmd_name)}"
            url = f"https://tldr.sh/{platform}/{cmd_name}"


            record = {
                "id": doc_id,
                "url": url,
                "title": f"TLDR: {cmd_name}",
                "content": content,
                "source": "tldr-pages",
                "category": "command_reference",
                "tags": ["tldr", platform, cmd_name],
                "scraped_at": now_iso,
                "metadata": {
                    "source_type": "tldr",
                    "platform": platform,
                    "command": cmd_name,
                    "description": desc_summary,
                },
            }

            writers[target_key].write(json.dumps(record, ensure_ascii=False) + "\n")
            counts[target_key] += 1
    finally:
        for w in writers.values():
            w.close()

    print(f"TLDR pages partitioned: {counts}")
    return counts


def remove_old_hf_datasets(data_dir: Path, verbose: bool = False):
    """Remove old stale/empty hf-datasets directory."""
    old_dir = data_dir / "linux" / "hf-datasets"
    if old_dir.exists():
        for f in old_dir.glob("*.jsonl"):
            print(f"Removing old dataset file: {f}")
            f.unlink()
        if not any(old_dir.iterdir()):
            old_dir.rmdir()
            print(f"Removed empty directory: {old_dir}")


def main():
    parser = argparse.ArgumentParser(description="Download clean replacement datasets")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="Path to data directory")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()
    data_dir = args.data_dir.resolve()

    # 1. Download Arch Wiki
    arch_wiki_file = data_dir / "linux" / "arch-wiki" / "arch_wiki.jsonl"
    arch_count = download_arch_wiki(arch_wiki_file, verbose=args.verbose)

    # 2. Download TLDR Pages
    tldr_counts = download_tldr_pages(data_dir, verbose=args.verbose)

    # 3. Clean old hf-datasets
    remove_old_hf_datasets(data_dir, verbose=args.verbose)

    print("\nReplacement Datasets Download Complete:")
    print(f"- Arch Wiki: {arch_count} docs in {arch_wiki_file.relative_to(data_dir)}")
    print(f"- TLDR Common: {tldr_counts['common']} docs")
    print(f"- TLDR Linux: {tldr_counts['linux']} docs")
    print(f"- TLDR macOS: {tldr_counts['osx']} docs")
    print(f"- TLDR BSD: {tldr_counts['bsd']} docs")


if __name__ == "__main__":
    main()
