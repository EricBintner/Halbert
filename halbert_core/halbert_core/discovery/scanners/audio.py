"""
Audio Scanner - Sound configuration and issues.

Common forum questions this addresses:
- "No sound / audio not working"
- "HDMI audio not showing up"
- "Bluetooth headphones no audio"
- "Microphone not detected"
- "PulseAudio vs PipeWire?"
- "Audio crackling / popping"
- "Wrong default audio device"
- "Volume too low / no amplification"

Discovers:
- Audio server (PulseAudio/PipeWire)
- Sound cards and devices
- Default input/output
- HDMI audio outputs
- Bluetooth audio devices
- Common audio issues
"""

from __future__ import annotations
from typing import List, Dict, Optional
from pathlib import Path
import re

from .base import BaseScanner
from ..schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class AudioScanner(BaseScanner):
    """
    Scanner for audio configuration and devices.
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.HARDWARE
    
    def scan(self) -> List[Discovery]:
        """Scan audio configuration."""
        discoveries = []
        
        discoveries.extend(self._scan_audio_server())
        discoveries.extend(self._scan_sound_cards())
        discoveries.extend(self._scan_sinks())
        discoveries.extend(self._scan_sources())
        
        self.logger.info(f"Found {len(discoveries)} audio discoveries")
        return discoveries
    
    def _scan_audio_server(self) -> List[Discovery]:
        """Detect PulseAudio vs PipeWire."""
        discoveries = []
        
        # Check for PipeWire first
        code, stdout, _ = self.run_command(["pw-cli", "info"], timeout=3)
        if code == 0:
            server = "PipeWire"
            # Get version
            code2, ver, _ = self.run_command(["pipewire", "--version"])
            version = ver.strip().splitlines()[0] if code2 == 0 else "Unknown"
        else:
            # Check for PulseAudio
            code, stdout, _ = self.run_command(["pactl", "info"], timeout=3)
            if code == 0 and "PulseAudio" in stdout:
                server = "PulseAudio"
                for line in stdout.splitlines():
                    if "Server Version" in line:
                        version = line.split(":")[-1].strip()
                        break
                else:
                    version = "Unknown"
            else:
                server = "ALSA (no server)"
                version = None
        
        discovery_id = make_discovery_id(DiscoveryType.HARDWARE, "audio-server")
        
        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.HARDWARE,
            name="audio-server",
            title="Audio Server",
            description=f"{server}" + (f" {version}" if version else ""),
            icon="volume-2",
            severity=DiscoverySeverity.SUCCESS,
            status=server,
            status_detail=version,
            data={
                "server": server,
                "version": version,
                "is_audio_server": True,
            },
            chat_context=f"Audio server: {server}. "
                        f"{'PipeWire is the modern replacement for PulseAudio with better Bluetooth and low-latency support. ' if server == 'PipeWire' else ''}"
                        f"{'PulseAudio handles mixing and device switching. ' if server == 'PulseAudio' else ''}"
                        f"Use 'pavucontrol' or 'pwvucontrol' for graphical audio control.",
        ))
        
        return discoveries
    
    def _scan_sound_cards(self) -> List[Discovery]:
        """Scan ALSA sound cards."""
        discoveries = []
        
        # Read /proc/asound/cards
        cards_file = Path("/proc/asound/cards")
        if not cards_file.exists():
            return discoveries
        
        cards_content = cards_file.read_text()
        
        # Parse cards: " 0 [PCH            ]: HDA-Intel - HDA Intel PCH"
        cards = []
        for line in cards_content.splitlines():
            match = re.match(r'\s*(\d+)\s+\[(\w+)\s*\]:\s*(.+)', line)
            if match:
                card_num = int(match.group(1))
                card_id = match.group(2)
                card_name = match.group(3)
                cards.append({
                    "number": card_num,
                    "id": card_id,
                    "name": card_name,
                })
        
        for card in cards:
            # Detect card type
            card_type = "Audio"
            if "HDMI" in card["name"].upper():
                card_type = "HDMI Audio"
            elif "USB" in card["name"].upper():
                card_type = "USB Audio"
            elif "HDA" in card["name"]:
                card_type = "HD Audio"
            
            discovery_id = make_discovery_id(DiscoveryType.HARDWARE, f"soundcard-{card['number']}")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.HARDWARE,
                name=f"soundcard-{card['number']}",
                title=f"Sound Card {card['number']}: {card['id']}",
                description=card["name"],
                icon="speaker",
                severity=DiscoverySeverity.SUCCESS,
                status=card_type,
                data={
                    "card_number": card["number"],
                    "card_id": card["id"],
                    "card_name": card["name"],
                    "card_type": card_type,
                    "is_sound_card": True,
                },
                chat_context=f"Sound card {card['number']}: {card['name']}. Type: {card_type}.",
            ))
        
        return discoveries
    
    def _scan_sinks(self) -> List[Discovery]:
        """Scan audio output devices (sinks)."""
        discoveries = []
        
        # Try pactl for sinks
        code, stdout, _ = self.run_command(["pactl", "list", "sinks", "short"], timeout=5)
        
        if code != 0:
            return discoveries
        
        sinks = []
        for line in stdout.strip().splitlines():
            parts = line.split('\t')
            if len(parts) >= 2:
                sink_num = parts[0]
                sink_name = parts[1]
                sinks.append({"num": sink_num, "name": sink_name})
        
        # Get default sink
        code2, default_out, _ = self.run_command(["pactl", "get-default-sink"])
        default_sink = default_out.strip() if code2 == 0 else ""
        
        for sink in sinks:
            is_default = sink["name"] == default_sink
            
            # Identify sink type
            sink_type = "Speaker"
            if "hdmi" in sink["name"].lower():
                sink_type = "HDMI"
            elif "bluetooth" in sink["name"].lower() or "bluez" in sink["name"].lower():
                sink_type = "Bluetooth"
            elif "usb" in sink["name"].lower():
                sink_type = "USB"
            elif "headphone" in sink["name"].lower():
                sink_type = "Headphones"
            
            severity = DiscoverySeverity.SUCCESS
            
            # Friendly name
            display_name = sink["name"].split(".")[-1][:30] if "." in sink["name"] else sink["name"][:30]
            
            discovery_id = make_discovery_id(DiscoveryType.HARDWARE, f"audio-sink-{sink['num']}")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.HARDWARE,
                name=f"audio-sink-{sink['num']}",
                title=f"Output: {display_name}",
                description=f"{sink_type}" + (" (Default)" if is_default else ""),
                icon="volume-2",
                severity=severity,
                status=f"{sink_type}" + (" ✓" if is_default else ""),
                data={
                    "sink_num": sink["num"],
                    "sink_name": sink["name"],
                    "sink_type": sink_type,
                    "is_default": is_default,
                    "is_audio_output": True,
                },
                actions=[
                    DiscoveryAction(
                        id="set-default",
                        label="Set as Default",
                        icon="check",
                        command=f"pactl set-default-sink {sink['name']}",
                    ),
                ] if not is_default else [],
                chat_context=f"Audio output '{display_name}' ({sink_type}). "
                            f"{'This is the default output. ' if is_default else ''}"
                            f"Set as default: pactl set-default-sink {sink['name']}",
            ))
        
        return discoveries
    
    def _scan_sources(self) -> List[Discovery]:
        """Scan audio input devices (sources/microphones)."""
        discoveries = []
        
        code, stdout, _ = self.run_command(["pactl", "list", "sources", "short"], timeout=5)
        
        if code != 0:
            return discoveries
        
        # Get default source
        code2, default_out, _ = self.run_command(["pactl", "get-default-source"])
        default_source = default_out.strip() if code2 == 0 else ""
        
        for line in stdout.strip().splitlines():
            parts = line.split('\t')
            if len(parts) >= 2:
                source_name = parts[1]
                
                # Skip monitor sources (they're output loopback)
                if ".monitor" in source_name:
                    continue
                
                is_default = source_name == default_source
                
                # Identify type
                source_type = "Microphone"
                if "bluetooth" in source_name.lower() or "bluez" in source_name.lower():
                    source_type = "Bluetooth Mic"
                elif "usb" in source_name.lower():
                    source_type = "USB Mic"
                elif "webcam" in source_name.lower():
                    source_type = "Webcam Mic"
                
                display_name = source_name.split(".")[-1][:30] if "." in source_name else source_name[:30]
                
                discovery_id = make_discovery_id(DiscoveryType.HARDWARE, f"audio-source-{parts[0]}")
                
                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.HARDWARE,
                    name=f"audio-source-{parts[0]}",
                    title=f"Input: {display_name}",
                    description=f"{source_type}" + (" (Default)" if is_default else ""),
                    icon="mic",
                    severity=DiscoverySeverity.SUCCESS,
                    status=f"{source_type}" + (" ✓" if is_default else ""),
                    data={
                        "source_name": source_name,
                        "source_type": source_type,
                        "is_default": is_default,
                        "is_audio_input": True,
                    },
                    chat_context=f"Audio input '{display_name}' ({source_type}). "
                                f"{'Default microphone. ' if is_default else ''}",
                ))
        
        return discoveries
