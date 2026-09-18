# macOS Always-On Home Server Deployment (Mac mini / Apple Silicon)

This guide documents the technical architecture, networking configuration, and operational considerations for running Halbert and Home Assistant on an always-on **Apple Silicon Mac** (such as a Mac mini M1/M2/M4 or Mac Studio).

---

## 1. Architectural Overview & The macOS Challenge

Apple Silicon Macs offer extraordinary energy efficiency (~5W–10W idle) and high-bandwidth unified memory architectures (100 GB/s to 800 GB/s), making them exceptional hardware for local LLM inference, computer vision, and ambient intelligence.

However, hosting smart home automation directly on macOS presents specific technical constraints:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ALWAYS-ON APPLE SILICON MAC (macOS Sonoma / Sequoia)                        │
│                                                                             │
│  Native macOS Host:                                                         │
│  ├── Halbert Pro Direct Edition (ai.halbert.macos.pro)                      │
│  │   ├── Unsandboxed, Full Disk Access                                      │
│  │   ├── Monitors launchd, Homebrew, APFS, and Unified Logging              │
│  │   └── High-speed unified memory LLM inference (MLX / Ollama)             │
│  │                                                                          │
│  ├── Apple Virtualization.framework (UTM Headless VM / OrbStack)            │
│  │   └── Bridged Interface (en0 — physical LAN IP: 192.168.1.50)           │
│  │       └── Home Assistant OS (HAOS) or Debian Container Host             │
│  │           ├── Native link-local mDNS/Zeroconf discovery                  │
│  │           └── Full Home Assistant Core + Supervisor                      │
│  │                                                                          │
│  └── External Network Coordinator (Ethernet / PoE):                         │
│      └── SMLIGHT SLZB-06 / TubesZB Zigbee & Thread Coordinator              │
│          (Eliminates USB serial passthrough dependencies)                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### The macOS Docker Pitfall
On macOS, Docker Desktop and standard container runtimes do **not** run directly on the XNU kernel; they run inside an isolated Linux virtual machine.
* **`network_mode: host` Fails:** In Docker Desktop on macOS, `network_mode: host` binds to the Linux VM's internal virtual interface, **not** to the Mac's physical Ethernet (`en0`). As a result, link-local multicast (mDNS, Zeroconf, SSDP) cannot traverse to the physical LAN. HomeKit, Matter, Google Cast, and Philips Hue device discovery will fail.
* **USB Serial Coordinator Flakiness:** Direct USB passthrough of Zigbee/Z-Wave dongles into macOS Docker containers is unreliable across host reboots and sleep cycles.

---

## 2. Recommended Configuration Paths

### Approach A: UTM Headless VM for Home Assistant (Recommended)

Running Home Assistant OS (HAOS) inside a lightweight virtual machine using **UTM** (backed by Apple's native `Virtualization.framework`) completely eliminates the Docker networking barrier:

1. **Install UTM:**
   Download UTM or install via Homebrew:
   ```bash
   brew install --cask utm
   ```
2. **Download HAOS Apple Silicon Image:**
   Download the official HAOS ARM64 (`aarch64`) raw or qcow2 image.
3. **VM Configuration in UTM:**
   * **Engine:** Apple Virtualization
   * **RAM:** 4096 MB
   * **CPU Cores:** 2 cores
   * **Network:** Set Network Mode to **Bridged (Advanced)** and select your physical Ethernet adapter (`en0`). This grants HAOS its own independent, real IP address on your home subnet with full native mDNS multicast capabilities.
4. **Headless Auto-Start:**
   Configure UTM to start the VM headlessly in the background on Mac boot:
   ```bash
   utmctl start "Home Assistant"
   ```

### Approach B: Network-Attached Smart Home Coordinators

Instead of attempting to pass physical USB serial dongles into a Mac VM or container, adopt **Ethernet/PoE Smart Home Coordinators** (such as the *SMLIGHT SLZB-06*, *TubesZB*, or a Matter-over-Thread border router):
* These coordinators plug directly into your home switch via Ethernet.
* Home Assistant and Zigbee2MQTT communicate with the coordinator over TCP/IP (`socket://192.168.1.75:6638`).
* **Result:** Total immunity to host reboot USB disconnects, driver quirks, or virtualization passthrough limitations.

---

## 3. Native Halbert Pro Installation on macOS

Run Halbert natively on the host to maximize its access to Apple Silicon hardware and local management tools:

1. **Install Halbert Pro:**
   Use the signed, unsandboxed Direct edition (`ai.halbert.macos.pro`) with Full Disk Access enabled in **System Settings → Privacy & Security → Full Disk Access**.

2. **Launchd Service Configuration:**
   Create `~/Library/LaunchAgents/ai.halbert.service.plist` so Halbert boots automatically in the background on system startup:

   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
       <key>Label</key>
       <string>ai.halbert.service</string>
       <key>ProgramArguments</key>
       <array>
           <string>/Users/youruser/Halbert/.venv/bin/python</string>
           <string>-m</string>
           <string>halbert_core.dashboard.app</string>
       </array>
       <key>EnvironmentVariables</key>
       <dict>
           <key>HALBERT_PORT</key>
           <string>8000</string>
           <key>HALBERT_DATA_DIR</key>
           <string>/Users/youruser/.local/share/halbert</string>
           <key>HALBERT_CONFIG_DIR</key>
           <string>/Users/youruser/.config/halbert</string>
       </dict>
       <key>RunAtLoad</key>
       <true/>
       <key>KeepAlive</key>
       <true/>
       <key>StandardOutPath</key>
       <string>/Users/youruser/Library/Logs/halbert.log</string>
       <key>StandardErrorPath</key>
       <string>/Users/youruser/Library/Logs/halbert-error.log</string>
   </dict>
   </plist>
   ```

   Load the service:
   ```bash
   launchctl load ~/Library/LaunchAgents/ai.halbert.service.plist
   ```

3. **Configure the Home Assistant Connection:**
   Point Halbert to the Home Assistant VM IP on your local subnet:
   ```bash
   python -c "
   from halbert_core.integrations.home_assistant.ha_config import save_ha_config, HAConfig
   save_ha_config(HAConfig(
       url='http://192.168.1.50:8123',
       token='YOUR_LONG_LIVED_TOKEN'
   ))
   "
   ```

---

## 4. macOS Server Power & Sleep Configuration

To ensure 24/7 reliability without unwanted sleeping:

1. **Disable System Sleep via CLI:**
   Execute with administrative privileges:
   ```bash
   # Prevent system sleep when idle; keep displays sleeping
   sudo pmset -a sleep 0
   sudo pmset -a displaysleep 5
   sudo pmset -a disksleep 0

   # Automatically restart after power loss
   sudo pmset -a autorestart 1

   # Enable Wake-on-LAN
   sudo pmset -a womp 1
   ```

2. **Verify Power Assertions:**
   Confirm that background processes are holding active power assertions:
   ```bash
   pmset -g assertions
   ```
