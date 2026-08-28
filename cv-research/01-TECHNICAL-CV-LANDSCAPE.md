# Technical CV Landscape: Real-Time Computer Vision for AI Assistants

> **Research Document for Halbert** - Homelab Sysadmin AI Assistant
> macOS + Linux | Tauri (React + Python FastAPI) | Existing `vision_model` LLM config slot
> Date: 2025

---

## Table of Contents

1. [Real-Time CV Frameworks and Tooling](#1-real-time-cv-frameworks-and-tooling)
2. [Whitepapers and Academic Research](#2-whitepapers-and-academic-research)
3. [Architecture Paths for Integrating CV into an AI Assistant](#3-architecture-paths-for-integrating-cv-into-an-ai-assistant)
4. [Existing Products Doing This](#4-existing-products-doing-this)
5. [Tooling Recommendations for Halbert](#5-tooling-recommendations-for-halbert)
6. [References](#6-references)

---

## 1. Real-Time CV Frameworks and Tooling

### 1.1 OpenCV - The Foundation Layer

OpenCV is the de facto standard for real-time video capture and processing in Python. It provides the lowest-level building blocks for any CV pipeline.

**Key Capabilities:**
- `cv2.VideoCapture()` for webcam/stream capture (supports RTSP, RTMP, file, device indices)
- Frame-by-frame processing loops with `cap.read()`
- Image transforms: resize, color conversion, Gaussian blur, thresholding
- `cv2.VideoWriter()` for recording processed output
- Integration with NumPy for array manipulation

**Performance Characteristics:**
- Webcam capture at 30+ FPS is standard on modern hardware
- Processing overhead depends on pipeline stages (resize, denoise, inference)
- The **producer-consumer pattern** is critical for real-time pipelines: separate frame capture (producer thread) from processing (consumer thread) via a thread-safe queue to prevent frame drops and UI freezes
- Use `collections.deque(maxlen=N)` instead of `queue.Queue` for atomic frame overwrites (always keeps freshest frame, drops oldest automatically)
- `qsize()` is unreliable across platforms; track frame counts in both threads and log periodically

**Cross-Platform Notes:**
- Works on macOS, Linux, and Windows
- On macOS, camera access requires entitlements (privacy permissions)
- Linux uses V4L2 backend; macOS uses AVFoundation backend
- `cv2.VideoCapture(0)` may block on Windows if camera is held by another process

**Relevance to Halbert:**
OpenCV is the capture and preprocessing backbone. Even if higher-level frameworks (MediaPipe, YOLO) are used for inference, OpenCV handles the raw frame I/O, resizing, color conversion, and format encoding (JPEG/PNG) before passing frames to models or APIs.

**Sources:**
- OpenCV Video Processing Pipeline Guide: https://pyquesthub.com/implementing-a-video-processing-pipeline-with-opencv-in-python
- Producer-Consumer Pattern for Real-Time Video: https://theneuralbase.com/opencv/learn/advanced/producer-consumer-pattern/
- Vision Stream Toolkit (OpenCV wrapper): https://github.com/Jenil16/vision-stream-toolkit

---

### 1.2 MediaPipe - Google's On-Device Perception Stack

MediaPipe is Google's cross-platform, on-device ML framework for real-time perception. It is the most mature option for human-centric CV tasks (faces, hands, pose, gestures).

**Tasks Available (via `mediapipe` Python package / `@mediapipe/tasks-vision` JS):**

| Task | Landmarks/Output | Model Size | Use Case |
|------|-----------------|------------|----------|
| Hand Landmarker | 21 points/hand + handedness | ~6MB | Gesture control, interaction |
| Pose Landmarker | 33 body points (lite/full) | 4.1-9.4MB | Body tracking, activity detection |
| Face Landmarker | 478-point face mesh + blendshapes | ~6MB | Expression, attention tracking |
| Face Detector | Bounding boxes (BlazeFace) | 230KB | Fast face detection |
| Gesture Recognizer | 7 built-in hand gestures | ~8MB | Command triggers (thumbs_up, open_palm, etc.) |
| Object Detector | Bounding boxes + labels | Variable | Scene understanding |
| Image Classifier | Scene/object classification | Variable | Context awareness |
| Selfie Segmentation | Person/background mask | 250KB | Privacy masking, focus |
| Holistic Landmarker | 543 total landmarks (face+pose+hands) | Combined | Full-body analysis |

**Running Modes:**
- `IMAGE`: Single image inference
- `VIDEO`: Decoded video frames (batch)
- `LIVE_STREAM`: Real-time camera feed with async `result_listener` callback

**Performance:**
- Models are tiny (230KB to 9.4MB), download once and cache, run offline
- Runs on CPU, GPU, or via WebAssembly in browser
- Real-time at 30+ FPS on modern hardware for most tasks
- The Holistic Landmarker combines face (468), pose (33), left hand (21), right hand (21) = 543 landmarks in a single pass

**Cross-Platform:**
- Python: `pip install mediapipe` (works on macOS, Linux, Windows)
- JavaScript: `@mediapipe/tasks-vision` (runs in browser via WASM)
- C++: Available via MediaPipe framework
- Android/iOS: Native support via LiteRT (formerly TFLite)

**Relevance to Halbert:**
MediaPipe is ideal for the "lightweight on-device" tier. If Halbert needs to detect user presence, gestures (for hands-free commands), or facial expressions (for context), MediaPipe runs these locally with minimal resource usage. The gesture recognizer could enable "wave to dismiss" or "thumbs up to confirm" interactions. The face detector + blendshapes could power "is the user looking at the screen?" awareness.

**Sources:**
- MediaPipe Holistic Landmarker: https://developers.google.cn/edge/mediapipe/solutions/vision/holistic_landmarker
- MediaPipe Gesture Recognizer: https://developers.google.com/edge/mediapipe/solutions/vision/gesture_recognizer
- LocalMode MediaPipe (browser, privacy-focused): https://localmode.dev/blog/mediapipe-hand-pose-face-tracking-browser

---

### 1.3 YOLO Variants - Real-Time Object Detection

YOLO (You Only Look Once) is the dominant family for real-time object detection. The Ultralytics ecosystem (YOLOv8, YOLOv10, YOLO11/YOLO26) provides a unified Python API.

#### YOLOv8 (Ultralytics, 2023)
- Anchor-free detection head with CSPDarknet backbone
- Supports: object detection, instance segmentation, image classification, pose estimation, oriented bounding boxes (OBB)
- Unified `ultralytics` Python package: `from ultralytics import YOLO; model = YOLO("yolov8n.pt")`
- Variants: Nano (n), Small (s), Medium (m), Large (l), XLarge (x) - scaling from ~3M to ~68M parameters
- Massive versatility for multi-stage pipelines

#### YOLOv10 (Tsinghua University, May 2024)
- **Key innovation: NMS-free training** via Consistent Dual Assignments
- Eliminates non-maximum suppression post-processing, reducing inference latency
- One-to-many head for training (rich supervision), one-to-one head for inference (single best prediction, no NMS)
- YOLOv10-S is 1.8x faster than RT-DETR-R18 at similar AP, with 2.8x fewer parameters
- YOLOv10-B has 46% less latency and 25% fewer parameters than YOLOv9-C at same performance
- Published at NeurIPS 2024

#### YOLO11 / YOLO26 (Ultralytics, latest)
- YOLO26 further develops the NMS-free approach pioneered by YOLOv10
- Continued optimization for edge deployment

**Export Formats (critical for cross-platform deployment):**
- ONNX (for ONNX Runtime on macOS/Linux)
- CoreML (for Apple Neural Engine on macOS)
- LiteRT/TFLite (for mobile/edge)
- OpenVINO (for Intel hardware)
- TensorRT (for NVIDIA GPUs)

**Performance on Edge:**
- YOLOv10-N (nano): suitable for resource-constrained environments, runs on CPU
- INT8 quantization available for further speedup
- On Apple Silicon with CoreML EP: 5-10x speedup for fixed-shape CNN models vs CPU

**Relevance to Halbert:**
YOLOv8n or YOLOv10n (nano variants) can run locally for scene understanding - detecting monitors, keyboards, servers, network equipment, people in frame. For a sysadmin assistant, object detection could identify hardware components, read labels, or detect when someone is at the desk. Export to ONNX for cross-platform, or CoreML for macOS-native acceleration.

**Sources:**
- YOLOv8 vs YOLOv10 Comparison: https://docs.ultralytics.com/compare/yolov8-vs-yolov10
- YOLOv10 Paper (NeurIPS 2024): https://proceedings.neurips.cc/paper_files/paper/2024/file/c34ddd05eb089991f06f3c5dc36836e0-Paper-Conference.pdf
- YOLOv10 to LiteRT Tutorial: https://medium.com/google-developer-experts/yolov10-to-litert-object-detection-on-android-with-google-ai-edge-2d0de5619e71
- YOLOv10 Model Page: https://docs.ultralytics.com/models/yolov10

---

### 1.4 Apple Vision Framework (macOS-Native CV)

Apple's Vision framework ships 25+ on-device CV operations that run on the Neural Engine (ANE), GPU, or CPU. It is the local-first CV framework for macOS.

**Capabilities:**
- Text recognition (OCR) - over 30 languages, dense text, real-time
- Face detection and landmarks (eyes, nose, mouth)
- Body and hand pose estimation
- Barcode reading (QR, PDF417, Aztec, Code 128, EAN-13, etc.)
- Document segmentation
- Image embeddings / similarity
- Saliency detection
- Animal detection
- Contours and trajectories
- Optical flow (for video-based motion analysis)
- Tap-to-segment (WWDC 2026) - isolate any object by tapping
- Image aesthetics scoring
- Holistic body pose (WWDC 2024)
- Runner for any Core ML model

**Performance:**
- Runs in milliseconds on Neural Engine (100-300ms for most operations)
- Free per call, no API key, no network required
- Data never leaves the device
- "Often fast enough to analyze video frames in real time" (Apple WWDC 2026)

**API Design (WWDC 2024 Redesign):**
- Redesigned with modern Swift concurrency and Swift 6 support
- Request-based: `DetectFaceRectanglesRequest`, `RecognizeTextRequest`, `DetectFaceLandmarksRequest`, etc.
- Everything begins with a Vision "request" (a question about an image)
- Async/await native, performant pipeline construction

**Foundation Models Integration (WWDC 2026):**
- Apple Foundation Models framework now supports image inputs
- Combine Vision's OCR/barcode scanning with LLM-powered visual understanding
- Create image-based tools for LLMs that unlock deeper image understanding
- Vision is now available on watchOS as well

**Limitations:**
- macOS/iOS only (not available on Linux)
- Swift/Objective-C API (not directly callable from Python without bridges)
- For Python on macOS, can be accessed via `pyobjc` bridge or through ONNX Runtime's CoreML Execution Provider

**Relevance to Halbert:**
On macOS, Vision is the optimal choice for lightweight CV tasks (OCR, face detection, barcode scanning). For Halbert's Tauri app, the Python backend could use `pyobjc` to call Vision APIs, or the Tauri Rust layer could call them natively. However, this creates a platform-specific code path. The recommended approach: use Vision for macOS-specific optimizations (OCR, face detection) and fall back to OpenCV/MediaPipe on Linux.

**Sources:**
- Vision Framework Overview: https://blakecrosley.com/blog/vision-framework-built-in
- WWDC 2026 - Image Understanding: https://developer.apple.com/videos/play/wwdc2026/237/
- WWDC 2024 - Vision Swift Enhancements: https://developer.apple.com/videos/play/wwdc2024/10163/
- Apple Developer Vision Docs: https://developer.apple.com/documentation/vision/analyzing-a-selfie-and-visualizing-its-content

---

### 1.5 ONNX Runtime / CoreML - On-Device Inference Runtimes

ONNX Runtime (ORT) is the cross-platform inference engine that bridges models trained in PyTorch/TensorFlow to deployment on diverse hardware. CoreML is Apple's native ML runtime.

#### ONNX Runtime

**Execution Providers (EPs):**
| Provider | Platform | Hardware | Use Case |
|----------|----------|----------|----------|
| CPU | All | CPU | Maximum compatibility, baseline |
| CoreML EP | macOS/iOS | ANE, GPU, CPU | Apple Silicon acceleration |
| CUDA | Linux/Windows | NVIDIA GPU | GPU inference |
| DirectML | Windows | GPU | Windows GPU |
| OpenVINO | Linux/Windows | Intel | Intel hardware optimization |

**CoreML Execution Provider Details:**
- Requires macOS 10.15+ (NeuralNetwork format) or macOS 12+ (MLProgram format)
- Official macOS Python wheels include CoreML EP: `pip install onnxruntime`
- Must be explicitly registered: `providers=[("CoreMLExecutionProvider", {...})]`
- `MLComputeUnits` options: `CPUOnly`, `CPUAndNeuralEngine`, `CPUAndGPU`, `ALL`
- `ModelFormat`: `MLProgram` (CoreML 5+, wider op coverage) or `NeuralNetwork` (legacy)

**Performance Findings (M2 MacBook Pro benchmarks):**
| Model | CPU EP | CoreML EP (ANE) | Speedup |
|-------|--------|-----------------|---------|
| MNIST (26KB) | 0.15ms | 0.8ms | 0.2x (slower!) |
| MobileNet v2 (14MB) | 12.4ms | 1.8ms | **6.8x faster** |
| Kokoro 82M (330MB) | 280ms | 290ms | ~1x (no benefit) |

**Key Insights:**
- Models under ~1MB with sub-1ms inference: CoreML dispatch overhead exceeds benefit, use CPU
- Fixed-shape CNN models (image classification, object detection, segmentation): enable CoreML, expect 5-10x speedup
- Dynamic-shape models (transformers, LLMs): CoreML struggles with dynamic axes, first-hit compile tax, silent CPU fallback
- MLProgram format jumps op coverage from 9% to 93% vs NeuralNetwork format
- For transformer attention blocks: `CPUAndGPU` is better than ANE (stricter dtype/shape constraints on ANE)
- Partition boundaries between CoreML-supported and unsupported ops create overhead (Cast operations for precision conversion)

**Cross-Platform Strategy:**
```python
import onnxruntime as ort

# macOS: use CoreML for CNN models
providers = [("CoreMLExecutionProvider", {
    "ModelFormat": "MLProgram",
    "MLComputeUnits": "CPUAndGPU",
}), "CPUExecutionProvider"]

# Linux: use CUDA if available, else CPU
providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]

session = ort.InferenceSession("model.onnx", providers=providers)
```

**Relevance to Halbert:**
ONNX Runtime is the unified inference layer. Export YOLO/MediaPipe/custom models to ONNX format, then use ORT with platform-appropriate execution providers. On macOS, CoreML EP gives 5-10x speedup for CNN-based vision models. On Linux, CUDA EP (if GPU available) or CPU. This gives Halbert a single codebase with platform-optimized execution.

**Sources:**
- ONNX Runtime CoreML EP Docs: https://onnxruntime.ai/docs/execution-providers/CoreML-ExecutionProvider.html
- CoreML Deployment on Apple Silicon: https://egordmitriev.dev/blog/2026-05-18-optimizing-samurai-part-3
- ONNX Runtime 6.8x Faster on Apple Silicon: https://www.xybrid.ai/blog/onnx-runtime-6x-faster-apple-silicon-coreml
- Mac ONNX Runtime Deep Dive: https://macgpu.com/en/blog/2026-0420-mac-onnx-runtime-coreml-ep-vs-cpu-dynamic-shapes-remote.html

---

### 1.6 Other Relevant Real-Time CV Tooling

#### Screen Capture Libraries

**MSS (Multi-Screen Shot) - Cross-Platform Screen Capture:**
- `pip install mss` - pure Python, cross-platform (macOS, Linux, Windows)
- Uses native OS APIs: CoreGraphics on macOS, X11/XShm on Linux
- Performance: ~45-65ms per full screenshot on M2 Pro Mac (~15-22 FPS)
- Partial screenshots (regions) are significantly faster: ~16ms (~60 FPS)
- 30x faster than pyautogui/PIL on macOS (which use `screencapture` CLI under the hood)
- Direct buffer access: `sct.grab()` returns memoryview (BGRA bytes), can convert to NumPy array
- Thread-safe: can share one MSS object across threads (serialized grabs)
- Python 3.12+ supports direct screenshot buffers (no copy) for NumPy/OpenCV integration

**pyautogui / PIL (Pillow) - Slower Alternatives:**
- pyautogui: ~1300-1500ms per screenshot on macOS (uses `screencapture` CLI)
- PIL ImageGrab: ~1300-1500ms on macOS (same underlying mechanism)
- These are 30x slower than MSS and unsuitable for real-time capture

**DXcam (Windows-only):**
- ~100 FPS on mid-tier PCs, with change detection optimization
- Not available on macOS/Linux

**Performance Summary for Screen Capture:**
| Method | macOS (M2 Pro) | Linux | Windows |
|--------|---------------|-------|---------|
| MSS (full screen) | ~15-22 FPS | ~20-30 FPS | ~25-30 FPS |
| MSS (region) | ~60 FPS | ~60+ FPS | ~60+ FPS |
| pyautogui | ~0.7 FPS | varies | varies |
| DXcam | N/A | N/A | ~100 FPS |

#### FFmpeg
- Can be used for efficient frame extraction: `ffmpeg -i input.mp4 -vf fps=2 frame_%04d.jpg`
- More efficient than Python-based frame extraction for large video files
- Useful for offline processing or as a capture backend

**Sources:**
- MSS Documentation: https://python-mss.readthedocs.io/latest/usage.html
- Quick Screenshots in Python (M2 Pro benchmarks): https://blog.trackmypop.com/2024/01/02/quick-screenshots-in-python/
- Python Fast Screen Capture: https://kylefu.me/2023/02/18/python-fast-screen-capture.html
- StackOverflow - MSS FPS on macOS: https://stackoverflow.com/questions/78752784/how-to-improve-the-fps-of-screenshot-using-pythonmss-pyautogui-pil-on-macos

---

## 2. Whitepapers and Academic Research

### 2.1 Real-Time Visual Perception for AI Assistants / Agents

#### Vinci: A Real-time Embodied Smart Assistant based on Egocentric Vision-Language Model (Dec 2024)
- **ArXiv:** https://arxiv.org/html/2412.21080
- **Code:** https://github.com/OpenGVLab/vinci
- **Key Contribution:** Real-time embodied smart assistant operating in "always on" mode on portable devices (smartphones, wearable cameras)
- **Architecture:** Egocentric vision-language model that continuously observes the environment, processes long video streams in real-time, answers queries about current and historical observations
- **Features:** Wake-word activation, natural conversation, audio responses, task planning from past interactions, video generation for step-by-step guidance
- **Relevance to Halbert:** Directly applicable architecture - "always on" vision assistant with streaming video processing, memory of past observations, and task planning. Vinci's approach of processing long video streams with configurable "stride of memory" is a pattern Halbert could adopt.

#### InternLM-XComposer2.5-OmniLive (IXC2.5-OL) (Dec 2024)
- **ArXiv:** https://arxiv.org/pdf/2412.09596
- **Key Contribution:** Disentangled streaming perception, reasoning, and memory for real-time interaction with streaming video and audio
- **Architecture:** Three-module design inspired by human cognition:
  1. **Streaming Perception Module:** Processes multimodal information in real-time, stores key details in memory, triggers reasoning on user queries
  2. **Multimodal Long Memory Module:** Integrates short-term and long-term memory, compresses short-term into long-term for efficient retrieval
  3. **Reasoning Module:** Responds to queries, coordinates with perception and memory
- **Key Insight:** Single sequence-to-sequence models cannot "think while perceiving" - disentangling these functions is essential for continuous interaction
- **Relevance to Halbert:** The three-module architecture (perception / memory / reasoning) maps directly to Halbert's needs. The "Specialized Generalist AI" concept - using separate specialized modules rather than one monolithic model - is architecturally sound for a homelab assistant.

---

### 2.2 Screen Understanding / GUI Agents with Vision

#### SeeClick: Harnessing GUI Grounding for Advanced Visual GUI Agents (ACL 2024)
- **Paper:** https://aclanthology.org/2024.acl-long.505.pdf
- **Code:** https://github.com/njucckevin/SeeClick
- **Key Contribution:** Visual GUI agent that relies only on screenshots (no HTML/accessibility tree)
- **Innovation:** GUI grounding pre-training - the ability to accurately locate screen elements based on instructions
- **Benchmark:** ScreenSpot - first realistic GUI grounding benchmark (mobile, desktop, web)
- **Key Finding:** Advancements in GUI grounding directly correlate with enhanced performance in downstream GUI agent tasks
- **Relevance to Halbert:** If Halbert needs to interact with the desktop (clicking buttons, reading dialogs), SeeClick's approach of pure visual GUI grounding is more robust than accessibility-tree parsing, especially on macOS where accessibility data is often incomplete.

#### OmniParser for Pure Vision Based GUI Agent (Aug 2024)
- **ArXiv:** https://arxiv.org/pdf/2408.00203
- **Key Contribution:** Comprehensive method for parsing UI screenshots into structured elements
- **Two-Stage Pipeline:**
  1. Detection model fine-tuned to identify interactable icons/regions
  2. Caption model to extract functional semantics of detected elements
- **Result:** Significantly improves GPT-4V's ability to generate actions grounded in correct screen regions
- **Relevance to Halbert:** OmniParser's approach of pre-processing screenshots into structured element descriptions before sending to an LLM reduces token usage and improves action accuracy. Halbert could use a similar pre-processing step.

#### Auto-GUI: You Only Look at Screens - Multimodal Chain-of-Action Agents (ACL Findings 2024)
- **Paper:** https://aclanthology.org/2024.findings-acl.186.pdf
- **Code:** https://github.com/cooelf/Auto-GUI
- **Key Contribution:** Direct interaction with GUI without environment parsing or application-dependent APIs
- **Innovation:** Chain-of-action technique using intermediate previous action histories and future action plans
- **Performance:** 90% action type prediction accuracy, 74% overall action success rate on AITW benchmark
- **Relevance to Halbert:** The chain-of-action approach could help Halbert plan multi-step desktop operations (e.g., "restart the Docker service" -> open terminal -> type command -> read output).

#### Aguvis: Unified Pure Vision Agents for Autonomous GUI Interaction (Dec 2024)
- **ArXiv:** https://arxiv.org/abs/2412.04454v1
- **Key Contribution:** Unified pure vision-based framework for autonomous GUI agents across platforms
- **Architecture:** Image-based observations, natural language grounding to visual elements, consistent action space for cross-platform generalization
- **Training:** Two-stage pipeline - GUI grounding first, then planning and reasoning
- **Result:** First fully autonomous pure vision GUI agent in real-world online scenarios

---

### 2.3 Multimodal LLMs with Real-Time Video/Streaming Vision Input

#### VideoLLM-online: Online Video LLM for Streaming Video (CVPR 2024)
- **ArXiv:** https://arxiv.org/abs/2406.11816
- **Code:** https://github.com/showlab/VideoLLM-online
- **Paper:** https://openaccess.thecvf.com/content/CVPR2024/papers/Chen_VideoLLM-online_Online_Video_Large_Language_Model_for_Streaming_Video_CVPR_2024_paper.pdf
- **Key Contribution:** First streaming video LLM - online interaction within a video stream (not offline clip processing)
- **Performance:** 5-10 FPS on NVIDIA 3090, 10-15 FPS on A100 GPU for 5-10 minute video clips
- **Framework:** Learning-In-Video-Stream (LIVE) - training objective for continuous streaming inputs, data synthesis from offline annotations, parallelized real-time inference
- **Key Challenges Identified:**
  1. Temporally aligned requirements (must scan every frame to avoid missing events)
  2. Long-context historical vision and language (context window overflow risk)
  3. Real-time generation keeping pace with video stream
- **Inference Architecture:** Parallelizes video encoding, LLM forwarding for video frames, and LLM response generation asynchronously
- **Relevance to Halbert:** This is the closest academic work to Halbert's use case. The LIVE framework's approach of parallelized inference (encode frames while generating responses) and streaming dialogue is directly applicable. The challenge of context window overflow is real for Halbert too.

#### Flash-VStream: Memory-Based Real-Time Understanding for Long Video Streams (2024)
- **ArXiv:** http://arxiv.org/pdf/2406.08085
- **Key Contribution:** Video-language model simulating human memory mechanism for real-time processing of extremely long video streams
- **Innovation:** Memory-based architecture that processes long streams in real-time while responding to asynchronous user queries
- **Result:** Significant reductions in inference latency and VRAM consumption
- **Benchmark:** VStream-QA - novel QA benchmark for online video streaming understanding
- **Relevance to Halbert:** The memory-based approach is critical for Halbert's "always-on" vision. You cannot keep every frame in context - Flash-VStream's memory compression pattern is the solution.

#### VideoStreaming: Streaming Long Video Understanding with LLMs (NeurIPS 2024)
- **Paper:** https://proceedings.neurips.cc/paper_files/paper/2024/file/d7ce06e9293c3d8e6cb3f80b4157f875-Paper-Conference.pdf
- **Key Contribution:** Constant number of video tokens for arbitrary-length video via Memory-Propagated Streaming Encoding + Adaptive Memory Selection
- **Architecture:**
  1. Segments long videos into short clips, sequentially encodes each with propagated memory
  2. Uses encoded results of preceding clip as historical memory, integrated with current clip
  3. Distills condensed representation encapsulating video content up to current timestamp
  4. Adaptive Memory Selection: selects question-related memories from all historical memories
- **Key Insight:** Fixed-length memory as global representation for arbitrarily long videos; disentangled video extraction and reasoning

#### VideoLLM-MoD: Efficient Video-Language Streaming with Mixture-of-Depths (2024)
- **ArXiv:** https://arxiv.org/pdf/2408.16730
- **Key Contribution:** Reduces vision compute by skipping layers for redundant vision tokens (80% skip rate) rather than decreasing token count
- **Result:** ~42% time savings, ~30% memory savings, preserves or improves performance
- **Relevance:** If Halbert runs a local VLM, this optimization could make real-time streaming feasible on consumer hardware.

#### StreamChat: Chatting with Streaming Video (Dec 2024)
- **ArXiv:** https://arxiv.org/pdf/2412.08646
- **Key Contribution:** Updates visual context at each decoding step (not just at query time)
- **Innovation:** Cross-attention-based architecture for dynamic streaming inputs, parallel 3D-RoPE for temporal encoding
- **Relevance:** Solves the "stale visual context" problem - model sees up-to-date video content throughout response generation.

#### StreamBridge: Turning Offline Video LLMs into Proactive Streaming Assistants (NeurIPS 2025)
- **Paper:** https://proceedings.neurips.cc/paper_files/paper/2025/file/bf6939f9058a391c47014731b2486e2a-Paper-Conference.pdf
- **Key Contribution:** Plug-and-play activation model that decouples proactive capability from main Video-LLM
- **Innovation:** Compact activation model operates in parallel with main Video-LLM, enabling proactive behavior without modifying the LLM
- **Dataset:** Stream-IT - large-scale dataset for streaming scenarios with temporally extended, interactive video-text sequences
- **Relevance to Halbert:** The "activation model" concept is directly applicable - a lightweight model that decides when to wake the main LLM based on visual changes, rather than continuously running the full model.

#### OASIS: On-Demand Hierarchical Event Memory for Streaming Video Reasoning (CVPR 2026)
- **Paper:** https://openaccess.thecvf.com/content/CVPR2026/papers/Liang_OASIS_On-Demand_Hierarchical_Event_Memory_for_Streaming_Video_Reasoning_CVPR_2026_paper.pdf
- **Key Contribution:** Training-free agent system for streaming video with hierarchical dynamic memory
- **Memory Hierarchy:**
  1. **High-fidelity short window:** Current frames at high frame rate (fine-grained, present-moment reasoning)
  2. **Medium-resolution buffer:** Recent but non-immediate frames at lower frame rate
  3. **Multi-resolution event hierarchy:** Compressed historical events
  4. **QA summary:** Textual summaries of past interactions
- **Two-Phase Reasoning:** Coarse reasoning on recent window + summative memory, then fine-grained reasoning on specific memory
- **Relevance to Halbert:** This hierarchical memory architecture is the most directly applicable pattern for Halbert's "always-on" vision. Keep recent frames at high fidelity, compress older frames, maintain event summaries.

#### ViCoStream: Streaming VideoLLMs Beyond 100 FPS (2026)
- **ArXiv:** https://arxiv.org/html/2606.19849
- **Key Contribution:** Stage-wise coordinated inference for bounded real-time streaming
- **Four Inference Stages:** Visual preprocessing, visual encoding, token dropping, LLM prefilling/decoding
- **Key Insight:** Bounded real-time streaming requires controlling each stage, not just reducing a single cost term
- **Two Paradigms Identified:**
  1. **Delayed streaming:** Accumulate frames, process at query time (latency grows with stream length)
  2. **Continuous streaming:** Incrementally process as frames arrive (better for real-time)

---

### 2.4 GPT-4o / Gemini / Claude Vision Approaches to Continuous Visual Input

#### GPT-4o (OpenAI, May 2024)
- **End-to-end multimodal:** Single neural network trained jointly across text, vision, and audio (early fusion)
- **Unified token stream:** Text tokens (BPE), image patch tokens (ViT-style patchifier), audio tokens (neural audio codec at ~24Hz)
- **Latency:** 232ms median audio response, 320ms average (human-like conversational speed)
- **Video via API:** Convert to frames at 2-4 FPS (uniform sampling or keyframe selection), send as image sequence
- **Realtime API:** WebSocket/WebRTC for streaming audio; video frames sent as individual images
- **Architecture inference:** Single transformer stack consuming all token types, modality-specific embedding/unembedding layers
- **System Card:** https://arxiv.org/html/2410.21276
- **Architecture Analysis:** https://mlsystemsreview.com/gpt4o-multimodal-arch/

#### Gemini Live API (Google)
- **Protocol:** Stateful WebSocket connection (WSS)
- **Input:** Audio (raw 16-bit PCM, 16kHz), images (JPEG, **max 1 FPS**), text
- **Output:** Audio (raw 16-bit PCM, 24kHz)
- **Video:** Sent as individual JPEG frames at 1 FPS, recommended 768x768 resolution
- **Session limits:** Audio-only 15 min, audio+video 2 min (configurable for longer)
- **Architecture:** `send_realtime_input()` for responsive streaming (non-deterministic ordering), `send_client_content()` for ordered context
- **VAD:** Automatic voice activity detection with configurable sensitivity
- **Docs:** https://ai.google.dev/gemini-api/docs/live-api

#### Claude Computer Use (Anthropic)
- **Approach:** Screenshot-based, not streaming video
- **Loop:** Take screenshot -> send to Claude -> Claude returns tool_use (click/type/screenshot) -> execute -> repeat
- **Pixel counting:** Claude counts pixels vertically/horizontally to determine cursor movement
- **Key constraint:** API has internal image size limits; images exceeding limits get downscaled, causing click inaccuracy
- **Best practice:** Pre-downscale screenshots before sending to API (biggest single optimization for click accuracy)
- **Safety:** Prompt-injection detection on screenshot content (only when using Anthropic-defined computer tool)
- **Architecture docs:** https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool.md
- **Best practices:** https://claude.com/blog/best-practices-for-computer-and-browser-use-with-claude

---

## 3. Architecture Paths for Integrating CV into an AI Assistant

### 3.1 Frame Capture Strategies

#### Screen Capture (Primary for Halbert as sysadmin assistant)

**Recommended: MSS library**
- Cross-platform (macOS + Linux)
- ~15-22 FPS full screen on macOS, faster for regions
- Direct NumPy array output: `np.asarray(sct.grab(monitor))`
- Thread-safe for producer-consumer pipelines

**Architecture:**
```
[Screen] -> MSS.grab() -> NumPy array -> [Preprocess] -> [CV Pipeline]
```

**Region-based capture:** For a sysadmin assistant, full-screen capture may be unnecessary. Capture specific windows, terminal regions, or dashboard areas at higher FPS (60+ FPS for small regions).

**macOS-specific alternative:** ScreenCaptureKit (native, Swift) via `pyobjc` bridge - higher performance but macOS-only. Vision framework can process these frames directly.

#### Webcam Capture (Optional, for physical environment awareness)

**Recommended: OpenCV `cv2.VideoCapture(0)`**
- Standard, cross-platform
- 30 FPS standard on most webcams
- Use producer-consumer pattern with `collections.deque(maxlen=1)` for always-fresh frame

**Architecture:**
```
[Webcam] -> cv2.VideoCapture -> deque(maxlen=1) -> [Consumer thread] -> [CV Pipeline]
```

#### Dual-Source Strategy

For Halbert, screen capture is primary (sysadmin context), webcam is optional (physical server/rack awareness). The architecture should support both independently:

```
Screen Capture Thread (MSS)          Webcam Capture Thread (OpenCV)
        |                                    |
        v                                    v
  Frame Buffer (deque)              Frame Buffer (deque)
        |                                    |
        +---------+--------------------------+
                  |
                  v
          Frame Router / Scheduler
                  |
          +-------+-------+
          |               |
          v               v
    Local CV Pipeline   Frame -> LLM
    (MediaPipe/YOLO)    (JPEG encode + API)
```

### 3.2 Frame Sampling Rates and Buffering

#### The Core Problem

You cannot send every frame to an LLM. Token costs and latency make this impractical:

**Token costs per model (per frame):**
| Model | Tokens/Frame | Notes |
|-------|-------------|-------|
| Claude 3.5 Sonnet | ~250 (flat) | Fixed regardless of resolution |
| GPT-4o | 85-2,550 | Depends on resolution (85 for 512x512, up to 2,550 for 4K) |
| Gemini 2.0 | ~258 | Per frame at default resolution |

**Cost example (60-second video at different rates with Claude):**
| FPS | Frames | Tokens | Context Impact |
|-----|--------|--------|----------------|
| 1 fps | 60 | 15,000 | Manageable |
| 5 fps | 300 | 75,000 | Heavy |
| 10 fps | 600 | 150,000 | Exceeds most context windows |

#### Recommended Sampling Strategy for Halbert

**Tier 1: Local CV (always running, no token cost)**
- Screen: 5-10 FPS via MSS (capture is cheap, ~45ms per frame)
- Webcam: 15-30 FPS via OpenCV
- Process locally with MediaPipe/YOLO - no LLM tokens consumed
- Output: structured observations ("person detected", "terminal window visible", "error dialog on screen")

**Tier 2: LLM Vision (on-demand or low-rate)**
- Screen: 0.5-1 FPS when actively monitoring (every 1-2 seconds)
- Webcam: 0.25-0.5 FPS for ambient awareness (every 2-4 seconds)
- Send JPEG-compressed frames to vision LLM
- Triggered by: user query, significant change detection, scheduled check-ins

**Tier 3: Event-Triggered High-Rate**
- When user asks "what's on my screen now?" or "watch this terminal"
- Burst capture: 3-5 frames at 2 FPS, send all to LLM
- Return to Tier 2 after burst

#### Smart Sampling Techniques

1. **Change detection:** Compare consecutive frames (pixel diff, histogram comparison). Only send to LLM when significant change detected. Use `np.sum(np.abs(frame1 - frame2))` or SSIM.

2. **Motion detection:** Use optical flow (OpenCV `calcOpticalFlowFarneback`) or simple frame differencing to detect activity. Sample more frequently during active periods.

3. **Event-based triggering:** Local CV detects an event (dialog appears, person enters frame, terminal output changes) -> trigger LLM vision query with the relevant frame.

4. **Adaptive sampling:** Increase FPS when user is actively interacting, decrease when idle. Most production systems use fixed rates because motion analysis adds latency, but for Halbert's use case (user at desk), simple heuristics work: "user typing -> 1 FPS screen, user idle -> 0.2 FPS screen."

5. **Hierarchical memory (from OASIS paper):**
   - Short window: High FPS, high fidelity (last 5 seconds)
   - Medium buffer: Lower FPS (last 60 seconds)
   - Event hierarchy: Compressed summaries (last hour)
   - QA summary: Text descriptions of past events

**Practical implementation:**
```python
import mss
import numpy as np
import time
from collections import deque

class FrameSampler:
    def __init__(self, source='screen', base_fps=1.0, burst_fps=5.0):
        self.source = source
        self.base_fps = base_fps
        self.burst_fps = burst_fps
        self.current_fps = base_fps
        self.frame_buffer = deque(maxlen=30)  # Keep last 30 frames
        self.last_sent = 0
        self.last_frame = None

    def should_send_to_llm(self, frame):
        """Decide if this frame is worth sending to the LLM."""
        if self.last_frame is None:
            return True

        # Change detection: pixel difference
        diff = np.mean(np.abs(frame.astype(float) - self.last_frame.astype(float)))
        if diff > 15.0:  # Significant visual change threshold
            return True

        # Time-based fallback
        if time.time() - self.last_sent > 1.0 / self.current_fps:
            return True

        return False
```

### 3.3 On-Device Preprocessing vs. Cloud Inference

#### On-Device (Local) Processing

**What to process locally:**
- Frame capture and resizing
- Object detection (YOLOv8n/v10n via ONNX Runtime)
- Face/hand/pose detection (MediaPipe)
- OCR (Apple Vision on macOS, Tesseract on Linux)
- Change detection / motion detection
- Scene classification (lightweight models)
- Privacy-sensitive processing (never leave device)

**Advantages:**
- Zero per-call cost
- Sub-100ms latency
- Privacy-preserving (data never leaves device)
- Works offline
- No rate limits

**Disadvantages:**
- Limited model size (constrained by device RAM/GPU)
- Less capable than frontier models for complex reasoning
- Battery/CPU impact
- Model management (download, update, version)

**Recommended local models for Halbert:**
| Task | Model | Size | Runtime |
|------|-------|------|---------|
| Object detection | YOLOv8n | ~6MB | ONNX Runtime (CoreML on macOS) |
| Face/hand/pose | MediaPipe Tasks | 230KB-9.4MB | MediaPipe native |
| OCR (macOS) | Apple Vision | Built-in | Vision framework |
| OCR (Linux) | Tesseract 5 | ~15MB | tesseract-ocr |
| Scene change | Custom (frame diff) | N/A | NumPy/OpenCV |

#### Cloud Inference

**What to send to cloud:**
- Complex visual reasoning ("what does this error message mean?")
- Multi-step GUI understanding ("click the button that says 'Restart'")
- Natural language description of screen content
- Tasks requiring world knowledge ("identify this network equipment model")

**Advantages:**
- Frontier model quality (GPT-4o, Claude 3.5, Gemini 2.0)
- No local model management
- Handles arbitrary complexity

**Disadvantages:**
- Per-call cost ($0.01-0.06 per image depending on model)
- 1-3 second round-trip latency
- Privacy concerns (image leaves device)
- Rate limits and API dependencies
- Requires internet

#### Hybrid Strategy for Halbert

```
Frame Input
    |
    v
[Local CV Layer - Always Running]
    |-- Object detection (YOLO) -> "monitor, keyboard, server rack detected"
    |-- Face detection (MediaPipe) -> "user present, looking at screen"
    |-- OCR (Vision/Tesseract) -> "terminal shows: 'docker restart web-server'"
    |-- Change detection -> "screen content changed significantly"
    |
    +-- [Event/Change Detected?]
            |
            YES --> [Encode frame as JPEG] --> [Send to Vision LLM]
                    "Here's what I see locally: [structured observations].
                     Here's the screenshot: [image].
                     User context: [query]. What should I do?"
            |
            NO  --> [Continue local processing, no LLM call]
```

This hybrid approach:
1. Minimizes LLM token usage (only send when something changes)
2. Provides rich local context to the LLM (structured observations reduce what the LLM needs to figure out)
3. Preserves privacy (most frames processed locally, never sent anywhere)
4. Falls back gracefully (if no internet, local CV still works)

### 3.4 Feeding Visual Frames into an LLM Context Window Efficiently

#### The Token Budget Problem

A vision LLM's context window is finite. Claude 3.5 Sonnet has 200K tokens; GPT-4o has 128K. At ~250 tokens per image (Claude), you can fit ~800 images in 200K tokens - but that leaves no room for text, system prompts, or conversation history.

#### Strategy 1: Frame Summaries (Text-Based)

Convert frames to text descriptions locally, then feed text to LLM:

```
[Frame] -> [Local CV: YOLO + OCR + MediaPipe] -> "Text description"
                                                    |
                                                    v
                                          [LLM context as text]
                                          "At 14:32: Screen shows terminal
                                           with 'docker ps' output. 3 containers
                                           running. No error dialogs. User present."
```

**Advantages:** Minimal token usage (~50 tokens per observation vs ~250 per image)
**Disadvantages:** Loses visual nuance, can't answer "what does this graph look like?"

#### Strategy 2: Selective Image Sending

Send images only when local CV cannot fully describe the situation:

```
Local CV confidence high -> Send text summary only
Local CV confidence low   -> Send text summary + image
User explicitly asks      -> Send image
Error/anomaly detected    -> Send image + local observations
```

#### Strategy 3: Hierarchical Context (from academic research)

Based on OASIS and IXC2.5-OL papers:

```
Context Window Layout:
[System prompt + tools]           ~2K tokens
[Recent conversation]             ~5K tokens
[Current frame (image)]           ~250 tokens (only most recent)
[Recent observations (text)]      ~2K tokens (last 5 min as text)
[Compressed event memory]         ~1K tokens (last hour as summaries)
[Long-term memory]                ~1K tokens (key events from today)
                                   --------
                                   ~11.5K tokens total (vs 150K+ for raw frames)
```

#### Strategy 4: Video Token Compression

From VideoStreaming paper: Memory-Propagated Streaming Encoding
- Segment video into clips
- Encode each clip, compress into fixed-length memory representation
- Only keep the compressed representation in context, not raw frames
- Adaptive selection: retrieve relevant memories when query arrives

#### Strategy 5: Activation Model (from StreamBridge paper)

Use a tiny local model as a "gatekeeper":
```
[Every frame] -> [Tiny activation model: "Is this frame interesting?"]
                        |
                        YES -> [Send to main LLM]
                        NO  -> [Discard or compress to memory]
```

The activation model runs locally, costs nothing per frame, and only wakes the expensive LLM when something worth attention happens.

### 3.5 Streaming Vision Approaches

#### Video Tokens vs. Frame Embeddings

**Frame Embeddings (current mainstream approach):**
- Each frame is encoded by a vision encoder (e.g., SigLIP, CLIP) into a set of patch tokens
- Tokens are laid end-to-end in the LLM context window
- Gemini: ~258 tokens/frame at 1 FPS
- GPT-4o: 85-2,550 tokens/frame depending on resolution
- Claude: ~250 tokens/frame (flat rate)

**Video Token Compression approaches from research:**
- **Q-Former / Perceiver Resampler:** Learnable queries that compress visual tokens into a fixed set
- **Mixture-of-Depths (VideoLLM-MoD):** Skip computation for 80% of vision tokens at each layer
- **Memory-Propagated Encoding (VideoStreaming):** Fixed-length memory across clips
- **Hierarchical Memory (OASIS):** Multi-resolution temporal memory

#### Practical Approach for Halbert

Given that Halbert uses existing vision LLMs (not training custom models), the practical approach is:

1. **Encode frames as JPEG** (smallest practical format)
2. **Send at controlled rate** (0.5-1 FPS for ambient, burst for active queries)
3. **Pre-downscale** to model-optimal resolution (Claude: max 1568x1568, GPT-4o: 512x512 for low-cost, 2048x2048 for detail)
4. **Use local CV to generate text context** alongside images
5. **Maintain a rolling text-based memory** of past observations (doesn't consume image tokens)

### 3.6 Edge vs. Cloud Processing for CV

| Factor | Edge (Local) | Cloud (API) |
|--------|-------------|-------------|
| Latency | 10-300ms | 1-3s |
| Cost | Free (compute only) | $0.01-0.06/image |
| Privacy | Data stays local | Data sent to provider |
| Model quality | Good (YOLO, MediaPipe) | Frontier (GPT-4o, Claude) |
| Offline | Works | Fails |
| Complexity | Model management needed | Simple API calls |
| Scalability | Limited by hardware | Scales with API quota |

**Recommended split for Halbert:**
- **Edge (always-on):** Frame capture, change detection, object detection, face/hand detection, OCR, gesture recognition
- **Cloud (on-demand):** Complex visual reasoning, GUI action planning, natural language description, anomaly interpretation
- **Hybrid trigger:** Edge detects event -> Cloud provides reasoning

---

## 4. Existing Products Doing This

### 4.1 Claude Computer Use (Anthropic)

**Approach:** Screenshot-based, not streaming video. Iterative loop.

**How it works:**
1. Developer adds `computer_toolset_20260801` to API tools array
2. Claude assesses whether desktop interaction can help with the query
3. Claude responds with `tool_use` blocks: `screenshot`, `left_click`, `type`, `zoom`, etc.
4. Application executes each tool call in its environment
5. Returns `tool_result` per `tool_use` block
6. Calls API again with results
7. Loop continues until task complete

**Key Technical Details:**
- Claude counts pixels to determine cursor movement (trained specifically for this)
- API has internal image size limits; images exceeding limits get downscaled automatically
- **Critical best practice:** Pre-downscale screenshots before sending to avoid click inaccuracy
- Batch actions supported: multiple `tool_use` blocks in one response
- Safety classifiers run on screenshot content (prompt-injection detection)
- Reference implementation: Docker container with Linux desktop (X11 + VNC)
- Best practices demo runs natively on macOS (no container)

**Architecture:**
```
User query -> Claude API (with computer toolset)
    <- Claude: "take screenshot"
    -> Execute: screenshot()
    <- Claude: "click at (x, y)"
    -> Execute: left_click(x, y)
    <- Claude: "type 'docker restart web'"
    -> Execute: type("docker restart web")
    ... (loop until done)
```

**Relevance to Halbert:** Claude Computer Use is the most directly applicable product pattern. Halbert could implement a similar agent loop using its existing `vision_model` config. The screenshot-based approach (not streaming) is simpler to implement and sufficient for sysadmin tasks. The pre-downscaling best practice is critical.

**Sources:**
- Anthropic Research Blog: https://www.anthropic.com/research/developing-computer-use
- Computer Use Tool Docs: https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool.md
- Best Practices: https://claude.com/blog/best-practices-for-computer-and-browser-use-with-claude
- Reference Implementation: https://github.com/anthropics/anthropic-quickstarts/blob/main/computer-use-demo/README.md

---

### 4.2 ChatGPT Vision / Advanced Voice Mode with Camera

**Approach:** Real-time multimodal streaming via WebRTC/WebSocket.

**Architecture (Advanced Voice Mode with video):**
1. User's speech/video captured by LiveKit client SDK in ChatGPT app
2. Streamed over LiveKit Cloud to OpenAI's voice agent
3. Agent relays to GPT-4o via WebSocket
4. GPT-4o runs inference, streams audio/video packets back
5. Agent relays response back to user device

**GPT-Live (third-generation, 2025):**
- Full-duplex: can listen and speak simultaneously (no turn detector needed)
- Media flow separated from application/business logic
- Audio on dedicated fast path; reasoning/tool use on async path
- Can consult frontier models (GPT-5.5) without interrupting conversation flow
- Stateful inference system built for continuous conversation

**Video Input via API:**
- Videos converted to frames at 2-4 FPS (uniform sampling or keyframe selection)
- Frames sent as image sequence to GPT-4o
- No native video encoder - image encoder called repeatedly on sampled frames

**Key Technical Details:**
- WebRTC used for client-to-server (handles packet loss better than WebSocket)
- WebSocket used for server-to-server
- ~300ms latency threshold for human-like speech
- Video and screen sharing available on iOS/Android Advanced Voice Mode

**Relevance to Halbert:** OpenAI's architecture shows the complexity of true real-time multimodal streaming. For Halbert (a desktop app, not a mobile app), the screenshot-based approach (like Claude) is more practical than full streaming. However, the "separate media flow from business logic" principle is architecturally important.

**Sources:**
- OpenAI GPT-Live Architecture: https://openai.com/index/continuous-voice-interaction-with-gpt-live/
- LiveKit Partnership: https://livekit.com/blog/openai-livekit-partnership-advanced-voice-realtime-api
- OpenAI Voice Agents Guide: https://developers.openai.com/api/docs/guides/voice-agents
- GPT-4o Announcement: https://openai.com/index/hello-gpt-4o/
- GPT-4o System Card: https://arxiv.org/html/2410.21276
- GPT-4o Architecture Analysis: https://mlsystemsreview.com/gpt4o-multimodal-arch/

---

### 4.3 Google Gemini Live (Camera Input)

**Approach:** Real-time bidirectional multimodal streaming via WebSocket.

**Architecture:**
- Stateful WebSocket connection (WSS)
- Input: Audio (raw 16-bit PCM, 16kHz), images (JPEG, max 1 FPS), text
- Output: Audio (raw 16-bit PCM, 24kHz)
- Video frames sent as individual JPEG images at max 1 FPS
- Recommended resolution: 768x768 at 1 FPS

**Implementation Pattern:**
```python
# From Google's official docs
async def send_video_stream(session):
    cap = cv2.VideoCapture(0)
    while True:
        ret, frame = cap.read()
        if not ret: break
        frame = cv2.resize(frame, (768, 768))
        _, buffer = cv2.imencode('.jpg', frame)
        await session.send_realtime_input(
            media=types.Blob(data=buffer.tobytes(), mime_type="image/jpeg")
        )
        await asyncio.sleep(1.0)  # 1 FPS
    cap.release()
```

**Key Technical Details:**
- `send_realtime_input()`: Optimized for responsiveness, non-deterministic ordering, automatic VAD
- `send_client_content()`: Ordered context, deterministic
- Session limits: Audio-only 15 min, audio+video 2 min (configurable)
- Media resolution configurable: `low`, `medium`, `high`
- Turn coverage configurable: include all video frames or only activity
- ADK Streaming for multi-agent architectures
- Third-party integrations: Fishjam, Stream Vision Agents (WebRTC)

**Google Cloud Architecture (for enterprise):**
- Technical guidance workflow: Gemini Live processes multimodal streams, coordinates with subagents
- Safety monitoring workflow: Gemini analyzes live video segments for hazards
- WebSocket messages package raw multimedia as Blob objects
- ADK LiveRequestQueue continuously streams input to dispatcher agent
- Dispatcher detects audio/visual commands, routes to Gemini Live model

**Relevance to Halbert:** Gemini Live's 1 FPS video rate is a useful baseline. The separation of `send_realtime_input` (responsive, non-deterministic) from `send_client_content` (ordered, deterministic) is a good architectural pattern. The WebSocket-based approach is simpler than WebRTC for a desktop app.

**Sources:**
- Gemini Live API Overview: https://ai.google.dev/gemini-api/docs/live-api
- Gemini Live Get Started (SDK): https://ai.google.dev/gemini-api/docs/live-api/get-started-sdk
- Send Audio/Video Streams: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/send-audio-video-streams
- Live API Capabilities: https://ai.google.dev/gemini-api/docs/live-api/capabilities
- Agentic AI Bidirectional Streaming Architecture: https://docs.cloud.google.com/architecture/agentic-ai-bidirectional-multimodal-streaming

---

### 4.4 Apple Intelligence Visual Intelligence

**Approach:** On-device processing with Private Cloud Compute fallback. Camera-based, not screen-based.

**How it works:**
- User clicks and holds Camera Control (iPhone 16+) or uses Action Button / Control Center
- Points camera at object/scene/text
- "Combination of on-device intelligence and Apple services that never store your images"
- Can route to third-party models (Google search, ChatGPT) with user consent

**Architecture:**
- On-device processing for most tasks (runs on Apple Neural Engine)
- Private Cloud Compute for tasks requiring more power (Apple silicon servers, data never stored/shared)
- Independent experts can inspect server code for privacy verification
- ChatGPT integration optional, IP addresses obscured, OpenAI doesn't store requests

**Foundation Models:**
- ~3 billion parameter on-device language model
- Larger server-based model via Private Cloud Compute
- Vision framework provides CV capabilities (OCR, face detection, object detection)
- Foundation Models framework (WWDC 2026) now supports image inputs for LLM-powered visual understanding

**Relevance to Halbert:** Apple's privacy-first, on-device-first approach is the gold standard for privacy-preserving AI. Halbert should adopt a similar philosophy: process locally when possible, only send to cloud when necessary, never store images. The Vision + Foundation Models combination (CV + LLM) is exactly the pattern Halbert should follow on macOS.

**Sources:**
- Apple Newsroom (Oct 2024): https://www.apple.com/newsroom/2024/10/apple-intelligence-is-available-today-on-iphone-ipad-and-mac/
- The Verge - Visual Intelligence: https://www.theverge.com/2024/9/9/24240094/apple-visual-intelligence-camera-control-iphone-16-ai-camera-control-google-lens
- Apple Foundation Models: https://machinelearning.apple.com/research/introducing-apple-foundation-models
- Apple Support - Visual Intelligence: https://support.apple.com/guide/iphone/use-visual-intelligence-iph12eb1545e/ios

---

### 4.5 Rabbit r1 / Humane AI Pin (Ambient Vision)

**Rabbit r1:**
- Pocket-sized AI device with camera (1080p, 24fps)
- Cloud-based AI (not enough local processing power for LLM/LAM)
- Camera for visual searches, text translation/transcription, scene understanding
- "Magic Camera" for AI-enhanced photos
- DLAM (Desktop Large Action Model): plug r1 into Mac/Windows/Linux computer for desktop control via voice/text
- No subscription required ($199 one-time)

**Humane AI Pin:**
- Wearable device with camera, laser projector (MEMS mirrors), sensors
- Cloud-based AI (same limitation as r1)
- Laser Ink Display projects onto user's palm
- Touch, tap, swipe gestures on device
- $699 + $24/month data plan
- Discontinued (acquired by HP, May 2024)

**Key Lessons for Halbert:**
1. Both devices failed because they relied entirely on cloud processing - high latency, poor offline experience, privacy concerns
2. The hardware was underpowered for local AI (confirmed by iFixit teardowns)
3. The camera was primarily for capture-and-send-to-cloud, not local CV processing
4. Rabbit's DLAM (desktop control) is the most relevant feature - but it's essentially Claude Computer Use with a phone as the interface

**Relevance to Halbert:** These are cautionary tales. Halbert should NOT follow the "capture and send everything to cloud" model. Local CV processing is essential for responsiveness, privacy, and offline capability. The Humane AI Pin's failure underscores that ambient vision must be paired with local intelligence.

**Sources:**
- iFixit Teardown: https://www.ifixit.com/News/95474/rabbit-r1-and-humane-ai-pin-teardown-the-beginning-of-a-new-device-category
- Rabbit r1 User Guide: https://www.rabbit.tech/r1-user-guide
- Rabbit r1 Product Page: https://www.rabbit.tech/rabbit-r1
- Trusted Reviews Comparison: https://www.trustedreviews.com/versus/rabbit-r1-vs-humane-ai-pin-4410517

---

### 4.6 Open-Source Projects

#### Vinci (OpenGVLab)
- **GitHub:** https://github.com/OpenGVLab/vinci (91 stars)
- Real-time embodied smart assistant, egocentric vision-language model
- "Always on" mode on portable devices (smartphones, wearable cameras)
- Processes long video streams, answers queries about current and historical observations
- RTMP streaming from smartphone/GoPro/DJI cameras
- Docker-based deployment, Gradio web demo
- Configurable "stride of memory" for temporal granularity

#### OpenLive
- **GitHub:** https://github.com/henliao/openlive
- Open voice + vision AI assistant, on-device voice pipeline
- "Open alternative to ElevenLabs, Gemini Live, and OpenAI Realtime"
- On-device: Silero VAD, Whisper STT, Smart-Turn end-of-turn detection, Kokoro TTS (all on WebGPU)
- Camera + screen sharing support via `look` tool
- MIT licensed, desktop app reference build
- **Highly relevant to Halbert:** This is the open-source equivalent of ChatGPT's Advanced Voice Mode with camera, running entirely locally.

#### Visionary AI
- **GitHub:** https://github.com/abhay-codes07/visionary_ai (4 stars)
- Real-time multimodal cognitive vision agent platform
- YOLOv8 object detection, temporal memory, contextual reasoning, WebSocket streaming
- WebRTC + Canvas webcam capture at configurable FPS
- Backend on HuggingFace Spaces, frontend on Vercel

#### Vision Assistant (KlementMultiverse)
- **GitHub:** https://github.com/KlementMultiverse/vision-assistant
- "First open-source Vision + Learning + Acting agent for home use"
- Real-time face recognition (82%+ accuracy at 1-2m), auto-learning
- YOLO person detection, InsightFace face detection
- GPT-4o Vision for context awareness
- Multi-camera support, visit tracking, voice greetings
- Deep Agents framework for intelligent decisions

#### DAXTER (arturmoret)
- **GitHub:** https://github.com/arturmoreet/DAXTER
- AI-powered smart glasses with real-time object detection
- YOLOv5 object detection, EasyOCR, dominant color detection
- Local voice (pyttsx3) + cloned voice (ElevenLabs)
- Raspberry Pi 4 compatible, cross-platform (Windows/Linux/macOS)

---

## 5. Tooling Recommendations for Halbert

### 5.1 Recommended Technology Stack

Based on the research, here is the concrete recommended stack for Halbert's real-time CV integration:

#### Screen Capture: MSS
```python
# pip install mss
import mss
import numpy as np

sct = mss.mss()
monitor = sct.monitors[0]  # Primary monitor

def capture_screen():
    return np.asarray(sct.grab(monitor))  # BGRA NumPy array
```
- **Why:** 30x faster than pyautogui/PIL on macOS, cross-platform, direct NumPy output
- **Performance:** ~15-22 FPS full screen, ~60 FPS for regions
- **Alternative on macOS:** ScreenCaptureKit via `pyobjc` for even better performance (macOS-only)

#### Webcam Capture: OpenCV
```python
# pip install opencv-python
import cv2

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FPS, 30)

def capture_webcam():
    ret, frame = cap.read()
    return frame if ret else None
```
- **Why:** Standard, cross-platform, well-documented
- **Performance:** 30 FPS standard

#### On-Device CV: MediaPipe + YOLOv8n (via ONNX Runtime)

**MediaPipe for human-centric tasks:**
```python
# pip install mediapipe
import mediapipe as mp

# Gesture recognition
GestureRecognizer = mp.tasks.vision.GestureRecognizer
recognizer = GestureRecognizer.create_from_options(
    mp.tasks.vision.GestureRecognizerOptions(
        running_mode=mp.tasks.vision.RunningMode.LIVE_STREAM,
        result_callback=on_gesture_result
    )
)
```

**YOLOv8n for object detection:**
```python
# pip install ultralytics onnxruntime
from ultralytics import YOLO

model = YOLO("yolov8n.pt")  # Nano variant, ~6MB
# Export to ONNX for cross-platform:
# model.export(format="onnx")

# Or load ONNX directly with ONNX Runtime:
import onnxruntime as ort
providers = [("CoreMLExecutionProvider", {"ModelFormat": "MLProgram", "MLComputeUnits": "CPUAndGPU"}),
             "CPUExecutionProvider"]  # macOS
# providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]  # Linux with GPU
session = ort.InferenceSession("yolov8n.onnx", providers=providers)
```

#### OCR: Apple Vision (macOS) / Tesseract (Linux)
```python
# macOS: use Vision framework via pyobjc
# Linux: use pytesseract
# pip install pytesseract  (Linux)

import platform

if platform.system() == "Darwin":
    # Use Vision framework via pyobjc
    from Vision import VNRecognizeTextRequest  # macOS native
else:
    import pytesseract
    def ocr(frame):
        return pytesseract.image_to_string(frame)
```

#### Frame-to-LLM: JPEG encode + API
```python
import cv2
import base64

def frame_to_llm(frame, max_dim=1024):
    # Downscale for token efficiency
    h, w = frame.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        frame = cv2.resize(frame, (int(w*scale), int(h*scale)))

    # Encode as JPEG
    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buffer.tobytes()
```

### 5.2 Architecture Recommendation for Halbert

```
+------------------------------------------------------------------+
|                     Halbert CV Architecture                       |
+------------------------------------------------------------------+
|                                                                  |
|  [Capture Layer]                                                 |
|  +------------------+    +------------------+                    |
|  | MSS Screen Cap   |    | OpenCV Webcam    |                    |
|  | (5-10 FPS)       |    | (15-30 FPS)      |                    |
|  +------------------+    +------------------+                    |
|         |                       |                                |
|         v                       v                                |
|  [Frame Buffer - deque(maxlen=30)]                               |
|         |                                                        |
|         v                                                        |
|  [Local CV Pipeline - Always Running]                            |
|  +------------------+    +------------------+    +-------------+ |
|  | YOLOv8n (ONNX)   |    | MediaPipe Tasks  |    | OCR         | |
|  | Object detection |    | Face/hand/gesture|    | Vision/Tess | |
|  | ~6MB, 5-10ms     |    | 230KB-9.4MB      |    |             | |
|  +------------------+    +------------------+    +-------------+ |
|         |                       |                    |          |
|         +-----------+-----------+--------------------+          |
|                     |                                            |
|                     v                                            |
|  [Change/Event Detector]                                         |
|  "Did something significant change?"                             |
|  "Was a gesture detected?"                                       |
|  "Did an error dialog appear?"                                   |
|                     |                                            |
|         +-----------+-----------+                                |
|         |                       |                                |
|         v                       v                                |
|    [NO CHANGE]            [CHANGE/EVENT DETECTED]                |
|    Update text            Encode frame as JPEG                   |
|    memory only            + local CV observations               |
|         |                 |                                      |
|         v                 v                                      |
|  [Rolling Memory]   [Vision LLM API Call]                        |
|  Text summaries     "Local observations: [text].                |
|  of recent          Screenshot: [image].                         |
|  observations       User query: [query]"                         |
|                     |                                            |
|                     v                                            |
|              [LLM Response -> Action]                            |
|              Text response, tool calls, etc.                     |
|                     |                                            |
|                     v                                            |
|              [Update Memory + Notify User]                       |
|                                                                  |
+------------------------------------------------------------------+
```

### 5.3 Privacy-Preserving Local Processing

**Principles (inspired by Apple Intelligence and LocalMode):**
1. **On-device first:** All CV processing (detection, OCR, gestures) runs locally. No frames leave the device unless explicitly needed for LLM reasoning.
2. **No raw frame storage:** Frames are processed and discarded. Only text-based observations are stored in memory.
3. **Explicit consent for cloud:** Only send frames to vision LLM when (a) user explicitly asks, (b) local CV detects an anomaly it can't classify, or (c) scheduled monitoring with user opt-in.
4. **Local model caching:** MediaPipe and YOLO models download once, cache locally, run offline.
5. **No telemetry:** CV processing produces no external network calls by default.

**Implementation:**
```python
class PrivacyPreservingCV:
    def __init__(self):
        self.local_models = {
            'object_detection': YOLO("yolov8n.onnx"),  # Local only
            'gesture': MediaPipeGestureRecognizer(),    # Local only
            'ocr': OCRBackend(),                        # Local only
        }
        self.cloud_enabled = False  # User must opt-in
        self.frame_storage = False  # Never store raw frames

    def process_frame(self, frame):
        # All local processing - no network calls
        observations = []
        observations.extend(self.local_models['object_detection'].detect(frame))
        observations.extend(self.local_models['ocr'].extract(frame))

        # Only send to cloud if explicitly enabled AND event detected
        if self.cloud_enabled and self._is_significant_event(observations):
            return self._send_to_llm(frame, observations)
        else:
            return observations  # Text only, no image leaves device
```

### 5.4 Recommended Libraries Summary

| Purpose | Library | Install | Size | Platform |
|---------|---------|---------|------|----------|
| Screen capture | MSS | `pip install mss` | ~100KB | macOS, Linux, Windows |
| Webcam capture | OpenCV | `pip install opencv-python` | ~60MB | All |
| Object detection | YOLOv8n (Ultralytics) | `pip install ultralytics` | ~6MB model | All |
| Inference runtime | ONNX Runtime | `pip install onnxruntime` | ~20MB | All |
| Face/hand/gesture | MediaPipe | `pip install mediapipe` | ~30MB | All |
| OCR (macOS) | Vision (via pyobjc) | `pip install pyobjc` | System | macOS |
| OCR (Linux) | Tesseract | `apt install tesseract-ocr` | ~15MB | Linux |
| Frame processing | NumPy | `pip install numpy` | ~15MB | All |
| Image encoding | OpenCV (imencode) | included with opencv | - | All |

**Total local model footprint:** ~50-80MB (models + libraries)
**All processing runs offline after initial model download**

### 5.5 Implementation Phasing Recommendation

**Phase 1: Screen Capture + LLM Vision (Minimal Viable)**
- MSS for screen capture
- JPEG encode + downscale
- Send to existing `vision_model` in Halbert's LLM config
- Simple 1 FPS sampling with change detection
- No local CV models yet

**Phase 2: Local CV Layer**
- Add YOLOv8n for object detection (via ONNX Runtime)
- Add OCR (Vision on macOS, Tesseract on Linux)
- Generate structured text observations from local CV
- Send observations + selective images to LLM
- Implement change detection to reduce LLM calls

**Phase 3: Full CV Pipeline**
- Add MediaPipe for face/gesture detection
- Implement hierarchical memory (OASIS pattern)
- Add activation model for smart LLM triggering
- Webcam support for physical environment awareness
- Gesture-based commands (wave, thumbs up)

**Phase 4: Advanced Features**
- GUI agent capabilities (SeeClick/OmniParser approach)
- Streaming video to LLM (if vision model supports it)
- Multi-monitor support
- Proactive monitoring (detect anomalies without user query)

---

## 6. References

### Frameworks and Libraries
1. OpenCV Video Processing Pipeline: https://pyquesthub.com/implementing-a-video-processing-pipeline-with-opencv-in-python
2. Producer-Consumer Pattern for Real-Time Video: https://theneuralbase.com/opencv/learn/advanced/producer-consumer-pattern/
3. Vision Stream Toolkit: https://github.com/Jenil16/vision-stream-toolkit
4. MediaPipe Holistic Landmarker: https://developers.google.cn/edge/mediapipe/solutions/vision/holistic_landmarker
5. MediaPipe Gesture Recognizer: https://developers.google.com/edge/mediapipe/solutions/vision/gesture_recognizer
6. LocalMode MediaPipe (Privacy): https://localmode.dev/blog/mediapipe-hand-pose-face-tracking-browser
7. YOLOv8 vs YOLOv10: https://docs.ultralytics.com/compare/yolov8-vs-yolov10
8. YOLOv10 Model Page: https://docs.ultralytics.com/models/yolov10
9. YOLOv10 to LiteRT Tutorial: https://medium.com/google-developer-experts/yolov10-to-litert-object-detection-on-android-with-google-ai-edge-2d0de5619e71
10. Apple Vision Framework Overview: https://blakecrosley.com/blog/vision-framework-built-in
11. WWDC 2026 Image Understanding: https://developer.apple.com/videos/play/wwdc2026/237/
12. WWDC 2024 Vision Swift: https://developer.apple.com/videos/play/wwdc2024/10163/
13. ONNX Runtime CoreML EP: https://onnxruntime.ai/docs/execution-providers/CoreML-ExecutionProvider.html
14. CoreML on Apple Silicon: https://egordmitriev.dev/blog/2026-05-18-optimizing-samurai-part-3
15. ONNX Runtime 6.8x Faster on Apple Silicon: https://www.xybrid.ai/blog/onnx-runtime-6x-faster-apple-silicon-coreml
16. MSS Documentation: https://python-mss.readthedocs.io/latest/usage.html
17. Quick Screenshots Benchmark: https://blog.trackmypop.com/2024/01/02/quick-screenshots-in-python/
18. Python Fast Screen Capture: https://kylefu.me/2023/02/18/python-fast-screen-capture.html

### Academic Papers
19. Vinci: Real-time Embodied Smart Assistant: https://arxiv.org/html/2412.21080 | Code: https://github.com/OpenGVLab/vinci
20. InternLM-XComposer2.5-OmniLive: https://arxiv.org/pdf/2412.09596
21. SeeClick: GUI Grounding for Visual GUI Agents (ACL 2024): https://aclanthology.org/2024.acl-long.505.pdf
22. OmniParser: Pure Vision Based GUI Agent: https://arxiv.org/pdf/2408.00203
23. Auto-GUI: Multimodal Chain-of-Action Agents (ACL Findings 2024): https://aclanthology.org/2024.findings-acl.186.pdf
24. Aguvis: Unified Pure Vision Agents: https://arxiv.org/abs/2412.04454v1
25. VideoLLM-online: Online Video LLM (CVPR 2024): https://arxiv.org/abs/2406.11816 | Code: https://github.com/showlab/VideoLLM-online
26. Flash-VStream: Memory-Based Real-Time Video: https://arxiv.org/pdf/2406.08085
27. VideoStreaming: Streaming Long Video Understanding (NeurIPS 2024): https://proceedings.neurips.cc/paper_files/paper/2024/file/d7ce06e9293c3d8e6cb3f80b4157f875-Paper-Conference.pdf
28. VideoLLM-MoD: Mixture-of-Depths Vision: https://arxiv.org/pdf/2408.16730
29. StreamChat: Chatting with Streaming Video: https://arxiv.org/pdf/2412.08646
30. StreamBridge: Proactive Streaming Assistant (NeurIPS 2025): https://proceedings.neurips.cc/paper_files/paper/2025/file/bf6939f9058a391c47014731b2486e2a-Paper-Conference.pdf
31. OASIS: Hierarchical Event Memory (CVPR 2026): https://openaccess.thecvf.com/content/CVPR2026/papers/Liang_OASIS_On-Demand_Hierarchical_Event_Memory_for_Streaming_Video_Reasoning_CVPR_2026_paper.pdf
32. ViCoStream: Streaming VideoLLMs Beyond 100 FPS: https://arxiv.org/html/2606.19849
33. YOLOv10 Paper (NeurIPS 2024): https://proceedings.neurips.cc/paper_files/paper/2024/file/c34ddd05eb089991f06f3c5dc36836e0-Paper-Conference.pdf
34. Visual Grounding for UIs (NAACL 2024): https://aclanthology.org/2024.naacl-industry.9.pdf
35. GPT-4o System Card: https://arxiv.org/html/2410.21276

### Product Documentation
36. Claude Computer Use: https://www.anthropic.com/research/developing-computer-use
37. Claude Computer Use Tool Docs: https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool.md
38. Claude Best Practices: https://claude.com/blog/best-practices-for-computer-and-browser-use-with-claude
39. Claude Reference Implementation: https://github.com/anthropics/anthropic-quickstarts/blob/main/computer-use-demo/README.md
40. OpenAI GPT-Live Architecture: https://openai.com/index/continuous-voice-interaction-with-gpt-live/
41. LiveKit + OpenAI Partnership: https://livekit.com/blog/openai-livekit-partnership-advanced-voice-realtime-api
42. OpenAI Voice Agents: https://developers.openai.com/api/docs/guides/voice-agents
43. GPT-4o Announcement: https://openai.com/index/hello-gpt-4o/
44. GPT-4o Architecture Analysis: https://mlsystemsreview.com/gpt4o-multimodal-arch/
45. Gemini Live API: https://ai.google.dev/gemini-api/docs/live-api
46. Gemini Live SDK: https://ai.google.dev/gemini-api/docs/live-api/get-started-sdk
47. Gemini Send Audio/Video: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/send-audio-video-streams
48. Gemini Live Capabilities: https://ai.google.dev/gemini-api/docs/live-api/capabilities
49. Google Cloud Agentic AI Streaming: https://docs.cloud.google.com/architecture/agentic-ai-bidirectional-multimodal-streaming
50. Apple Intelligence Newsroom: https://www.apple.com/newsroom/2024/10/apple-intelligence-is-available-today-on-iphone-ipad-and-mac/
51. Apple Visual Intelligence (Verge): https://www.theverge.com/2024/9/9/24240094/apple-visual-intelligence-camera-control-iphone-16-ai-camera-control-google-lens
52. Apple Foundation Models: https://machinelearning.apple.com/research/introducing-apple-foundation-models
53. Rabbit r1 Teardown (iFixit): https://www.ifixit.com/News/95474/rabbit-r1-and-humane-ai-pin-teardown-the-beginning-of-a-new-device-category
54. Rabbit r1 User Guide: https://www.rabbit.tech/r1-user-guide

### Open-Source Projects
55. Vinci: https://github.com/OpenGVLab/vinci
56. OpenLive: https://github.com/henliao/openlive
57. Visionary AI: https://github.com/abhay-codes07/visionary_ai
58. Vision Assistant: https://github.com/KlementMultiverse/vision-assistant
59. DAXTER: https://github.com/arturmoret/DAXTER

### Additional Resources
60. Frame Sampling Rate Decisions: https://theneuralbase.com/multimodal/learn/intermediate/frame-sampling-rate-decisions/
61. Video Understanding: Frames, Sampling and Cost: https://multigrid.ai/learn/video-understanding
62. Semantic Router: GPT-4o Video Chunking: https://buduroiu.com/blog/semantic-router-gpt4o-video-chunking/
63. Mac ONNX Runtime Deep Dive: https://macgpu.com/en/blog/2026-0420-mac-onnx-runtime-coreml-ep-vs-cpu-dynamic-shapes-remote.html
64. Real-Time CV for Live Streaming: https://www.technolynx.com/post/real-time-computer-vision-for-live-streaming
65. KULVEX (Self-hosted AI platform): https://kulvex.ai/
66. Aura Home (Local AI): https://www.archotec.ai/aura-home
67. Home Assistant Voice PE: https://www.theverge.com/2024/12/19/24325101/home-assistant-voice-preview-edition-smart-home-voice-assistant-hardware
68. IRIS: Wireless Ring for Vision-Based Smart Home: https://arxiv.org/html/2407.18141
69. LLM Book - Frontier Omni Models: https://llmbook.apartsin.com/part-5-multimodal-llms/module-22-vision-language-models/section-22.9.html
