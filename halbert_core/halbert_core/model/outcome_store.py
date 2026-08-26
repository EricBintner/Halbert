# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Outcome store for model-call self-tuning (A3).

Records per-call outcomes (model, success, latency, tokens, cost, complexity,
task) to SQLite so the ``MetaHarnessRouter`` (C2a) can blend recorded evidence
with tier-based priors. The store is best-effort: recording must NEVER break
generation — every public method swallows exceptions and logs at debug level.

Uses SQLite for queryability (the OPUS-HANDOFF chose SQLite over OCC's JSONL
append-only). A single shared connection (``check_same_thread=False``) plus a
write lock keeps it safe across the sync generate() path and any background
thread. See OPUS-HANDOFF §A3 and STRATEGY-V2-SCRUTINY.md §4.
"""

from __future__ import annotations
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("halbert.model.outcome_store")

_DEFAULT_DB = str(Path.home() / ".halbert" / "model_outcomes.db")


class OutcomeStore:
    """Records and aggregates model call outcomes (best-effort, never throws)."""

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or _DEFAULT_DB
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        try:
            if self._db_path != ":memory:":
                Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                self._db_path, check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
            self._ensure_schema()
        except Exception as e:
            # Never fail construction — generation must not break on a bad db.
            logger.debug(f"OutcomeStore init failed (non-fatal): {e}")
            self._conn = None

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        try:
            with self._lock:
                cur = self._conn.cursor()
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS model_outcomes (
                        id           INTEGER PRIMARY KEY AUTOINCREMENT,
                        model        TEXT NOT NULL,
                        success      INTEGER NOT NULL,
                        latency_ms   REAL NOT NULL DEFAULT 0,
                        input_tokens INTEGER NOT NULL DEFAULT 0,
                        output_tokens INTEGER NOT NULL DEFAULT 0,
                        cost_usd     REAL NOT NULL DEFAULT 0,
                        complexity   REAL,
                        task         TEXT,
                        ts           REAL NOT NULL
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_outcomes_model "
                    "ON model_outcomes(model)"
                )
                self._conn.commit()
        except Exception as e:
            logger.debug(f"OutcomeStore schema failed (non-fatal): {e}")

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def record(
        self,
        model: str,
        success: bool,
        latency_ms: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        complexity: Optional[float] = None,
        task: Optional[str] = None,
    ) -> None:
        """Record one model-call outcome. Best-effort; never raises."""
        if self._conn is None:
            return
        try:
            with self._lock:
                self._conn.execute(
                    """
                    INSERT INTO model_outcomes
                        (model, success, latency_ms, input_tokens,
                         output_tokens, cost_usd, complexity, task, ts)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(model),
                        1 if success else 0,
                        float(latency_ms or 0),
                        int(input_tokens or 0),
                        int(output_tokens or 0),
                        float(cost_usd or 0),
                        complexity,
                        task,
                        time.time(),
                    ),
                )
                self._conn.commit()
        except Exception as e:
            logger.debug(f"Outcome record failed (non-fatal): {e}")

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def stats_for(self, model: str) -> Dict[str, Any]:
        """Aggregate stats for a model.

        Returns ``{attempts, successes, success_rate, avg_latency, avg_cost}``.
        On any error returns zeroed stats so callers can treat a missing model
        as "no evidence yet" (the router's min_samples gate then falls back to
        the prior).
        """
        zero = {
            "attempts": 0,
            "successes": 0,
            "success_rate": 0.0,
            "avg_latency": 0.0,
            "avg_cost": 0.0,
        }
        if self._conn is None:
            return zero
        try:
            with self._lock:
                cur = self._conn.execute(
                    """
                    SELECT COUNT(*) AS attempts,
                           COALESCE(SUM(success), 0) AS successes,
                           COALESCE(AVG(latency_ms), 0) AS avg_latency,
                           COALESCE(AVG(cost_usd), 0) AS avg_cost
                    FROM model_outcomes WHERE model = ?
                    """,
                    (str(model),),
                )
                row = cur.fetchone()
            if not row or not row["attempts"]:
                return zero
            attempts = int(row["attempts"])
            successes = int(row["successes"])
            return {
                "attempts": attempts,
                "successes": successes,
                "success_rate": successes / attempts if attempts else 0.0,
                "avg_latency": float(row["avg_latency"] or 0),
                "avg_cost": float(row["avg_cost"] or 0),
            }
        except Exception as e:
            logger.debug(f"Outcome stats_for failed (non-fatal): {e}")
            return zero

    def summary(self) -> List[Dict[str, Any]]:
        """Per-model aggregate summary (all models with recorded outcomes)."""
        if self._conn is None:
            return []
        try:
            with self._lock:
                cur = self._conn.execute(
                    """
                    SELECT model,
                           COUNT(*) AS attempts,
                           COALESCE(SUM(success), 0) AS successes,
                           COALESCE(AVG(latency_ms), 0) AS avg_latency,
                           COALESCE(AVG(cost_usd), 0) AS avg_cost
                    FROM model_outcomes
                    GROUP BY model
                    ORDER BY attempts DESC
                    """
                )
                rows = cur.fetchall()
            out = []
            for r in rows:
                attempts = int(r["attempts"])
                out.append({
                    "model": r["model"],
                    "attempts": attempts,
                    "successes": int(r["successes"]),
                    "success_rate": (int(r["successes"]) / attempts) if attempts else 0.0,
                    "avg_latency": float(r["avg_latency"] or 0),
                    "avg_cost": float(r["avg_cost"] or 0),
                })
            return out
        except Exception as e:
            logger.debug(f"Outcome summary failed (non-fatal): {e}")
            return []

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


# Global instance (lazy) ----------------------------------------------------

_outcome_store: Optional[OutcomeStore] = None


def get_outcome_store() -> OutcomeStore:
    """Get the global OutcomeStore (created lazily)."""
    global _outcome_store
    if _outcome_store is None:
        _outcome_store = OutcomeStore()
    return _outcome_store
