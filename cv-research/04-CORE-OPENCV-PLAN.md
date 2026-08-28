# Core OpenCV Plan: Giving Halbert Eyes

**Date:** 2026-08-27
**Status:** Design — ready for implementation planning
**Scope:** Basic screen capture + webcam input for the sysadmin Halbert. Local-only. No cloud video.

---

## 1. What Exists Today (and What's Broken)

### 1.1 Backend Vision Routing — WORKS

The backend has a complete vision model routing path:

- `model/client.py:217` — `get_vision_model()` returns `(model, url, provider)` from the `vision_model` slot in `llm_config`. Falls back to the chat model when unset.
- `dashboard/routes/agent.py:53` — `SendMessageRequest.images: Optional[List[str]]` accepts base64-encoded images.
- `agent.py:278` — `_attach_images()` hangs images on the last user message.
- `agent.py:427-432` — `_resolve_turn_model()` auto-routes to the vision tier when images are present.
- `agent.py:675-698` — The `chat()` method has a dedicated vision path that attaches images and calls the vision model, with fallback to text on failure.
- `agent.py:820-821` — The `stream()` method also attaches images for the vision path.
- `agents/state_machine.py:371` — `process()` accepts `images: List[str]` and passes them through the full state machine.
- `intake/signals.py` — Detects image references (markdown `![](url)`, data URIs) and sets `has_images=True`, which routes to vision.

**The backend is ready.** The vision model slot, routing, image attachment, and streaming all work. The problem is upstream.

### 1.2 Frontend Image Collection — PARTIALLY WORKS

- `AgentChat.tsx:245-247` — `attachedImages` state, `isDraggingImage` state.
- `AgentChat.tsx:456-465` — `processImageFile()` reads image files as base64 data URLs.
- `AgentChat.tsx:488-502` — `handleDrop()` processes drag-and-dropped image files.
- `AgentChat.tsx:504-523` — `handlePaste()` processes pasted images from clipboard.
- `AgentChat.tsx:1072-1086` — Attached image preview thumbnails with remove buttons.
- `AgentChat.tsx:1133-1139` — Camera icon button dispatches `halbert:capture-screenshot`.

**Drag/drop and paste work** — images are collected into `attachedImages` and previewed.

### 1.3 The Broken Chain — THREE BREAKS

**Break 1: Images never reach the backend.**

`AgentChat.tsx:773`:
```
// TODO: Pass images to agent backend when vision support is added
sendMessage(input.trim(), undefined, picker.selection);
```

`sendMessage` in `useAgentStream.ts:662`:
```typescript
const sendMessage = useCallback((message: string, sessionId?: string, selection?: ModelSelection) => {
```

The `sendMessage` function does not accept an `images` parameter. The `attachedImages` array is cleared (`setAttachedImages([])` on line 770) but the base64 data is never passed to the API call. The backend's `images` field on `SendMessageRequest` is never populated.

**Break 2: Screenshot event is never consumed.**

`AgentChat.tsx:1135` dispatches `halbert:capture-screenshot`.
`Layout.tsx:265-296` handles it — uses `html2canvas` to capture the dashboard DOM, then dispatches `halbert:add-screenshot` with `{ dataUrl, base64, name }`.

But `AgentChat.tsx` has **no listener** for `halbert:add-screenshot`. The event is dispatched into the void. The screenshot is captured, converted to base64, and then dropped on the floor.

**Break 3: "Screenshot" captures the dashboard, not the desktop.**

`Layout.tsx:267` uses `html2canvas` on `document.body` — this captures the Halbert dashboard's own rendered DOM, not the actual operating system desktop. For a sysadmin assistant that needs to see terminal windows, error dialogs, system preferences, or other applications, this is useless. It's a screenshot of itself.

### 1.4 No Webcam Support

There is zero webcam infrastructure. No OpenCV, no camera capture, no webcam UI controls.

### 1.5 No Agent-Callable Screenshot Tool

The agent state machine has tools (`tools/system_tools.py`) for disk space, service status, etc. There is no `capture_screenshot` tool the LLM can call autonomously to look at the screen when it needs visual context.

### 1.6 No Visual State Tracker

`integrations/state_trackers.py` has 4 trackers: `DiskHealthTracker`, `ServiceStatusTracker`, `SystemResourceTracker`, `AdminPresenceTracker`. There is no visual state tracker that could notice "error dialog on screen" or "terminal showing a stack trace."

---

## 2. Architecture: Two Capture Sources, One Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                    CAPTURE SOURCES                           │
│                                                              │
│  ┌──────────────┐          ┌──────────────┐                 │
│  │ Screen Capture│         │ Webcam Capture│                 │
│  │ (MSS / SCKit) │         │ (OpenCV)      │                 │
│  │               │         │               │                 │
│  │ - Full screen │         │ - Frame grab  │                 │
│  │ - Region      │         │ - 1 FPS ambient│                │
│  │ - Window      │         │ - On-demand   │                 │
│  └──────┬───────┘          └──────┬───────┘                 │
│         │                         │                          │
│         v                         v                          │
│  ┌──────────────────────────────────────┐                    │
│  │      Frame Processor (local)          │                    │
│  │  - Downscale to model-optimal size    │                    │
│  │  - JPEG encode (quality 85)           │                    │
│  │  - Base64 encode                      │                    │
│  └──────────────┬───────────────────────┘                    │
│                 │                                             │
│                 v                                             │
│  ┌──────────────────────────────────────┐                    │
│  │      Vision Router                    │                    │
│  │  - User-attached images → send with   │                    │
│  │    message (existing path)            │                    │
│  │  - Agent tool call → attach to turn   │                    │
│  │  - Ambient webcam → visual state      │                    │
│  │    tracker (text summary, not image)  │                    │
│  └──────────────┬───────────────────────┘                    │
│                 │                                             │
│                 v                                             │
│  ┌──────────────────────────────────────┐                    │
│  │  Vision Model (local Ollama only)     │                    │
│  │  get_vision_model() → llm_config      │                    │
│  │  vision_model slot                    │                    │
│  └──────────────────────────────────────┘                    │
└─────────────────────────────────────────────────────────────┘
```

**Privacy boundary:** All frames are processed locally. Frames are only sent to the configured vision model endpoint. If the vision model points to a cloud API, a prominent warning is shown in settings. The default is local Ollama. No frame is ever stored to disk unless the user explicitly saves a conversation with images.

---

## 3. Screen Capture

### 3.1 Library Choice

**Primary: MSS** (`pip install mss`)
- Cross-platform (macOS + Linux)
- ~15-22 FPS full screen on M2 Pro, ~60 FPS for regions
- 30x faster than pyautogui/PIL on macOS
- Direct NumPy array output via `sct.grab()`
- Pure Python, no native compilation needed

**macOS enhancement: ScreenCaptureKit** (via `pyobjc`)
- Native macOS 12.1+ screen capture API
- Higher performance than MSS on macOS (hardware-accelerated)
- Supports per-window capture (not just full screen)
- Requires TCC permission (Screen Recording entitlement)
- Used as an optional fast path when available; MSS as fallback

**Linux: MSS uses X11/XShm** — works on X11. For Wayland, `mss` may need `xdg-desktop-portal` integration (future work; X11 is the primary Linux target for now).

### 3.2 Screen Capture Module

New file: `halbert_core/halbert_core/vision/screen_capture.py`

```python
class ScreenCapture:
    """Cross-platform screen capture. MSS primary, ScreenCaptureKit on macOS when available."""

    def __init__(self):
        self._sct = mss.mss()
        self._sckit_available = self._check_sckit()

    def capture_full(self) -> bytes:
        """Full primary monitor as JPEG bytes."""
        monitor = self._sct.monitors[0]
        frame = np.asarray(self._sct.grab(monitor))  # BGRA
        return self._encode_jpeg(frame)

    def capture_region(self, x: int, y: int, w: int, h: int) -> bytes:
        """Specific screen region as JPEG bytes."""
        region = {"top": y, "left": x, "width": w, "height": h}
        frame = np.asarray(self._sct.grab(region))
        return self._encode_jpeg(frame)

    def capture_to_base64(self, region=None, max_dim=1568) -> str:
        """Capture and return base64 JPEG, downscaled to max_dim on longest side."""
        jpeg = self.capture_full() if region is None else self.capture_region(**region)
        return base64.b64encode(jpeg).decode("ascii")

    def _encode_jpeg(self, frame_bgra: np.ndarray, quality=85, max_dim=1568) -> bytes:
        """Convert BGRA → BGR, downscale, JPEG encode."""
        frame = frame_bgra[:, :, :3]  # Strip alpha
        h, w = frame.shape[:2]
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            frame = cv2.resize(frame, (int(w*scale), int(h*scale)))
        return cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()
```

**Downscale target:** 1568px max dimension (Claude's max input resolution). For local Ollama vision models (llava, etc.), 768px is typically sufficient and faster. The `max_dim` parameter lets the caller choose.

### 3.3 macOS TCC Permission

Screen capture on macOS requires Screen Recording permission in System Settings → Privacy & Security → Screen Recording. The first capture attempt will fail (or return a black frame) until the user grants permission.

The module should:
1. Detect when permission is missing (black frame or MSS error)
2. Return a structured error: `{"error": "screen_permission_required", "platform": "macos"}`
3. The frontend shows a dialog: "Halbert needs Screen Recording permission to capture your screen. Open System Settings?"

On macOS Sequoia (15+), the permission must be re-confirmed monthly. The module should handle this gracefully — if a previously-working capture starts returning black frames, surface the re-auth prompt.

---

## 4. Webcam Capture

### 4.1 Library Choice

**OpenCV** (`pip install opencv-python`)
- Standard, cross-platform, well-documented
- `cv2.VideoCapture(0)` for default webcam
- 30 FPS capture standard
- Already recommended in the technical research doc

### 4.2 Webcam Capture Module

New file: `halbert_core/halbert_core/vision/webcam_capture.py`

```python
class WebcamCapture:
    """Webcam capture via OpenCV. Single-frame grab, not continuous streaming."""

    def __init__(self, camera_index: int = 0):
        self._camera_index = camera_index
        self._cap = None  # Lazy-open; don't hold the camera when idle

    def grab_frame(self) -> bytes:
        """Open camera, grab one frame, close camera. Returns JPEG bytes."""
        cap = cv2.VideoCapture(self._camera_index)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open camera {self._camera_index}")
        try:
            ret, frame = cap.read()
            if not ret:
                raise RuntimeError("Camera read failed")
            return self._encode_jpeg(frame)
        finally:
            cap.release()

    def grab_to_base64(self, max_dim=768) -> str:
        """Grab frame and return base64 JPEG."""
        jpeg = self.grab_frame()
        return base64.b64encode(jpeg).decode("ascii")
```

**Key design decision: lazy-open, not persistent.** The camera is opened per-capture and released immediately. This:
- Avoids holding the camera (and its LED) when Halbert isn't actively looking
- Avoids the privacy concern of an always-on camera
- Makes the "Halbert is looking" state explicit and momentary
- Works around macOS camera LED behavior (LED is on while camera is open)

**Ambient mode (future):** If we later want periodic webcam checks (e.g., "is someone at the desk?"), a separate `AmbientWebcamMonitor` class would open the camera at 1 FPS intervals, run a lightweight local CV check (face detection via MediaPipe), and close between checks. This is NOT in the initial scope.

### 4.3 Camera Permission

macOS: Camera access requires TCC permission (Privacy & Security → Camera). Same pattern as screen capture — detect missing permission, surface a dialog.

Linux: Camera access is typically `/dev/video0`. No TCC, but the user must be in the `video` group. If the device doesn't exist or isn't readable, return a structured error.

---

## 5. Agent Screenshot Tool

The LLM needs to be able to call "take a screenshot" autonomously — not just when the user attaches an image. When the user says "what's on my screen?" or "check if there's an error dialog," the agent should be able to capture the screen and reason about it.

### 5.1 Tool Definition

Add to `tools/system_tools.py` (or a new `tools/vision_tools.py`):

```python
VISION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "capture_screenshot",
            "description": "Capture the current screen. Use this when the user asks about what's on screen, an error dialog, a terminal output they can see, or anything visual on their display.",
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {
                        "type": "object",
                        "description": "Optional screen region to capture instead of full screen",
                        "properties": {
                            "x": {"type": "integer"},
                            "y": {"type": "integer"},
                            "width": {"type": "integer"},
                            "height": {"type": "integer"}
                        }
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "capture_webcam",
            "description": "Capture a single frame from the webcam. Use this when the user asks you to look at something physical (hardware, a label, a screen on another device).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]
```

### 5.2 Tool Execution

The tool executor returns `ExecutionResult(success, result, ...)`. The state machine's `_handle_executing` (line ~2392) calls `_format_tool_observation(name, args, result.result)` which converts the result to a string observation. For vision tools, we need a different path.

**Approach: structured result with image field.**

The vision tool handler returns a dict instead of a string:

```python
async def _capture_screenshot(self, args: Dict) -> dict:
    from ..vision.screen_capture import ScreenCapture
    cap = ScreenCapture()
    base64_img = cap.capture_to_base64()
    return {"image": base64_img, "description": "Screenshot captured"}
```

The state machine's `_handle_executing` needs to detect this:

```python
# In _handle_executing, after result = await self.tools.execute(...):
if result.success and isinstance(result.result, dict) and "image" in result.result:
    # Append the image to ctx.images so the next LLM call uses the vision path
    if self.ctx.images is None:
        self.ctx.images = []
    self.ctx.images.append(result.result["image"])
    # The observation is the text description, not the base64
    self.ctx.add_observation(
        f"Executed {tool_name}: {result.result.get('description', 'image captured')}"
    )
else:
    # Existing path: format as text observation
    self.ctx.add_observation(
        _format_tool_observation(tool_name, tool_args, result.result)
    )
```

This works because `ctx.images` is already threaded through to both `self.llm.chat()` and `self.llm.stream()` in PLANNING (line 1624) and RESPONDING (line 2587). Appending mid-turn means the next LLM call in the loop will route through the vision path via `_resolve_turn_model` (line 427-432: `if images or ...`).

**Important:** `ctx.images` is set once at turn start from the user's attached images. Vision tool captures *append* to this list, they don't replace it. This means user-attached images and agent-captured screenshots coexist in the same turn.

### 5.3 Tool Registration

Vision tools should be registered via a `register_vision_tools()` method on `ToolExecutor`, following the `register_system_tools()` pattern (line 606):

```python
def register_vision_tools(self):
    """Register vision capture tools."""
    from .vision_tools import VISION_TOOL_SCHEMAS, VISION_TOOL_HANDLERS
    for name, schema in VISION_TOOL_SCHEMAS.items():
        handler = VISION_TOOL_HANDLERS.get(name)
        if handler:
            self.register(name, handler, schema)
```

This is called wherever `register_system_tools()` is called (likely in the agent setup/wiring code).

### 5.4 Safety Classification

The safety framework's `_classify_builtin()` (line 388) has explicit branches for known tools. Unknown tools default to `MEDIUM` (line 417). Vision tools need explicit entries:

```python
# In _classify_builtin(), add before the else branch:
elif tool_name in ("capture_screenshot", "capture_webcam"):
    return SafetyCheckResult(
        risk_level=RiskLevel.SAFE,
        allowed=True,
        requires_confirmation=False,
        reason="Local vision capture (read-only)"
    )
```

Both tools are classified as `SAFE` (auto-execute, no confirmation). The privacy gates are handled at the OS level (TCC permissions) and via the `vision_config.yml` enabled/disabled flags, not through the safety framework. The safety framework is about system damage risk, not privacy consent — that's a separate layer.

| Tool | Risk Level | Rationale |
|------|-----------|-----------|
| `capture_screenshot` | SAFE | Read-only, captures display pixels, no system modification |
| `capture_webcam` | SAFE | Read-only, captures one frame, no system modification |

Webcam's first-use consent is handled by the vision config layer (`first_use_consent.webcam`), not the safety framework. The camera LED provides hardware-level notification on macOS.

---

## 6. Fixing the Broken Image Chain

This is the highest-priority item. The backend is ready, the frontend collects images, but they never connect.

### 6.1 Fix Break 1: Send images to backend

**`useAgentStream.ts`** — `sendMessage` needs an `images` parameter. The request body is `JSON.stringify` (not URLSearchParams — the existing code at line 742 uses `Content-Type: application/json`):

```typescript
const sendMessage = useCallback((
    message: string,
    sessionId?: string,
    selection?: ModelSelection,
    images?: string[],  // NEW: base64-encoded images
) => {
    // ... existing code unchanged through line 738 ...

    fetch(apiUrl('/api/agent/message'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: message,
        session_id: sid,
        max_tokens: maxTokens,
        temperature: temperature,
        // NEW: images field matches SendMessageRequest.images on the backend
        ...(images && images.length > 0 ? { images } : {}),
        ...(selection?.model ? { model: selection.model } : {}),
        ...(selection?.tier && selection.tier !== 'auto'
          ? { tier: selection.tier }
          : {}),
        ...(selection?.endpointId ? { endpoint_id: selection.endpointId } : {}),
      }),
      signal: controller.signal
    }).then(async (response) => {
      // ... rest of existing code unchanged ...
```

The dependency array at line 810 (`[initSession, handleEvent, options]`) does not need changes — `images` is passed per-call, not captured as a closure dep.

**`AgentChat.tsx`** — Pass images when sending (line ~773-776, replace the TODO):

```typescript
// The imageData extraction already exists at lines 748-751.
// The fix is just passing it to sendMessage:
sendMessage(
    input.trim() || (imageData.length > 0 ? '[Image]' : ''),
    undefined,
    picker.selection,
    imageData.length > 0 ? imageData : undefined,
);
```

### 6.2 Fix Break 2: Consume screenshot event

**`AgentChat.tsx`** — Add a listener for `halbert:add-screenshot`:

```typescript
useEffect(() => {
    const handleAddScreenshot = (e: Event) => {
        const detail = (e as CustomEvent).detail;
        if (detail?.dataUrl) {
            setAttachedImages(prev => [...prev, {
                id: 'screenshot-' + Date.now(),
                dataUrl: detail.dataUrl,
                name: detail.name || 'Screenshot',
            }]);
        }
    };
    window.addEventListener('halbert:add-screenshot', handleAddScreenshot);
    return () => window.removeEventListener('halbert:add-screenshot', handleAddScreenshot);
}, []);
```

### 6.3 Fix Break 3: Real screen capture

Replace the `html2canvas` approach in `Layout.tsx` with a backend call that uses the real screen capture module.

**New backend endpoint** in `dashboard/routes/agent.py` (or a new `dashboard/routes/vision.py`):

```python
@router.get("/api/vision/screenshot")
async def capture_screenshot(region: Optional[str] = None):
    """Capture the real screen and return base64 JPEG."""
    from ...vision.screen_capture import ScreenCapture
    cap = ScreenCapture()
    try:
        base64_img = cap.capture_to_base64()
        return {"image": base64_img, "format": "jpeg"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
```

**`Layout.tsx`** — Replace html2canvas with backend call:

```typescript
const handleCaptureScreenshot = async () => {
    try {
        const resp = await fetch(apiUrl('/api/vision/screenshot'));
        if (!resp.ok) throw new Error('Screenshot failed');
        const data = await resp.json();
        const dataUrl = `data:image/jpeg;base64,${data.image}`;
        window.dispatchEvent(new CustomEvent('halbert:add-screenshot', {
            detail: { dataUrl, base64: data.image, name: `Screenshot ${new Date().toLocaleTimeString()}` }
        }));
    } catch (err) {
        console.error('[Layout] Screenshot failed:', err);
    }
};
```

This removes the `html2canvas` dependency entirely and captures the real desktop.

---

## 7. Privacy Gates and Defaults

### 7.1 Configuration

New config file: `~/.config/halbert/vision_config.yml`

```yaml
screen_capture:
  enabled: false          # OFF by default
  max_fps: 1              # For ambient mode (future)
  quality: 85             # JPEG quality
  max_dimension: 1568     # Downscale target

webcam:
  enabled: false          # OFF by default
  camera_index: 0
  quality: 85
  max_dimension: 768

privacy:
  cloud_vision_warning_shown: false
  first_use_consent:
    screen: false         # Set true after first accept
    webcam: false         # Set true after first accept
```

### 7.2 Consent Flow

**First screen capture attempt:**
1. Frontend detects `screen_capture.enabled == false`
2. Shows dialog: "Halbert wants to capture your screen. This will take a screenshot of your display and send it to your vision model ([model name] at [endpoint]). Screenshots are not stored. Enable screen capture?"
3. If the vision model endpoint is a cloud URL (not localhost), add: "WARNING: Your vision model is configured to a cloud endpoint ([url]). Screenshots will be sent to this external service. Consider using a local Ollama vision model for privacy. Enable anyway?"
4. On accept: set `screen_capture.enabled = true`, `first_use_consent.screen = true`
5. macOS: also prompt for TCC Screen Recording permission

**First webcam capture attempt:**
1. Frontend detects `webcam.enabled == false`
2. Shows dialog: "Halbert wants to access your camera. This will capture a single frame from your webcam and send it to your vision model. The camera LED will light up briefly. Frames are not stored. Enable webcam access?"
3. Same cloud warning if applicable
4. On accept: set `webcam.enabled = true`, `first_use_consent.webcam = true`
5. macOS: also prompt for TCC Camera permission

### 7.3 Visual Indicators

When vision is active (a capture is in progress or an image is being sent to the vision model):

- **Chat composer**: A small "eye" icon (lucide `Eye`) appears next to the camera button with a subtle pulse animation
- **Timeline**: When a vision tool executes, the tool call event shows "Captured screenshot" or "Captured webcam frame" with a thumbnail
- **Status bar**: If ambient mode is ever added, a persistent "Vision active" indicator

### 7.4 Cloud Vision Warning

In Settings → AI Models, when the vision model endpoint is not localhost/127.0.0.1:

```
[!] Vision model is configured to a cloud endpoint
    Screenshots and webcam frames will be sent to: [url]
    For privacy, consider using a local vision model (e.g., llava via Ollama).
    [Use local model] [Dismiss]
```

This is a warning, not a block — the user can use cloud vision if they choose. But the default should steer toward local.

---

## 8. UI Changes

### 8.1 Chat Composer (AgentChat.tsx)

The existing camera icon button stays, but:
- It now triggers a real screen capture (via backend), not html2canvas
- A second icon button (lucide `Video`) for webcam capture is added next to it
- Both show a brief loading state during capture
- Captured images appear in the `attachedImages` preview strip

```
[textarea ...........................] [camera] [video] [send]
                                         ^        ^
                                    screenshot  webcam
```

### 8.2 Settings Page — New "Vision" Tab

Add a "Vision" tab to Settings (alongside AI Models, Personality, etc.):

```
Vision Settings
────────────────────────────────────────

Screen Capture
  [ ] Enable screen capture
      When enabled, Halbert can take screenshots of your display
      to answer questions about what's on screen.

  Quality:     [85] (JPEG, 1-100)
  Max size:    [1568] px (longest side)

Webcam
  [ ] Enable webcam access
      When enabled, Halbert can capture frames from your camera
      to look at physical objects, hardware, etc.

  Camera:      [Camera 0 ▾] (dropdown of available cameras)
  Quality:     [85]
  Max size:    [768] px

Privacy
  Vision model: [llava:7b] at [http://127.0.0.1:11434]
  [x] Warn before sending frames to non-local endpoints
  [ ] Store images in conversation history
      (Off by default — images are processed but not persisted)

  [Test screen capture]  [Test webcam]
```

### 8.3 Timeline — Vision Tool Results

When the agent calls `capture_screenshot` or `capture_webcam`, the timeline shows:

```
[tool_call] capture_screenshot()
[tool_result] Screenshot captured (1920x1080 → 1568x882)
[thumbnail preview of the captured frame]
```

The thumbnail is shown inline in the timeline, similar to how user-attached images appear. Clicking it opens a full-size view.

---

## 9. New Files

| Path | Purpose |
|------|---------|
| `halbert_core/halbert_core/vision/__init__.py` | Package marker |
| `halbert_core/halbert_core/vision/screen_capture.py` | MSS-based screen capture + macOS SCKit fast path |
| `halbert_core/halbert_core/vision/webcam_capture.py` | OpenCV-based webcam capture |
| `halbert_core/halbert_core/vision/config.py` | VisionConfig dataclass, load/save from `vision_config.yml` |
| `halbert_core/halbert_core/tools/vision_tools.py` | `capture_screenshot` and `capture_webcam` tool definitions |
| `halbert_core/halbert_core/dashboard/routes/vision.py` | `GET /api/vision/screenshot`, `GET /api/vision/webcam`, `GET/PUT /api/vision/config` |
| `halbert_core/tests/test_screen_capture.py` | Unit tests for screen capture (mocked MSS) |
| `halbert_core/tests/test_webcam_capture.py` | Unit tests for webcam capture (mocked OpenCV) |
| `halbert_core/tests/test_vision_tools.py` | Unit tests for vision tool definitions and execution |
| `halbert_core/tests/test_vision_routes.py` | Unit tests for vision API endpoints |

## 10. Modified Files

| Path | Change |
|------|--------|
| `dashboard/frontend/src/hooks/useAgentStream.ts` | Add `images` parameter to `sendMessage`, include in request body |
| `dashboard/frontend/src/components/agent/AgentChat.tsx` | Pass `imageData` to `sendMessage`, add `halbert:add-screenshot` listener, add webcam button |
| `dashboard/frontend/src/components/Layout.tsx` | Replace html2canvas with backend `/api/vision/screenshot` call |
| `dashboard/frontend/src/pages/Settings.tsx` | Add Vision tab with screen capture, webcam, privacy controls |
| `dashboard/frontend/src/components/Layout.tsx` | Add Vision to navigation |
| `halbert_core/halbert_core/dashboard/app.py` | Register `vision.router` |
| `halbert_core/halbert_core/tools/executor.py` | Handle vision tool results (detect `image` field, attach to turn) |
| `halbert_core/halbert_core/agents/state_machine.py` | Pass vision tool images through to next LLM call |
| `halbert_core/halbert_core/tools/safety.py` | Classify `capture_screenshot` as LOW, `capture_webcam` as MEDIUM |
| `requirements.txt` or `pyproject.toml` | Add `mss`, `opencv-python` dependencies |

## 11. Dependencies

| Package | Purpose | Size | Platform |
|---------|---------|------|----------|
| `mss` | Screen capture | ~50KB | macOS, Linux, Windows |
| `opencv-python` | Webcam capture, image encoding | ~60MB | All |
| `numpy` | Array manipulation (already installed) | — | — |
| `pyobjc-framework-ScreenCaptureKit` | macOS native fast path (optional) | ~5MB | macOS only |

`opencv-python` is the heavy dependency. If we want to avoid it, we could use `Pillow` + `mss` for screen capture (MSS already provides the frame, Pillow can JPEG-encode) and a lighter webcam library. But OpenCV is the standard and gives us the encoding pipeline for free.

**Alternative without OpenCV:** Use `mss` for screen capture (it can grab to PIL Image), and `v4l2py` on Linux / `AVFoundation` bridge on macOS for webcam. But this is more code for less benefit. OpenCV is the pragmatic choice.

---

## 12. Implementation Order

### Phase 1: Fix the broken chain (smallest, highest impact)

1. Add `images` parameter to `sendMessage` in `useAgentStream.ts`
2. Pass `imageData` to `sendMessage` in `AgentChat.tsx` (fix the TODO)
3. Add `halbert:add-screenshot` listener in `AgentChat.tsx`
4. **Result:** Drag/drop and paste images now actually reach the vision model. This is a pure frontend fix with zero new dependencies.

### Phase 2: Real screen capture

1. Create `vision/screen_capture.py` with MSS
2. Add `GET /api/vision/screenshot` endpoint
3. Replace html2canvas in `Layout.tsx` with backend call
4. Remove `html2canvas` dependency
5. **Result:** The camera button captures the real desktop, not the dashboard.

### Phase 3: Agent screenshot tool

1. Create `tools/vision_tools.py` with `capture_screenshot` definition
2. Register vision tools in the tool executor
3. Modify state machine to handle image-bearing tool results
4. Classify tools in `safety.py`
5. **Result:** The LLM can autonomously capture the screen when it needs visual context.

### Phase 4: Webcam capture

1. Add `opencv-python` dependency
2. Create `vision/webcam_capture.py`
3. Add `GET /api/vision/webcam` endpoint
4. Add webcam button to chat composer
5. Add `capture_webcam` tool definition
6. **Result:** Halbert can look at physical objects via webcam.

### Phase 5: Privacy gates and settings UI

1. Create `vision/config.py` with VisionConfig
2. Add Vision tab to Settings page
3. Implement consent dialogs (first-use)
4. Implement cloud endpoint warning
5. Add visual indicators during capture
6. **Result:** Privacy controls are in place, everything is opt-in.

### Phase 6: macOS native enhancements (optional)

1. Add `pyobjc-framework-ScreenCaptureKit` optional dependency
2. Implement SCKit fast path in `screen_capture.py`
3. Handle TCC permission detection and re-auth prompts
4. **Result:** Better performance on macOS, proper permission handling.

---

## 13. What This Plan Does NOT Include

- **Continuous video streaming** — This is single-frame capture, not a video feed. The agent captures a frame when it needs to see something, not a constant stream.
- **Cloud video** — Frames only go to the configured vision model endpoint. No cloud video services. The settings UI actively warns against cloud vision endpoints.
- **HA/Frigate integration** — That's the separate "HA listener" path (Track 2 from the CV research). This plan is purely about the local sysadmin Halbert having basic eyes.
- **Object detection / scene understanding** — No YOLO, MediaPipe, or local CV inference beyond the vision LLM itself. The vision model (e.g., llava) does all interpretation. Local CV preprocessing is a future optimization.
- **Ambient monitoring** — No always-on camera or periodic screen checks. Every capture is explicitly triggered (by user button press or agent tool call).
- **Image storage** — Images are processed by the vision model and then discarded. They are not saved to conversation history unless the user explicitly enables that in settings (default off).

---

## 14. Relationship to Other CV Research

| Document | Scope | Relationship |
|----------|-------|-------------|
| `01-TECHNICAL-CV-LANDSCAPE.md` | Full technical landscape (frameworks, papers, products) | This plan uses MSS + OpenCV from its recommendations (§5.1) |
| `02-LEGAL-PRIVACY-CV.md` | Legal/privacy framework | This plan implements its recommendations: default-off, consent dialogs, cloud warning, no storage |
| `03-INTEGRATION-POINTS-AND-UI.md` | Full codebase integration analysis (running) | This plan is the focused, actionable subset — just the core local vision |
| `.handoff/HOME-AUTOMATION-*.md` | HA integration (Phase 4: Frigate) | Separate path. HA CV events come through `ha_event_mapper.py`, not through this local vision module |

This plan is the **minimum viable vision** — enough for Halbert to see the screen and webcam, with proper privacy gates. The HA/Frigate path and the advanced local CV (YOLO, MediaPipe) are future phases that build on this foundation.

---

## 15. Scrutiny Findings (Reverse-Engineering Pass)

Every code reference in this plan was verified against the actual codebase. Findings:

### Verified Correct

- **Break 1 (images never sent):** Confirmed. `AgentChat.tsx:773` has the TODO, `sendMessage` at `useAgentStream.ts:662` has no `images` parameter.
- **Break 2 (screenshot event unconsumed):** Confirmed. `Layout.tsx:279` dispatches `halbert:add-screenshot`, but `AgentChat.tsx` has no listener for it.
- **Break 3 (html2canvas captures dashboard):** Confirmed. `Layout.tsx:268-269` uses `html2canvas(document.body)`.
- **Backend vision routing:** Confirmed fully wired. `agent.py:1323` passes `request.images` to `agent.process()`, which sets `ctx.images` (states.py:192), which is threaded to `self.llm.chat()` (state_machine.py:1624) and `self.llm.stream()` (state_machine.py:2587).
- **`_resolve_turn_model` auto-routes on images:** Confirmed at agent.py:427-432.
- **`SendMessageRequest.images` field:** Confirmed at agent.py:53 — `Optional[List[str]]`.
- **State machine OBSERVING state:** Confirmed at state_machine.py:2407. Transitions to REFLECTING or PLANNING.
- **`StateContext.images`:** Confirmed at states.py:192 — `Optional[List[str]] = None`.
- **`add_observation` takes a string:** Confirmed at states.py:237-239.

### Fixed During Scrutiny

1. **Request body format:** Plan originally showed `URLSearchParams` — actual code uses `JSON.stringify` with `Content-Type: application/json` (useAgentStream.ts:741-742). Fixed in section 6.1.

2. **Safety classification:** Plan originally said `capture_screenshot` = LOW, `capture_webcam` = MEDIUM. But the safety framework's `_classify_builtin()` (safety.py:388) has no entry for these — unknown tools default to `MEDIUM` (safety.py:417). Fixed: both should be explicitly classified as `SAFE` in `_classify_builtin()`, with privacy consent handled separately by the vision config layer. Section 5.4 updated.

3. **Tool registration pattern:** Plan didn't specify how tools get registered. The executor has `register_system_tools()` (executor.py:606) that imports schemas/handlers from `system_info.py`. Vision tools should follow the same pattern with a `register_vision_tools()` method. Section 5.3 added.

4. **Tool result handling:** Plan said "detect when a tool result contains an `image` field" but didn't specify the mechanism. `ExecutionResult.result` is `Any` (executor.py:34), and `_handle_executing` calls `_format_tool_observation(name, args, result.result)` which does `str(result)` (state_machine.py:151). A dict result with an `"image"` key would be stringified into `{'image': 'base64...'}` — useless. Fixed: the state machine needs to check `isinstance(result.result, dict) and "image" in result.result` *before* calling `_format_tool_observation`, append the image to `ctx.images`, and use the `"description"` field as the observation text. Section 5.2 rewritten with exact code.

5. **`ctx.images` append vs replace:** Plan didn't clarify that vision tool captures must *append* to `ctx.images`, not replace it. User-attached images and agent-captured screenshots coexist. Section 5.2 now states this explicitly.

### No Issues Found

- The `sendMessage` dependency array (`[initSession, handleEvent, options]` at line 810) does not need changes — `images` is a per-call parameter, not a closure dep.
- The intake pipeline's image detection (`intake/signals.py`) works on message text (markdown image syntax, data URIs) — it doesn't need changes for the vision tool path, since tool-captured images bypass intake.
- The context assembler doesn't need changes — it doesn't touch `ctx.images`, which is handled directly by the LLM adapter.
