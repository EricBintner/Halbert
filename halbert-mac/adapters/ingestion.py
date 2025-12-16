"""
macOS Unified Logging ingestion adapter.

Provides log collection from macOS Unified Logging system using 'log' command.
Equivalent to Linux journald adapter.
"""

import subprocess
import json
from typing import Dict, Any, Iterator, Optional
from datetime import datetime, timezone


class UnifiedLoggingAdapter:
    """
    Adapter for macOS Unified Logging collection.
    
    Equivalent to Linux JournaldAdapter, but uses macOS 'log' command.
    """
    
    def __init__(self):
        self.name = "unified_logging"
    
    def collect_logs(
        self,
        filters: Optional[Dict[str, Any]] = None,
        follow: bool = True,
        limit: Optional[int] = None
    ) -> Iterator[Dict[str, Any]]:
        """
        Collect logs from macOS Unified Logging.
        
        Args:
            filters: Optional filters (process, subsystem, level)
            follow: If True, stream logs continuously
            limit: Optional limit on number of entries (for non-follow)
            
        Yields:
            Log entries as normalized dicts
        """
        # Build log command
        if follow:
            cmd = ['log', 'stream', '--style', 'json', '--level', 'info']
        else:
            # For historical logs, use 'log show'
            cmd = ['log', 'show', '--style', 'json', '--last', '1h']
            if limit:
                cmd.extend(['--limit', str(limit)])
        
        # Apply filters
        if filters:
            if filters.get('process'):
                cmd.extend(['--process', filters['process']])
            if filters.get('subsystem'):
                cmd.extend(['--subsystem', filters['subsystem']])
            if filters.get('level'):
                # Map to macOS levels: default, info, debug
                level_map = {
                    'error': 'default',
                    'warning': 'info',
                    'info': 'info',
                    'debug': 'debug',
                }
                mac_level = level_map.get(filters['level'], 'info')
                # Already set --level above, modify if different
                if mac_level != 'info':
                    # Replace --level info with filtered level
                    for i, arg in enumerate(cmd):
                        if arg == '--level' and i + 1 < len(cmd):
                            cmd[i + 1] = mac_level
                            break
        
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    entry = json.loads(line)
                    # Normalize to Cerebrix schema
                    yield self._normalize(entry)
                except json.JSONDecodeError:
                    # Skip malformed JSON
                    continue
                except Exception as e:
                    # Skip entries that fail normalization
                    continue
        
        except FileNotFoundError:
            yield {'error': 'log command not found (macOS only)'}
        except Exception as e:
            yield {'error': str(e)}
    
    def _normalize(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize macOS log entry to Cerebrix schema.
        
        Args:
            entry: Raw log entry from 'log' command
            
        Returns:
            Normalized dict matching Cerebrix telemetry schema
        """
        # Extract timestamp
        ts = entry.get('timestamp')
        if not ts:
            ts = datetime.now(timezone.utc).isoformat()
        
        # Map macOS message type to severity
        message_type = entry.get('messageType', 'Default')
        severity = self._map_severity(message_type)
        
        # Extract process info
        process = entry.get('processImagePath', '')
        process_name = process.split('/')[-1] if process else 'unknown'
        
        return {
            "ts": ts,
            "source": "unified_logging",
            "host": entry.get('machTimestamp', 'localhost'),
            "type": "log",
            "subsystem": entry.get('subsystem', 'system'),
            "severity": severity,
            "message": entry.get('eventMessage', ''),
            "data": {
                "process": process_name,
                "process_path": process,
                "pid": entry.get('processID'),
                "message_type": message_type,
                "category": entry.get('category', ''),
            },
            "tags": ["log", "macos"],
        }
    
    def _map_severity(self, message_type: str) -> str:
        """
        Map macOS message type to Cerebrix severity.
        
        Args:
            message_type: macOS message type (Default, Info, Debug, Error, Fault)
            
        Returns:
            Severity string (error, warning, info, debug)
        """
        mapping = {
            'Error': 'error',
            'Fault': 'error',
            'Default': 'info',
            'Info': 'info',
            'Debug': 'debug',
        }
        return mapping.get(message_type, 'info')
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get Unified Logging system status.
        
        Returns:
            Dict with status information
        """
        try:
            # Check if log command is available
            result = subprocess.run(
                ['which', 'log'],
                capture_output=True,
                text=True
            )
            
            available = result.returncode == 0
            
            return {
                'ok': available,
                'active': available,
                'message': 'Unified Logging available' if available else 'log command not found',
            }
        except Exception as e:
            return {
                'ok': False,
                'error': str(e),
            }
    
    def is_available(self) -> bool:
        """
        Check if Unified Logging is available.
        
        Returns:
            True if 'log' command exists
        """
        try:
            result = subprocess.run(
                ['which', 'log'],
                capture_output=True
            )
            return result.returncode == 0
        except Exception:
            return False
