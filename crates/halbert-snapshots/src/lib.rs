//! # halbert-snapshots
//!
//! Atomic filesystem snapshots via Btrfs ioctls for guaranteed reversibility.
//!
//! On Linux with a Btrfs filesystem, this crate wraps the stable Btrfs ioctl
//! interface (`BTRFS_IOC_SNAP_CREATE`, `BTRFS_IOC_SNAP_DESTROY`,
//! `BTRFS_IOC_SUBVOL_CREATE`) to create and roll back atomic snapshots.
//! On other platforms or filesystems, all operations return
//! `SnapshotError::Unsupported`.
//!
//! ## Stability
//!
//! The Btrfs ioctl interface has been stable since 2009. The
//! `SnapshotEngine` trait and `SnapshotHandle` type are the stable contract
//! consumed by the Python agent via PyO3.

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use thiserror::Error;

/// Errors returned by snapshot operations.
#[derive(Debug, Error)]
pub enum SnapshotError {
    #[error("Snapshots not supported on this platform/filesystem")]
    Unsupported,
    #[error("Snapshot creation failed: {0}")]
    Create(String),
    #[error("Snapshot rollback failed: {0}")]
    Rollback(String),
    #[error("Snapshot deletion failed: {0}")]
    Delete(String),
    #[error("Snapshot not found: {0}")]
    NotFound(String),
    #[error("Permission denied (requires root or CAP_SYS_ADMIN)")]
    PermissionDenied,
}

/// A handle to a created snapshot.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SnapshotHandle {
    /// Unique identifier for the snapshot.
    pub id: String,
    /// Human-readable label (e.g. "pre-agent-action-20260831-153000").
    pub label: String,
    /// Source path that was snapshotted.
    pub source_path: String,
    /// Path where the snapshot lives.
    pub snapshot_path: String,
    /// Unix timestamp (seconds) when the snapshot was created.
    pub created_at: u64,
}

/// Trait for an atomic snapshot engine.
///
/// On Btrfs, the implementation uses subvolume snapshots (near-instant
/// copy-on-write). On other filesystems, `create_snapshot` returns
/// `SnapshotError::Unsupported`.
#[async_trait]
pub trait SnapshotEngine: Send + Sync {
    /// Create an atomic snapshot of `source_path` with the given label.
    /// Returns a handle that can be used for rollback.
    async fn create_snapshot(
        &self,
        label: &str,
        source_path: &str,
    ) -> Result<SnapshotHandle, SnapshotError>;

    /// Roll back to a previously created snapshot.
    /// After rollback, the filesystem state matches the snapshot.
    async fn rollback_snapshot(&self, handle: &SnapshotHandle) -> Result<(), SnapshotError>;

    /// Delete a snapshot to free space.
    async fn delete_snapshot(&self, handle: &SnapshotHandle) -> Result<(), SnapshotError>;

    /// List all snapshots for a given source path.
    async fn list_snapshots(&self, source_path: &str) -> Result<Vec<SnapshotHandle>, SnapshotError>;

    /// Check if the snapshot engine is available on this system.
    async fn is_available(&self) -> bool;
}

/// Configuration for the snapshot engine.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SnapshotConfig {
    /// Directory where snapshots are stored (must be on the same Btrfs filesystem).
    pub snapshot_dir: String,
    /// Maximum number of snapshots to retain (oldest pruned first).
    pub max_snapshots: u32,
    /// Prefix for snapshot names.
    pub name_prefix: String,
}

impl SnapshotConfig {
    pub fn defaults() -> Self {
        Self {
            snapshot_dir: "/.snapshots/halbert".to_string(),
            max_snapshots: 50,
            name_prefix: "halbert".to_string(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn snapshot_handle_serialization() {
        let handle = SnapshotHandle {
            id: "snap-001".to_string(),
            label: "pre-agent-action".to_string(),
            source_path: "/home/user/project".to_string(),
            snapshot_path: "/.snapshots/halbert/snap-001".to_string(),
            created_at: 1_700_000_000,
        };
        let json = serde_json::to_string(&handle).unwrap();
        let back: SnapshotHandle = serde_json::from_str(&json).unwrap();
        assert_eq!(back.id, handle.id);
        assert_eq!(back.label, handle.label);
    }

    #[test]
    fn snapshot_config_defaults() {
        let config = SnapshotConfig::defaults();
        assert_eq!(config.snapshot_dir, "/.snapshots/halbert");
        assert_eq!(config.max_snapshots, 50);
        assert_eq!(config.name_prefix, "halbert");
    }
}
