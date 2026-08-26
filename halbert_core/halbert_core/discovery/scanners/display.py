# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Display Scanner - Monitor configuration and graphics.

Common forum questions this addresses:
- "Second monitor not detected"
- "Wrong resolution on external monitor"
- "Screen tearing / vsync issues"
- "Which GPU is active?" (hybrid graphics)
- "HDMI audio not working" (related to display)
- "4K monitor stuck at 30Hz"
- "Scaling issues on HiDPI"
- "Wayland vs X11 which am I using?"

Discovers:
- Connected displays and resolutions
- Display server (X11/Wayland)
- Active GPU for rendering
- Hybrid graphics status (nvidia-prime, optimus)
- Compositor info
- Refresh rate settings
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


class DisplayScanner(BaseScanner):
    """
    Scanner for displays, graphics, and rendering configuration.
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.DESKTOP
    
    def scan(self) -> List[Discovery]:
        """Scan display configuration."""
        discoveries = []
        
        discoveries.extend(self._scan_display_server())
        discoveries.extend(self._scan_monitors())
        discoveries.extend(self._scan_gpus())
        discoveries.extend(self._scan_hybrid_graphics())
        discoveries.extend(self._scan_compositor())
        
        self.logger.info(f"Found {len(discoveries)} display discoveries")
        return discoveries
    
    def _scan_display_server(self) -> List[Discovery]:
        """Detect X11 vs Wayland."""
        discoveries = []
        
        import os
        xdg_session = os.environ.get("XDG_SESSION_TYPE", "")
        wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
        display = os.environ.get("DISPLAY", "")
        
        if wayland_display or xdg_session == "wayland":
            server = "Wayland"
            compositor = os.environ.get("XDG_CURRENT_DESKTOP", "Unknown")
        elif display or xdg_session == "x11":
            server = "X11"
            compositor = "X.Org"
        else:
            server = "None/TTY"
            compositor = "None"
        
        discovery_id = make_discovery_id(DiscoveryType.DESKTOP, "display-server")
        
        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.DESKTOP,
            name="display-server",
            title="Display Server",
            description=f"Running on {server}",
            icon="monitor",
            severity=DiscoverySeverity.SUCCESS,
            status=server,
            status_detail=f"Session: {compositor}",
            data={
                "server": server,
                "compositor": compositor,
                "wayland_display": wayland_display,
                "x11_display": display,
                "is_display_server": True,
            },
            chat_context=f"Display server: {server}. Desktop: {compositor}. "
                        f"{'Some X11-only apps may need XWayland. ' if server == 'Wayland' else ''}"
                        f"{'Screen capture and some games work better on X11. ' if server == 'Wayland' else ''}",
        ))
        
        return discoveries
    
    def _scan_monitors(self) -> List[Discovery]:
        """Scan connected monitors using xrandr or wlr-randr."""
        discoveries = []
        
        # Try xrandr first (works on X11 and XWayland)
        code, stdout, _ = self.run_command(["xrandr", "--query"], timeout=5)
        
        monitors = []
        current_monitor = None
        
        if code == 0:
            for line in stdout.splitlines():
                # Match connected outputs: "HDMI-1 connected primary 1920x1080+0+0"
                match = re.match(r'^(\S+)\s+(connected|disconnected)\s*(primary)?\s*(\d+x\d+\+\d+\+\d+)?', line)
                if match:
                    output = match.group(1)
                    connected = match.group(2) == "connected"
                    primary = match.group(3) is not None
                    geometry = match.group(4)
                    
                    if connected:
                        current_monitor = {
                            "output": output,
                            "connected": True,
                            "primary": primary,
                            "geometry": geometry,
                            "modes": []
                        }
                        monitors.append(current_monitor)
                
                # Match resolution lines: "   1920x1080     60.00*+  59.94"
                elif current_monitor and line.startswith("   "):
                    mode_match = re.match(r'\s+(\d+x\d+)\s+(\d+\.?\d*)\*?\+?', line)
                    if mode_match:
                        res = mode_match.group(1)
                        rate = mode_match.group(2)
                        is_current = "*" in line
                        current_monitor["modes"].append({
                            "resolution": res,
                            "refresh": float(rate),
                            "current": is_current
                        })
                        if is_current:
                            current_monitor["current_mode"] = f"{res}@{rate}Hz"
        
        # Create discoveries for each monitor
        for mon in monitors:
            output = mon["output"]
            
            # Determine issues
            issues = []
            current_mode = mon.get("current_mode", "Unknown")
            
            # Check for common problems
            if mon["modes"]:
                max_res = max(mon["modes"], key=lambda m: int(m["resolution"].split("x")[0]) * int(m["resolution"].split("x")[1]))
                current_res = next((m for m in mon["modes"] if m.get("current")), None)
                
                if current_res:
                    # Check if not using highest resolution
                    if current_res["resolution"] != max_res["resolution"]:
                        issues.append(f"Not using max resolution ({max_res['resolution']} available)")
                    
                    # Check for 4K@30Hz issue
                    if "3840" in current_res["resolution"] and current_res["refresh"] < 50:
                        issues.append(f"4K at {current_res['refresh']}Hz - check cable/port for 60Hz support")
            
            severity = DiscoverySeverity.WARNING if issues else DiscoverySeverity.SUCCESS
            
            discovery_id = make_discovery_id(DiscoveryType.DESKTOP, f"monitor-{output}")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.DESKTOP,
                name=f"monitor-{output}",
                title=f"Monitor: {output}",
                description=f"{current_mode}" + (" (Primary)" if mon.get("primary") else ""),
                icon="monitor",
                severity=severity,
                status=current_mode,
                status_detail="; ".join(issues) if issues else None,
                data={
                    "output": output,
                    "geometry": mon.get("geometry"),
                    "primary": mon.get("primary", False),
                    "current_mode": current_mode,
                    "available_modes": mon["modes"][:10],  # Limit
                    "issues": issues,
                    "is_monitor": True,
                },
                actions=[
                    DiscoveryAction(
                        id="settings",
                        label="Display Settings",
                        icon="settings",
                    ),
                ],
                chat_context=f"Monitor {output}: {current_mode}. "
                            f"{'Primary display. ' if mon.get('primary') else ''}"
                            f"{'Issues: ' + '; '.join(issues) + '. ' if issues else ''}",
            ))
        
        # Summary if multiple monitors
        if len(monitors) > 1:
            discovery_id = make_discovery_id(DiscoveryType.DESKTOP, "multi-monitor")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.DESKTOP,
                name="multi-monitor",
                title="Multi-Monitor Setup",
                description=f"{len(monitors)} displays connected",
                icon="monitors",
                severity=DiscoverySeverity.SUCCESS,
                status=f"{len(monitors)} monitors",
                data={
                    "monitor_count": len(monitors),
                    "outputs": [m["output"] for m in monitors],
                    "is_multi_monitor": True,
                },
                chat_context=f"Multi-monitor setup with {len(monitors)} displays: "
                            f"{', '.join(m['output'] for m in monitors)}. "
                            f"Use 'xrandr' or display settings to configure layout.",
            ))
        
        return discoveries
    
    def _scan_gpus(self) -> List[Discovery]:
        """Scan graphics cards."""
        discoveries = []
        
        # Use lspci to find GPUs
        code, stdout, _ = self.run_command(["lspci", "-nn"])
        
        gpus = []
        if code == 0:
            for line in stdout.splitlines():
                if "VGA" in line or "3D controller" in line or "Display controller" in line:
                    gpus.append(line.strip())
        
        for i, gpu_line in enumerate(gpus):
            # Extract GPU name
            match = re.search(r':\s+(.+?)(?:\s+\[|$)', gpu_line)
            gpu_name = match.group(1) if match else gpu_line[:50]
            
            # Detect GPU type
            gpu_type = "Unknown"
            if "NVIDIA" in gpu_line.upper():
                gpu_type = "NVIDIA"
            elif "AMD" in gpu_line.upper() or "ATI" in gpu_line.upper():
                gpu_type = "AMD"
            elif "INTEL" in gpu_line.upper():
                gpu_type = "Intel"
            
            discovery_id = make_discovery_id(DiscoveryType.GPU, f"gpu-{i}")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.GPU,
                name=f"gpu-{i}",
                title=f"GPU {i}: {gpu_type}",
                description=gpu_name[:60],
                icon="cpu",
                severity=DiscoverySeverity.SUCCESS,
                status=gpu_type,
                data={
                    "gpu_index": i,
                    "gpu_type": gpu_type,
                    "full_name": gpu_name,
                    "pci_line": gpu_line,
                    "is_gpu": True,
                },
                chat_context=f"GPU {i}: {gpu_name}. Type: {gpu_type}.",
            ))
        
        return discoveries
    
    def _scan_hybrid_graphics(self) -> List[Discovery]:
        """Scan for hybrid graphics (nvidia-prime, optimus)."""
        discoveries = []
        
        # Check for nvidia-prime
        code, stdout, _ = self.run_command(["prime-select", "query"])
        if code == 0:
            mode = stdout.strip()
            
            discovery_id = make_discovery_id(DiscoveryType.GPU, "hybrid-graphics")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.GPU,
                name="hybrid-graphics",
                title="Hybrid Graphics (PRIME)",
                description=f"Current mode: {mode}",
                icon="layers",
                severity=DiscoverySeverity.SUCCESS,
                status=mode.title(),
                data={
                    "mode": mode,
                    "technology": "nvidia-prime",
                    "is_hybrid_graphics": True,
                },
                actions=[
                    DiscoveryAction(
                        id="intel",
                        label="Intel (Power Save)",
                        icon="battery",
                        command="sudo prime-select intel",
                        requires_approval=True,
                    ),
                    DiscoveryAction(
                        id="nvidia",
                        label="NVIDIA (Performance)",
                        icon="zap",
                        command="sudo prime-select nvidia",
                        requires_approval=True,
                    ),
                    DiscoveryAction(
                        id="on-demand",
                        label="On-Demand",
                        icon="activity",
                        command="sudo prime-select on-demand",
                        requires_approval=True,
                    ),
                ],
                chat_context=f"Hybrid graphics using nvidia-prime, mode: {mode}. "
                            f"Change with 'sudo prime-select <mode>'. Requires logout. "
                            f"Use 'nvidia' for gaming, 'intel' for battery, 'on-demand' for automatic.",
            ))
        
        # Check for switcheroo (kernel hybrid graphics)
        switcheroo = Path("/sys/kernel/debug/vgaswitcheroo/switch")
        if switcheroo.exists():
            try:
                content = switcheroo.read_text()
                discovery_id = make_discovery_id(DiscoveryType.GPU, "vga-switcheroo")
                
                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.GPU,
                    name="vga-switcheroo",
                    title="VGA Switcheroo",
                    description="Kernel-level GPU switching available",
                    icon="layers",
                    severity=DiscoverySeverity.INFO,
                    status="Available",
                    data={
                        "technology": "vga_switcheroo",
                        "is_hybrid_graphics": True,
                    },
                    chat_context="VGA Switcheroo kernel interface available for GPU switching.",
                ))
            except:
                pass
        
        return discoveries
    
    def _scan_compositor(self) -> List[Discovery]:
        """Detect compositor and vsync settings."""
        discoveries = []
        
        import os
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        
        compositor_info = {
            "name": "Unknown",
            "vsync": "Unknown",
        }
        
        # Check for various compositors
        if "gnome" in desktop:
            compositor_info["name"] = "Mutter (GNOME)"
            # Check mutter settings
            code, stdout, _ = self.run_command([
                "gsettings", "get", "org.gnome.mutter", "experimental-features"
            ])
            if code == 0:
                compositor_info["features"] = stdout.strip()
        elif "kde" in desktop or "plasma" in desktop:
            compositor_info["name"] = "KWin (KDE)"
        elif self.command_exists("picom"):
            compositor_info["name"] = "Picom"
        elif self.command_exists("compton"):
            compositor_info["name"] = "Compton"
        
        if compositor_info["name"] != "Unknown":
            discovery_id = make_discovery_id(DiscoveryType.DESKTOP, "compositor")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.DESKTOP,
                name="compositor",
                title="Compositor",
                description=compositor_info["name"],
                icon="layers",
                severity=DiscoverySeverity.SUCCESS,
                status=compositor_info["name"],
                data={
                    "compositor": compositor_info["name"],
                    "desktop": desktop,
                    "is_compositor": True,
                },
                chat_context=f"Desktop compositor: {compositor_info['name']}. "
                            f"Screen tearing? Try enabling vsync in compositor settings. "
                            f"Gaming issues? Some compositors add latency - try full-screen mode.",
            ))
        
        return discoveries
