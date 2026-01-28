#!/usr/bin/env python3
"""
Arch Wiki Deduplication Script

Filters out non-English pages from the Arch Wiki scrape.
Non-English pages are identified by language suffixes in parentheses
like "(Español)", "(Русский)", "(简体中文)", etc.
"""

import json
import re
import sys
from pathlib import Path

# Language suffixes to filter out (translated pages)
LANGUAGE_SUFFIXES = [
    "Español", "Русский", "简体中文", "Português", "Italiano", 
    "日本語", "Magyar", "Česky", "Français", "Polski",
    "正體中文", "Українська", "Čeština", "العربية", "한국어",
    "Ελληνικά", "Српски", "Nederlands", "Türkçe", "Slovenský",
    "Indonesia", "Lietuviškai", "Dansk", "Tiếng Việt", "Català",
    "עברית", "Norsk Bokmål", "ไทย", "فارسی", "Suomi",
    "Български", "Slovenščina", "Esperanto", "Română", "繁體中文",
    "Azərbaycanca", "Hrvatski", "Монгол", "ქართული",
]

# Build regex pattern for language suffix detection
LANG_PATTERN = re.compile(
    r'\((' + '|'.join(re.escape(lang) for lang in LANGUAGE_SUFFIXES) + r')\)\s*$',
    re.IGNORECASE
)


def is_english_page(entry: dict) -> bool:
    """Check if a page is English (no language suffix in title)."""
    title = entry.get("title", "")
    page_title = entry.get("metadata", {}).get("page_title", title)
    
    # Check if title ends with a language suffix
    if LANG_PATTERN.search(page_title):
        return False
    if LANG_PATTERN.search(title):
        return False
    
    return True


def dedup_arch_wiki(input_path: Path, output_path: Path) -> dict:
    """
    Filter Arch Wiki JSONL to keep only English pages.
    
    Returns stats about the deduplication.
    """
    stats = {
        "total": 0,
        "english": 0,
        "filtered": 0,
        "languages_found": {},
    }
    
    with open(input_path, 'r', encoding='utf-8') as infile, \
         open(output_path, 'w', encoding='utf-8') as outfile:
        
        for line in infile:
            stats["total"] += 1
            
            try:
                entry = json.loads(line.strip())
            except json.JSONDecodeError:
                continue
            
            if is_english_page(entry):
                outfile.write(line)
                stats["english"] += 1
            else:
                stats["filtered"] += 1
                # Track which language was filtered
                title = entry.get("metadata", {}).get("page_title", entry.get("title", ""))
                match = LANG_PATTERN.search(title)
                if match:
                    lang = match.group(1)
                    stats["languages_found"][lang] = stats["languages_found"].get(lang, 0) + 1
    
    return stats


def main():
    repo_root = Path(__file__).parent.parent
    input_file = repo_root / "data" / "linux" / "arch-wiki-full" / "arch_wiki.jsonl"
    output_file = repo_root / "data" / "linux" / "arch-wiki-full" / "arch_wiki_english.jsonl"
    
    if not input_file.exists():
        print(f"Error: Input file not found: {input_file}")
        sys.exit(1)
    
    print(f"Input:  {input_file}")
    print(f"Output: {output_file}")
    print("Processing...")
    
    stats = dedup_arch_wiki(input_file, output_file)
    
    print(f"\n=== Deduplication Complete ===")
    print(f"Total entries:    {stats['total']:,}")
    print(f"English kept:     {stats['english']:,}")
    print(f"Non-English:      {stats['filtered']:,}")
    print(f"Reduction:        {stats['filtered'] / stats['total'] * 100:.1f}%")
    
    if stats["languages_found"]:
        print(f"\nFiltered languages (top 10):")
        sorted_langs = sorted(stats["languages_found"].items(), key=lambda x: -x[1])
        for lang, count in sorted_langs[:10]:
            print(f"  {lang}: {count:,}")
    
    # Calculate file sizes
    input_size = input_file.stat().st_size / (1024 * 1024)
    output_size = output_file.stat().st_size / (1024 * 1024)
    print(f"\nFile sizes:")
    print(f"  Input:  {input_size:.1f} MB")
    print(f"  Output: {output_size:.1f} MB")
    print(f"  Saved:  {input_size - output_size:.1f} MB ({(1 - output_size/input_size) * 100:.1f}%)")


if __name__ == "__main__":
    main()
