// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
//! Microphone capture with optional software acoustic echo cancellation (AEC).
//!
//! Implements the desktop ingress of the audio workstream (T2.3/T2.4 in
//! `.handoff/audio/04-PHASED-WORK-BREAKDOWN.md`): a `cpal` input stream is
//! resampled/downmixed to 16 kHz mono, run through WebRTC's AudioProcessing
//! echo canceller (when compiled with the `aec` feature) and dispatched as
//! 16-bit little-endian PCM to every client connected to a loopback TCP
//! socket, which the Python backend (`halbert_core/audio/ingress/`) reads.
//!
//! Wire protocol: a TCP listener on `127.0.0.1:<port>` streams raw
//! 16 kHz / 16-bit / mono LE PCM. When AEC is compiled, a second listener on
//! `port + 1` accepts the echo reference: 16 kHz / mono / f32 LE samples of
//! what is being sent to the speakers (Piper TTS output). The reference can
//! also be pushed from the webview via the `feed_tts_reference` command.
//!
//! Both features are opt-in (`voice-capture`, `aec` in Cargo.toml) so default
//! builds stay free of audio-hardware backends. Without the features the
//! commands below still exist and answer with a clear "not compiled" error,
//! letting the frontend degrade gracefully.

use serde::Serialize;
#[cfg(feature = "voice-capture")]
use std::sync::Mutex;

/// Sample rate every consumer of the loopback socket expects.
#[cfg(any(feature = "voice-capture", test))]
pub const TARGET_SAMPLE_RATE: u32 = 16_000;
/// APM frame length: 10 ms at [`TARGET_SAMPLE_RATE`].
#[cfg(any(feature = "voice-capture", test))]
pub const TARGET_FRAME_SAMPLES: usize = TARGET_SAMPLE_RATE as usize / 100;
/// Default loopback port for the AEC'd capture stream. The echo reference
/// (TTS) listener, when compiled, binds to `port + 1`.
#[cfg(any(feature = "voice-capture", test))]
pub const DEFAULT_AUDIO_PORT: u16 = 18400;

/// Pure sample-format helpers: always unit-testable (kept in `test` builds
/// and in `voice-capture` builds; other builds exclude them as dead code).
#[cfg(any(feature = "voice-capture", test))]
pub mod dsp {
    /// Interleaved input downmixed to mono by averaging all channels.
    /// `channels == 0` yields silence; `channels == 1` copies.
    pub fn downmix_to_mono(input: &[f32], channels: usize) -> Vec<f32> {
        if channels == 0 {
            return Vec::new();
        }
        if channels == 1 {
            return input.to_vec();
        }
        input
            .chunks(channels)
            .map(|frame| frame.iter().sum::<f32>() / channels as f32)
            .collect()
    }

    /// Clamp-and-scale an f32 sample to 16-bit PCM range.
    pub fn f32_to_i16(sample: f32) -> i16 {
        (sample.clamp(-1.0, 1.0) * 32_767.0) as i16
    }

    /// Stateful linear resampler from an arbitrary source rate to
    /// [`super::TARGET_SAMPLE_RATE`].
    ///
    /// Holds back the last sample of each block so output can interpolate
    /// across block boundaries; the internal buffer stays bounded no matter
    /// how the input is chunked.
    pub struct LinearResampler {
        step: f64,
        pos: f64,
        buf: Vec<f32>,
    }

    impl LinearResampler {
        pub fn new(src_rate: u32) -> Self {
            Self {
                step: f64::from(src_rate) / f64::from(super::TARGET_SAMPLE_RATE),
                pos: 0.0,
                buf: Vec::new(),
            }
        }

        /// Feed `input` and take all fully-interpolatable output samples.
        pub fn process(&mut self, input: &[f32]) -> Vec<f32> {
            self.buf.extend_from_slice(input);
            let mut out = Vec::new();
            loop {
                // Need the sample at floor(pos) and floor(pos)+1.
                let hi = self.pos.floor() as usize + 1;
                if hi >= self.buf.len() {
                    break;
                }
                let lo = hi - 1;
                let frac = (self.pos - lo as f64) as f32;
                let s0 = self.buf[lo];
                let s1 = self.buf[hi];
                out.push(s0 + (s1 - s0) * frac);
                self.pos += self.step;
            }
            // `pos` may overshoot the buffer end by more than one sample
            // (step > 1 skips anchor samples that no output will need), so
            // clamp: everything drained is either consumed or skipped.
            let consumed = (self.pos.floor() as usize).min(self.buf.len());
            self.buf.drain(..consumed);
            self.pos -= consumed as f64;
            out
        }
    }

    /// Buffers samples and hands them out as fixed-size frames (e.g. the
    /// 160-sample / 10 ms frames WebRTC's AudioProcessing expects).
    pub struct FrameChunker {
        frame_len: usize,
        buf: Vec<f32>,
    }

    impl FrameChunker {
        pub fn new(frame_len: usize) -> Self {
            assert!(frame_len > 0);
            Self {
                frame_len,
                buf: Vec::with_capacity(frame_len),
            }
        }

        pub fn push(&mut self, samples: &[f32]) {
            self.buf.extend_from_slice(samples);
        }

        /// Copy out the next complete frame, if any.
        pub fn pop_frame(&mut self) -> Option<Vec<f32>> {
            if self.buf.len() < self.frame_len {
                return None;
            }
            Some(self.buf.drain(..self.frame_len).collect())
        }
    }
}

/// Status snapshot shared by all capture commands.
#[derive(Serialize, Clone, Debug, Default, PartialEq)]
pub struct AudioCaptureStatus {
    pub running: bool,
    /// Whether this binary was compiled with the `aec` feature.
    pub aec_compiled: bool,
    /// Whether an echo canceller is actually running on the capture path.
    pub aec_active: bool,
    pub muted: bool,
    pub port: Option<u16>,
    /// Loopback port for the TTS echo reference (AEC builds only).
    pub reference_port: Option<u16>,
    pub host_sample_rate: Option<u32>,
    pub host_channels: Option<u16>,
    /// Connected PCM consumers.
    pub clients: usize,
    /// Frames dropped because no consumer kept up.
    pub dropped_frames: u64,
}

/// Managed state: the running capture, if any.
#[cfg(feature = "voice-capture")]
pub struct AudioCaptureState(Mutex<Option<engine::ActiveCapture>>);
#[cfg(not(feature = "voice-capture"))]
pub struct AudioCaptureState;

impl AudioCaptureState {
    pub fn new() -> Self {
        #[cfg(feature = "voice-capture")]
        {
            Self(Mutex::new(None))
        }
        #[cfg(not(feature = "voice-capture"))]
        {
            Self
        }
    }
}

impl Default for AudioCaptureState {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// Capture engine (only with the `voice-capture` feature)
// ---------------------------------------------------------------------------

#[cfg(feature = "voice-capture")]
mod engine {
    use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
    use cpal::FromSample;
    use super::dsp::{self, FrameChunker, LinearResampler};
    use super::{AudioCaptureStatus, TARGET_FRAME_SAMPLES, TARGET_SAMPLE_RATE};
    use std::io::Write;
    #[cfg(feature = "aec")]
    use std::io::Read;
    use std::net::{TcpListener, TcpStream};
    use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
    use std::sync::mpsc::{sync_channel, SyncSender};
    use std::sync::{Arc, Mutex};
    use std::thread::JoinHandle;
    use std::time::Duration;

    /// Everything a running capture owns. Dropping it stops the stream and
    /// the worker threads.
    pub struct ActiveCapture {
        pub port: u16,
        pub host_sample_rate: u32,
        pub host_channels: u16,
        pub muted: Arc<AtomicBool>,
        dropped_frames: Arc<AtomicU64>,
        clients: Arc<Mutex<Vec<TcpStream>>>,
        stop: Arc<AtomicBool>,
        stream: Option<cpal::Stream>,
        accept_thread: Option<JoinHandle<()>>,
        writer_thread: Option<JoinHandle<()>>,
        #[cfg(feature = "aec")]
        pub aec: Option<Arc<webrtc_audio_processing::Processor>>,
        #[cfg(feature = "aec")]
        pub reference_port: Option<u16>,
        #[cfg(feature = "aec")]
        reference_thread: Option<JoinHandle<()>>,
    }

    impl Drop for ActiveCapture {
        fn drop(&mut self) {
            self.stop.store(true, Ordering::Relaxed);
            // Dropping the stream first stops the realtime callback so the
            // writer channel drains instead of erroring on a full buffer.
            self.stream.take();
            if let Some(t) = self.accept_thread.take() {
                let _ = t.join();
            }
            if let Some(t) = self.writer_thread.take() {
                let _ = t.join();
            }
            #[cfg(feature = "aec")]
            if let Some(t) = self.reference_thread.take() {
                let _ = t.join();
            }
        }
    }

    /// Create the WebRTC AudioProcessing echo canceller for the capture path.
    #[cfg(feature = "aec")]
    fn make_aec_processor() -> Result<webrtc_audio_processing::Processor, String> {
        let apm = webrtc_audio_processing::Processor::new(TARGET_SAMPLE_RATE)
            .map_err(|e| format!("AEC initialisation failed: {e:?}"))?;
        // Echo cancellation plus a high-pass filter; the rest (AGC, NS) stays
        // off so the pipeline only removes what we know causes harm.
        let config = webrtc_audio_processing::Config {
            echo_canceller: Some(Default::default()),
            high_pass_filter: Some(Default::default()),
            ..Default::default()
        };
        apm.set_config(config);
        Ok(apm)
    }

    /// State shared between the realtime callback and the command surface.
    #[derive(Clone)]
    struct CallbackShared {
        muted: Arc<AtomicBool>,
        dropped_frames: Arc<AtomicU64>,
        tx: SyncSender<Vec<i16>>,
    }

    /// Build the cpal input stream for one concrete sample type.
    fn build_capture_stream<T>(
        device: &cpal::Device,
        config: cpal::StreamConfig,
        channels: usize,
        shared: CallbackShared,
        #[cfg(feature = "aec")] aec: Option<Arc<webrtc_audio_processing::Processor>>,
    ) -> Result<cpal::Stream, String>
    where
        T: cpal::SizedSample,
        f32: cpal::FromSample<T>,
    {
        let CallbackShared {
            muted,
            dropped_frames,
            tx,
        } = shared;
        let mut resampler = LinearResampler::new(config.sample_rate);
        let mut chunker = FrameChunker::new(TARGET_FRAME_SAMPLES);
        #[cfg(feature = "aec")]
        let mut aec_frame = aec.map(|apm| {
            (
                apm,
                vec![vec![0.0f32; TARGET_FRAME_SAMPLES]],
            )
        });

        device
            .build_input_stream::<T, _, _>(
                config,
                move |data: &[T], _info: &cpal::InputCallbackInfo| {
                    // Realtime context: allocations kept small and no
                    // blocking calls. The heavy lifting (TCP) happens on the
                    // writer thread via the bounded channel below.
                    let floats: Vec<f32> =
                        data.iter().map(|s| f32::from_sample_(*s)).collect();
                    let mono = dsp::downmix_to_mono(&floats, channels);
                    let resampled = resampler.process(&mono);
                    chunker.push(&resampled);
                    while let Some(frame) = chunker.pop_frame() {
                        if muted.load(Ordering::Relaxed) {
                            // Muted mic: emit silence so consumers stay frame
                            // aligned, without feeding zeros into the AEC
                            // (that would corrupt its adaptive state).
                            if tx.try_send(vec![0; TARGET_FRAME_SAMPLES]).is_err() {
                                dropped_frames.fetch_add(1, Ordering::Relaxed);
                            }
                            continue;
                        }
                        // Only the AEC path mutates the frame in place.
                        #[cfg(feature = "aec")]
                        let mut frame = frame;
                        #[cfg(feature = "aec")]
                        if let Some((apm, buffer)) = aec_frame.as_mut() {
                            buffer[0].copy_from_slice(&frame);
                            // Reborrow: `process_capture_frame` takes the
                            // frame by value; moving `buffer` would end its
                            // borrow for this callback invocation.
                            if let Err(e) = apm.process_capture_frame(&mut *buffer) {
                                eprintln!("[Halbert] AEC process error: {e:?}");
                            }
                            frame.copy_from_slice(&buffer[0]);
                        }
                        let pcm: Vec<i16> = frame.iter().map(|s| dsp::f32_to_i16(*s)).collect();
                        if tx.try_send(pcm).is_err() {
                            dropped_frames.fetch_add(1, Ordering::Relaxed);
                        }
                    }
                },
                |err| eprintln!("[Halbert] audio capture error: {err}"),
                None,
            )
            .map_err(|e| format!("failed to build input stream: {e}"))
    }

    /// Start capture. Binds the loopback PCM socket (and, with AEC, the
    /// echo-reference socket on `port + 1`) before the audio stream so
    /// consumers can never miss the first frames.
    pub fn start(port: u16) -> Result<ActiveCapture, String> {
        let host = cpal::default_host();
        let device = host
            .default_input_device()
            .ok_or("no default input device available")?;
        let supported = device
            .default_input_config()
            .map_err(|e| format!("no usable default input config: {e}"))?;
        let sample_rate = supported.sample_rate();
        let channels = supported.channels();
        if channels == 0 {
            return Err("input device reports zero channels".into());
        }
        let config = cpal::StreamConfig {
            channels,
            sample_rate: supported.sample_rate(),
            buffer_size: cpal::BufferSize::Default,
        };

        let listener =
            TcpListener::bind(("127.0.0.1", port)).map_err(|e| format!("bind 127.0.0.1:{port}: {e}"))?;
        let port = listener
            .local_addr()
            .map_err(|e| format!("local_addr: {e}"))?
            .port();
        listener
            .set_nonblocking(true)
            .map_err(|e| format!("listener nonblocking: {e}"))?;

        #[cfg(feature = "aec")]
        let (reference_port, reference_listener) = {
            if port == u16::MAX {
                return Err("capture port 65535 leaves no room for the AEC reference socket".into());
            }
            let l = TcpListener::bind(("127.0.0.1", port + 1))
                .map_err(|e| format!("bind reference socket 127.0.0.1:{}: {e}", port + 1))?;
            (Some(port + 1), l)
        };

        // APM before the stream so a failure to initialise AEC aborts before
        // any audio flows.
        #[cfg(feature = "aec")]
        let aec = Some(Arc::new(make_aec_processor()?));

        let (tx, rx) = sync_channel::<Vec<i16>>(64);
        let muted = Arc::new(AtomicBool::new(false));
        let dropped_frames = Arc::new(AtomicU64::new(0));
        let clients: Arc<Mutex<Vec<TcpStream>>> = Arc::new(Mutex::new(Vec::new()));
        let stop = Arc::new(AtomicBool::new(false));

        let shared = CallbackShared {
            muted: Arc::clone(&muted),
            dropped_frames: Arc::clone(&dropped_frames),
            tx: tx.clone(),
        };
        let stream = match supported.sample_format() {
            cpal::SampleFormat::F32 => build_capture_stream::<f32>(
                &device,
                config.clone(),
                channels as usize,
                shared,
                #[cfg(feature = "aec")]
                aec.clone(),
            )?,
            cpal::SampleFormat::I16 => build_capture_stream::<i16>(
                &device,
                config.clone(),
                channels as usize,
                shared,
                #[cfg(feature = "aec")]
                aec.clone(),
            )?,
            cpal::SampleFormat::U16 => build_capture_stream::<u16>(
                &device,
                config.clone(),
                channels as usize,
                shared,
                #[cfg(feature = "aec")]
                aec.clone(),
            )?,
            other => return Err(format!("unsupported input sample format: {other:?}")),
        };

        // Accept loop: registers PCM consumers.
        let accept_thread = {
            let clients = Arc::clone(&clients);
            let stop = Arc::clone(&stop);
            std::thread::Builder::new()
                .name("halbert-audio-accept".into())
                .spawn(move || loop {
                    if stop.load(Ordering::Relaxed) {
                        break;
                    }
                    match listener.accept() {
                        Ok((socket, addr)) => {
                            let _ = socket.set_nodelay(true);
                            println!("[Halbert] audio capture client connected: {addr}");
                            clients.lock().unwrap().push(socket);
                        }
                        Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                            std::thread::sleep(Duration::from_millis(25));
                        }
                        Err(e) => {
                            eprintln!("[Halbert] audio accept error: {e}");
                            break;
                        }
                    }
                })
                .map_err(|e| format!("spawn accept thread: {e}"))?
        };

        // Writer loop: drains AEC'd frames to every consumer.
        let writer_thread = {
            let clients = Arc::clone(&clients);
            let stop = Arc::clone(&stop);
            std::thread::Builder::new()
                .name("halbert-audio-writer".into())
                .spawn(move || {
                    let mut bytes: Vec<u8> = Vec::with_capacity(TARGET_FRAME_SAMPLES * 2);
                    loop {
                        if stop.load(Ordering::Relaxed) {
                            break;
                        }
                        match rx.recv_timeout(Duration::from_millis(100)) {
                            Ok(frame) => {
                                bytes.clear();
                                for sample in frame {
                                    bytes.extend_from_slice(&sample.to_le_bytes());
                                }
                                let mut guard = clients.lock().unwrap();
                                guard.retain_mut(|socket| socket.write_all(&bytes).is_ok());
                            }
                            Err(std::sync::mpsc::RecvTimeoutError::Timeout) => continue,
                            Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => break,
                        }
                    }
                })
                .map_err(|e| format!("spawn writer thread: {e}"))?
        };

        // AEC reference reader: the backend streams the TTS output here.
        #[cfg(feature = "aec")]
        let reference_thread = {
            let aec = aec.clone();
            let stop = Arc::clone(&stop);
            let listener = reference_listener;
            std::thread::Builder::new()
                .name("halbert-audio-reference".into())
                .spawn(move || {
                    let apm = match aec {
                        Some(apm) => apm,
                        None => return,
                    };
                    if let Err(e) = listener.set_nonblocking(true) {
                        eprintln!("[Halbert] reference listener: {e}");
                        return;
                    }
                    // `apm` is used by `read_reference` for every accepted
                    // feeder connection below.
                    loop {
                        if stop.load(Ordering::Relaxed) {
                            break;
                        }
                        match listener.accept() {
                            Ok((mut socket, addr)) => {
                                println!("[Halbert] AEC reference feeder connected: {addr}");
                                read_reference(&mut socket, &apm);
                            }
                            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                                std::thread::sleep(Duration::from_millis(50));
                            }
                            Err(e) => {
                                eprintln!("[Halbert] reference accept error: {e}");
                                break;
                            }
                        }
                    }
                })
                .map_err(|e| format!("spawn reference thread: {e}"))?
        };

        stream
            .play()
            .map_err(|e| format!("failed to start input stream: {e}"))?;
        #[cfg(feature = "aec")]
        let aec_note = format!(
            " (AEC reference on 127.0.0.1:{})",
            reference_port.unwrap_or(0)
        );
        #[cfg(not(feature = "aec"))]
        let aec_note = String::new();
        println!(
            "[Halbert] audio capture: {sample_rate} Hz / {channels}ch -> {TARGET_SAMPLE_RATE} Hz mono on 127.0.0.1:{port}{aec_note}"
        );

        Ok(ActiveCapture {
            port,
            host_sample_rate: sample_rate,
            host_channels: channels,
            muted,
            dropped_frames,
            clients,
            stop,
            stream: Some(stream),
            accept_thread: Some(accept_thread),
            writer_thread: Some(writer_thread),
            #[cfg(feature = "aec")]
            aec,
            #[cfg(feature = "aec")]
            reference_port,
            #[cfg(feature = "aec")]
            reference_thread: Some(reference_thread),
        })
    }

    /// Push TTS output (16 kHz / mono / f32) through the echo canceller's
    /// render path. Accepts any chunking; a trailing partial frame is
    /// dropped (callers should push whole multiples of 10 ms).
    #[cfg(feature = "aec")]
    pub fn feed_reference(
        capture: &ActiveCapture,
        samples: &[f32],
    ) -> Result<usize, String> {
        let apm = capture
            .aec
            .as_ref()
            .ok_or("AEC is compiled but no echo canceller is active")?;
        let mut frames = 0;
        let mut iter = samples.chunks_exact(TARGET_FRAME_SAMPLES);
        for chunk in &mut iter {
            let mut frame = vec![chunk.to_vec()];
            apm.process_render_frame(&mut frame)
                .map_err(|e| format!("AEC render error: {e:?}"))?;
            frames += 1;
        }
        Ok(frames)
    }

    /// Read one reference connection, chunking bytes into 160-sample f32 LE
    /// frames and pushing them through the render path.
    #[cfg(feature = "aec")]
    fn read_reference(socket: &mut TcpStream, apm: &webrtc_audio_processing::Processor) {
        let frame_bytes = TARGET_FRAME_SAMPLES * 4;
        let mut bytes = Vec::with_capacity(frame_bytes);
        let mut chunk = [0u8; 4096];
        loop {
            match socket.read(&mut chunk) {
                Ok(0) => break,
                Ok(n) => {
                    bytes.extend_from_slice(&chunk[..n]);
                    while bytes.len() >= frame_bytes {
                        let frame: Vec<f32> = bytes[..frame_bytes]
                            .chunks_exact(4)
                            .map(|b| f32::from_le_bytes([b[0], b[1], b[2], b[3]]))
                            .collect();
                        let mut frame = vec![frame];
                        if let Err(e) = apm.process_render_frame(&mut frame) {
                            eprintln!("[Halbert] AEC render error: {e:?}");
                        }
                        bytes.drain(..frame_bytes);
                    }
                }
                Err(e) => {
                    eprintln!("[Halbert] AEC reference read error: {e}");
                    break;
                }
            }
        }
    }

    pub fn status(capture: &ActiveCapture) -> AudioCaptureStatus {
        AudioCaptureStatus {
            running: true,
            aec_compiled: cfg!(feature = "aec"),
            #[cfg(feature = "aec")]
            aec_active: capture.aec.is_some(),
            #[cfg(not(feature = "aec"))]
            aec_active: false,
            muted: capture.muted.load(Ordering::Relaxed),
            port: Some(capture.port),
            #[cfg(feature = "aec")]
            reference_port: capture.reference_port,
            #[cfg(not(feature = "aec"))]
            reference_port: None,
            host_sample_rate: Some(capture.host_sample_rate),
            host_channels: Some(capture.host_channels),
            clients: capture.clients.lock().unwrap().len(),
            dropped_frames: capture.dropped_frames.load(Ordering::Relaxed),
        }
    }
}

// ---------------------------------------------------------------------------
// Tauri command surface (always compiled; graceful without the features)
// ---------------------------------------------------------------------------

#[tauri::command]
pub fn start_audio_capture(
    state: tauri::State<'_, AudioCaptureState>,
    port: Option<u16>,
) -> Result<AudioCaptureStatus, String> {
    #[cfg(feature = "voice-capture")]
    {
        let mut guard = state.0.lock().unwrap();
        if let Some(active) = guard.as_ref() {
            // Idempotent: report the running capture instead of failing.
            return Ok(engine::status(active));
        }
        let active = engine::start(port.unwrap_or(DEFAULT_AUDIO_PORT))?;
        let status = engine::status(&active);
        *guard = Some(active);
        Ok(status)
    }
    #[cfg(not(feature = "voice-capture"))]
    {
        let _ = (state, port);
        Err("voice capture is not compiled into this build \
             (rebuild with --features voice-capture or aec)"
            .into())
    }
}

#[tauri::command]
pub fn stop_audio_capture(
    state: tauri::State<'_, AudioCaptureState>,
) -> Result<AudioCaptureStatus, String> {
    #[cfg(feature = "voice-capture")]
    {
        let mut guard = state.0.lock().unwrap();
        guard.take(); // Drop stops the stream and worker threads.
        Ok(AudioCaptureStatus::default())
    }
    #[cfg(not(feature = "voice-capture"))]
    {
        let _ = state;
        Err("voice capture is not compiled into this build \
             (rebuild with --features voice-capture or aec)"
            .into())
    }
}

#[tauri::command]
pub fn set_mic_muted(
    state: tauri::State<'_, AudioCaptureState>,
    muted: bool,
) -> Result<AudioCaptureStatus, String> {
    #[cfg(feature = "voice-capture")]
    {
        let guard = state.0.lock().unwrap();
        match guard.as_ref() {
            Some(active) => {
                active.muted.store(muted, std::sync::atomic::Ordering::Relaxed);
                Ok(engine::status(active))
            }
            None => Err("audio capture is not running".into()),
        }
    }
    #[cfg(not(feature = "voice-capture"))]
    {
        let _ = (state, muted);
        Err("voice capture is not compiled into this build \
             (rebuild with --features voice-capture or aec)"
            .into())
    }
}

#[tauri::command]
pub fn get_audio_capture_status(
    state: tauri::State<'_, AudioCaptureState>,
) -> AudioCaptureStatus {
    #[cfg(feature = "voice-capture")]
    {
        let guard = state.0.lock().unwrap();
        match guard.as_ref() {
            Some(active) => engine::status(active),
            None => AudioCaptureStatus::default(),
        }
    }
    #[cfg(not(feature = "voice-capture"))]
    {
        let _ = state;
        AudioCaptureStatus {
            aec_compiled: false,
            ..Default::default()
        }
    }
}

/// Push TTS output (16 kHz / mono / f32) into the echo canceller as the
/// far-end reference, so barge-in works while Halbert speaks. Returns the
/// number of 10 ms frames accepted.
#[tauri::command]
pub fn feed_tts_reference(
    state: tauri::State<'_, AudioCaptureState>,
    samples: Vec<f32>,
) -> Result<u32, String> {
    #[cfg(all(feature = "voice-capture", feature = "aec"))]
    {
        let guard = state.0.lock().unwrap();
        match guard.as_ref() {
            Some(active) => Ok(engine::feed_reference(active, &samples)? as u32),
            None => Err("audio capture is not running".into()),
        }
    }
    #[cfg(not(all(feature = "voice-capture", feature = "aec")))]
    {
        let _ = (state, samples);
        Err("AEC is not compiled into this build (rebuild with --features aec)".into())
    }
}

#[cfg(test)]
mod tests {
    use super::dsp::{downmix_to_mono, f32_to_i16, FrameChunker, LinearResampler};
    use super::{AudioCaptureStatus, DEFAULT_AUDIO_PORT, TARGET_FRAME_SAMPLES, TARGET_SAMPLE_RATE};

    #[test]
    fn downmix_averages_channels() {
        assert_eq!(downmix_to_mono(&[1.0, -1.0, 0.5, 0.5, 2.0, 0.0], 2), vec![0.0, 0.5, 1.0]);
        assert_eq!(downmix_to_mono(&[0.25, 0.75], 1), vec![0.25, 0.75]);
        assert!(downmix_to_mono(&[1.0, 2.0], 0).is_empty());
    }

    #[test]
    fn f32_to_i16_clamps_out_of_range() {
        assert_eq!(f32_to_i16(0.0), 0);
        assert_eq!(f32_to_i16(1.5), 32_767);
        assert_eq!(f32_to_i16(-1.5), -32_767);
        assert_eq!(f32_to_i16(0.5), 16_383);
    }

    #[test]
    fn resampler_downsamples_by_the_rate_ratio() {
        let mut r = LinearResampler::new(48_000);
        let input: Vec<f32> = (0..4_800).map(|i| i as f32).collect();
        let out = r.process(&input);
        // 3:1 downsampling, +-1 for interpolation latency.
        let expected = 4_800 * TARGET_SAMPLE_RATE as usize / 48_000;
        assert!((out.len() as i64 - expected as i64).abs() <= 1);
    }

    #[test]
    fn resampler_is_chunking_independent() {
        let input: Vec<f32> = (0..9_600).map(|i| (i as f32 * 0.01).sin()).collect();
        let mut whole = LinearResampler::new(44_100);
        let out_whole = whole.process(&input);
        let mut pieced = LinearResampler::new(44_100);
        let mut out_pieced = Vec::new();
        for chunk in input.chunks(37) {
            out_pieced.extend(pieced.process(chunk));
        }
        assert_eq!(out_whole.len(), out_pieced.len());
        for (a, b) in out_whole.iter().zip(out_pieced.iter()) {
            assert!((a - b).abs() < 1e-5);
        }
    }

    #[test]
    fn resampler_handles_empty_and_short_input() {
        let mut r = LinearResampler::new(44_100);
        assert!(r.process(&[]).is_empty());
        assert!(r.process(&[1.0]).is_empty());
        let out = r.process(&[0.0, 1.0, 2.0, 3.0, 4.0, 5.0]);
        assert!(!out.is_empty());
    }

    #[test]
    fn chunker_emits_only_complete_frames_and_keeps_remainders() {
        let mut c = FrameChunker::new(TARGET_FRAME_SAMPLES);
        c.push(&[0.0; 100]);
        assert!(c.pop_frame().is_none());
        c.push(&[0.0; 100]);
        // 200 buffered, still < 160? no: 200 >= 160 -> one frame, 40 left.
        let frame = c.pop_frame().expect("200 >= 160");
        assert_eq!(frame.len(), TARGET_FRAME_SAMPLES);
        assert!(c.pop_frame().is_none());
        c.push(&[7.0; 120]);
        // 40 leftovers (zeros) + 120 new = 160 -> exactly one more frame.
        let frame = c.pop_frame().expect("40 + 120 = 160");
        assert_eq!(frame.len(), TARGET_FRAME_SAMPLES);
        assert_eq!(frame[0], 0.0); // leftover from the first push pair
        assert_eq!(frame[TARGET_FRAME_SAMPLES - 1], 7.0);
        assert!(c.pop_frame().is_none());
    }

    #[test]
    fn status_defaults_to_stopped() {
        let status = AudioCaptureStatus::default();
        assert!(!status.running);
        assert!(!status.aec_compiled);
        assert_eq!(status.port, None);
        assert_eq!(status.clients, 0);
    }

    #[test]
    fn default_port_is_in_the_unprivileged_range() {
        assert!(DEFAULT_AUDIO_PORT >= 1024);
    }

    #[test]
    fn frame_length_is_ten_ms() {
        assert_eq!(TARGET_FRAME_SAMPLES, (TARGET_SAMPLE_RATE as usize) / 100);
    }
}