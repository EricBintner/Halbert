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


class TestCaptureScreenshotHandler:
    """Test the tool handler with mocked ScreenCapture."""

    @pytest.mark.asyncio
    async def test_returns_dict_with_image_key(self):
        from halbert_core.tools.vision_tools import capture_screenshot

        mock_cap = MagicMock()
        mock_cap.capture_to_base64.return_value = "base64datahere"

        with patch("halbert_core.vision.screen_capture.ScreenCapture", return_value=mock_cap):
            result = await capture_screenshot({})

        assert isinstance(result, dict)
        assert "image" in result
        assert result["image"] == "base64datahere"
        assert "description" in result
        assert "Screenshot" in result["description"]

    @pytest.mark.asyncio
    async def test_region_capture(self):
        from halbert_core.tools.vision_tools import capture_screenshot

        mock_cap = MagicMock()
        mock_cap.capture_to_base64.return_value = "regiondata"

        with patch("halbert_core.vision.screen_capture.ScreenCapture", return_value=mock_cap):
            result = await capture_screenshot({
                "region": {"x": 100, "y": 200, "width": 800, "height": 600}
            })

        assert result["image"] == "regiondata"
        assert "region" in result["description"].lower()
        # Verify region was passed
        call_args = mock_cap.capture_to_base64.call_args
        assert call_args.kwargs.get("region") == (100, 200, 800, 600)

    @pytest.mark.asyncio
    async def test_dependency_error_returns_error_dict(self):
        from halbert_core.tools.vision_tools import capture_screenshot

        with patch("halbert_core.vision.screen_capture.ScreenCapture",
                    side_effect=ImportError("mss not installed")):
            result = await capture_screenshot({})

        assert "error" in result
        assert result.get("error_type") == "dependency_missing"
        assert "image" not in result


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
