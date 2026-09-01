//! # halbert-telemetry
//!
//! Kernel telemetry via eBPF for zero-overhead system observability.
//!
//! On Linux (kernel >= 5.8), this crate loads eBPF probes that stream
//! kernel events (process exec, OOM kills, TCP connections, file deletions)
//! via a ring buffer. On macOS and other platforms, all operations return
//! `TelemetryError::Unsupported` and the stream yields no events.
//!
//! ## Stability
//!
//! The eBPF probe targets (`sys_enter_execve`, `oom_mark_victim`,
//! `tcp_v4_connect`, `vfs_unlink`) are stable kernel tracepoints. The
//! `TelemetryEvent` enum and `TelemetrySource` trait are the stable
//! contract consumed by the Python agent via PyO3.

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use thiserror::Error;

/// Errors returned by telemetry operations.
#[derive(Debug, Error)]
pub enum TelemetryError {
    #[error("Telemetry not supported on this platform")]
    Unsupported,
    #[error("eBPF probe load failed: {0}")]
    ProbeLoad(String),
    #[error("eBPF ring buffer error: {0}")]
    RingBuffer(String),
    #[error("Telemetry stream closed")]
    StreamClosed,
}

/// Type of kernel event observed by an eBPF probe.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum TelemetryEventKind {
    /// Process creation (`execve` syscall).
    Exec,
    /// OOM killer marked a process as victim.
    OomKill,
    /// Outbound TCP connection initiated.
    TcpConnect,
    /// File deletion (`vfs_unlink`).
    FileDelete,
}

/// A single kernel telemetry event streamed from an eBPF probe.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TelemetryEvent {
    pub kind: TelemetryEventKind,
    pub timestamp_ns: u64,
    pub pid: u32,
    pub ppid: u32,
    pub comm: String,
    /// Event-specific payload (e.g. argv for Exec, daddr for TcpConnect).
    pub data: serde_json::Value,
}

/// Trait for a source of kernel telemetry events.
///
/// On Linux, the implementation loads eBPF probes and streams events
/// from a ring buffer. On other platforms, `start()` returns
/// `TelemetryError::Unsupported`.
#[async_trait]
pub trait TelemetrySource: Send + Sync {
    /// Start the eBPF probes and begin streaming events.
    async fn start(&self) -> Result<(), TelemetryError>;

    /// Stop all eBPF probes and close the event stream.
    async fn stop(&self) -> Result<(), TelemetryError>;

    /// Check if telemetry is currently active.
    async fn is_running(&self) -> bool;

    /// Receive the next telemetry event. Blocks until an event arrives.
    async fn recv(&self) -> Result<TelemetryEvent, TelemetryError>;
}

/// Configuration for the telemetry source.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct TelemetryConfig {
    /// Enable individual probe types. All enabled by default.
    pub enable_exec: bool,
    pub enable_oom: bool,
    pub enable_tcp_connect: bool,
    pub enable_file_delete: bool,
    /// Ring buffer size in pages (must be power of 2).
    pub ring_buffer_pages: u32,
}

impl TelemetryConfig {
    pub fn defaults() -> Self {
        Self {
            enable_exec: true,
            enable_oom: true,
            enable_tcp_connect: true,
            enable_file_delete: true,
            ring_buffer_pages: 64,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn telemetry_event_serialization() {
        let event = TelemetryEvent {
            kind: TelemetryEventKind::Exec,
            timestamp_ns: 1_700_000_000_000_000_000,
            pid: 1234,
            ppid: 1,
            comm: "bash".to_string(),
            data: serde_json::json!({"argv": ["/bin/ls", "-la"]}),
        };
        let json = serde_json::to_string(&event).unwrap();
        let back: TelemetryEvent = serde_json::from_str(&json).unwrap();
        assert_eq!(back.kind, TelemetryEventKind::Exec);
        assert_eq!(back.pid, 1234);
        assert_eq!(back.comm, "bash");
    }

    #[test]
    fn telemetry_config_defaults() {
        let config = TelemetryConfig::defaults();
        assert!(config.enable_exec);
        assert!(config.enable_oom);
        assert!(config.enable_tcp_connect);
        assert!(config.enable_file_delete);
        assert_eq!(config.ring_buffer_pages, 64);
    }
}
