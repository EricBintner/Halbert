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
    """Create a README.md dataset card for HuggingFace."""
    return f"""---
license: other
license_name: mixed
license_link: LICENSE
task_categories:
  - text-generation
  - question-answering
language:
  - en
tags:
  - linux
  - system-administration
  - documentation
  - rag
  - knowledge-base
size_categories:
  - 10K<n<100K
---

# Halbert Linux RAG Corpus

A curated knowledge base for Linux system administration, designed for RAG (Retrieval-Augmented Generation) applications.

## Version

- **Version**: {manifest.get('version', 'unknown')}
- **Release Date**: {manifest.get('release_date', 'unknown')}
- **Total Documents**: {manifest.get('total_documents', 0):,}

## Contents

| Source | Documents | License | Description |
|--------|-----------|---------|-------------|
"""
    # Add source table rows
    card = create_dataset_card.__doc__  # Placeholder, we'll build it properly
    
    sources_table = ""
    for source_name, source_info in manifest.get("sources", {}).items():
        doc_count = source_info.get("document_count", 0)
        license_type = source_info.get("license", "Unknown")
        description = source_info.get("description", "")
        sources_table += f"| {source_name} | {doc_count:,} | {license_type} | {description} |\n"
    
    return f"""---
license: other
license_name: mixed
license_link: LICENSE
task_categories:
  - text-generation
  - question-answering
language:
  - en
tags:
  - linux
  - system-administration
  - documentation
  - rag
  - knowledge-base
size_categories:
  - 10K<n<100K
---

# Halbert Linux RAG Corpus

A curated knowledge base for Linux system administration, designed for RAG (Retrieval-Augmented Generation) applications.

## Version

- **Version**: {manifest.get('version', 'unknown')}
- **Release Date**: {manifest.get('release_date', 'unknown')}
- **Total Documents**: {manifest.get('total_documents', 0):,}

## Contents

| Source | Documents | License | Description |
|--------|-----------|---------|-------------|
{sources_table}

## Usage

```python
from datasets import load_dataset

# Load the full dataset
dataset = load_dataset("{repo_name}")

# Or load specific files
dataset = load_dataset("{repo_name}", data_files="linux/merged/*.jsonl")
```

## Document Format

Each document is a JSON object with:

```json
{{
  "id": "unique_document_id",
  "title": "Document Title",
  "content": "Full document content...",
  "source": "source_name",
  "url": "https://original.source/url",
  "scraped_at": "2025-12-01T00:00:00",
  "metadata": {{
    "category": "system_admin",
    "tags": ["systemd", "services"]
  }}
}}
```

## Licensing

This dataset contains content under various licenses:

- **GNU FDL 1.3**: Arch Wiki content (arch-wiki-full, arch-wiki-ext)
- **CC BY 4.0**: TLDR pages
- **CC BY-SA 4.0**: Stack Exchange content (requires attribution)
- **Apache 2.0**: Various vendor documentation
- **BSD/MIT**: Man pages and utilities documentation

**For commercial use**: Exclude GNU FDL content. See `manifest.json` for `mac_build: false` sources.

## Attribution

When using Stack Exchange content, attribution is required per CC BY-SA 4.0.

## Updates

Check `manifest.json` for version info. The Halbert app can check for updates automatically.

## Related

- [Halbert](https://github.com/EricBintworksGit/LinuxBrain) - The AI assistant that uses this corpus
- [Documentation](https://github.com/EricBintworksGit/LinuxBrain/tree/main/docs)
"""


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
