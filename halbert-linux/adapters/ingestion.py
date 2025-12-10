"""
Linux journald ingestion adapter.

Wraps existing halbert_core journald ingestion functionality
to work with platform abstraction layer.
"""

from typing import Dict, Any, Iterator, Optional
import sys
import os

# Add halbert_core to path
halbert_path = os.path.join(os.path.dirname(__file__), '../../halbert_core')
if halbert_path not in sys.path:
    sys.path.insert(0, halbert_path)

from halbert_core.ingestion.journald import follow_journal


class JournaldAdapter:
    """
    Adapter for Linux journald log collection.
    
    Wraps existing halbert_core.ingestion.journald functionality.
    """
    
    def __init__(self):
        self.name = "journald"
    
    def collect_logs(
        self,
        filters: Optional[Dict[str, Any]] = None,
        follow: bool = True,
        cursor_path: Optional[str] = None,
        persist_every: int = 100
    ) -> Iterator[Dict[str, Any]]:
        """
        Collect logs from journald.
        
        Args:
            filters: Optional filters (identifiers, units, severities)
            follow: If True, stream logs continuously
            cursor_path: Path to save cursor for resuming
            persist_every: Save cursor every N entries
            
        Yields:
            Log entries as normalized dicts
        """
        if follow:
            # Use existing follow_journal function
            yield from follow_journal(
                filters=filters,
                cursor_path=cursor_path,
                persist_every=persist_every
            )
        else:
            # For non-following, we can use journalctl with limit
            import subprocess
            import json
            from halbert_core.ingestion.journald import _normalize
            
            cmd = ['journalctl', '--output=json', '--no-pager', '-n', '100']
            
            if filters:
                if filters.get('unit'):
                    cmd.extend(['--unit', filters['unit']])
                if filters.get('since'):
                    cmd.extend(['--since', filters['since']])
            
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        yield _normalize(entry)
                    except json.JSONDecodeError:
                        continue
            except Exception as e:
                yield {'error': str(e)}
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get journald service status.
        
        Returns:
            Dict with status information
        """
        import subprocess
        
        try:
            result = subprocess.run(
                ['systemctl', 'status', 'systemd-journald'],
                capture_output=True,
                text=True
            )
            
            return {
                'ok': result.returncode == 0,
                'active': 'active (running)' in result.stdout,
                'status': result.stdout,
            }
        except Exception as e:
            return {
                'ok': False,
                'error': str(e),
            }
