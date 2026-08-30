# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Speaker profile store — SQLite persistence for enrolled voiceprints.

Stores 256-dim CAM++ embedding centroids (1024 bytes per BLOB).
The sherpa-onnx ``SpeakerEmbeddingManager`` handles cosine similarity math;
this class handles persistence only.

Database location: ``data_subdir("audio") / "speaker_profiles.db"``
(same pattern as findings/store.py using utils.paths.data_subdir).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ...utils.paths import data_subdir

logger = logging.getLogger("halbert.audio.storage.speaker_store")


@dataclass
class SpeakerProfile:
    """An enrolled speaker profile."""
    speaker_id: str
    name: str
    role: str  # 'admin', 'member', 'guest', 'restricted'
    embedding_centroid: bytes  # 256-dim float32 (1024 bytes)
    sample_count: int = 1
    threshold: float = 0.75
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def embedding_dim(self) -> int:
        """Embedding dimensionality (256 for CAM++)."""
        return len(self.embedding_centroid) // 4  # float32 = 4 bytes

    def embedding_as_list(self) -> List[float]:
        """Unpack the centroid BLOB to a list of floats."""
        n = len(self.embedding_centroid) // 4
        return list(struct.unpack(f'<{n}f', self.embedding_centroid))


_SCHEMA = """
CREATE TABLE IF NOT EXISTS speaker_profiles (
    speaker_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'member', 'guest', 'restricted')),
    embedding_centroid BLOB NOT NULL,
    sample_count INTEGER DEFAULT 1,
    threshold REAL DEFAULT 0.75,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
"""


class SpeakerProfileStore:
    """SQLite store for enrolled household speaker voiceprints.

    Persists CAM++ 256-dim embedding centroids. The sherpa-onnx
    ``SpeakerEmbeddingManager`` does the cosine similarity math;
    this class handles persistence only.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = str(Path(data_subdir("audio")) / "speaker_profiles.db")
        self._db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Create the table if it doesn't exist."""
        with sqlite3.connect(self._db_path) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def _row_to_profile(self, row: sqlite3.Row) -> SpeakerProfile:
        return SpeakerProfile(
            speaker_id=row["speaker_id"],
            name=row["name"],
            role=row["role"],
            embedding_centroid=row["embedding_centroid"],
            sample_count=row["sample_count"],
            threshold=row["threshold"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def enroll(
        self,
        speaker_id: str,
        name: str,
        role: str,
        embedding: List[float],
        threshold: float = 0.75,
    ) -> SpeakerProfile:
        """Enroll a new speaker or update an existing one.

        Args:
            speaker_id: Unique ID for the speaker.
            name: Human-readable name.
            role: One of 'admin', 'member', 'guest', 'restricted'.
            embedding: 256-dim float list (CAM++ embedding centroid).
            threshold: Cosine similarity threshold for verification.

        Returns:
            The stored SpeakerProfile.
        """
        centroid_bytes = struct.pack(f'<{len(embedding)}f', *embedding)
        now = time.time()

        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO speaker_profiles
                   (speaker_id, name, role, embedding_centroid, sample_count,
                    threshold, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (speaker_id, name, role, centroid_bytes, 1, threshold, now, now),
            )
            conn.commit()

        logger.info(f"Enrolled speaker '{name}' ({speaker_id}, role={role})")
        return SpeakerProfile(
            speaker_id=speaker_id,
            name=name,
            role=role,
            embedding_centroid=centroid_bytes,
            threshold=threshold,
            created_at=now,
            updated_at=now,
        )

    def update_centroid(
        self,
        speaker_id: str,
        new_embedding: List[float],
        sample_count: int,
    ) -> bool:
        """Update the centroid for an existing speaker.

        Args:
            speaker_id: The speaker to update.
            new_embedding: New averaged centroid (256-dim float list).
            sample_count: Total number of samples enrolled so far.

        Returns:
            True if updated, False if speaker not found.
        """
        centroid_bytes = struct.pack(f'<{len(new_embedding)}f', *new_embedding)
        now = time.time()

        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                """UPDATE speaker_profiles
                   SET embedding_centroid = ?, sample_count = ?, updated_at = ?
                   WHERE speaker_id = ?""",
                (centroid_bytes, sample_count, now, speaker_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get(self, speaker_id: str) -> Optional[SpeakerProfile]:
        """Get a single speaker profile by ID."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM speaker_profiles WHERE speaker_id = ?",
                (speaker_id,),
            ).fetchone()
            return self._row_to_profile(row) if row else None

    def list_all(self) -> List[SpeakerProfile]:
        """List all enrolled speaker profiles."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM speaker_profiles ORDER BY created_at"
            ).fetchall()
            return [self._row_to_profile(r) for r in rows]

    def delete(self, speaker_id: str) -> bool:
        """Delete a speaker profile.

        Returns:
            True if deleted, False if not found.
        """
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM speaker_profiles WHERE speaker_id = ?",
                (speaker_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_by_role(self, role: str) -> List[SpeakerProfile]:
        """List all speakers with a given role."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM speaker_profiles WHERE role = ? ORDER BY name",
                (role,),
            ).fetchall()
            return [self._row_to_profile(r) for r in rows]
