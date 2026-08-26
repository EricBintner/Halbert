# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Migrate self_conversations from ChromaDB to the HybridMemorySystem.

Reads all records from the ChromaDB `self_conversations` collection and
writes them to Halbert's HybridMemorySystem as conversation-type memories.
Each record's metadata (conversation_id, timestamp, role, etc.) is preserved.

Usage:
    python -m halbert_core.tools.migrate_conversations           # dry run
    python -m halbert_core.tools.migrate_conversations --apply   # write
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def read_chroma_conversations(
    collection_name: str = "self_conversations",
) -> List[Dict[str, Any]]:
    """Read all records from the ChromaDB self_conversations collection.

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


async def migrate_to_memory(
    records: List[Dict[str, Any]],
    dry_run: bool = True,
) -> Dict[str, int]:
    """Write conversation records to the HybridMemorySystem.

    Args:
        records: List of record dicts from read_chroma_conversations.
        dry_run: If True, print what would be migrated without writing.

    Returns:
        Dict with 'success', 'failed', 'total' counts.
    """
    from ..memory.hybrid import HybridMemorySystem, MemoryType

    memory_system = HybridMemorySystem()

    success = 0
    failed = 0

    for rec in records:
        content = rec["content"]
        metadata = rec["metadata"]

        if dry_run:
            logger.info(
                f"[DRY RUN] Would migrate: id={rec['id']}, "
                f"content={content[:80]}..., "
                f"conversation_id={metadata.get('conversation_id', 'N/A')}"
            )
            success += 1
            continue

        try:
            await memory_system.store(
                content=content,
                memory_type=MemoryType.FACT,
                metadata={
                    **metadata,
                    "migrated_from": "chromadb:self_conversations",
                    "original_id": rec["id"],
                },
                importance=0.6,
            )
            success += 1
        except Exception as e:
            logger.warning(f"Failed to migrate record {rec['id']}: {e}")
            failed += 1

    return {"success": success, "failed": failed, "total": len(records)}


def main():
    parser = argparse.ArgumentParser(
        description="Migrate self_conversations from ChromaDB to HybridMemorySystem"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write to memory system (default: dry run)",
    )
    parser.add_argument(
        "--collection",
        default="self_conversations",
        help="ChromaDB collection to migrate (default: self_conversations)",
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
    records = read_chroma_conversations(args.collection)
    logger.info(f"Found {len(records)} records")

    if not records:
        print("No records to migrate.")
        sys.exit(0)

    logger.info(f"{'DRY RUN' if not args.apply else 'APPLYING'} migration to memory system...")
    stats = asyncio.run(migrate_to_memory(records, dry_run=not args.apply))

    print(f"\nMigration complete:")
    print(f"  Total records:  {stats['total']}")
    print(f"  Success:        {stats['success']}")
    print(f"  Failed:         {stats['failed']}")

    if not args.apply:
        print(f"\n  (Dry run — no records were written. Use --apply to migrate.)")

    sys.exit(0 if stats["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
