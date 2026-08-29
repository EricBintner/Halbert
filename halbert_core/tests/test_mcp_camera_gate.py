# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for MCP camera data gate — ensures no image data leaks via MCP."""
import pytest

from halbert_core.mcp.camera_gate import (
    strip_image_data, is_camera_query, FRIGATE_MCP_TOOLS,
    FRIGATE_MCP_TOOL_HANDLERS,
)


class TestStripImageData:
    def test_strips_image_field(self):
        payload = {"camera": "front", "image": "base64data"}
        result = strip_image_data(payload)
        assert result["image"] == "<redacted:image>"
        assert result["camera"] == "front"

    def test_strips_snapshot_field(self):
        payload = {"event_id": "123", "snapshot": "jpeg_bytes"}
        result = strip_image_data(payload)
        assert result["snapshot"] == "<redacted:image>"
        assert result["event_id"] == "123"

    def test_strips_data_uri(self):
        payload = {"frame": "data:image/jpeg;base64,abc123"}
        result = strip_image_data(payload)
        assert result["frame"] == "<redacted:image>"

    def test_preserves_safe_fields(self):
        payload = {
            "camera": "front_door",
            "label": "person",
            "score": 0.95,
            "zones": ["porch"],
            "has_snapshot": True,
        }
        result = strip_image_data(payload)
        assert result == payload  # nothing stripped

    def test_recursive_dict(self):
        payload = {
            "events": [
                {"camera": "front", "image": "data1"},
                {"camera": "back", "image": "data2"},
            ]
        }
        result = strip_image_data(payload)
        assert result["events"][0]["image"] == "<redacted:image>"
        assert result["events"][1]["image"] == "<redacted:image>"
        assert result["events"][0]["camera"] == "front"

    def test_nested_dict(self):
        payload = {
            "metadata": {"camera": "front", "thumbnail": "bytes"},
            "data": {"score": 0.9},
        }
        result = strip_image_data(payload)
        assert result["metadata"]["thumbnail"] == "<redacted:image>"
        assert result["data"]["score"] == 0.9

    def test_strips_frame_bytes(self):
        payload = {"frame_bytes": b"binary_data", "label": "person"}
        result = strip_image_data(payload)
        assert result["frame_bytes"] == "<redacted:image>"

    def test_strips_jpeg_field(self):
        payload = {"jpeg": "base64", "camera": "front"}
        result = strip_image_data(payload)
        assert result["jpeg"] == "<redacted:image>"

    def test_empty_dict(self):
        assert strip_image_data({}) == {}

    def test_non_dict_passthrough(self):
        assert strip_image_data("hello") == "hello"
        assert strip_image_data(42) == 42
        assert strip_image_data(None) is None

    def test_list_of_strings(self):
        payload = ["person", "car", "dog"]
        result = strip_image_data(payload)
        assert result == ["person", "car", "dog"]


class TestIsCameraQuery:
    def test_frigate_events_is_camera(self):
        assert is_camera_query("frigate_get_events") is True

    def test_frigate_reviews_is_camera(self):
        assert is_camera_query("frigate_get_reviews") is True

    def test_vision_detections_is_camera(self):
        assert is_camera_query("vision_get_detections") is True

    def test_non_camera_query(self):
        assert is_camera_query("get_vitals") is False
        assert is_camera_query("get_findings") is False
        assert is_camera_query("search_knowledge") is False


class TestFrigateMCPTools:
    def test_all_tools_have_descriptions(self):
        for name, tool in FRIGATE_MCP_TOOLS.items():
            assert "description" in tool, f"{name} missing description"

    def test_all_tools_have_input_schema(self):
        for name, tool in FRIGATE_MCP_TOOLS.items():
            assert "inputSchema" in tool, f"{name} missing inputSchema"

    def test_descriptions_mention_no_images(self):
        """Every camera tool description must state it doesn't expose images."""
        for name, tool in FRIGATE_MCP_TOOLS.items():
            desc = tool["description"].lower()
            assert "no image" in desc or "metadata only" in desc or "text metadata" in desc, \
                f"{name} description doesn't mention image restriction"

    def test_handlers_match_tools(self):
        assert set(FRIGATE_MCP_TOOLS.keys()) == set(FRIGATE_MCP_TOOL_HANDLERS.keys())

    def test_handler_count(self):
        assert len(FRIGATE_MCP_TOOL_HANDLERS) == 6


class TestMCPToolHandlers:
    def test_frigate_get_events_not_configured(self):
        """Should return error when Frigate isn't configured."""
        result = FRIGATE_MCP_TOOL_HANDLERS["frigate_get_events"]({})
        assert "error" in result or "events" in result

    def test_frigate_list_cameras_not_configured(self):
        result = FRIGATE_MCP_TOOL_HANDLERS["frigate_list_cameras"]({})
        assert "error" in result or "cameras" in result

    def test_frigate_get_active_detections_returns_list(self):
        result = FRIGATE_MCP_TOOL_HANDLERS["frigate_get_active_detections"]({})
        assert "active_detections" in result
        assert isinstance(result["active_detections"], list)

    def test_vision_get_detections_no_image_data(self):
        result = FRIGATE_MCP_TOOL_HANDLERS["vision_get_detections"]({})
        # Must not contain any image fields
        assert "image" not in result
        assert "snapshot" not in result
        assert "frame" not in result

    def test_vision_get_motion_no_image_data(self):
        result = FRIGATE_MCP_TOOL_HANDLERS["vision_get_motion"]({})
        assert "image" not in result
        assert "frame" not in result


class TestExpandedForbiddenFields:
    """Test the expanded forbidden field list."""

    def test_strips_img_field(self):
        from halbert_core.mcp.camera_gate import strip_image_data
        assert strip_image_data({"img": "data"})["img"] == "<redacted:image>"

    def test_strips_picture_field(self):
        from halbert_core.mcp.camera_gate import strip_image_data
        assert strip_image_data({"picture": "data"})["picture"] == "<redacted:image>"

    def test_strips_photo_field(self):
        from halbert_core.mcp.camera_gate import strip_image_data
        assert strip_image_data({"photo": "data"})["photo"] == "<redacted:image>"

    def test_strips_video_field(self):
        from halbert_core.mcp.camera_gate import strip_image_data
        assert strip_image_data({"video": "data"})["video"] == "<redacted:image>"

    def test_strips_clip_field(self):
        from halbert_core.mcp.camera_gate import strip_image_data
        assert strip_image_data({"clip": "data"})["clip"] == "<redacted:image>"

    def test_strips_thumb_field(self):
        from halbert_core.mcp.camera_gate import strip_image_data
        assert strip_image_data({"thumb": "data"})["thumb"] == "<redacted:image>"

    def test_strips_src_field(self):
        from halbert_core.mcp.camera_gate import strip_image_data
        assert strip_image_data({"src": "data"})["src"] == "<redacted:image>"

    def test_strips_base64_field(self):
        from halbert_core.mcp.camera_gate import strip_image_data
        assert strip_image_data({"base64": "data"})["base64"] == "<redacted:image>"


class TestCaseInsensitiveDataURI:
    """Test case-insensitive data URI detection."""

    def test_uppercase_data_uri(self):
        from halbert_core.mcp.camera_gate import strip_image_data
        payload = {"data": "DATA:IMAGE/JPEG;BASE64,abc123"}
        result = strip_image_data(payload)
        assert result["data"] == "<redacted:image>"

    def test_mixed_case_data_uri(self):
        from halbert_core.mcp.camera_gate import strip_image_data
        payload = {"data": "Data:Image/PNG;base64,xyz"}
        result = strip_image_data(payload)
        assert result["data"] == "<redacted:image>"

    def test_leading_whitespace_data_uri(self):
        from halbert_core.mcp.camera_gate import strip_image_data
        payload = {"data": "  data:image/jpeg;base64,abc"}
        result = strip_image_data(payload)
        assert result["data"] == "<redacted:image>"


class TestListImageStripping:
    """Test that image data in lists is stripped."""

    def test_data_uri_in_list(self):
        from halbert_core.mcp.camera_gate import strip_image_data
        payload = {"frames": ["data:image/jpeg;base64,abc", "text"]}
        result = strip_image_data(payload)
        assert result["frames"][0] == "<redacted:image>"
        assert result["frames"][1] == "text"

    def test_long_base64_in_list(self):
        from halbert_core.mcp.camera_gate import strip_image_data
        long_b64 = "A" * 1500
        payload = {"items": [long_b64, "short"]}
        result = strip_image_data(payload)
        assert result["items"][0] == "<redacted:image>"
        assert result["items"][1] == "short"


class TestGateResponse:
    """Test the gate_response() entry point."""

    def test_camera_query_stripped(self):
        from halbert_core.mcp.camera_gate import gate_response
        response = {"camera": "front", "image": "base64data"}
        result = gate_response("frigate_get_events", response)
        assert result["image"] == "<redacted:image>"
        assert result["camera"] == "front"

    def test_non_camera_query_passthrough(self):
        from halbert_core.mcp.camera_gate import gate_response
        response = {"vitals": {"heart_rate": 72}}
        result = gate_response("get_vitals", response)
        assert result == response  # unchanged


class TestVerifyBearerToken:
    """Test constant-time bearer token verification."""

    def test_correct_token(self):
        from halbert_core.mcp.camera_gate import verify_bearer_token
        assert verify_bearer_token("secret123", "secret123") is True

    def test_wrong_token(self):
        from halbert_core.mcp.camera_gate import verify_bearer_token
        assert verify_bearer_token("wrong", "secret123") is False

    def test_empty_provided(self):
        from halbert_core.mcp.camera_gate import verify_bearer_token
        assert verify_bearer_token("", "secret123") is False

    def test_empty_expected(self):
        from halbert_core.mcp.camera_gate import verify_bearer_token
        assert verify_bearer_token("secret123", "") is False

    def test_both_empty(self):
        from halbert_core.mcp.camera_gate import verify_bearer_token
        assert verify_bearer_token("", "") is False


class TestExpandedIsCameraQuery:
    """Test the expanded is_camera_query() list."""

    def test_frigate_get_active_detections_is_camera(self):
        from halbert_core.mcp.camera_gate import is_camera_query
        assert is_camera_query("frigate_get_active_detections") is True

    def test_frigate_get_snapshot_is_camera(self):
        from halbert_core.mcp.camera_gate import is_camera_query
        assert is_camera_query("frigate_get_snapshot") is True

    def test_capture_screenshot_is_camera(self):
        from halbert_core.mcp.camera_gate import is_camera_query
        assert is_camera_query("capture_screenshot") is True

    def test_detect_objects_is_camera(self):
        from halbert_core.mcp.camera_gate import is_camera_query
        assert is_camera_query("detect_objects") is True
