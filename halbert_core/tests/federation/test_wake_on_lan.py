# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P6a: Wake-on-LAN magic packet tests.

Verifies packet construction (6x 0xFF + 16x MAC), MAC parsing, and
send behavior with mocked sockets.
"""

import socket
from unittest.mock import patch, MagicMock

import pytest

from halbert_core.federation.wake_on_lan import (
    parse_mac,
    build_magic_packet,
    send_wol_packet,
    send_wol_packet_dual,
    DEFAULT_BROADCAST,
    WOL_PORT_PRIMARY,
    WOL_PORT_SECONDARY,
)


class TestParseMac:
    def test_parse_colon_separated(self):
        assert parse_mac("AA:BB:CC:DD:EE:FF") == bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])

    def test_parse_hyphen_separated(self):
        assert parse_mac("AA-BB-CC-DD-EE-FF") == bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])

    def test_parse_lowercase(self):
        assert parse_mac("aa:bb:cc:dd:ee:ff") == bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])

    def test_parse_mixed_case(self):
        assert parse_mac("Aa:Bb:Cc:Dd:Ee:Ff") == bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])

    def test_parse_invalid_short(self):
        with pytest.raises(ValueError, match="Invalid MAC"):
            parse_mac("AA:BB:CC:DD:EE")

    def test_parse_invalid_chars(self):
        with pytest.raises(ValueError, match="Invalid MAC"):
            parse_mac("GG:BB:CC:DD:EE:FF")

    def test_parse_invalid_separator(self):
        with pytest.raises(ValueError, match="Invalid MAC"):
            parse_mac("AA.BB.CC.DD.EE.FF")

    def test_parse_empty(self):
        with pytest.raises(ValueError, match="Invalid MAC"):
            parse_mac("")


class TestBuildMagicPacket:
    def test_packet_starts_with_six_ff(self):
        pkt = build_magic_packet("AA:BB:CC:DD:EE:FF")
        assert pkt[:6] == b"\xff" * 6

    def test_packet_contains_16_mac_repeats(self):
        mac = "AA:BB:CC:DD:EE:FF"
        pkt = build_magic_packet(mac)
        mac_bytes = bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])
        assert pkt[6:] == mac_bytes * 16

    def test_packet_total_length_102(self):
        pkt = build_magic_packet("AA:BB:CC:DD:EE:FF")
        assert len(pkt) == 102  # 6 + (6 * 16)

    def test_packet_invalid_mac_raises(self):
        with pytest.raises(ValueError):
            build_magic_packet("invalid")


def _mock_socket():
    """Create a MagicMock that works as a socket context manager."""
    mock_sock = MagicMock()
    mock_sock.__enter__.return_value = mock_sock
    mock_sock.__exit__.return_value = False
    return mock_sock


class TestSendWolPacket:
    def test_successful_send(self):
        mock_sock = _mock_socket()
        with patch("socket.socket", return_value=mock_sock):
            result = send_wol_packet("AA:BB:CC:DD:EE:FF", "192.168.1.255", port=9)
        assert result is True
        mock_sock.setsockopt.assert_called_once_with(
            socket.SOL_SOCKET, socket.SO_BROADCAST, 1
        )
        # Verify sendto was called with the magic packet
        assert mock_sock.sendto.call_count == 1
        sent_data, (addr, port) = mock_sock.sendto.call_args[0]
        assert len(sent_data) == 102
        assert addr == "192.168.1.255"
        assert port == 9

    def test_default_broadcast(self):
        mock_sock = _mock_socket()
        with patch("socket.socket", return_value=mock_sock):
            send_wol_packet("AA:BB:CC:DD:EE:FF")
        _, (addr, _) = mock_sock.sendto.call_args[0]
        assert addr == DEFAULT_BROADCAST

    def test_default_port_is_9(self):
        mock_sock = _mock_socket()
        with patch("socket.socket", return_value=mock_sock):
            send_wol_packet("AA:BB:CC:DD:EE:FF")
        _, (_, port) = mock_sock.sendto.call_args[0]
        assert port == WOL_PORT_PRIMARY

    def test_invalid_mac_returns_false(self):
        result = send_wol_packet("invalid-mac")
        assert result is False

    def test_socket_error_returns_false(self):
        with patch("socket.socket", side_effect=OSError("permission denied")):
            result = send_wol_packet("AA:BB:CC:DD:EE:FF")
        assert result is False

    def test_sendto_error_returns_false(self):
        mock_sock = _mock_socket()
        mock_sock.sendto.side_effect = OSError("network unreachable")
        with patch("socket.socket", return_value=mock_sock):
            result = send_wol_packet("AA:BB:CC:DD:EE:FF")
        assert result is False


class TestSendWolPacketDual:
    def test_dual_send_both_succeed(self):
        mock_sock = _mock_socket()
        with patch("socket.socket", return_value=mock_sock):
            result = send_wol_packet_dual("AA:BB:CC:DD:EE:FF", "192.168.1.255")
        assert result is True
        assert mock_sock.sendto.call_count == 2
        # First call to port 9, second to port 7
        ports = [call[0][1][1] for call in mock_sock.sendto.call_args_list]
        assert WOL_PORT_PRIMARY in ports
        assert WOL_PORT_SECONDARY in ports

    def test_dual_send_one_fails_still_true(self):
        mock_sock = _mock_socket()
        mock_sock.sendto.side_effect = [None, OSError("port 7 blocked")]
        with patch("socket.socket", return_value=mock_sock):
            result = send_wol_packet_dual("AA:BB:CC:DD:EE:FF")
        assert result is True

    def test_dual_send_both_fail_returns_false(self):
        mock_sock = _mock_socket()
        mock_sock.sendto.side_effect = [OSError("fail1"), OSError("fail2")]
        with patch("socket.socket", return_value=mock_sock):
            result = send_wol_packet_dual("AA:BB:CC:DD:EE:FF")
        assert result is False
