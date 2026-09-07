# halbert Rust Crates

Universal Rust Core for Halbert — kernel-level features delivered as
library crates, consumable by the Tauri desktop app (Cargo dependency),
the Python agent (PyO3 bridge), and `halbertd` (standalone daemon).

## Workspace Layout

```
crates/
├── Cargo.toml              # Workspace manifest
├── halbert-mqtt/           # MQTT client + device state cache
├── halbert-telemetry/      # eBPF kernel telemetry (Linux, macOS stub)
├── halbert-snapshots/      # Btrfs atomic snapshots (Linux, macOS stub)
├── halbert-sandbox/        # Landlock kernel sandboxing (Linux, macOS stub)
└── halbert-ffi/            # PyO3 bridge -> Python `import halbert_rs`
```

## Architectural Principle

> **Rewrite the interfaces to stable system APIs in Rust.**
> **Keep the application logic in Python.**
> Rust crates are thin native layers; Python is the brain that calls them.

A component qualifies for Rust only if:
1. It wraps a **stable kernel/syscall API** or **stable protocol** (frozen for years)
2. It is **CPU-bound or latency-sensitive** (not I/O-bound text parsing)
3. Its **interface contract** is unlikely to change

## Trait Contracts (Stable)

These trait definitions ARE the interface spec. Python and `halbertd`
implement against these. Changes to trait signatures are breaking changes
and require a major version bump.

### `halbert_mqtt::MqttClient`

```rust
async fn connect(&self, config: &MqttConfig) -> Result<(), MqttError>;
async fn subscribe(&self, topic: &str, qos: Qos) -> Result<(), MqttError>;
async fn unsubscribe(&self, topic: &str) -> Result<(), MqttError>;
async fn publish(&self, topic: &str, payload: &str, qos: Qos, retain: bool) -> Result<(), MqttError>;
async fn recv(&self) -> Result<MqttMessage, MqttError>;
async fn is_connected(&self) -> bool;
async fn disconnect(&self) -> Result<(), MqttError>;
```

### `halbert_mqtt::DeviceStateCache`

```rust
fn get_state(&self, topic: &str) -> Option<String>;
fn update_state(&self, topic: &str, payload: &str);
fn remove_state(&self, topic: &str);
fn list_topics(&self) -> Vec<String>;
fn clear(&self);
```

### `halbert_telemetry::TelemetrySource`

```rust
async fn start(&self) -> Result<(), TelemetryError>;
async fn stop(&self) -> Result<(), TelemetryError>;
async fn is_running(&self) -> bool;
async fn recv(&self) -> Result<TelemetryEvent, TelemetryError>;
```

### `halbert_snapshots::SnapshotEngine`

```rust
async fn create_snapshot(&self, label: &str, source_path: &str) -> Result<SnapshotHandle, SnapshotError>;
async fn rollback_snapshot(&self, handle: &SnapshotHandle) -> Result<(), SnapshotError>;
async fn delete_snapshot(&self, handle: &SnapshotHandle) -> Result<(), SnapshotError>;
async fn list_snapshots(&self, source_path: &str) -> Result<Vec<SnapshotHandle>, SnapshotError>;
async fn is_available(&self) -> bool;
```

### `halbert_sandbox::SandboxEngine`

```rust
async fn create_sandbox(&self, rules: &SandboxRules) -> Result<String, SandboxError>;
async fn enter_sandbox(&self, sandbox_id: &str) -> Result<(), SandboxError>;
async fn is_available(&self) -> bool;
async fn destroy_sandbox(&self, sandbox_id: &str) -> Result<(), SandboxError>;
```

## What Stays in Python

| Component | Why |
|-----------|-----|
| Agent state machine / CRAG | High-velocity, idiomatic Python |
| Prompt assembly | Still evolving (modality/voice work) |
| RAG / vector search | Mid-migration, retrieval backend changing |
| Discovery scanners (24 files) | I/O-bound, not CPU-bound |
| Device registry / entity mapping | Application logic, schema may evolve |
| Event mappers | Application logic, follows existing patterns |
| Dashboard frontend | React/TypeScript, already fast |
| Tool definitions | Agent tool interface, high-velocity |
| Safety policy generation | Deciding which paths to snapshot/allow |

## Build

```bash
# Build all crates
cargo build --workspace

# Run tests
cargo test --workspace

# Lint
cargo clippy --workspace -- -D warnings

# Build the PyO3 wheel (requires maturin)
cd crates/halbert-ffi && maturin build --release
```

## Platform Support

| Feature | Linux | macOS | Windows |
|---------|-------|-------|---------|
| `halbert-mqtt` | Yes | Yes | Yes |
| `halbert-telemetry` | Yes (eBPF) | Stub (unsupported) | Stub (unsupported) |
| `halbert-snapshots` | Yes (Btrfs) | Stub (unsupported) | Stub (unsupported) |
| `halbert-sandbox` | Yes (Landlock) | Stub (unsupported) | Stub (unsupported) |
| `halbert-ffi` | Yes | Yes | Yes (limited) |

## Versioning

All crates share a workspace version (`0.1.0` currently). Trait signature
changes are breaking and require a major version bump. Adding new methods
to traits is also breaking (requires implementors to add the method).

## License

GPL-3.0-or-later (same as the rest of Halbert).
