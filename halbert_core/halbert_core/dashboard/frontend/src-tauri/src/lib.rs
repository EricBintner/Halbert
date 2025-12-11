// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
use serde::Serialize;
use sysinfo::System;

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
        let key = (total, available); // Use size combo as unique identifier
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
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            greet,
            get_system_info,
            get_system_metrics,
            get_pending_approvals,
            approve_request,
            reject_request,
            get_active_jobs,
            get_memory_stats,
            get_documents
        ])
        .setup(|app| {
            // Set window icon for Linux taskbar
            #[cfg(target_os = "linux")]
            {
                use tauri::Manager;
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
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
