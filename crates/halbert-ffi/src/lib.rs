//! # halbert-ffi
//!
//! PyO3 bridge exposing the `halbert-*` Rust crates to the Python agent.
//!
//! This crate builds as `halbert_rs` (a Python extension module) via Maturin.
//! The Python agent imports it as `import halbert_rs` and calls the Rust
//! crate implementations through typed Python classes.
//!
//! ## Modules
//!
//! - `halbert_rs.mqtt` — MQTT client and device state cache
//! - `halbert_rs.telemetry` — Kernel telemetry event stream
//! - `halbert_rs.snapshots` — Atomic filesystem snapshots
//! - `halbert_rs.sandbox` — Kernel-level sandboxing
//!
//! ## Graceful degradation
//!
//! If a feature is not available on the current platform (e.g. eBPF on
//! macOS), the corresponding Python class raises a clear `RuntimeError`
//! on use. The Python agent should catch this and fall back to pure-Python
//! implementations.

use pyo3::prelude::*;

/// Python module entry point.
#[pymodule]
fn halbert_rs(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Sub-modules will be registered here in R4.2-R4.5.
    // For now, just expose a version string so Python can verify the import.
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;

    // Re-export the error type so Python can catch it.
    m.add("UnsupportedError", _py.get_type_bound::<PyUnsupportedError>())?;

    Ok(())
}

/// Python-visible error for unsupported platform features.
#[pyclass(extends = pyo3::exceptions::PyRuntimeError, module = "halbert_rs")]
pub struct PyUnsupportedError;

#[pymethods]
impl PyUnsupportedError {
    #[new]
    #[pyo3(signature = (msg=None))]
    fn new(msg: Option<String>) -> Self {
        let _ = msg; // The message is handled by Python's RuntimeError constructor.
        Self
    }
}
