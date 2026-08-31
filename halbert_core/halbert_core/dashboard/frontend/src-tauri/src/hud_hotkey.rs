// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
//! Global Esc/Space interception for the floating voice HUD.
//!
//! A non-activating NSPanel cannot become the key window, so while the HUD
//! is visible a plain `Esc` or `Space` press would fall through to whatever
//! IDE or terminal the sysadmin is working in — dismissing the pill could
//! instead abort a running shell script (doc 12, landmine 4:
//! `documentation/design/12-scrutiny-and-reverse-engineering-modality-handoff.md`).
//!
//! While the panel is visible, a temporary macOS `CGEventTap` watches for
//! `kVK_Escape` / `kVK_Space` key-downs, swallows them so they never reach
//! the background app, and dispatches the dismiss/interrupt action. When the
//! panel hides, the tap is deregistered immediately.
//!
//! Note: a key-down event tap requires the app to be trusted for
//! Accessibility (System Settings > Privacy & Security > Accessibility). If
//! the tap cannot be created, [`HotkeyTap::start`] fails and the HUD still
//! works — only via mouse, with keys falling through as before.

use serde::Serialize;

/// macOS virtual keycode for Escape (`kVK_Escape`).
pub const KVK_ESCAPE: i64 = 0x35;
/// macOS virtual keycode for Space (`kVK_Space`).
pub const KVK_SPACE: i64 = 0x31;

/// Which HUD action a keycode maps to.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HudKey {
    /// Escape: dismiss the HUD.
    Dismiss,
    /// Space: interrupt / pause the current TTS playback.
    Interrupt,
    Other,
}

pub fn classify_keycode(keycode: i64) -> HudKey {
    match keycode {
        KVK_ESCAPE => HudKey::Dismiss,
        KVK_SPACE => HudKey::Interrupt,
        _ => HudKey::Other,
    }
}

/// What the tap should do with a key event.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HotkeyAction {
    DismissPanel,
    InterruptPlayback,
    None,
}

/// Payload forwarded to the HUD webview when a hotkey fires.
#[derive(Serialize, Clone, Debug)]
pub struct HotkeyEvent {
    /// Human-readable key name ("escape" / "space").
    pub key: String,
    /// Action taken: "dismiss" / "interrupt".
    pub action: String,
}

/// Pure decision core: given a key, the panel visibility and whether the
/// event is a key repeat, decide whether the tap swallows the event and what
/// it should do.
///
/// - Nothing is touched while the panel is hidden: a background IDE must
///   never lose keys to an invisible HUD.
/// - While visible, `Esc`/`Space` are always swallowed (so repeats cannot
///   leak into the background app either), but only the first press
///   (non-autorepeat) triggers an action.
/// - Any other key always passes through untouched.
pub fn decide_hotkey(key: HudKey, panel_visible: bool, autorepeat: bool) -> (bool, HotkeyAction) {
    if !panel_visible || key == HudKey::Other {
        return (false, HotkeyAction::None);
    }
    let action = if autorepeat {
        HotkeyAction::None
    } else {
        match key {
            HudKey::Dismiss => HotkeyAction::DismissPanel,
            HudKey::Interrupt => HotkeyAction::InterruptPlayback,
            HudKey::Other => HotkeyAction::None,
        }
    };
    (true, action)
}

/// Why a hotkey tap could not be started.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HotkeyError {
    /// The CGEventTap could not be created — usually the app is not trusted
    /// for Accessibility.
    TapCreationFailed,
    /// The platform has no CGEventTap (non-macOS builds).
    #[cfg_attr(target_os = "macos", allow(dead_code))]
    Unsupported,
}

#[cfg(target_os = "macos")]
pub use tap::HotkeyTap;
#[cfg(not(target_os = "macos"))]
pub use stub::HotkeyTap;

#[cfg(target_os = "macos")]
mod tap {
    use super::{classify_keycode, decide_hotkey, HotkeyAction, HotkeyError, HotkeyEvent};
    use crate::floating_panel::HUD_WINDOW_LABEL;
    use core_foundation::base::TCFType;
    use core_foundation::mach_port::CFMachPort;
    use core_foundation::runloop::{kCFRunLoopCommonModes, CFRunLoop};
    use core_graphics::event::{
        CGEventTap, CGEventTapLocation, CGEventTapOptions, CGEventTapPlacement, CGEventType,
        EventField,
    };
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::sync::{Arc, Mutex};
    use std::thread::JoinHandle;
    use std::time::Duration;
    use tauri::{Emitter, Manager};

    // core-graphics 0.24 does not re-export `CGEventTapEnable` from its sys
    // crate; declare it ourselves (CoreGraphics is already linked).
    unsafe extern "C" {
        fn CGEventTapEnable(tap: core_foundation::mach_port::CFMachPortRef, enable: bool);
    }

    /// `CFRunLoop` is not `Send` in core-foundation, but `CFRunLoopStop` is
    /// explicitly allowed (and intended) to be called from another thread.
    struct SendRunLoop(CFRunLoop);
    // SAFETY: the only cross-thread use is `CFRunLoopStop` on this run loop,
    // which Core Foundation documents as thread-safe. The run loop is never
    // otherwise touched after it is handed over.
    unsafe impl Send for SendRunLoop {}

    /// A live CGEventTap on its own thread + run loop. Stopping drops the
    /// tap, which deregisters it from the event stream.
    pub struct HotkeyTap {
        thread: Option<JoinHandle<()>>,
        runloop: Option<SendRunLoop>,
        active: Arc<AtomicBool>,
    }

    impl HotkeyTap {
        /// Register the tap. Returns after the tap is confirmed live (or
        /// failed) on its own thread.
        pub fn start(
            app: &tauri::AppHandle,
            panel_visible: Arc<AtomicBool>,
        ) -> Result<Self, HotkeyError> {
            let app = app.clone();
            let active = Arc::new(AtomicBool::new(false));
            let active_thread = Arc::clone(&active);
            let (tx, rx) = std::sync::mpsc::channel::<Result<CFRunLoop, ()>>();

            let thread = std::thread::Builder::new()
                .name("halbert-hud-hotkey".into())
                .spawn(move || {
                    // Owned by this thread only: the tap callback needs the
                    // tap's own mach port to re-enable after timeouts, and
                    // CFMachPort is not Send, so the slot lives here.
                    let port_slot: Arc<Mutex<Option<CFMachPort>>> =
                        Arc::new(Mutex::new(None));
                    let port_slot_cb = Arc::clone(&port_slot);
                    let visible_cb = Arc::clone(&panel_visible);
                    let app_cb = app.clone();

                    let callback = move |_proxy,
                                         event_type,
                                         event: &core_graphics::event::CGEvent|
                          -> Option<core_graphics::event::CGEvent> {
                        match event_type {
                            CGEventType::KeyDown => {}
                            CGEventType::TapDisabledByTimeout
                            | CGEventType::TapDisabledByUserInput => {
                                // The system disabled us (timeout / secure
                                // input). Try to re-enable immediately.
                                eprintln!(
                                    "[Halbert] HUD hotkey tap disabled ({event_type:?}); re-enabling"
                                );
                                if let Some(port) = port_slot_cb.lock().unwrap().as_ref() {
                                    unsafe {
                                        CGEventTapEnable(port.as_concrete_TypeRef(), true)
                                    };
                                }
                                return Some(event.clone());
                            }
                            _ => return Some(event.clone()),
                        }
                        let keycode =
                            event.get_integer_value_field(EventField::KEYBOARD_EVENT_KEYCODE);
                        let autorepeat = event
                            .get_integer_value_field(EventField::KEYBOARD_EVENT_AUTOREPEAT)
                            != 0;
                        let (swallow, action) = decide_hotkey(
                            classify_keycode(keycode),
                            visible_cb.load(Ordering::Relaxed),
                            autorepeat,
                        );
                        dispatch(&app_cb, action, &visible_cb);
                        if swallow {
                            None // NULL from a Default-option tap deletes the event.
                        } else {
                            Some(event.clone())
                        }
                    };

                    match CGEventTap::new(
                        CGEventTapLocation::HID,
                        CGEventTapPlacement::HeadInsertEventTap,
                        CGEventTapOptions::Default,
                        vec![CGEventType::KeyDown],
                        callback,
                    ) {
                        Ok(tap) => {
                            *port_slot.lock().unwrap() = Some(tap.mach_port.clone());
                            let runloop_source = match tap.mach_port.create_runloop_source(0) {
                                Ok(source) => source,
                                Err(()) => {
                                    let _ = tx.send(Err(()));
                                    return;
                                }
                            };
                            let runloop = CFRunLoop::get_current();
                            unsafe {
                                runloop.add_source(&runloop_source, kCFRunLoopCommonModes)
                            };
                            tap.enable();
                            active_thread.store(true, Ordering::Relaxed);
                            let _ = tx.send(Ok(runloop.clone()));
                            // Blocks until CFRunLoopStop from HotkeyTap::stop.
                            CFRunLoop::run_current();
                            unsafe {
                                runloop.remove_source(&runloop_source, kCFRunLoopCommonModes)
                            };
                            active_thread.store(false, Ordering::Relaxed);
                            // `tap` (and its mach port) drops here, which
                            // deregisters it from the HID event stream.
                        }
                        Err(()) => {
                            // Typically: not trusted for Accessibility.
                            eprintln!(
                                "[Halbert] HUD hotkey tap could not be created; \
                                 grant Accessibility access to Halbert to enable Esc/Space"
                            );
                            let _ = tx.send(Err(()));
                        }
                    }
                })
                .map_err(|_| HotkeyError::TapCreationFailed)?;

            match rx.recv_timeout(Duration::from_secs(5)) {
                Ok(Ok(runloop)) => Ok(HotkeyTap {
                    thread: Some(thread),
                    runloop: Some(SendRunLoop(runloop)),
                    active,
                }),
                Ok(Err(())) | Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => {
                    let _ = thread.join();
                    Err(HotkeyError::TapCreationFailed)
                }
                Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {
                    // The thread never reported in; leave it be and fail.
                    Err(HotkeyError::TapCreationFailed)
                }
            }
        }

        /// Deregister the tap and join its thread.
        pub fn stop(mut self) {
            if let Some(runloop) = self.runloop.take() {
                runloop.0.stop();
            }
            if let Some(thread) = self.thread.take() {
                let _ = thread.join();
            }
            self.active.store(false, Ordering::Relaxed);
        }

        pub fn is_active(&self) -> bool {
            self.active.load(Ordering::Relaxed)
        }
    }

    fn dispatch(
        app: &tauri::AppHandle,
        action: HotkeyAction,
        visible: &AtomicBool,
    ) {
        match action {
            HotkeyAction::DismissPanel => {
                // Rust owns the dismissal so the panel and the shared
                // visibility flag can never desync; the webview still gets
                // the event so it can stop playback / finalise state.
                visible.store(false, Ordering::Relaxed);
                if let Some(window) = app.get_webview_window(HUD_WINDOW_LABEL) {
                    let _ = window.hide();
                }
                let _ = app.emit_to(
                    HUD_WINDOW_LABEL,
                    "voice-hud:hotkey",
                    HotkeyEvent {
                        key: "escape".into(),
                        action: "dismiss".into(),
                    },
                );
            }
            HotkeyAction::InterruptPlayback => {
                let _ = app.emit_to(
                    HUD_WINDOW_LABEL,
                    "voice-hud:hotkey",
                    HotkeyEvent {
                        key: "space".into(),
                        action: "interrupt".into(),
                    },
                );
            }
            HotkeyAction::None => {}
        }
    }
}

#[cfg(not(target_os = "macos"))]
mod stub {
    use super::HotkeyError;
    use std::sync::atomic::AtomicBool;
    use std::sync::Arc;

    /// Non-macOS builds have no CGEventTap; the floating HUD falls back to
    /// plain window focus for keys.
    pub struct HotkeyTap;

    impl HotkeyTap {
        pub fn start(
            _app: &tauri::AppHandle,
            _panel_visible: Arc<AtomicBool>,
        ) -> Result<Self, HotkeyError> {
            Err(HotkeyError::Unsupported)
        }

        pub fn stop(self) {}

        pub fn is_active(&self) -> bool {
            false
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{classify_keycode, decide_hotkey, HudKey, HotkeyAction, KVK_ESCAPE, KVK_SPACE};

    #[test]
    fn escape_and_space_are_classified() {
        assert_eq!(classify_keycode(KVK_ESCAPE), HudKey::Dismiss);
        assert_eq!(classify_keycode(KVK_SPACE), HudKey::Interrupt);
        assert_eq!(classify_keycode(0), HudKey::Other);
        assert_eq!(classify_keycode(36), HudKey::Other); // Return
    }

    #[test]
    fn hidden_panel_never_swallows() {
        for key in [HudKey::Dismiss, HudKey::Interrupt, HudKey::Other] {
            let (swallow, action) = decide_hotkey(key, false, false);
            assert!(!swallow);
            assert_eq!(action, HotkeyAction::None);
        }
    }

    #[test]
    fn visible_panel_acts_on_first_press_only() {
        let (swallow, action) = decide_hotkey(HudKey::Dismiss, true, false);
        assert!(swallow);
        assert_eq!(action, HotkeyAction::DismissPanel);

        let (swallow, action) = decide_hotkey(HudKey::Interrupt, true, false);
        assert!(swallow);
        assert_eq!(action, HotkeyAction::InterruptPlayback);
    }

    #[test]
    fn visible_panel_swallows_repeats_without_acting() {
        // A held key must not machine-gun interrupt events, but the repeats
        // still may not leak into the background IDE.
        let (swallow, action) = decide_hotkey(HudKey::Interrupt, true, true);
        assert!(swallow);
        assert_eq!(action, HotkeyAction::None);
        let (swallow, action) = decide_hotkey(HudKey::Dismiss, true, true);
        assert!(swallow);
        assert_eq!(action, HotkeyAction::None);
    }

    #[test]
    fn other_keys_always_pass_through() {
        let (swallow, action) = decide_hotkey(HudKey::Other, true, false);
        assert!(!swallow);
        assert_eq!(action, HotkeyAction::None);
    }
}