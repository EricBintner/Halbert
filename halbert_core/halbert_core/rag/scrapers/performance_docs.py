"""
Performance Documentation Scraper.

Phase 27: RAG Coverage

Comprehensive performance guides covering:
- System monitoring (top, htop, vmstat)
- Memory analysis
- CPU profiling
- I/O performance
- Benchmarking
"""

import logging
from typing import List
from datetime import datetime
from pathlib import Path

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class PerformanceDocsScraper(BaseScraper):
    """Generates comprehensive performance documentation."""
    
    def __init__(self, config: ScraperConfig):
        super().__init__(config)
    
    def get_source_name(self) -> str:
        return "performance-docs"
    
    def scrape(self) -> List[ScrapedDocument]:
        """Generate performance documentation."""
        logger.info("Generating performance documentation...")
        
        documents = []
        documents.extend(self._generate_guides())
        
        logger.info(f"Total performance documents: {len(documents)}")
        return documents
    
    def _generate_guides(self) -> List[ScrapedDocument]:
        """Generate all performance guides."""
        guides = []
        
        guides.append(self._monitoring_guide())
        guides.append(self._memory_guide())
        guides.append(self._cpu_guide())
        guides.append(self._io_guide())
        guides.append(self._network_perf_guide())
        guides.append(self._troubleshooting_guide())
        
        return guides
    
    def _monitoring_guide(self) -> ScrapedDocument:
        """System monitoring guide."""
        content = """# Linux System Monitoring Guide

## top

```bash
# Basic usage
top

# Sort by memory
top -o %MEM

# Sort by CPU
top -o %CPU

# Update every 2 seconds
top -d 2

# Show specific user
top -u username

# Batch mode (for scripts)
top -b -n 1
```

### top Interactive Keys

| Key | Action |
|-----|--------|
| `1` | Show individual CPUs |
| `m` | Toggle memory display |
| `t` | Toggle task/CPU display |
| `k` | Kill process |
| `r` | Renice process |
| `f` | Select fields |
| `o` | Filter processes |
| `c` | Toggle command line |
| `H` | Toggle threads |
| `q` | Quit |

## htop

```bash
# Install
sudo apt install htop

# Basic usage
htop

# Show specific user
htop -u username

# No colors
htop -C
```

### htop Features
- Color-coded display
- Mouse support
- Process tree view (F5)
- Search processes (F3)
- Filter processes (F4)
- Kill with signal selection (F9)

## vmstat

```bash
# One-time report
vmstat

# Every 2 seconds, 10 times
vmstat 2 10

# With timestamps
vmstat -t 2 5

# Memory in MB
vmstat -S M 2 5

# Disk stats
vmstat -d

# Active/inactive memory
vmstat -a
```

### vmstat Columns

| Column | Description |
|--------|-------------|
| r | Runnable processes |
| b | Blocked processes |
| swpd | Virtual memory used |
| free | Free memory |
| buff | Buffer memory |
| cache | Cache memory |
| si | Swap in |
| so | Swap out |
| bi | Block in (disk read) |
| bo | Block out (disk write) |
| in | Interrupts/sec |
| cs | Context switches/sec |
| us | User CPU % |
| sy | System CPU % |
| id | Idle CPU % |
| wa | Wait I/O % |

## uptime

```bash
uptime
# Output: 14:32:15 up 7 days, 3:24, 2 users, load average: 0.15, 0.10, 0.05
```

**Load Average**: 1-min, 5-min, 15-min
- Value of 1.0 = 1 CPU fully utilized
- Compare to number of CPUs

## dstat

```bash
# Install
sudo apt install dstat

# Default display
dstat

# CPU, disk, network
dstat -cdn

# With timestamps
dstat -t

# Top CPU/memory consumers
dstat --top-cpu --top-mem

# Save to CSV
dstat -cdn --output stats.csv
```

## glances

```bash
# Install
sudo apt install glances

# Run
glances

# Web interface
glances -w

# Client/server mode
glances -s           # Server
glances -c server    # Client
```

## sar (System Activity Reporter)

```bash
# Install
sudo apt install sysstat

# Enable data collection
sudo systemctl enable sysstat

# CPU stats
sar -u 2 5

# Memory stats
sar -r 2 5

# Disk stats
sar -d 2 5

# Network stats
sar -n DEV 2 5

# Historical data
sar -f /var/log/sysstat/sa01
```
"""
        return ScrapedDocument(
            id=self._generate_id("monitoring"),
            url="synthetic://monitoring",
            title="Linux System Monitoring Guide",
            content=content,
            source=self.get_source_name(),
            category="performance",
            tags=["monitoring", "top", "htop", "vmstat", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _memory_guide(self) -> ScrapedDocument:
        """Memory analysis guide."""
        content = """# Linux Memory Analysis Guide

## free Command

```bash
# Basic output
free

# Human readable
free -h

# In megabytes
free -m

# Continuous update
free -s 2

# Wide output
free -w
```

### Understanding free Output

```
              total        used        free      shared  buff/cache   available
Mem:          16Gi       4.2Gi       8.1Gi       412Mi       3.7Gi        11Gi
Swap:         8.0Gi          0B       8.0Gi
```

- **total**: Total physical memory
- **used**: Memory in use
- **free**: Completely unused memory
- **shared**: Memory used by tmpfs
- **buff/cache**: Buffers + cached data (reclaimable)
- **available**: Memory available for new apps

## /proc/meminfo

```bash
# All memory info
cat /proc/meminfo

# Specific values
grep MemTotal /proc/meminfo
grep MemAvailable /proc/meminfo
grep SwapTotal /proc/meminfo
```

### Key Metrics

| Metric | Description |
|--------|-------------|
| MemTotal | Total RAM |
| MemFree | Unused RAM |
| MemAvailable | Available for allocation |
| Buffers | Raw disk block buffers |
| Cached | Page cache |
| SwapTotal | Total swap |
| SwapFree | Free swap |
| Dirty | Pending disk writes |
| Shmem | Shared memory |

## Per-Process Memory

```bash
# Process memory
ps aux --sort=-%mem | head
pmap PID
cat /proc/PID/status | grep -i mem
cat /proc/PID/smaps

# Summary
smem -t
smem -u           # By user
```

### Memory Types

| Type | Description |
|------|-------------|
| VSZ/VIRT | Virtual memory size |
| RSS/RES | Resident set size (physical) |
| SHR | Shared memory |
| PSS | Proportional set size |
| USS | Unique set size |

## Swap Analysis

```bash
# Swap usage
swapon --show
cat /proc/swaps

# Swap per process
for file in /proc/*/status; do
    awk '/VmSwap|Name/{printf $2 " " $3}END{print ""}' $file
done | sort -k 2 -n -r | head

# Swappiness (0-100)
cat /proc/sys/vm/swappiness
sudo sysctl vm.swappiness=10
```

## Memory Pressure

```bash
# OOM killer scores
cat /proc/PID/oom_score
cat /proc/PID/oom_score_adj

# Prevent OOM kill
echo -1000 > /proc/PID/oom_score_adj

# View OOM kills
dmesg | grep -i "out of memory"
journalctl -k | grep -i "oom"
```

## Clearing Caches

```bash
# Drop page cache
sudo sync
echo 1 | sudo tee /proc/sys/vm/drop_caches

# Drop dentries and inodes
echo 2 | sudo tee /proc/sys/vm/drop_caches

# Drop all
echo 3 | sudo tee /proc/sys/vm/drop_caches
```

## Memory Tuning

```bash
# /etc/sysctl.conf

# Swappiness (lower = prefer RAM)
vm.swappiness = 10

# Cache pressure
vm.vfs_cache_pressure = 50

# Dirty ratio (% before writeback)
vm.dirty_ratio = 20
vm.dirty_background_ratio = 5

# Apply changes
sudo sysctl -p
```
"""
        return ScrapedDocument(
            id=self._generate_id("memory"),
            url="synthetic://memory",
            title="Linux Memory Analysis Guide",
            content=content,
            source=self.get_source_name(),
            category="performance",
            tags=["memory", "free", "swap", "linux", "performance"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _cpu_guide(self) -> ScrapedDocument:
        """CPU performance guide."""
        content = """# Linux CPU Performance Guide

## CPU Information

```bash
# CPU info
lscpu
cat /proc/cpuinfo

# Number of CPUs
nproc
getconf _NPROCESSORS_ONLN

# CPU frequency
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq
watch -n 1 "cat /proc/cpuinfo | grep MHz"
```

## CPU Usage

```bash
# Overall CPU
mpstat
mpstat 2 5                     # Every 2 sec, 5 times
mpstat -P ALL 2 5              # Per CPU

# Per process
pidstat 2 5
pidstat -p PID 2 5

# Load average
uptime
cat /proc/loadavg
```

### Understanding Load Average

```
Load Average: 0.50, 0.75, 1.00
             1-min  5-min  15-min
```

- Compare to CPU count
- Load 1.0 = 1 CPU fully utilized
- 4-core system: load 4.0 = 100% utilized
- Higher than CPU count = processes waiting

## Per-Process CPU

```bash
# Top CPU consumers
ps aux --sort=-%cpu | head

# Specific process
ps -p PID -o %cpu,cmd

# Real-time
top -p PID
htop -p PID

# Time breakdown
cat /proc/PID/stat
```

## Profiling

### perf

```bash
# Install
sudo apt install linux-tools-generic

# CPU profile
sudo perf top
sudo perf record -g command
sudo perf report

# Count events
sudo perf stat command
sudo perf stat -p PID

# Flame graph
sudo perf record -F 99 -g -- sleep 30
sudo perf script | ./stackcollapse-perf.pl | ./flamegraph.pl > graph.svg
```

### strace (System Calls)

```bash
# Trace process
strace command
strace -p PID

# Summary
strace -c command

# Follow forks
strace -f command

# Time calls
strace -T command
```

## CPU Frequency

```bash
# Current frequency
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq

# Available governors
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors

# Current governor
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

# Set governor
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# cpupower tool
sudo apt install linux-tools-common
cpupower frequency-info
sudo cpupower frequency-set -g performance
```

## CPU Affinity

```bash
# Run on specific CPU
taskset -c 0 command
taskset -c 0,1 command

# Set affinity of running process
taskset -c 0-3 -p PID

# View affinity
taskset -p PID
```

## Process Priority

```bash
# Nice values (-20 to 19, lower = higher priority)
nice -n 10 command          # Lower priority
sudo nice -n -10 command    # Higher priority

# Change running process
renice 10 -p PID
sudo renice -10 -p PID

# Real-time priority
sudo chrt -f 50 command     # FIFO
sudo chrt -r 50 command     # Round-robin
```
"""
        return ScrapedDocument(
            id=self._generate_id("cpu"),
            url="synthetic://cpu",
            title="Linux CPU Performance Guide",
            content=content,
            source=self.get_source_name(),
            category="performance",
            tags=["cpu", "performance", "linux", "profiling"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _io_guide(self) -> ScrapedDocument:
        """I/O performance guide."""
        content = """# Linux I/O Performance Guide

## iotop

```bash
# Install
sudo apt install iotop

# Basic usage
sudo iotop

# Only active processes
sudo iotop -o

# Batch mode
sudo iotop -b -n 5

# Specific process
sudo iotop -p PID
```

## iostat

```bash
# Install (part of sysstat)
sudo apt install sysstat

# Basic
iostat

# Extended stats
iostat -x

# Per device
iostat -d sda

# Continuous
iostat -x 2 5              # Every 2 sec, 5 times

# In MB
iostat -m
```

### iostat Columns

| Column | Description |
|--------|-------------|
| tps | Transfers per second |
| kB_read/s | Read KB/sec |
| kB_wrtn/s | Write KB/sec |
| await | Average wait time (ms) |
| svctm | Average service time |
| %util | Device utilization |

## pidstat I/O

```bash
# I/O per process
pidstat -d 2 5

# Specific process
pidstat -d -p PID 2 5
```

## Block Device Stats

```bash
# /proc/diskstats
cat /proc/diskstats

# Parsed output
cat /sys/block/sda/stat

# Queue depth
cat /sys/block/sda/queue/nr_requests
```

## I/O Schedulers

```bash
# Current scheduler
cat /sys/block/sda/queue/scheduler

# Available schedulers
# [mq-deadline] kyber bfq none

# Change scheduler
echo mq-deadline | sudo tee /sys/block/sda/queue/scheduler

# For SSDs, 'none' or 'mq-deadline' often best
```

## fio (Benchmarking)

```bash
# Install
sudo apt install fio

# Random read test
fio --name=randread --ioengine=libaio --iodepth=16 --rw=randread \
    --bs=4k --direct=1 --size=1G --numjobs=4 --runtime=60

# Random write test
fio --name=randwrite --ioengine=libaio --iodepth=16 --rw=randwrite \
    --bs=4k --direct=1 --size=1G --numjobs=4 --runtime=60

# Sequential read
fio --name=seqread --ioengine=libaio --rw=read --bs=1M \
    --direct=1 --size=1G --runtime=60

# Mixed workload
fio --name=mixed --ioengine=libaio --rw=randrw --rwmixread=70 \
    --bs=4k --direct=1 --size=1G --numjobs=4 --runtime=60
```

## dd (Simple Benchmark)

```bash
# Write test
dd if=/dev/zero of=testfile bs=1G count=1 oflag=direct

# Read test
dd if=testfile of=/dev/null bs=1G count=1 iflag=direct

# With timing
dd if=/dev/zero of=testfile bs=1M count=1024 conv=fdatasync
```

## Tuning

```bash
# Read-ahead
cat /sys/block/sda/queue/read_ahead_kb
echo 256 | sudo tee /sys/block/sda/queue/read_ahead_kb

# I/O priority
# ionice classes: 1=realtime, 2=best-effort, 3=idle
ionice -c 3 command              # Idle priority
ionice -c 2 -n 0 command         # Best-effort, high
ionice -p PID                    # Check process

# Dirty ratio
echo 20 | sudo tee /proc/sys/vm/dirty_ratio
echo 10 | sudo tee /proc/sys/vm/dirty_background_ratio
```
"""
        return ScrapedDocument(
            id=self._generate_id("io"),
            url="synthetic://io",
            title="Linux I/O Performance Guide",
            content=content,
            source=self.get_source_name(),
            category="performance",
            tags=["io", "disk", "performance", "linux", "iotop"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _network_perf_guide(self) -> ScrapedDocument:
        """Network performance guide."""
        content = """# Linux Network Performance Guide

## Bandwidth Monitoring

### iftop

```bash
# Install
sudo apt install iftop

# Monitor interface
sudo iftop -i eth0

# No DNS resolution
sudo iftop -n

# Show ports
sudo iftop -P
```

### nload

```bash
# Install
sudo apt install nload

# Basic usage
nload

# Specific interface
nload eth0

# Multiple interfaces
nload eth0 eth1
```

### vnstat

```bash
# Install
sudo apt install vnstat

# Summary
vnstat

# Live monitor
vnstat -l

# Hourly stats
vnstat -h

# Daily stats
vnstat -d

# Top 10 days
vnstat -t
```

## Connection Analysis

### ss (Socket Statistics)

```bash
# All connections
ss -a

# TCP connections
ss -t

# Listening sockets
ss -l

# With process info
ss -p

# Statistics
ss -s

# Connection states
ss state established
ss state time-wait
```

### netstat

```bash
# All connections
netstat -a

# TCP with process
netstat -tlnp

# Statistics
netstat -s

# Routing table
netstat -r
```

## Bandwidth Testing

### iperf3

```bash
# Install
sudo apt install iperf3

# Server
iperf3 -s

# Client (test upload)
iperf3 -c server_ip

# Reverse (test download)
iperf3 -c server_ip -R

# UDP test
iperf3 -c server_ip -u

# Duration
iperf3 -c server_ip -t 60

# Parallel streams
iperf3 -c server_ip -P 4
```

### speedtest-cli

```bash
# Install
sudo apt install speedtest-cli

# Basic test
speedtest-cli

# Simple output
speedtest-cli --simple

# Specific server
speedtest-cli --server SERVER_ID
```

## Latency Testing

```bash
# Basic ping
ping -c 10 google.com

# With statistics
ping -c 100 -q google.com

# Flood ping (root)
sudo ping -f google.com

# Traceroute
traceroute google.com
mtr google.com
```

## Network Tuning

```bash
# /etc/sysctl.conf

# TCP buffer sizes
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216

# Connection handling
net.core.somaxconn = 65535
net.core.netdev_max_backlog = 65535
net.ipv4.tcp_max_syn_backlog = 65535

# Keepalive
net.ipv4.tcp_keepalive_time = 600
net.ipv4.tcp_keepalive_intvl = 60
net.ipv4.tcp_keepalive_probes = 3

# TIME_WAIT handling
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 30

# Apply
sudo sysctl -p
```

## Interface Statistics

```bash
# Interface stats
ip -s link show eth0
cat /proc/net/dev

# Errors and drops
ethtool -S eth0

# Ring buffer size
ethtool -g eth0
sudo ethtool -G eth0 rx 4096 tx 4096
```
"""
        return ScrapedDocument(
            id=self._generate_id("network-perf"),
            url="synthetic://network-perf",
            title="Linux Network Performance Guide",
            content=content,
            source=self.get_source_name(),
            category="performance",
            tags=["network", "performance", "linux", "bandwidth"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _troubleshooting_guide(self) -> ScrapedDocument:
        """Performance troubleshooting guide."""
        content = """# Performance Troubleshooting Guide

## Quick Diagnosis

```bash
# 1. Check load average
uptime

# 2. Check CPU
top -bn1 | head -20
mpstat 1 5

# 3. Check memory
free -h
vmstat 1 5

# 4. Check I/O
iostat -x 1 5
iotop -bn 3

# 5. Check network
ss -s
iftop -n
```

## High CPU Usage

```bash
# Find culprit
top -o %CPU
ps aux --sort=-%cpu | head

# Per-core breakdown
mpstat -P ALL 1 5

# Check wait I/O
vmstat 1 5              # Check 'wa' column

# Profile the process
sudo perf top -p PID
strace -c -p PID
```

### Common Causes
- Runaway process
- High I/O wait (disk bottleneck)
- Insufficient CPUs for workload
- Inefficient code

## High Memory Usage

```bash
# Find memory hogs
ps aux --sort=-%mem | head
smem -t

# Check for memory leak
watch -n 5 "ps -p PID -o rss,vsz,cmd"

# Check swap
swapon --show
vmstat 1 5              # Check 'si' and 'so'

# Clear cache (if needed)
sync; echo 3 > /proc/sys/vm/drop_caches
```

### Common Causes
- Memory leak
- Large file caching
- Insufficient RAM
- High swapping

## High I/O Wait

```bash
# Find I/O processes
sudo iotop -o
pidstat -d 1 5

# Check disk stats
iostat -x 1 5           # Check await and %util

# Check for disk errors
dmesg | grep -i "error"
smartctl -a /dev/sda
```

### Common Causes
- Slow disk
- Too much disk activity
- Disk failing
- Wrong I/O scheduler

## Slow Network

```bash
# Check interface errors
ip -s link show eth0
ethtool -S eth0 | grep -i error

# Check connection states
ss -s
netstat -s | grep -i "retransmit"

# Test latency
ping -c 100 gateway
mtr target

# Test bandwidth
iperf3 -c server
```

### Common Causes
- Network congestion
- High packet loss
- MTU issues
- DNS problems
- Firewall bottleneck

## System Unresponsive

```bash
# If you can SSH in:
# Check for fork bomb or too many processes
ps aux | wc -l
cat /proc/sys/kernel/pid_max

# Check OOM killer
dmesg | grep -i "oom"
journalctl -k | grep -i "killed process"

# Check disk space
df -h
df -i                   # Inodes

# Check zombie processes
ps aux | grep 'Z'
```

## Performance Checklist

```markdown
## CPU
- [ ] Load average < number of CPUs
- [ ] No process at 100% unexpectedly
- [ ] Low I/O wait

## Memory
- [ ] Adequate free/available memory
- [ ] Minimal swapping
- [ ] No OOM kills

## Disk
- [ ] Low await times (<10ms for SSD)
- [ ] Low utilization (<80%)
- [ ] No errors in dmesg

## Network
- [ ] No packet loss
- [ ] Low retransmissions
- [ ] Adequate bandwidth
```
"""
        return ScrapedDocument(
            id=self._generate_id("troubleshooting"),
            url="synthetic://performance-troubleshooting",
            title="Performance Troubleshooting Guide",
            content=content,
            source=self.get_source_name(),
            category="troubleshooting",
            tags=["performance", "troubleshooting", "linux", "diagnosis"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "troubleshooting", "priority": "high"}
        )
    
    def _generate_id(self, name: str) -> str:
        """Generate document ID."""
        import hashlib
        return hashlib.md5(f"performance-docs:{name}".encode()).hexdigest()[:16]


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate performance documentation")
    parser.add_argument("--output-dir", default="data/linux/performance-docs")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    
    config = ScraperConfig(output_dir=Path(args.output_dir))
    scraper = PerformanceDocsScraper(config)
    
    docs = scraper.scrape()
    scraper.save_documents(docs, "performance_docs.jsonl")
