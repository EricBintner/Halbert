// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
use serde::Serialize;
use sysinfo::System;
use std::path::PathBuf;
use std::sync::Mutex;
use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Managed state: the running backend sidecar (None once killed).
struct Backend(Mutex<Option<CommandChild>>);

const DEFAULT_PORT: u16 = 8000;
const HOST: &str = "127.0.0.1";

fn backend_port() -> u16 {
    std::env::var("HALBERT_PORT")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(DEFAULT_PORT)
}

fn api_base() -> String {
    format!("http://{}:{}", HOST, backend_port())
}

/// Repo root for the sidecar. Precedence: HALBERT_REPO_ROOT env, then (dev builds only)
/// walk up from CARGO_MANIFEST_DIR until a dir containing halbert_core/pyproject.toml.
fn repo_root() -> Option<PathBuf> {
    if let Ok(p) = std::env::var("HALBERT_REPO_ROOT") {
        return Some(PathBuf::from(p));
    }
    #[cfg(debug_assertions)]
    {
        let mut dir: Option<&std::path::Path> = Some(std::path::Path::new(env!("CARGO_MANIFEST_DIR")));
        while let Some(d) = dir {
            if d.join("halbert_core").join("pyproject.toml").is_file() {
                return Some(d.to_path_buf());
            }
            dir = d.parent();
        }
    }
    None
}

#[tauri::command]
fn get_api_base() -> String {
    api_base()
}

fn spawn_backend(app: &tauri::AppHandle) -> tauri::Result<()> {
    let mut cmd = app
        .shell()
        .sidecar("halbert-api")
        .map_err(|e| tauri::Error::Anyhow(e.into()))?
        .env("HALBERT_HOST", HOST)
        .env("HALBERT_PORT", backend_port().to_string())
        // The backend's parent watchdog (dashboard/parent_watchdog.py) exits
        // uvicorn when this pid disappears, covering force-quit and crashes
        // where kill_backend() never runs.
        .env("HALBERT_PARENT_PID", std::process::id().to_string());
    if let Some(root) = repo_root() {
        cmd = cmd.env("HALBERT_REPO_ROOT", &root).current_dir(&root);
    }
    let (mut rx, child) = cmd.spawn().map_err(|e| tauri::Error::Anyhow(e.into()))?;
    println!("[Halbert] backend sidecar pid {} on {}", child.pid(), api_base());
    app.manage(Backend(Mutex::new(Some(child))));
    // MUST drain: the plugin uses a bounded channel(1) with blocking sends; an
    // un-polled receiver would stall uvicorn's stdout pipe.
    tauri::async_runtime::spawn(async move {
        while let Some(ev) = rx.recv().await {
            match ev {
                CommandEvent::Stdout(b) | CommandEvent::Stderr(b) => {
                    eprintln!("[halbert-api] {}", String::from_utf8_lossy(&b).trim_end());
                }
                CommandEvent::Error(e) => eprintln!("[halbert-api] error: {e}"),
                CommandEvent::Terminated(p) => {
                    eprintln!("[halbert-api] exited code={:?} signal={:?}", p.code, p.signal);
                    break;
                }
                _ => {}
            }
        }
    });
    Ok(())
}

fn kill_backend(app: &tauri::AppHandle) {
    if let Some(state) = app.try_state::<Backend>() {
        if let Some(child) = state.0.lock().unwrap().take() {
            if let Err(e) = child.kill() {
                eprintln!("[Halbert] failed to kill backend: {e}");
            }
        }
    }
}

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[derive(Serialize)]
struct SystemInfo {
    hostname: String,
    os_name: String,
    os_version: String,
    kernel_version: String,
    total_memory_mb: u64,
    available_memory_mb: u64,
    cpu_count: usize,
}

#[tauri::command]
fn get_system_info() -> SystemInfo {
    let mut sys = System::new_all();
    sys.refresh_all();

    SystemInfo {
        hostname: System::host_name().unwrap_or_default(),
        os_name: System::name().unwrap_or_default(),
        os_version: System::os_version().unwrap_or_default(),
        kernel_version: System::kernel_version().unwrap_or_default(),
        total_memory_mb: sys.total_memory() / 1024,
        available_memory_mb: sys.available_memory() / 1024,
        cpu_count: sys.cpus().len(),
    }
}

#[derive(Serialize)]
struct DiskInfo {
    mount_point: String,
    fs_type: String,
    total_gb: f32,
    used_gb: f32,
    available_gb: f32,
    usage_percent: f32,
}

#[derive(Serialize)]
struct SystemMetrics {
    cpu_percent: f32,
    memory_percent: f32,
    memory_used_gb: f32,
    memory_total_gb: f32,
    memory_available_gb: f32,
    disks: Vec<DiskInfo>,
    uptime_seconds: u64,
}

#[tauri::command]
fn get_system_metrics() -> SystemMetrics {
    let mut sys = System::new_all();
    sys.refresh_all();
    
    // Get global CPU usage (average across all CPUs)
    let cpu_percent = sys.cpus().iter()
        .map(|cpu| cpu.cpu_usage())
        .sum::<f32>() / sys.cpus().len() as f32;
    
    // Memory stats (convert KB to GB properly)
    let total_mem = sys.total_memory();
    let used_mem = sys.used_memory();
    let available_mem = sys.available_memory();
    let memory_percent = (used_mem as f32 / total_mem as f32) * 100.0;
    
    // Disk stats (all mounted filesystems)
    use sysinfo::Disks;
    use std::collections::HashMap;
    let disks_sys = Disks::new_with_refreshed_list();
    
    // Collect all disks first, then deduplicate by device
    let mut disk_map: HashMap<u64, DiskInfo> = HashMap::new();
    
    for d in disks_sys.iter() {
        let mount = d.mount_point().to_str().unwrap_or("");
        
        // Filter to major mount points and skip temporary/virtual filesystems
        if !mount.starts_with("/") || mount.starts_with("/snap") || 
           mount.starts_with("/sys") || mount.starts_with("/proc") ||
           mount.starts_with("/dev") || mount.starts_with("/run") {
            continue;
        }
        
        let total = d.total_space();
        let available = d.available_space();
        let used = total.saturating_sub(available);
        let usage_percent = if total > 0 {
            (used as f32 / total as f32) * 100.0
        } else {
            0.0
        };
        
        let disk_info = DiskInfo {
            mount_point: mount.to_string(),
            fs_type: format!("{:?}", d.file_system()).trim_matches('"').to_string(),
            total_gb: (total as f32) / 1024.0 / 1024.0 / 1024.0,
            used_gb: (used as f32) / 1024.0 / 1024.0 / 1024.0,
            available_gb: (available as f32) / 1024.0 / 1024.0 / 1024.0,
            usage_percent,
        };
        
        // Use total_space as a simple hash for deduplication
        // If duplicate, prefer shorter mount point (e.g., "/" over "/btrfs/root")
        let hash_key = ((total >> 32) ^ (total & 0xFFFFFFFF)) as u64;
        
        if let Some(existing) = disk_map.get(&hash_key) {
            // Keep the shorter mount point
            if mount.len() < existing.mount_point.len() {
                disk_map.insert(hash_key, disk_info);
            }
        } else {
            disk_map.insert(hash_key, disk_info);
        }
    }
    
    let mut disks: Vec<DiskInfo> = disk_map.into_values().collect();
    // Sort by mount point for consistent ordering
    disks.sort_by(|a, b| a.mount_point.cmp(&b.mount_point));
    
    SystemMetrics {
        cpu_percent,
        memory_percent,
        memory_used_gb: (used_mem as f32) / 1024.0 / 1024.0 / 1024.0,  // bytes to GB
        memory_total_gb: (total_mem as f32) / 1024.0 / 1024.0 / 1024.0,  // bytes to GB
        memory_available_gb: (available_mem as f32) / 1024.0 / 1024.0 / 1024.0,  // bytes to GB
        disks,
        uptime_seconds: System::uptime(),
    }
}

#[derive(Serialize)]
struct ApprovalRequest {
    id: String,
    task: String,
    action: String,
    reasoning: String,
    confidence: f32,
    risk_level: String,
    affected_resources: Vec<String>,
    requested_at: String,
    status: String,
}

#[tauri::command]
fn get_pending_approvals() -> Vec<ApprovalRequest> {
    // Mock approval requests for UI development
    vec![
        ApprovalRequest {
            id: "req_001".to_string(),
            task: "System Update".to_string(),
            action: "Update 47 packages including kernel 6.14.0-37".to_string(),
            reasoning: "Security patches available. 12 critical CVEs fixed in this update.".to_string(),
            confidence: 0.92,
            risk_level: "medium".to_string(),
            affected_resources: vec![
                "linux-image-6.14.0-37-generic".to_string(),
                "systemd".to_string(),
                "openssh-server".to_string(),
            ],
            requested_at: chrono::Utc::now().to_rfc3339(),
            status: "pending".to_string(),
        },
        ApprovalRequest {
            id: "req_002".to_string(),
            task: "Disk Cleanup".to_string(),
            action: "Delete 15.2 GB of old logs and cache files".to_string(),
            reasoning: "Root partition at 25.2% - cleaning old logs older than 90 days.".to_string(),
            confidence: 0.88,
            risk_level: "low".to_string(),
            affected_resources: vec![
                "/var/log/*.gz".to_string(),
                "~/.cache/thumbnails/*".to_string(),
            ],
            requested_at: chrono::Utc::now().to_rfc3339(),
            status: "pending".to_string(),
        },
    ]
}

#[tauri::command]
fn approve_request(request_id: String) -> Result<String, String> {
    // Mock approval - in real system would call Python backend
    println!("Approved request: {}", request_id);
    Ok(format!("Request {} approved", request_id))
}

#[tauri::command]
fn reject_request(request_id: String, reason: String) -> Result<String, String> {
    // Mock rejection - in real system would call Python backend
    println!("Rejected request {}: {}", request_id, reason);
    Ok(format!("Request {} rejected", request_id))
}

#[derive(Serialize)]
struct Job {
    id: String,
    name: String,
    status: String,
    started_at: String,
    progress: f32,
    logs: Vec<String>,
    task_type: String,
}

#[tauri::command]
fn get_active_jobs() -> Vec<Job> {
    // Mock active jobs
    vec![
        Job {
            id: "job_001".to_string(),
            name: "System Health Monitor".to_string(),
            status: "running".to_string(),
            started_at: chrono::Utc::now().to_rfc3339(),
            progress: 0.0,
            logs: vec![
                "Started health monitoring".to_string(),
                "Checking CPU temperature...".to_string(),
                "CPU temp: 45°C (normal)".to_string(),
            ],
            task_type: "monitoring".to_string(),
        },
        Job {
            id: "job_002".to_string(),
            name: "RAG Document Indexing".to_string(),
            status: "running".to_string(),
            started_at: chrono::Utc::now().to_rfc3339(),
            progress: 0.67,
            logs: vec![
                "Loading documents from data/".to_string(),
                "Found 1,247 markdown files".to_string(),
                "Indexed 834 / 1247 documents".to_string(),
                "Building BM25 index...".to_string(),
            ],
            task_type: "indexing".to_string(),
        },
        Job {
            id: "job_003".to_string(),
            name: "Weekly Backup".to_string(),
            status: "pending".to_string(),
            started_at: chrono::Utc::now().to_rfc3339(),
            progress: 0.0,
            logs: vec![
                "Scheduled for 02:00 AM".to_string(),
            ],
            task_type: "backup".to_string(),
        },
    ]
}

#[derive(Serialize)]
struct MemoryStats {
    total_documents: u32,
    total_chunks: u32,
    index_size_mb: f32,
    last_indexed: String,
    corpus_status: String,
}

#[derive(Serialize)]
struct Document {
    id: String,
    title: String,
    source: String,
    doc_type: String,
    chunk_count: u32,
    indexed_at: String,
    size_kb: f32,
}

#[tauri::command]
fn get_memory_stats() -> MemoryStats {
    // Mock memory/RAG stats
    MemoryStats {
        total_documents: 1247,
        total_chunks: 8934,
        index_size_mb: 156.8,
        last_indexed: chrono::Utc::now().to_rfc3339(),
        corpus_status: "healthy".to_string(),
    }
}

#[tauri::command]
fn get_documents() -> Vec<Document> {
    // Mock document list
    vec![
        Document {
            id: "doc_001".to_string(),
            title: "Linux System Administration Guide".to_string(),
            source: "docs/linux/sysadmin.md".to_string(),
            doc_type: "markdown".to_string(),
            chunk_count: 87,
            indexed_at: chrono::Utc::now().to_rfc3339(),
            size_kb: 124.5,
        },
        Document {
            id: "doc_002".to_string(),
            title: "Rust Programming Best Practices".to_string(),
            source: "docs/rust/best-practices.md".to_string(),
            doc_type: "markdown".to_string(),
            chunk_count: 62,
            indexed_at: chrono::Utc::now().to_rfc3339(),
            size_kb: 89.2,
        },
        Document {
            id: "doc_003".to_string(),
            title: "Tauri Desktop Development".to_string(),
            source: "docs/tauri/desktop.md".to_string(),
            doc_type: "markdown".to_string(),
            chunk_count: 45,
            indexed_at: chrono::Utc::now().to_rfc3339(),
            size_kb: 67.8,
        },
        Document {
            id: "doc_004".to_string(),
            title: "man: systemctl (System Control)".to_string(),
            source: "scraped/man/systemctl.txt".to_string(),
            doc_type: "manpage".to_string(),
            chunk_count: 134,
            indexed_at: chrono::Utc::now().to_rfc3339(),
            size_kb: 234.1,
        },
        Document {
            id: "doc_005".to_string(),
            title: "Phase 8 UI/UX Design Spec".to_string(),
            source: "docs/Phase8/ui-spec.md".to_string(),
            doc_type: "markdown".to_string(),
            chunk_count: 56,
            indexed_at: chrono::Utc::now().to_rfc3339(),
            size_kb: 78.9,
        },
    ]
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Injected before any page script runs so the frontend (src/lib/apiBase.ts)
    // knows the backend origin inside the tauri://localhost webview.
    let init_script = format!(
        "window.__HALBERT_API_BASE__ = {};",
        serde_json::to_string(&api_base()).unwrap()
    );
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(
            tauri::plugin::Builder::<tauri::Wry>::new("halbert-env")
                .js_init_script(init_script)
                .build(),
        )
        .invoke_handler(tauri::generate_handler![
            greet,
            get_system_info,
            get_system_metrics,
            get_pending_approvals,
            approve_request,
            reject_request,
            get_active_jobs,
            get_memory_stats,
            get_documents,
            get_api_base
        ])
        .setup(|app| {
            spawn_backend(app.handle())?;

            // Set window icon for Linux taskbar
            #[cfg(target_os = "linux")]
            {
                use image::ImageReader;
                use std::io::Cursor;
                
                println!("[Halbert] Setting up window icon...");
                
                if let Some(window) = app.get_webview_window("main") {
                    // Embed icon at compile time for reliability
                    let icon_bytes = include_bytes!("../icons/icon.png");
                    println!("[Halbert] Icon bytes loaded: {} bytes", icon_bytes.len());
                    
                    if let Some(img) = ImageReader::new(Cursor::new(icon_bytes))
                        .with_guessed_format()
                        .ok()
                        .and_then(|r| r.decode().ok())
                    {
                        let rgba = img.to_rgba8();
                        let (width, height) = rgba.dimensions();
                        println!("[Halbert] Icon decoded: {}x{}", width, height);
                        
                        let icon = tauri::image::Image::new_owned(
                            rgba.into_raw(),
                            width,
                            height,
                        );
                        match window.set_icon(icon) {
                            Ok(_) => println!("[Halbert] Window icon set successfully!"),
                            Err(e) => println!("[Halbert] Failed to set icon: {:?}", e),
                        }
                    } else {
                        println!("[Halbert] Failed to decode icon image");
                    }
                } else {
                    println!("[Halbert] Could not get main window");
                }
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            // ExitRequested fires for window-close / app.exit(); Exit is the
            // final event on every quit path (Cmd-Q, AppleScript `quit`, …).
            // kill_backend() takes the child out of state, so running it on
            // both is idempotent.
            match event {
                RunEvent::ExitRequested { .. } | RunEvent::Exit => kill_backend(app),
                _ => {}
            }
        });
}

#[cfg(test)]
mod tests {
    #[test]
    fn repo_root_found_in_dev() {
        let root = super::repo_root().expect("repo root not found");
        assert!(root.join("halbert_core").join("pyproject.toml").is_file());
    }

    #[test]
    fn api_base_uses_default_port() {
        assert!(super::api_base().starts_with("http://127.0.0.1:"));
    }
}
