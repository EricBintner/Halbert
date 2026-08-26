#!/usr/bin/env python3
"""
Upload RAG corpus to HuggingFace as a versioned dataset.

Usage:
    python scripts/upload_hf_dataset.py --version 1.0.0 --repo halbert/linux-rag

Requirements:
    pip install huggingface_hub

Environment:
    HF_TOKEN - HuggingFace API token with write access
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime


def check_dependencies():
    """Check if required dependencies are installed."""
    try:
        from huggingface_hub import HfApi, create_repo
        return True
    except ImportError:
        print("Error: huggingface_hub not installed")
        print("Run: pip install huggingface_hub")
        return False


def load_manifest(data_dir: Path) -> dict:
    """Load the data manifest."""
    manifest_path = data_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"Error: No manifest.json found at {manifest_path}")
        print("Run the data versioning first to create a manifest.")
        sys.exit(1)
    
    with open(manifest_path) as f:
        return json.load(f)


def update_manifest_for_release(manifest: dict, version: str, repo_url: str) -> dict:
    """Update manifest with release info."""
    manifest["version"] = version
    manifest["release_date"] = datetime.now().strftime("%Y-%m-%d")
    manifest["remote_url"] = repo_url
    manifest["check_updates_url"] = f"https://huggingface.co/api/datasets/{repo_url.split('/')[-2]}/{repo_url.split('/')[-1]}"
    return manifest


def get_files_to_upload(data_dir: Path, include_arch_wiki: bool = True) -> list:
    """
    Get list of files to upload.
    
    Args:
        data_dir: Path to data directory
        include_arch_wiki: Whether to include GNU FDL Arch Wiki content
        
    Returns:
        List of (local_path, repo_path) tuples
    """
    files = []
    
    # Always include manifest
    manifest_path = data_dir / "manifest.json"
    if manifest_path.exists():
        files.append((manifest_path, "manifest.json"))
    
    # Include merged corpus (main RAG file)
    merged_dir = data_dir / "linux" / "merged"
    if merged_dir.exists():
        for f in merged_dir.glob("*.jsonl"):
            files.append((f, f"linux/merged/{f.name}"))
    
    # Include HF datasets (permissive licenses)
    hf_dir = data_dir / "linux" / "hf-datasets"
    if hf_dir.exists():
        for f in hf_dir.glob("*.jsonl"):
            # Skip arch_wiki if not including
            if not include_arch_wiki and "arch_wiki" in f.name:
                continue
            files.append((f, f"linux/hf-datasets/{f.name}"))
    
    # Include man pages
    man_dir = data_dir / "linux" / "man-pages"
    if man_dir.exists():
        for f in man_dir.glob("*.jsonl"):
            files.append((f, f"linux/man-pages/{f.name}"))
    
    # Include vendor docs
    vendor_dirs = [
        "vendor-docs", "docker-docs", "kubernetes-docs", "systemd-docs",
        "nvidia-docs", "podman-docs", "ubuntu-docs", "ubuntu-server"
    ]
    for vdir in vendor_dirs:
        vpath = data_dir / "linux" / vdir
        if vpath.exists():
            for f in vpath.glob("*.jsonl"):
                files.append((f, f"linux/{vdir}/{f.name}"))
    
    # Include topic guides
    topic_dirs = [
        "network-docs", "security-docs", "backup-docs", "filesystem-docs",
        "monitoring-docs", "logging-docs", "automation-docs", "shell-docs"
    ]
    for tdir in topic_dirs:
        tpath = data_dir / "linux" / tdir
        if tpath.exists():
            for f in tpath.glob("*.jsonl"):
                files.append((f, f"linux/{tdir}/{f.name}"))
    
    # Include Stack Exchange (with attribution note)
    se_dirs = ["unix-se", "serverfault"]
    for sedir in se_dirs:
        sepath = data_dir / "linux" / sedir
        if sepath.exists():
            for f in sepath.glob("*.jsonl"):
                files.append((f, f"linux/{sedir}/{f.name}"))
    
    # Optionally include Arch Wiki (GNU FDL)
    if include_arch_wiki:
        arch_dirs = ["arch-wiki-full", "arch-wiki-ext", "more-arch"]
        for adir in arch_dirs:
            apath = data_dir / "linux" / adir
            if apath.exists():
                for f in apath.glob("*.jsonl"):
                    files.append((f, f"linux/{adir}/{f.name}"))
    
    # Include macOS data
    macos_dirs = ["homebrew", "support"]
    for mdir in macos_dirs:
        mpath = data_dir / "macos" / mdir
        if mpath.exists():
            for f in mpath.glob("*.jsonl"):
                files.append((f, f"macos/{mdir}/{f.name}"))
    
    return files


def create_dataset_card(manifest: dict, repo_name: str) -> str:
    """Create a README.md dataset card for HuggingFace.

    Generates a license-compliant card with:
      - proper `license:` YAML tags derived from the manifest sources
      - per-source attribution table with upstream URLs and license links
      - origin URL and author acknowledgments
      - commercial-use exclusion notes for copyleft / non-commercial sources

    The card targets the dataset named by `repo_name`. The dataset's bucket
    (linux / macos / eval) is inferred from the repo slug.
    """
    bucket = _infer_bucket(repo_name)
    bucket_sources = _filter_sources_by_bucket(manifest, bucket)

    license_tags = _license_yaml_tags(bucket_sources)
    total_docs = sum(s.get("document_count", 0) for s in bucket_sources.values())
    size_cat = _size_category(total_docs)

    sources_table = _sources_attribution_table(bucket_sources)

    return f"""---
{license_tags}
task_categories:
  - text-generation
  - question-answering
language:
  - en
tags:
  - system-administration
  - documentation
  - rag
  - knowledge-base
  - {bucket}
size_categories:
  - {size_cat}
---

# Halbert {bucket.title()} RAG Corpus

A curated knowledge base for {bucket} system administration, designed for
RAG (Retrieval-Augmented Generation) applications. Part of the Halbert
project's published corpus alongside `halbert-rag-linux`,
`halbert-rag-macos`, and `halbert-rag-eval`.

## Version

- **Version**: {manifest.get('version', 'unknown')}
- **Release Date**: {manifest.get('release_date', 'unknown')}
- **Documents in this dataset**: {total_docs:,}
- **Total corpus documents**: {manifest.get('total_documents', 0):,}

## Contents

| Source | Documents | License | Upstream | Attribution required |
|--------|-----------|---------|----------|----------------------|
{sources_table}

## Document Format

Each document is a JSON object with the unified Halbert schema:

```json
{{
  "id": "unique_document_id",
  "title": "Document Title",
  "content": "Full document content...",
  "source": "source_name",
  "url": "https://original.source/url",
  "scraped_at": "2026-08-23T00:00:00",
  "metadata": {{
    "category": "system_admin",
    "tags": ["systemd", "services"],
    "author": "upstream author display name (where applicable)"
  }}
}}
```

The `url` field preserves the origin URL for every record so downstream
users can satisfy attribution requirements by linking back to the source.
The `metadata.author` field is populated for Stack Exchange content and
other sources where per-record authorship is required by the upstream
license.

## Licensing

This dataset is **mixed-license**. Each record's source carries the
license listed in the table above. The dataset as a whole is distributed
under the terms of its most restrictive included license.

**Commercial use notes:**

- **GNU FDL 1.3** content (Arch Wiki) is copyleft and excluded from
  Halbert's macOS commercial builds. See `manifest.json` `mac_build: false`.
- **CC BY-NC 4.0** content (SS64) is non-commercial only and **must not**
  be included in any commercial redistribution. See the
  `data/non-commercial/` quarantine in the Halbert repo.
- **CC BY-SA 4.0** content (Ask Different, Linux system docs slice)
  requires attribution **and** share-alike of any derivative.
- All other included licenses are permissive (BSD, MIT, Apache 2.0,
  CC BY 4.0, FreeBSD Documentation License) and require attribution.

See `THIRD-PARTY-LICENSES.md` in the Halbert repository for the full
per-source license texts and attribution statements.

## Attribution

When redistributing this dataset or any derivative, you must:

1. Preserve the `url` and `metadata.author` fields on every record.
2. Include the per-source attribution statements from
   `THIRD-PARTY-LICENSES.md`.
3. For CC BY-SA 4.0 content, link to the original question, link to the
   author profile, and list the author display name (per Stack Exchange's
   CC BY-SA 4.0 attribution policy).
4. For CC BY-NC 4.0 content, do not use the content for any commercial
   purpose.

## Updates

Check `manifest.json` for version info. The Halbert app checks for updates
automatically via the `check_updates_url` field. Update cadence: monthly.

## Related

- [Halbert](https://github.com/EricBintner/Halbert) - The AI assistant that uses this corpus
- [Legal hub](https://github.com/EricBintner/Halbert/tree/main/documentation/legal) - Licenses, privacy, trademarks, disclaimer
- [RAG data sources reference](https://github.com/EricBintner/Halbert/blob/main/documentation/RAG-DATA-SOURCES-2026-08-24.md)
"""


# ── Dataset card helpers ─────────────────────────────────────────────

# Map manifest source names to (bucket, upstream URL, license SPDX-ish tag,
# attribution-required flag). Used by the card generator.
SOURCE_REGISTRY = {
    "arch_wiki":            ("linux",  "https://wiki.archlinux.org/",                       "GNU FDL 1.3",                True),
    "linux_man_pages":      ("linux",  "https://www.kernel.org/doc/man-pages/",             "Various (GPL, BSD, MIT)",    True),
    "tldr_pages":           ("common", "https://tldr.sh/",                                  "CC BY 4.0",                  True),
    "common_tools":         ("common", "https://github.com/ (per-project)",                 "Various (permissive)",       True),
    "linux_system_docs":    ("linux",  "https://www.freedesktop.org/ (per-project)",        "Various (permissive, CC BY-SA)", True),
    "vendor_and_distro_docs": ("linux","https://www.docker.com/ , https://kubernetes.io/",  "Various (permissive)",       True),
    "macos_homebrew":       ("macos",  "https://docs.brew.sh/",                             "BSD-2-Clause",               True),
    "macos_man_pages":      ("macos",  "macOS system /usr/share/man/",                      "Various (BSD, APSL 2.0)",    True),
    "macos_support":        ("macos",  "https://ss64.com/mac/",                             "CC BY-NC 4.0 (SS64), Halbert (synthetic)", True),
    "macos_ask_different":  ("macos",  "https://apple.stackexchange.com/",                  "CC BY-SA 4.0",               True),
    "macos_macports_guide": ("macos",  "https://guide.macports.org/",                       "BSD-like (MacPorts)",        True),
    "freebsd_handbook":     ("bsd",    "https://docs.freebsd.org/en/books/handbook/",       "FreeBSD Documentation License", True),
    "freebsd_man_pages":    ("bsd",    "https://www.freebsd.org/cgi/man.cgi",               "FreeBSD Documentation License", True),
}

# Buckets included in each published dataset.
BUCKET_MEMBERSHIP = {
    "linux":  {"linux", "common"},
    "macos":  {"macos", "bsd"},
    "eval":   set(),  # eval is a separate small dataset, no corpus sources
}


def _infer_bucket(repo_name: str) -> str:
    """Infer the dataset bucket from the repo slug."""
    slug = repo_name.lower()
    if "eval" in slug:
        return "eval"
    if "macos" in slug or "mac" in slug:
        return "macos"
    return "linux"


def _filter_sources_by_bucket(manifest: dict, bucket: str) -> dict:
    """Return only the manifest sources that belong to the given dataset bucket."""
    if bucket == "eval":
        return {}
    members = BUCKET_MEMBERSHIP.get(bucket, set())
    out = {}
    for name, info in manifest.get("sources", {}).items():
        reg = SOURCE_REGISTRY.get(name)
        src_bucket = reg[0] if reg else "common"
        if src_bucket in members:
            out[name] = info
    return out


def _license_yaml_tags(bucket_sources: dict) -> str:
    """Build the `license:` YAML block for the dataset card.

    HuggingFace supports a list of license identifiers. We emit the most
    restrictive applicable tag plus a `license_name`/`license_link` pair for
    the mixed-license case.
    """
    # Collect SPDX-ish tags present in this bucket
    tags = set()
    for name in bucket_sources:
        reg = SOURCE_REGISTRY.get(name)
        if not reg:
            continue
        lic = reg[2]
        if "GNU FDL" in lic:
            tags.add("GFDL-1.3-no-invariants-only")
        if "CC BY-NC" in lic:
            tags.add("CC-BY-NC-4.0")
        if "CC BY-SA" in lic:
            tags.add("CC-BY-SA-4.0")
        if "CC BY 4.0" in lic:
            tags.add("CC-BY-4.0")
        if "BSD-2" in lic:
            tags.add("BSD-2-Clause")
        if "BSD-3" in lic:
            tags.add("BSD-3-Clause")
        if "APSL" in lic:
            tags.add("APSL-2.0")
        if "Apache" in lic:
            tags.add("Apache-2.0")
        if "MIT" in lic:
            tags.add("MIT")
        if "FreeBSD Documentation" in lic:
            tags.add("other")
    if not tags:
        tags.add("other")
    # 'other' covers the FreeBSD Documentation License and "Various" buckets
    lines = ["license:"]
    for t in sorted(tags):
        lines.append(f"  - {t}")
    lines.append("license_name: mixed (see THIRD-PARTY-LICENSES.md)")
    lines.append("license_link: https://github.com/EricBintner/Halbert/blob/main/documentation/legal/THIRD-PARTY-LICENSES.md")
    return "\n".join(lines)


def _size_category(total_docs: int) -> str:
    if total_docs < 1000:
        return "n<1K"
    if total_docs < 10000:
        return "1K<n<10K"
    if total_docs < 100000:
        return "10K<n<100K"
    return "100K<n<1M"


def _sources_attribution_table(bucket_sources: dict) -> str:
    """Render the per-source attribution markdown table rows."""
    rows = []
    for name, info in bucket_sources.items():
        reg = SOURCE_REGISTRY.get(name)
        upstream = reg[1] if reg else ""
        lic = info.get("license", "Unknown") if reg is None else reg[2]
        attr = "Yes" if (reg and reg[3]) else "Per-source"
        docs = info.get("document_count", 0)
        rows.append(f"| {name} | {docs:,} | {lic} | {upstream} | {attr} |")
    return "\n".join(rows) if rows else "| (eval dataset — no corpus sources) | - | - | - | - |"


def upload_to_huggingface(
    data_dir: Path,
    repo_name: str,
    version: str,
    include_arch_wiki: bool = True,
    dry_run: bool = False
):
    """
    Upload dataset to HuggingFace.
    
    Args:
        data_dir: Path to data directory
        repo_name: HuggingFace repo name (e.g., "halbert/linux-rag")
        version: Version string (e.g., "1.0.0")
        include_arch_wiki: Whether to include GNU FDL content
        dry_run: If True, only show what would be uploaded
    """
    from huggingface_hub import HfApi, create_repo
    
    # Load and update manifest
    manifest = load_manifest(data_dir)
    repo_url = f"https://huggingface.co/datasets/{repo_name}"
    manifest = update_manifest_for_release(manifest, version, repo_url)
    
    # Get files to upload
    files = get_files_to_upload(data_dir, include_arch_wiki)
    
    print(f"\n{'='*60}")
    print(f"Halbert RAG Dataset Upload")
    print(f"{'='*60}")
    print(f"Repository: {repo_name}")
    print(f"Version: {version}")
    print(f"Include Arch Wiki (GNU FDL): {include_arch_wiki}")
    print(f"Files to upload: {len(files)}")
    print(f"{'='*60}\n")
    
    # Calculate total size
    total_size = sum(f[0].stat().st_size for f in files if f[0].exists())
    print(f"Total upload size: {total_size / 1024 / 1024:.1f} MB\n")
    
    if dry_run:
        print("DRY RUN - Files that would be uploaded:")
        for local_path, repo_path in files:
            size_mb = local_path.stat().st_size / 1024 / 1024
            print(f"  {repo_path} ({size_mb:.2f} MB)")
        print("\nRun without --dry-run to actually upload.")
        return
    
    # Check for HF token
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("Error: HF_TOKEN environment variable not set")
        print("Get your token from: https://huggingface.co/settings/tokens")
        sys.exit(1)
    
    api = HfApi(token=token)
    
    # Create repo if it doesn't exist
    try:
        create_repo(repo_name, repo_type="dataset", exist_ok=True, token=token)
        print(f"Repository ready: {repo_url}")
    except Exception as e:
        print(f"Warning: Could not create repo: {e}")
    
    # Save updated manifest
    manifest_path = data_dir / "manifest.json"
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f"Updated manifest.json with version {version}")
    
    # Create and upload README
    readme_content = create_dataset_card(manifest, repo_name)
    readme_path = data_dir / "README_HF.md"
    with open(readme_path, 'w') as f:
        f.write(readme_content)
    
    # Upload files
    print("\nUploading files...")
    for i, (local_path, repo_path) in enumerate(files):
        if not local_path.exists():
            print(f"  Skipping (not found): {repo_path}")
            continue
        
        try:
            api.upload_file(
                path_or_fileobj=str(local_path),
                path_in_repo=repo_path,
                repo_id=repo_name,
                repo_type="dataset",
                commit_message=f"Upload {repo_path} (v{version})"
            )
            print(f"  [{i+1}/{len(files)}] {repo_path}")
        except Exception as e:
            print(f"  Error uploading {repo_path}: {e}")
    
    # Upload README
    try:
        api.upload_file(
            path_or_fileobj=str(readme_path),
            path_in_repo="README.md",
            repo_id=repo_name,
            repo_type="dataset",
            commit_message=f"Update README for v{version}"
        )
        print("  README.md")
    except Exception as e:
        print(f"  Error uploading README: {e}")
    
    print(f"\n{'='*60}")
    print(f"Upload complete!")
    print(f"Dataset URL: {repo_url}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="Upload Halbert RAG corpus to HuggingFace"
    )
    parser.add_argument(
        "--version", "-v",
        required=True,
        help="Version string (e.g., 1.0.0)"
    )
    parser.add_argument(
        "--repo", "-r",
        default="halbert/linux-rag",
        help="HuggingFace repo name (default: halbert/linux-rag)"
    )
    parser.add_argument(
        "--data-dir", "-d",
        default=None,
        help="Path to data directory (default: auto-detect)"
    )
    parser.add_argument(
        "--no-arch-wiki",
        action="store_true",
        help="Exclude GNU FDL Arch Wiki content"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be uploaded without actually uploading"
    )
    
    args = parser.parse_args()
    
    if not check_dependencies():
        sys.exit(1)
    
    # Find data directory
    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        # Auto-detect from script location
        script_dir = Path(__file__).parent
        data_dir = script_dir.parent / "data"
    
    if not data_dir.exists():
        print(f"Error: Data directory not found: {data_dir}")
        sys.exit(1)
    
    print(f"Data directory: {data_dir}")
    
    upload_to_huggingface(
        data_dir=data_dir,
        repo_name=args.repo,
        version=args.version,
        include_arch_wiki=not args.no_arch_wiki,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()
