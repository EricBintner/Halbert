//! # halbert-sandbox
//!
//! Kernel-level sandboxing via Landlock for blast-radius containment.
//!
//! On Linux (kernel >= 5.13), this crate wraps the stable Landlock syscall
//! interface (`landlock_create_ruleset`, `landlock_add_rule`,
//! `landlock_restrict_self`) to restrict a process's filesystem and network
//! access at the kernel level. On other platforms, all operations return
//! `SandboxError::Unsupported`.
//!
//! ## Stability
//!
//! The Landlock syscall interface has been stable since kernel 5.13 (2021).
//! The `SandboxEngine` trait and `SandboxRules` type are the stable contract
//! consumed by the Python agent via PyO3.

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use thiserror::Error;

/// Errors returned by sandbox operations.
#[derive(Debug, Error)]
pub enum SandboxError {
    #[error("Sandboxing not supported on this platform")]
    Unsupported,
    #[error("Sandbox creation failed: {0}")]
    Create(String),
    #[error("Sandbox entry failed: {0}")]
    Enter(String),
    #[error("Landlock restriction failed: {0}")]
    Restrict(String),
    #[error("Permission denied (requires no special privileges, but Landlock must be enabled)")]
    PermissionDenied,
}

/// Filesystem access level for a sandboxed path.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FsAccess {
    /// No access (deny all operations).
    None,
    /// Read-only (read files, list directories).
    ReadOnly,
    /// Read-write (read, write, create, delete).
    ReadWrite,
    /// Full access (read, write, create, delete, execute).
    Full,
}

/// Network access level for a sandboxed process.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NetAccess {
    /// No network access.
    None,
    /// Outbound TCP/UDP only (bind to any port, connect to any host).
    OutboundOnly,
    /// Full network access.
    Full,
}

/// Rules defining a sandbox's restrictions.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SandboxRules {
    /// Filesystem path access rules (path -> access level).
    pub fs_rules: Vec<FsRule>,
    /// Network access level.
    pub net_access: NetAccess,
    /// CPU quota (percentage of one core, 0 = unlimited).
    pub cpu_quota_percent: u32,
    /// Memory limit in MB (0 = unlimited).
    pub memory_limit_mb: u32,
    /// Max PID count (0 = unlimited).
    pub max_pids: u32,
}

/// A single filesystem access rule.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FsRule {
    pub path: String,
    pub access: FsAccess,
    /// Whether this rule applies recursively to subdirectories.
    pub recursive: bool,
}

impl Default for SandboxRules {
    fn default() -> Self {
        Self {
            fs_rules: vec![],
            net_access: NetAccess::None,
            cpu_quota_percent: 0,
            memory_limit_mb: 0,
            max_pids: 0,
        }
    }
}

/// Trait for a kernel-level sandbox engine.
///
/// On Linux, the implementation uses Landlock for filesystem restrictions
/// and cgroups v2 for resource limits. On other platforms, `create_sandbox`
/// returns `SandboxError::Unsupported`.
#[async_trait]
pub trait SandboxEngine: Send + Sync {
    /// Create a sandbox with the given rules. Returns a sandbox ID.
    async fn create_sandbox(&self, rules: &SandboxRules) -> Result<String, SandboxError>;

    /// Enter the sandbox with the given ID. After this call, the current
    /// process (and all children) are restricted by the sandbox rules.
    async fn enter_sandbox(&self, sandbox_id: &str) -> Result<(), SandboxError>;

    /// Check if the sandbox engine is available on this system.
    async fn is_available(&self) -> bool;

    /// Destroy a sandbox (releases cgroup resources).
    async fn destroy_sandbox(&self, sandbox_id: &str) -> Result<(), SandboxError>;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sandbox_rules_default() {
        let rules = SandboxRules::default();
        assert!(rules.fs_rules.is_empty());
        assert_eq!(rules.net_access, NetAccess::None);
        assert_eq!(rules.cpu_quota_percent, 0);
    }

    #[test]
    fn fs_access_serialization() {
        let access = FsAccess::ReadOnly;
        let json = serde_json::to_string(&access).unwrap();
        assert_eq!(json, r#""read_only""#);
        let back: FsAccess = serde_json::from_str(&json).unwrap();
        assert_eq!(back, FsAccess::ReadOnly);
    }

    #[test]
    fn sandbox_rules_serialization() {
        let rules = SandboxRules {
            fs_rules: vec![FsRule {
                path: "/tmp".to_string(),
                access: FsAccess::ReadWrite,
                recursive: true,
            }],
            net_access: NetAccess::OutboundOnly,
            cpu_quota_percent: 50,
            memory_limit_mb: 512,
            max_pids: 100,
        };
        let json = serde_json::to_string(&rules).unwrap();
        let back: SandboxRules = serde_json::from_str(&json).unwrap();
        assert_eq!(back.fs_rules.len(), 1);
        assert_eq!(back.fs_rules[0].path, "/tmp");
        assert_eq!(back.net_access, NetAccess::OutboundOnly);
        assert_eq!(back.cpu_quota_percent, 50);
    }
}
