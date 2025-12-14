"""
Scheduled Tasks Scanner - Cron jobs and systemd timers.

Common forum questions this addresses:
- "Why did this run at 3am?"
- "Cron job not running"
- "Systemd timer failed"
- "What scheduled tasks are on my system?"
- "Backup not running on schedule"
- "High disk I/O at random times"

Discovers:
- System cron jobs (/etc/cron.*)
- User cron jobs
- Systemd timers
- Failed timers
- Anacron status
"""

from __future__ import annotations
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime
import re

from .base import BaseScanner
from ..schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class ScheduledScanner(BaseScanner):
    """
    Scanner for scheduled tasks (cron, systemd timers).
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.TASK
    
    def scan(self) -> List[Discovery]:
        """Scan scheduled tasks."""
        discoveries = []
        
        discoveries.extend(self._scan_systemd_timers())
        discoveries.extend(self._scan_cron_jobs())
        discoveries.append(self._create_summary())
        
        self.logger.info(f"Found {len(discoveries)} scheduled task discoveries")
        return discoveries
    
    def _scan_systemd_timers(self) -> List[Discovery]:
        """Scan systemd timers."""
        discoveries = []
        
        code, stdout, _ = self.run_command([
            "systemctl", "list-timers", "--all", "--no-pager"
        ], timeout=10)
        
        if code != 0:
            return discoveries
        
        timers = []
        failed_timers = []
        
        for line in stdout.splitlines():
            # Skip header and footer lines
            if not line.strip() or line.startswith("NEXT") or "timers listed" in line:
                continue
            
            parts = line.split()
            if len(parts) >= 7:
                # Parse timer info
                # Format: NEXT LEFT LAST PASSED UNIT ACTIVATES
                timer_name = None
                for i, p in enumerate(parts):
                    if ".timer" in p:
                        timer_name = p
                        break
                
                if timer_name:
                    timers.append({
                        "name": timer_name,
                        "line": line.strip(),
                    })
        
        # Check for failed timers
        code2, stdout2, _ = self.run_command([
            "systemctl", "list-timers", "--failed", "--no-pager"
        ])
        if code2 == 0:
            for line in stdout2.splitlines():
                if ".timer" in line:
                    failed_timers.append(line.strip())
        
        # Create discoveries for important timers
        important_timers = [
            "apt-daily", "apt-daily-upgrade", "fstrim", "logrotate",
            "man-db", "snapd", "backup", "restic", "borg"
        ]
        
        for timer in timers:
            timer_name = timer["name"]
            is_important = any(imp in timer_name for imp in important_timers)
            is_failed = any(timer_name in f for f in failed_timers)
            
            if is_important or is_failed:
                # Get more details
                code, stdout, _ = self.run_command([
                    "systemctl", "show", timer_name, "--property=LastTriggerUSec,Result"
                ])
                
                last_run = "Unknown"
                result = "Unknown"
                if code == 0:
                    for line in stdout.splitlines():
                        if line.startswith("LastTriggerUSec="):
                            ts = line.split("=")[1]
                            if ts and ts != "0":
                                # Parse timestamp
                                try:
                                    last_run = ts.split()[0] + " " + ts.split()[1] if len(ts.split()) > 1 else ts
                                except:
                                    pass
                        if line.startswith("Result="):
                            result = line.split("=")[1]
                
                severity = DiscoverySeverity.CRITICAL if is_failed else DiscoverySeverity.SUCCESS
                status = "Failed" if is_failed else "Active"
                
                clean_name = timer_name.replace(".timer", "")
                discovery_id = make_discovery_id(DiscoveryType.TASK, f"timer-{clean_name}")
                
                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.TASK,
                    name=f"timer-{clean_name}",
                    title=f"Timer: {clean_name}",
                    description=f"Systemd timer, last: {last_run[:20] if last_run else 'never'}",
                    icon="clock",
                    severity=severity,
                    status=status,
                    status_detail=f"Result: {result}" if result != "success" else None,
                    data={
                        "timer_name": timer_name,
                        "last_run": last_run,
                        "result": result,
                        "is_failed": is_failed,
                        "is_systemd_timer": True,
                    },
                    actions=[
                        DiscoveryAction(
                            id="run-now",
                            label="Run Now",
                            icon="play",
                            command=f"sudo systemctl start {timer_name.replace('.timer', '.service')}",
                            requires_approval=True,
                        ),
                        DiscoveryAction(
                            id="logs",
                            label="View Logs",
                            icon="file-text",
                            command=f"journalctl -u {timer_name.replace('.timer', '.service')} -n 50",
                        ),
                    ],
                    chat_context=f"Systemd timer '{clean_name}': {status}. Last run: {last_run}. "
                                f"{'⚠️ Timer has failed! Check logs with journalctl. ' if is_failed else ''}"
                                f"Trigger manually: systemctl start {timer_name.replace('.timer', '.service')}",
                ))
        
        return discoveries
    
    def _scan_cron_jobs(self) -> List[Discovery]:
        """Scan cron jobs."""
        discoveries = []
        
        cron_dirs = [
            ("/etc/cron.d", "System"),
            ("/etc/cron.daily", "Daily"),
            ("/etc/cron.hourly", "Hourly"),
            ("/etc/cron.weekly", "Weekly"),
            ("/etc/cron.monthly", "Monthly"),
        ]
        
        total_jobs = 0
        job_summary = []
        
        for cron_dir, schedule in cron_dirs:
            path = Path(cron_dir)
            if path.exists():
                jobs = [f for f in path.iterdir() if f.is_file() and not f.name.startswith('.')]
                if jobs:
                    total_jobs += len(jobs)
                    job_summary.append(f"{schedule}: {len(jobs)}")
        
        # Check user crontab
        code, stdout, _ = self.run_command(["crontab", "-l"])
        user_jobs = 0
        if code == 0 and stdout.strip():
            user_jobs = len([l for l in stdout.splitlines() if l.strip() and not l.startswith('#')])
            if user_jobs:
                job_summary.append(f"User: {user_jobs}")
                total_jobs += user_jobs
        
        if total_jobs > 0:
            discovery_id = make_discovery_id(DiscoveryType.TASK, "cron-jobs")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.TASK,
                name="cron-jobs",
                title="Cron Jobs",
                description=f"{total_jobs} scheduled tasks",
                icon="clock",
                severity=DiscoverySeverity.SUCCESS,
                status=f"{total_jobs} jobs",
                status_detail="; ".join(job_summary),
                data={
                    "total_jobs": total_jobs,
                    "user_jobs": user_jobs,
                    "summary": job_summary,
                    "is_cron": True,
                },
                actions=[
                    DiscoveryAction(
                        id="list",
                        label="List Jobs",
                        icon="list",
                        command="cat /etc/crontab; ls -la /etc/cron.*",
                    ),
                ],
                chat_context=f"{total_jobs} cron jobs scheduled: {'; '.join(job_summary)}. "
                            f"Edit user crontab: 'crontab -e'. "
                            f"System cron in /etc/cron.* directories.",
            ))
        
        return discoveries
    
    def _create_summary(self) -> Discovery:
        """Create summary of scheduled tasks."""
        # Count systemd timers
        code, stdout, _ = self.run_command(["systemctl", "list-timers", "--no-pager"])
        timer_count = 0
        if code == 0:
            timer_count = len([l for l in stdout.splitlines() if ".timer" in l])
        
        # Count cron jobs  
        cron_count = 0
        for cron_dir in ["/etc/cron.d", "/etc/cron.daily", "/etc/cron.hourly", "/etc/cron.weekly"]:
            path = Path(cron_dir)
            if path.exists():
                cron_count += len([f for f in path.iterdir() if f.is_file()])
        
        total = timer_count + cron_count
        
        discovery_id = make_discovery_id(DiscoveryType.TASK, "scheduled-summary")
        
        return Discovery(
            id=discovery_id,
            type=DiscoveryType.TASK,
            name="scheduled-summary",
            title="Scheduled Tasks",
            description=f"{total} tasks ({timer_count} timers, {cron_count} cron)",
            icon="calendar",
            severity=DiscoverySeverity.SUCCESS,
            status=f"{total} tasks",
            data={
                "total": total,
                "timer_count": timer_count,
                "cron_count": cron_count,
                "is_summary": True,
            },
            chat_context=f"System has {total} scheduled tasks: {timer_count} systemd timers, {cron_count} cron jobs. "
                        f"View timers: 'systemctl list-timers'. View cron: 'crontab -l' and /etc/cron.*",
        )
