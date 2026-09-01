# N150 Kiosk Appliance — Voice Mode Runbook

> **Target hardware:** Intel N150, 16GB RAM, 256GB NVMe, 10" HDMI capacitive touch display
> **Software:** Halbert home variant + Chromium kiosk browser
> **Route:** `http://localhost:<port>/voice`

## Overview

The N150 appliance runs Halbert in home variant mode with the dashboard served
by the FastAPI backend. A Chromium kiosk browser connects to the `/voice` route
for the full-screen, touch-first, audio-reactive Voice Mode surface.

This is the **kiosk browser** deployment path. The Tauri desktop shell is an
alternative, but see the WebKitGTK caveat below — Tauri on Linux renders
WebKitGTK, not Chromium, and Web Audio + AEC are materially weaker there.

## Prerequisites

1. **Halbert backend** running and accessible on `localhost:<port>` (default 8000)
2. **Audio subsystem enabled** — `audio_config.yml` with `enabled: true` and
   the desired ingress/engress configured (local mic, Wyoming, or both)
3. **sherpa-onnx installed** — `pip install halbert-core[audio-inference]`
4. **Chromium or Chromium-based browser** installed (not Chrome — the snap
   confinement on Ubuntu can block getUserMedia; use the deb or flatpak)
5. **X11 session** — the kiosk unit requires an active X display for `xset`
   DPMS control. Wayland is not yet supported by the `xset` preamble.

## Installation

### 1. Install Chromium

```bash
# Ubuntu/Debian (deb, not snap)
sudo apt install chromium-browser

# Or via flatpak (avoids snap confinement issues)
flatpak install flathub org.chromium.Chromium
```

### 2. Copy the systemd unit

```bash
mkdir -p ~/.config/systemd/user
cp scripts/halbert-kiosk.service ~/.config/systemd/user/
systemctl --user daemon-reload
```

### 3. Configure the port

Edit `~/.config/systemd/user/halbert-kiosk.service` and set the `HALBERT_PORT`
environment variable to match your backend port (default: 8000).

### 4. Enable and start

```bash
# Enable auto-start on login
systemctl --user enable halbert-kiosk

# Start now (requires an active X session)
systemctl --user start halbert-kiosk
```

### 5. Auto-login (headless appliance)

For a dedicated appliance that boots directly into the kiosk:

```bash
# Enable auto-login for the display manager
sudo systemctl edit getty@tty1
# Add:
# [Service]
# ExecStart=
# ExecStart=-/sbin/agetty --autologin <username> --noclear %I $TERM

# Start X on login
echo 'startx -- -nocursor' >> ~/.bash_profile
# Or use a display manager with auto-login
```

## The systemd Unit

The unit file is at `scripts/halbert-kiosk.service`. It:

1. Disables screen blanking and DPMS via `xset s off -dpms` (P2's display
   power daemon takes over DPMS thereafter)
2. Launches Chromium in kiosk mode pointing at `http://localhost:<port>/voice`
3. Disables infobars, update checks, and error dialogs
4. Runs as a `--user` service (no root required)

## WebKitGTK Caveat (Tauri on Linux)

Tauri on Linux renders via **WebKitGTK**, not Chromium. This has material
consequences for Voice Mode:

| Feature | Chromium | WebKitGTK (Tauri) |
|---------|----------|-------------------|
| Web Audio FFT (`AnalyserNode`) | Full support | Supported but lower precision |
| `getUserMedia` AEC | Chromium-grade echo cancellation | Weaker AEC; may cause duplex issues |
| `AudioWorklet` | Full support | Supported but less tested |
| `MediaRecorder` | Full support | Supported |

**Recommendation:** For the N150 appliance, use the **Chromium kiosk** path
(documented here) rather than the Tauri shell. The Tauri shell is suitable for
desktop use on macOS/Windows where the webview engine is WebKit (macOS) or
WebView2 (Windows), both of which have better audio support than WebKitGTK.

The Tauri `voice-hud` floating panel (Rust `floating_panel.rs`) is a separate
concern — see implementation plan Task P4 for the build-or-retire decision.

## Troubleshooting

### Microphone not working

- Check `chromium://settings/content/microphone` — ensure the Halbert URL is allowed
- If using snap Chromium, switch to deb or flatpak (snap confinement blocks
  `getUserMedia` in kiosk mode)
- Verify `audio_config.yml` has `local_mic.enabled: true`

### Screen blanks after 10 minutes

- The `xset s off -dpms` preamble in the systemd unit should prevent this
- If P2 (display power daemon) is running, it manages DPMS — check
  `GET /api/system/display` for the current state
- The Voice Mode standby controller (P1) implements software dimming in-app;
  hardware DPMS is P2's domain

### Backlight dimming does not work (P2)

- P2's backlight path writes to `/sys/class/backlight/*/brightness`. Without
  a udev rule granting write access, the kiosk user (non-root) cannot write
  to these sysfs files and the backlight silently no-ops
  (`available.backlight: false` in `GET /api/system/display`).
- Fix: create a udev rule that grants the kiosk user write access to the
  backlight brightness file:

```bash
# Find the backlight device name
ls /sys/class/backlight/
# e.g. intel_backlight

# Create a udev rule (replace <device> and <kiosk_user>)
echo 'SUBSYSTEM=="backlight", KERNEL=="<device>", RUN+="/usr/bin/chmod 0666 /sys/class/backlight/%k/brightness"' \
  | sudo tee /etc/udev/rules.d/90-backlight.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

- After this rule is in place, restart Halbert and verify
  `available.backlight: true` in the display status endpoint.
- DPMS control via `xset` does not require this rule — only the backlight
  dim path does.

### Chromium shows "can't reach page"

- Verify the backend is running: `curl http://localhost:<port>/api/health`
- Check the `HALBERT_PORT` env var in the systemd unit matches the backend
- Chromium starts before the backend on boot — the unit has `Restart=on-failure`
  with a 5s delay, so it will retry

### Touch input not registering

- Verify the touch display is recognized: `xinput list`
- Chromium kiosk mode should handle touch events natively
- If using a USB touch controller, check `dmesg` for HID device enumeration
