# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Migrate self_knowledge_all from ChromaDB to SourcePrep observations.

Reads all records from the ChromaDB `self_knowledge_all` collection and
writes them to SourcePrep via the observations API. Each record becomes
a SourcePrep observation with category "note" and tags ["self_knowledge",
"migrated"].

Usage:
    python -m halbert_core.tools.migrate_self_knowledge           # dry run
    python -m halbert_core.tools.migrate_self_knowledge --apply   # write
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def read_chroma_records(collection_name: str = "self_knowledge_all") -> List[Dict[str, Any]]:
    """Read all records from a ChromaDB collection.

    Returns:
        List of dicts with 'id', 'content', and 'metadata' keys.
    """
    from ..index.chroma_index import get_index

    index = get_index()
    if index is None or index.client is None:
        logger.error("ChromaDB index not available")
        return []

    col = index._collection(collection_name)
    if col is None:
        logger.warning(f"Collection '{collection_name}' not found")
        return []

    try:
        result = col.get()
    except Exception as e:
        logger.error(f"Failed to read collection '{collection_name}': {e}")
        return []

    records = []
    ids = result.get("ids", [])
    documents = result.get("documents", [])
    metadatas = result.get("metadatas", [])

    for i, doc_id in enumerate(ids):
        content = documents[i] if i < len(documents) else ""
        metadata = metadatas[i] if i < len(metadatas) else {}
        if not content:
            continue
        records.append({
            "id": doc_id,
            "content": content,
            "metadata": metadata,
        })

    return records


def migrate_to_sourceprep(
    records: List[Dict[str, Any]],
    project_id: Optional[str] = None,
    dry_run: bool = True,
) -> Dict[str, int]:
    """Write records to SourcePrep observations.

    Args:
        records: List of record dicts from read_chroma_records.
        project_id: SourcePrep project ID. If None, uses client default.
        dry_run: If True, print what would be migrated without writing.

    Returns:
        Dict with 'success', 'failed', 'total' counts.
    """
    from ..integrations.sourceprep_client import SourcePrepClient

    client = SourcePrepClient(project_id=project_id)

    if not dry_run:
        if not client.health():
            logger.error("SourcePrep daemon not reachable — aborting migration")
            return {"success": 0, "failed": len(records), "total": len(records)}

    success = 0
    failed = 0

    for rec in records:
        content = rec["content"]
        metadata = rec["metadata"]
        file_path = metadata.get("source") or metadata.get("file_path")

        if dry_run:
            logger.info(
                f"[DRY RUN] Would migrate: id={rec['id']}, "
                f"content={content[:80]}..., source={file_path}"
            )
            success += 1
            continue

        try:
            client.save_observation(
                content=content,
                file_path=file_path,
                category="note",
                created_by="migration:self_knowledge",
                project_id=project_id,
            )
            success += 1
        except Exception as e:
            logger.warning(f"Failed to migrate record {rec['id']}: {e}")
            failed += 1

    return {"success": success, "failed": failed, "total": len(records)}


def main():
    parser = argparse.ArgumentParser(
        description="Migrate self_knowledge_all from ChromaDB to SourcePrep observations"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write to SourcePrep (default: dry run)",
    )
    parser.add_argument(
        "--project-id",
        default=None,
        help="SourcePrep project ID (default: from SOURCEPREP_PROJECT_ID env)",
    )
    parser.add_argument(
        "--collection",
        default="self_knowledge_all",
        help="ChromaDB collection to migrate (default: self_knowledge_all)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    logger.info(f"Reading records from ChromaDB collection '{args.collection}'...")
    records = read_chroma_records(args.collection)
    logger.info(f"Found {len(records)} records")

    if not records:
        print("No records to migrate.")
        sys.exit(0)

    logger.info(f"{'DRY RUN' if not args.apply else 'APPLYING'} migration to SourcePrep...")
    stats = migrate_to_sourceprep(records, project_id=args.project_id, dry_run=not args.apply)

    print(f"\nMigration complete:")
    print(f"  Total records:  {stats['total']}")
    print(f"  Success:        {stats['success']}")
    print(f"  Failed:         {stats['failed']}")

    if not args.apply:
        print(f"\n  (Dry run — no records were written. Use --apply to migrate.)")

    sys.exit(0 if stats["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
