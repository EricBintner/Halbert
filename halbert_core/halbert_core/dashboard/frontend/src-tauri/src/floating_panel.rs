// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
//! Opt-in floating voice HUD window (the `VoiceCompanionPill` host).
//!
//! `show_voice_hud` lazily creates a small, borderless, always-on-top,
//! non-activating overlay window centered at the top of the screen — the
//! Siri/Apple-Intelligence-style companion surface (audio workstream T2.8 /
//! UX Surface 2 in `.handoff/HANDOFF-AUDIO-AI-ARCHITECTURE-AND-UX-2026-08-29.md`).
//! It never replaces or focuses the main window: on macOS the created
//! NSWindow is converted to a non-activating panel style so summoning the
//! HUD does not steal focus from the IDE/terminal the sysadmin is in, and a
//! [`crate::hud_hotkey::HotkeyTap`] swallows Esc/Space while it is visible
//! (see `hud_hotkey.rs`).
//!
//! This is an opt-in window mode driven purely by Tauri commands — the main
//! window in `tauri.conf.json` is untouched, and the HUD webview loads the
//! same frontend at the `voice-hud` route, so the existing
//! `VoiceCompanionPill.tsx` component can render there. The pill window
//! needs `macos-private-api` (transparent windows); note that App Store
//! distribution restricts private API use, so App Store builds may need to
//! drop the transparency instead.

use crate::hud_hotkey::{HotkeyError, HotkeyTap};
use serde::Serialize;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use tauri::Manager;

/// Tauri window label of the floating voice HUD.
pub(crate) const HUD_WINDOW_LABEL: &str = "voice-hud";
/// Logical size and top margin (CSS px) of the HUD pill.
pub(crate) const HUD_WIDTH: f64 = 480.0;
pub(crate) const HUD_HEIGHT: f64 = 72.0;
pub(crate) const HUD_TOP_MARGIN: f64 = 48.0;

/// Lifecycle state of the Esc/Space event tap.
#[derive(Serialize, Clone, Copy, Debug, PartialEq, Eq)]
pub enum HotkeyTapState {
    /// Tap registered and swallowing Esc/Space.
    Active,
    /// No tap (panel hidden).
    Inactive,
    /// Tap refused — usually missing Accessibility trust.
    Unavailable,
    /// Platform without CGEventTap support.
    Unsupported,
}

#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct VoiceHudStatus {
    pub visible: bool,
    pub hotkey_tap: HotkeyTapState,
}

/// Managed state for the HUD lifecycle.
pub struct VoiceHudState {
    visible: Arc<AtomicBool>,
    /// Serializes show/hide (Tauri commands can run concurrently).
    lock: Mutex<()>,
    tap: Mutex<Option<HotkeyTap>>,
}

impl VoiceHudState {
    pub fn new() -> Self {
        Self {
            visible: Arc::new(AtomicBool::new(false)),
            lock: Mutex::new(()),
            tap: Mutex::new(None),
        }
    }
}

impl Default for VoiceHudState {
    fn default() -> Self {
        Self::new()
    }
}

fn current_status(state: &VoiceHudState) -> VoiceHudStatus {
    let tap = state.tap.lock().unwrap();
    let hotkey_tap = match tap.as_ref() {
        Some(t) if t.is_active() => HotkeyTapState::Active,
        Some(_) => HotkeyTapState::Inactive,
        None => HotkeyTapState::Inactive,
    };
    VoiceHudStatus {
        visible: state.visible.load(Ordering::Relaxed),
        hotkey_tap,
    }
}

/// Show (and lazily create) the floating voice HUD. Returns the resulting
/// lifecycle status so the frontend can tell whether Esc/Space interception
/// is armed.
#[tauri::command]
pub fn show_voice_hud(
    app: tauri::AppHandle,
    state: tauri::State<'_, VoiceHudState>,
) -> Result<VoiceHudStatus, String> {
    let _guard = state.lock.lock().unwrap();

    let window = match app.get_webview_window(HUD_WINDOW_LABEL) {
        Some(window) => window,
        None => {
            let window = tauri::WebviewWindowBuilder::new(
                &app,
                HUD_WINDOW_LABEL,
                tauri::WebviewUrl::App(std::path::PathBuf::from("voice-hud")),
            )
            .title("Halbert Voice")
            .inner_size(HUD_WIDTH, HUD_HEIGHT)
            .decorations(false)
            .resizable(false)
            .minimizable(false)
            .maximizable(false)
            .closable(false)
            .shadow(false)
            .transparent(true)
            .always_on_top(true)
            .skip_taskbar(true)
            // Never steal focus from the app the user is working in.
            .focused(false)
            // Created hidden: style + position first, then show.
            .visible(false)
            .build()
            .map_err(|e| format!("failed to create voice HUD window: {e}"))?;
            apply_non_activating_panel_style(&window)?;
            window
        }
    };

    position_top_center(&window)?;
    window
        .show()
        .map_err(|e| format!("failed to show voice HUD: {e}"))?;
    state.visible.store(true, Ordering::Relaxed);

    // Arm the Esc/Space interceptor while visible.
    let hotkey_tap = {
        let mut tap = state.tap.lock().unwrap();
        if tap.as_ref().is_some_and(HotkeyTap::is_active) {
            HotkeyTapState::Active
        } else {
            match HotkeyTap::start(&app, Arc::clone(&state.visible)) {
                Ok(new_tap) => {
                    *tap = Some(new_tap);
                    HotkeyTapState::Active
                }
                Err(HotkeyError::TapCreationFailed) => {
                    eprintln!(
                        "[Halbert] voice HUD shown without Esc/Space interception; \
                         grant Halbert Accessibility permission to enable it"
                    );
                    HotkeyTapState::Unavailable
                }
                Err(HotkeyError::Unsupported) => HotkeyTapState::Unsupported,
            }
        }
    };

    Ok(VoiceHudStatus {
        visible: true,
        hotkey_tap,
    })
}

/// Hide the HUD and immediately deregister the hotkey tap so background
/// Esc/Space presses fall through again.
#[tauri::command]
pub fn hide_voice_hud(
    app: tauri::AppHandle,
    state: tauri::State<'_, VoiceHudState>,
) -> VoiceHudStatus {
    let _guard = state.lock.lock().unwrap();
    state.visible.store(false, Ordering::Relaxed);
    if let Some(tap) = state.tap.lock().unwrap().take() {
        tap.stop();
    }
    if let Some(window) = app.get_webview_window(HUD_WINDOW_LABEL) {
        let _ = window.hide();
    }
    VoiceHudStatus {
        visible: false,
        hotkey_tap: HotkeyTapState::Inactive,
    }
}

#[tauri::command]
pub fn get_voice_hud_status(state: tauri::State<'_, VoiceHudState>) -> VoiceHudStatus {
    current_status(&state)
}

/// Center the pill horizontally at the top of the window's current monitor
/// (fullscreen apps included — the panel joins all spaces).
fn position_top_center(window: &tauri::WebviewWindow) -> Result<(), String> {
    let monitor = window
        .current_monitor()
        .ok()
        .flatten()
        .or_else(|| window.primary_monitor().ok().flatten())
        .ok_or_else(|| "no monitor available for HUD placement".to_string())?;
    let scale = monitor.scale_factor();
    let monitor_size = monitor.size();
    let monitor_pos = monitor.position();
    let x = monitor_pos.x as f64 + (monitor_size.width as f64 - HUD_WIDTH * scale) / 2.0;
    let y = monitor_pos.y as f64 + HUD_TOP_MARGIN * scale;
    window
        .set_position(tauri::PhysicalPosition::new(x as i32, y as i32))
        .map_err(|e| format!("failed to position voice HUD: {e}"))
}

/// Convert the created window to a non-activating, all-spaces floating
/// panel on macOS. Other platforms keep the plain borderless overlay.
#[cfg(target_os = "macos")]
fn apply_non_activating_panel_style(window: &tauri::WebviewWindow) -> Result<(), String> {
    use objc2_app_kit::{NSWindow, NSWindowCollectionBehavior, NSWindowStyleMask};

    /// `NSFloatingWindowLevel` (== `kCGFloatingWindowLevel == 3`): above
    /// ordinary windows, below modal panels and the menu bar. objc2-app-kit
    /// does not export the constant, so it is restated here.
    const NS_FLOATING_WINDOW_LEVEL: isize = 3;

    let ns_ptr = window
        .ns_window()
        .map_err(|e| format!("no NSWindow for voice HUD: {e}"))?;
    // Retain around our calls; balanced when `ns_window` drops. The webview
    // keeps its own strong reference, so the object outlives this scope.
    let ns_window = unsafe {
        objc2::rc::Retained::retain(ns_ptr.cast::<NSWindow>())
            .ok_or("NSWindow pointer was null")?
    };
    // Borderless + NonactivatingPanel: the window cannot become key, so
    // clicks and summoning never yank focus from the user's IDE.
    // FullSizeContentView keeps the webview flush with the pill edges.
    ns_window.setStyleMask(
        NSWindowStyleMask::Borderless
            | NSWindowStyleMask::NonactivatingPanel
            | NSWindowStyleMask::FullSizeContentView,
    );
    ns_window.setLevel(NS_FLOATING_WINDOW_LEVEL);
    // Visible on every space and over fullscreen apps, and excluded from
    // Cmd-` window cycling.
    ns_window.setCollectionBehavior(
        NSWindowCollectionBehavior::CanJoinAllSpaces
            | NSWindowCollectionBehavior::FullScreenAuxiliary
            | NSWindowCollectionBehavior::IgnoresCycle,
    );
    Ok(())
}

#[cfg(not(target_os = "macos"))]
fn apply_non_activating_panel_style(_window: &tauri::WebviewWindow) -> Result<(), String> {
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{VoiceHudState, VoiceHudStatus, HotkeyTapState, HUD_HEIGHT, HUD_WIDTH};

    #[test]
    fn new_state_is_hidden_and_disarmed() {
        let state = VoiceHudState::new();
        assert!(!state.visible.load(std::sync::atomic::Ordering::Relaxed));
        assert!(state.tap.lock().unwrap().is_none());
    }

    #[test]
    fn hud_dimensions_are_a_pill() {
        // A pill is a wide, short overlay — sanity-check the constants so a
        // future edit does not silently make a square window.
        assert!(HUD_WIDTH > HUD_HEIGHT * 4.0);
    }

    #[test]
    fn status_serializes_all_fields() {
        let status = VoiceHudStatus {
            visible: false,
            hotkey_tap: HotkeyTapState::Inactive,
        };
        let json = serde_json::to_string(&status).expect("serializable");
        assert!(json.contains("\"visible\":false"));
        assert!(json.contains("Inactive"));
    }
}