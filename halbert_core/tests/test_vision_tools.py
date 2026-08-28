# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for vision tools and the state machine's image-result handling."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# Vision tool schemas and handlers
# ─────────────────────────────────────────────────────────────────────────────

class TestVisionToolSchemas:
    def test_screenshot_schema_structure(self):
        from halbert_core.tools.vision_tools import VISION_TOOL_SCHEMAS
        schema = VISION_TOOL_SCHEMAS["capture_screenshot"]
        assert schema["name"] == "capture_screenshot"
        assert "description" in schema
        params = schema["parameters"]
        assert params["type"] == "object"
        assert "region" in params["properties"]
        assert params["required"] == []

    def test_handler_mapping(self):
        from halbert_core.tools.vision_tools import VISION_TOOL_HANDLERS
        assert "capture_screenshot" in VISION_TOOL_HANDLERS
        assert callable(VISION_TOOL_HANDLERS["capture_screenshot"])

    def test_webcam_schema_structure(self):
        from halbert_core.tools.vision_tools import VISION_TOOL_SCHEMAS
        schema = VISION_TOOL_SCHEMAS["capture_webcam"]
        assert schema["name"] == "capture_webcam"
        assert "description" in schema
        params = schema["parameters"]
        assert "camera" in params["properties"]
        assert params["required"] == []

    def test_webcam_handler_mapping(self):
        from halbert_core.tools.vision_tools import VISION_TOOL_HANDLERS
        assert "capture_webcam" in VISION_TOOL_HANDLERS
        assert callable(VISION_TOOL_HANDLERS["capture_webcam"])


class TestCaptureWebcamHandler:
    """Test the webcam tool handler with mocked WebcamCapture."""

    @pytest.mark.asyncio
    async def test_returns_dict_with_image_key(self):
        import halbert_core.tools.vision_tools as vt
        vt._last_webcam_hash = None

        from halbert_core.tools.vision_tools import capture_webcam

        mock_cap = MagicMock()
        mock_cap.grab_frame.return_value = b"webcamjpeg"

        with patch("halbert_core.vision.config.is_webcam_enabled",
                    return_value=True), \
             patch("halbert_core.vision.config.load_config") as mock_load, \
             patch("halbert_core.vision.webcam_capture.WebcamCapture", return_value=mock_cap):
            mock_load.return_value = MagicMock(
                screen_capture=MagicMock(),
                webcam=MagicMock(camera_index=0, quality=85, max_dimension=768, grayscale=False),
            )
            result = await capture_webcam({})

        assert isinstance(result, dict)
        assert "image" in result
        assert "description" in result
        vt._last_webcam_hash = None

    @pytest.mark.asyncio
    async def test_blocked_when_disabled(self):
        """Privacy gate: capture_webcam must check config before capturing."""
        from halbert_core.tools.vision_tools import capture_webcam

        with patch("halbert_core.vision.config.is_webcam_enabled",
                    return_value=False), \
             patch("halbert_core.vision.webcam_capture.WebcamCapture") as mock_cap:
            result = await capture_webcam({})

        assert "error" in result
        assert result["error_type"] == "disabled"
        assert "image" not in result
        mock_cap.assert_not_called()


class TestCaptureScreenshotHandler:
    """Test the tool handler with mocked ScreenCapture."""

    @pytest.mark.asyncio
    async def test_returns_dict_with_image_key(self):
        import halbert_core.tools.vision_tools as vt
        vt._last_screenshot_hash = None  # Reset dedup

        from halbert_core.tools.vision_tools import capture_screenshot

        mock_cap = MagicMock()
        mock_cap.capture_full.return_value = b"jpegdata"

        with patch("halbert_core.vision.config.is_screen_capture_enabled",
                    return_value=True), \
             patch("halbert_core.vision.config.load_config") as mock_load, \
             patch("halbert_core.vision.screen_capture.ScreenCapture", return_value=mock_cap):
            mock_load.return_value = MagicMock(
                screen_capture=MagicMock(quality=85, max_dimension=1568, monitor_index=1, grayscale=False),
                webcam=MagicMock(),
            )
            result = await capture_screenshot({})

        assert isinstance(result, dict)
        assert "image" in result
        assert "description" in result
        assert "Screenshot" in result["description"]
        vt._last_screenshot_hash = None

    @pytest.mark.asyncio
    async def test_region_capture(self):
        import halbert_core.tools.vision_tools as vt
        vt._last_screenshot_hash = None

        from halbert_core.tools.vision_tools import capture_screenshot

        mock_cap = MagicMock()
        mock_cap.capture_region.return_value = b"regionjpeg"

        with patch("halbert_core.vision.config.is_screen_capture_enabled",
                    return_value=True), \
             patch("halbert_core.vision.config.load_config") as mock_load, \
             patch("halbert_core.vision.screen_capture.ScreenCapture", return_value=mock_cap):
            mock_load.return_value = MagicMock(
                screen_capture=MagicMock(quality=85, max_dimension=1568, monitor_index=1, grayscale=False),
                webcam=MagicMock(),
            )
            result = await capture_screenshot({
                "region": {"x": 100, "y": 200, "width": 800, "height": 600}
            })

        assert "image" in result
        assert "region" in result["description"].lower()
        mock_cap.capture_region.assert_called_once_with(100, 200, 800, 600)
        vt._last_screenshot_hash = None

    @pytest.mark.asyncio
    async def test_dependency_error_returns_error_dict(self):
        import halbert_core.tools.vision_tools as vt
        vt._last_screenshot_hash = None

        from halbert_core.tools.vision_tools import capture_screenshot

        with patch("halbert_core.vision.config.is_screen_capture_enabled",
                    return_value=True), \
             patch("halbert_core.vision.config.load_config") as mock_load, \
             patch("halbert_core.vision.screen_capture.ScreenCapture",
                   side_effect=ImportError("mss not installed")):
            mock_load.return_value = MagicMock(
                screen_capture=MagicMock(quality=85, max_dimension=1568, monitor_index=1, grayscale=False),
                webcam=MagicMock(),
            )
            result = await capture_screenshot({})

        assert "error" in result
        assert result.get("error_type") == "dependency_missing"
        assert "image" not in result
        vt._last_screenshot_hash = None

    @pytest.mark.asyncio
    async def test_screenshot_blocked_when_disabled(self):
        """Privacy gate: capture_screenshot must check config before capturing."""
        from halbert_core.tools.vision_tools import capture_screenshot

        with patch("halbert_core.vision.config.is_screen_capture_enabled",
                    return_value=False), \
             patch("halbert_core.vision.screen_capture.ScreenCapture") as mock_cap:
            result = await capture_screenshot({})

        assert "error" in result
        assert result["error_type"] == "disabled"
        assert "image" not in result
        # ScreenCapture must not have been instantiated
        mock_cap.assert_not_called()

    @pytest.mark.asyncio
    async def test_screenshot_proceeds_when_enabled(self):
        """When enabled, the capture proceeds normally."""
        from halbert_core.tools.vision_tools import capture_screenshot

        mock_cap = MagicMock()
        mock_cap.capture_full.return_value = b"jpegdata"

        with patch("halbert_core.vision.config.is_screen_capture_enabled",
                    return_value=True), \
             patch("halbert_core.vision.config.load_config") as mock_load, \
             patch("halbert_core.vision.screen_capture.ScreenCapture", return_value=mock_cap):
            mock_load.return_value = MagicMock(
                screen_capture=MagicMock(quality=85, max_dimension=1568, monitor_index=1, grayscale=False),
                webcam=MagicMock(),
            )
            result = await capture_screenshot({})

        assert result.get("image") is not None
        assert "description" in result

    @pytest.mark.asyncio
    async def test_screenshot_dedup_skips_unchanged_screen(self):
        """When the screen hasn't changed, dedup returns no image."""
        import halbert_core.tools.vision_tools as vt

        mock_cap = MagicMock()
        mock_cap.capture_full.return_value = b"sameframe"

        # Reset dedup state
        vt._last_screenshot_hash = None

        with patch("halbert_core.vision.config.is_screen_capture_enabled",
                    return_value=True), \
             patch("halbert_core.vision.config.load_config") as mock_load, \
             patch("halbert_core.vision.screen_capture.ScreenCapture", return_value=mock_cap):
            mock_load.return_value = MagicMock(
                screen_capture=MagicMock(quality=85, max_dimension=1568, monitor_index=1, grayscale=False),
                webcam=MagicMock(),
            )
            # First capture: should return image
            r1 = await vt.capture_screenshot({})
            assert "image" in r1

            # Second capture with same frame: should dedup
            r2 = await vt.capture_screenshot({})
            assert "image" not in r2
            assert r2.get("unchanged") is True
            assert "unchanged" in r2["description"].lower()

        # Cleanup
        vt._last_screenshot_hash = None


# ─────────────────────────────────────────────────────────────────────────────
# Safety classification
# ─────────────────────────────────────────────────────────────────────────────

class TestVisionToolSafety:
    def test_screenshot_classified_safe(self):
        from halbert_core.tools.safety import ToolSafetyFramework, RiskLevel
        safety = ToolSafetyFramework()
        result = safety.classify("capture_screenshot", {})
        assert result.risk_level == RiskLevel.SAFE
        assert result.allowed is True
        assert result.requires_confirmation is False

    def test_webcam_classified_safe(self):
        from halbert_core.tools.safety import ToolSafetyFramework, RiskLevel
        safety = ToolSafetyFramework()
        result = safety.classify("capture_webcam", {})
        assert result.risk_level == RiskLevel.SAFE


# ─────────────────────────────────────────────────────────────────────────────
# Tool executor registration
# ─────────────────────────────────────────────────────────────────────────────

class TestVisionToolRegistration:
    def test_register_vision_tools_adds_screenshot(self):
        from halbert_core.tools.executor import ToolExecutor
        executor = ToolExecutor()
        executor.register_vision_tools()
        schemas = {s["function"]["name"]: s["function"] for s in executor.get_schemas()}
        assert "capture_screenshot" in schemas

    def test_vision_tool_handler_is_callable(self):
        from halbert_core.tools.executor import ToolExecutor
        executor = ToolExecutor()
        executor.register_vision_tools()
        assert "capture_screenshot" in executor.tools
        assert callable(executor.tools["capture_screenshot"])


# ─────────────────────────────────────────────────────────────────────────────
# State machine image-result detection
# ─────────────────────────────────────────────────────────────────────────────

class TestStateMachineImageDetection:
    """Test that _handle_executing detects image-bearing tool results."""

    @pytest.mark.asyncio
    async def test_image_result_appended_to_ctx(self):
        """When a tool returns {image: ...}, it should be appended to ctx.images."""
        from halbert_core.agents.state_machine import AgentStateMachine, AgentState
        from halbert_core.agents.states import StateContext, ToolCall
        from halbert_core.tools.executor import ToolExecutor, ExecutionResult
        from halbert_core.tools.safety import RiskLevel, SafetyCheckResult

        # Mock executor that returns an image-bearing result
        mock_executor = MagicMock()
        mock_executor.get_schemas.return_value = []
        mock_executor.execute = AsyncMock(return_value=ExecutionResult(
            success=True,
            result={"image": "base64screenshot", "description": "Screenshot captured"},
            risk_level=RiskLevel.SAFE,
        ))

        # Mock safety to return SAFE
        mock_safety = MagicMock()
        mock_safety.classify.return_value = SafetyCheckResult(
            risk_level=RiskLevel.SAFE, allowed=True,
            requires_confirmation=False, reason="test",
        )
        mock_executor.safety = mock_safety

        agent = AgentStateMachine(llm_client=None, tool_executor=mock_executor, max_loops=5)
        agent.ctx = StateContext(
            session_id="test",
            request_id="req-1",
            user_query="what's on my screen?",
        )
        agent.ctx.images = None  # Start with no images
        agent.current_state = AgentState.EXECUTING

        # Add a pending tool call (states.py ToolCall uses name/args, not FunctionCall)
        agent.ctx.tool_calls.append(ToolCall(
            id="call-1",
            name="capture_screenshot",
            args={},
        ))
        agent.ctx.pending_confirmation = {"action_id": "call-1", "confirmed": True}

        # Run _handle_executing
        events = []
        async for event in agent._handle_executing():
            events.append(event)

        # Verify the image was appended to ctx.images
        assert agent.ctx.images is not None
        assert len(agent.ctx.images) == 1
        assert agent.ctx.images[0] == "base64screenshot"

        # Verify the observation mentions the description, not the base64
        assert any("Screenshot captured" in obs for obs in agent.ctx.observations)
        assert not any("base64screenshot" in obs for obs in agent.ctx.observations)

    @pytest.mark.asyncio
    async def test_non_image_result_uses_normal_path(self):
        """Non-image tool results should use the normal _format_tool_observation path."""
        from halbert_core.agents.state_machine import AgentStateMachine, AgentState
        from halbert_core.agents.states import StateContext, ToolCall
        from halbert_core.tools.executor import ExecutionResult
        from halbert_core.tools.safety import RiskLevel, SafetyCheckResult

        mock_executor = MagicMock()
        mock_executor.get_schemas.return_value = []
        mock_executor.execute = AsyncMock(return_value=ExecutionResult(
            success=True,
            result="Disk usage: 50%",
            risk_level=RiskLevel.SAFE,
        ))
        mock_safety = MagicMock()
        mock_safety.classify.return_value = SafetyCheckResult(
            risk_level=RiskLevel.SAFE, allowed=True,
            requires_confirmation=False, reason="test",
        )
        mock_executor.safety = mock_safety

        agent = AgentStateMachine(llm_client=None, tool_executor=mock_executor, max_loops=5)
        agent.ctx = StateContext(
            session_id="test", request_id="req-1", user_query="disk usage?",
        )
        agent.current_state = AgentState.EXECUTING

        agent.ctx.tool_calls.append(ToolCall(
            id="call-1",
            name="get_disk_usage",
            args={},
        ))
        agent.ctx.pending_confirmation = {"action_id": "call-1", "confirmed": True}

        events = []
        async for event in agent._handle_executing():
            events.append(event)

        # No images should be appended
        assert agent.ctx.images is None
        # The observation should contain the tool output
        assert any("Disk usage" in obs for obs in agent.ctx.observations)
