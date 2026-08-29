# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Shell integration: OSC 133 parser, password-prompt detection, remote detection.

The OSC 133 parser is a byte-level state machine that recognises shell
integration markers (prompt start, input start, output start, output end)
and OSC 7 (cwd) sequences emitted by the rc files. It carries partial
sequences across reads and passes all bytes through to xterm.js unchanged
— boundaries are metadata, not filtering.

See plan-b-contracts.md section 3.
"""
from __future__ import annotations

import base64
import enum
import re
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import unquote


class OSCState(enum.Enum):
    GROUND = 0
    ESC = 1
    OSC = 2
    CSI = 3
    INTERM = 4


@dataclass
class BlockBoundary:
    kind: str  # 'A' | 'B' | 'C' | 'D' | '7' | 'alt_enter' | 'alt_exit'
    block_id: Optional[str] = None
    command: Optional[str] = None
    exit_code: Optional[int] = None
    cwd: Optional[str] = None


@dataclass
class ParsedOutput:
    passthrough: bytes = b""
    boundaries: List[BlockBoundary] = field(default_factory=list)
    block_bytes: bytes = b""


# Password prompt detection
PASSWORD_PROMPT_RE = re.compile(
    rb"(?:[Pp]assword(?:\s+for\s+\S+)?|[Pp]assphrase|[Ss]udo)\s*[:\xef\xbc\x9a]\s*$"
)

# Remote command prefixes
REMOTE_PREFIXES = ("ssh ", "mosh ", "slogin ")


def detect_needs_input(block_tail: bytes, silence_seconds: float) -> bool:
    """True when the tail matches a password prompt AND silence >= 5.0."""
    if silence_seconds < 5.0:
        return False
    return bool(PASSWORD_PROMPT_RE.search(block_tail))


def is_remote_command(command: str) -> bool:
    """True if the command starts with an ssh/mosh/slogin prefix."""
    stripped = command.lstrip()
    return stripped.startswith(REMOTE_PREFIXES)


class OSCParser:
    """Byte-level state machine for OSC 133 and OSC 7 sequences.

    Carries partial sequences across reads. Everything passes through to
    xterm unchanged; boundaries are metadata.
    """

    def __init__(self) -> None:
        self._state = OSCState.GROUND
        self._buf = bytearray()
        self._boundaries: List[BlockBoundary] = []
        self._passthrough = bytearray()
        self._block_bytes = bytearray()
        self._in_block = False
        self._in_alt_screen = False

    def feed(self, data: bytes) -> ParsedOutput:
        self._boundaries.clear()
        self._passthrough.clear()
        self._block_bytes.clear()

        for byte in data:
            self._process_byte(byte)

        result = ParsedOutput(
            passthrough=bytes(self._passthrough),
            boundaries=list(self._boundaries),
            block_bytes=bytes(self._block_bytes),
        )
        return result

    def _process_byte(self, byte: int) -> None:
        state = self._state

        if state == OSCState.GROUND:
            if byte == 0x1B:  # ESC
                self._state = OSCState.ESC
                self._buf = bytearray([byte])
            else:
                self._passthrough.append(byte)
                if self._in_block and not self._in_alt_screen:
                    self._block_bytes.append(byte)

        elif state == OSCState.ESC:
            self._buf.append(byte)
            if byte == ord("]"):
                # OSC start
                self._state = OSCState.OSC
            elif byte == ord("["):
                # CSI start
                self._state = OSCState.CSI
            else:
                # Other escape (e.g. \e\r) — flush as passthrough
                self._passthrough.extend(self._buf)
                if self._in_block and not self._in_alt_screen:
                    self._block_bytes.extend(self._buf)
                self._state = OSCState.GROUND
                self._buf = bytearray()

        elif state == OSCState.OSC:
            self._buf.append(byte)
            if byte == 0x07:  # BEL — OSC terminator
                self._handle_osc()
                self._state = OSCState.GROUND
                self._buf = bytearray()
            elif byte == 0x1B:  # Possible ST start
                self._state = OSCState.INTERM
            # else: keep accumulating

        elif state == OSCState.INTERM:
            self._buf.append(byte)
            if byte == ord("\\"):
                # ST terminator complete
                # Remove the \x1b\\ from the buffer for parsing
                osc_data = self._buf[:-2]
                self._buf = osc_data
                self._handle_osc()
                self._state = OSCState.GROUND
                self._buf = bytearray()
            else:
                # Not ST — was just an ESC inside OSC data
                # Put it back into OSC state and continue
                self._state = OSCState.OSC

        elif state == OSCState.CSI:
            self._buf.append(byte)
            # Check for alt-screen sequences
            buf_str = bytes(self._buf).decode("ascii", errors="replace")
            # \e[?1049h, \e[?47h — alt enter
            # \e[?1049l, \e[?47l — alt exit
            if byte == ord("h") and ("?1049" in buf_str or "?47" in buf_str):
                self._handle_alt_enter()
                self._state = OSCState.GROUND
                self._buf = bytearray()
            elif byte == ord("l") and ("?1049" in buf_str or "?47" in buf_str):
                self._handle_alt_exit()
                self._state = OSCState.GROUND
                self._buf = bytearray()
            elif 0x40 <= byte <= 0x7E:
                # CSI terminator — flush as passthrough
                self._passthrough.extend(self._buf)
                if self._in_block and not self._in_alt_screen:
                    self._block_bytes.extend(self._buf)
                self._state = OSCState.GROUND
                self._buf = bytearray()

    def _handle_osc(self) -> None:
        """Parse the completed OSC sequence in self._buf."""
        # buf starts with \x1b], strip those
        payload = bytes(self._buf[2:])
        # Remove trailing terminator (BEL already stripped, or ST stripped)
        if payload.endswith(b"\x07"):
            payload = payload[:-1]

        # Parse: 133;X[;params]  or  7;file://host/path
        try:
            text = payload.decode("utf-8", errors="replace")
        except Exception:
            self._passthrough.extend(self._buf)
            return

        if text.startswith("133;"):
            self._handle_osc133(text[4:])
            # OSC 133 sequences are passthrough (xterm renders them)
            self._passthrough.extend(self._buf)
        elif text.startswith("7;"):
            self._handle_osc7(text[2:])
            self._passthrough.extend(self._buf)
        else:
            # Unknown OSC — passthrough
            self._passthrough.extend(self._buf)

    def _handle_osc133(self, params: str) -> None:
        """Handle 133;X[;params]."""
        if not params:
            return
        kind = params[0]
        rest = params[1:]  # may start with ;

        if kind in ("A", "B"):
            self._boundaries.append(BlockBoundary(kind=kind))
            if kind == "A":
                # Prompt — not in a block
                self._in_block = False
        elif kind == "C":
            block_id, command = self._parse_c_params(rest)
            self._boundaries.append(
                BlockBoundary(kind="C", block_id=block_id, command=command)
            )
            self._in_block = True
            self._block_bytes.clear()
        elif kind == "D":
            exit_code, block_id = self._parse_d_params(rest)
            self._boundaries.append(BlockBoundary(kind="D", exit_code=exit_code, block_id=block_id))
            self._in_block = False

    def _parse_c_params(self, rest: str) -> tuple[Optional[str], Optional[str]]:
        """Parse ;id=<id>;cmd=<b64> from C marker."""
        rest = rest.lstrip(";")
        parts = rest.split(";")
        block_id: Optional[str] = None
        command: Optional[str] = None
        for part in parts:
            if part.startswith("id="):
                block_id = part[3:]
            elif part.startswith("cmd="):
                b64 = part[4:]
                try:
                    command = base64.b64decode(b64).decode("utf-8", errors="replace")
                except Exception:
                    command = None
        return block_id, command

    def _parse_d_params(self, rest: str) -> tuple[Optional[int], Optional[str]]:
        """Parse ;<exit_code>[;id=<block_id>] from D marker."""
        rest = rest.lstrip(";")
        if not rest:
            return (None, None)
        parts = rest.split(";")
        exit_code: Optional[int] = None
        block_id: Optional[str] = None
        for part in parts:
            if part.startswith("id="):
                block_id = part[3:]
            else:
                try:
                    exit_code = int(part)
                except ValueError:
                    pass
        return (exit_code, block_id)

    def _handle_osc7(self, params: str) -> None:
        """Handle 7;file://host/path."""
        # Extract path from file://host/path
        if params.startswith("file://"):
            path = params[7:]
            # Strip host part
            slash = path.find("/")
            if slash >= 0:
                path = path[slash:]
            path = unquote(path)
            self._boundaries.append(BlockBoundary(kind="7", cwd=path))

    def _handle_alt_enter(self) -> None:
        self._boundaries.append(BlockBoundary(kind="alt_enter"))
        self._in_alt_screen = True
        self._passthrough.extend(self._buf)

    def _handle_alt_exit(self) -> None:
        self._boundaries.append(BlockBoundary(kind="alt_exit"))
        self._in_alt_screen = False
        self._passthrough.extend(self._buf)
