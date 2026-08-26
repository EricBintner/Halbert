# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Linux Networking Documentation Scraper.

Phase 27: RAG Coverage

Comprehensive networking guides covering:
- ip command suite
- Network troubleshooting
- DNS configuration
- Firewall (iptables, nftables)
- SSH and VPN
"""

import logging
from typing import List
from datetime import datetime
from pathlib import Path

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class NetworkingDocsScraper(BaseScraper):
    """Generates comprehensive Linux networking documentation."""
    
    def __init__(self, config: ScraperConfig):
        super().__init__(config)
    
    def get_source_name(self) -> str:
        return "networking-docs"
    
    def scrape(self) -> List[ScrapedDocument]:
        """Generate networking documentation."""
        logger.info("Generating networking documentation...")
        
        documents = []
        documents.extend(self._generate_guides())
        
        logger.info(f"Total networking documents: {len(documents)}")
        return documents
    
    def _generate_guides(self) -> List[ScrapedDocument]:
        """Generate all networking guides."""
        guides = []
        
        guides.append(self._ip_command_guide())
        guides.append(self._ss_netstat_guide())
        guides.append(self._dns_guide())
        guides.append(self._iptables_guide())
        guides.append(self._nftables_guide())
        guides.append(self._ssh_guide())
        guides.append(self._troubleshooting_guide())
        guides.append(self._tcpdump_guide())
        
        return guides
    
    def _ip_command_guide(self) -> ScrapedDocument:
        """ip command reference."""
        content = """# Linux ip Command Complete Reference

## Overview

The `ip` command is the modern replacement for `ifconfig`, `route`, and `arp`.

## IP Address Management

```bash
# Show all addresses
ip addr show
ip a                                # Short form

# Show specific interface
ip addr show eth0

# Add IP address
sudo ip addr add 192.168.1.100/24 dev eth0

# Add secondary IP
sudo ip addr add 192.168.1.101/24 dev eth0 label eth0:1

# Delete IP address
sudo ip addr del 192.168.1.100/24 dev eth0

# Flush all addresses
sudo ip addr flush dev eth0
```

## Link (Interface) Management

```bash
# Show all interfaces
ip link show
ip l

# Bring interface up/down
sudo ip link set eth0 up
sudo ip link set eth0 down

# Set MTU
sudo ip link set eth0 mtu 9000

# Set MAC address
sudo ip link set eth0 address 00:11:22:33:44:55

# Create VLAN
sudo ip link add link eth0 name eth0.100 type vlan id 100

# Create bridge
sudo ip link add br0 type bridge
sudo ip link set eth0 master br0

# Create bond
sudo ip link add bond0 type bond mode 802.3ad
sudo ip link set eth0 master bond0
```

## Routing

```bash
# Show routing table
ip route show
ip r

# Show specific route
ip route get 8.8.8.8

# Add default gateway
sudo ip route add default via 192.168.1.1

# Add static route
sudo ip route add 10.0.0.0/8 via 192.168.1.1
sudo ip route add 10.0.0.0/8 via 192.168.1.1 dev eth0

# Delete route
sudo ip route del 10.0.0.0/8

# Replace route
sudo ip route replace default via 192.168.1.2
```

## Neighbor (ARP) Table

```bash
# Show ARP table
ip neigh show
ip n

# Add static ARP entry
sudo ip neigh add 192.168.1.1 lladdr 00:11:22:33:44:55 dev eth0

# Delete entry
sudo ip neigh del 192.168.1.1 dev eth0

# Flush ARP cache
sudo ip neigh flush all
```

## Network Namespaces

```bash
# List namespaces
ip netns list

# Create namespace
sudo ip netns add myns

# Execute in namespace
sudo ip netns exec myns ip addr show

# Delete namespace
sudo ip netns del myns

# Move interface to namespace
sudo ip link set eth1 netns myns
```

## Monitoring

```bash
# Watch for changes
ip monitor all
ip monitor link
ip monitor route

# Statistics
ip -s link show eth0
ip -s -s link show eth0    # More stats
```

## Useful Options

```bash
# JSON output
ip -j addr show
ip -j route show | jq

# Brief output
ip -br addr show
ip -br link show

# Color output
ip -c addr show

# Show only IPv4/IPv6
ip -4 addr show
ip -6 addr show
```
"""
        return ScrapedDocument(
            id=self._generate_id("ip-command"),
            url="https://man7.org/linux/man-pages/man8/ip.8.html",
            title="Linux ip Command Complete Reference",
            content=content,
            source=self.get_source_name(),
            category="networking",
            tags=["linux", "ip", "networking", "iproute2"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "reference", "priority": "high"}
        )
    
    def _ss_netstat_guide(self) -> ScrapedDocument:
        """ss and netstat guide."""
        content = """# ss and netstat - Network Connection Analysis

## ss (Socket Statistics) - Modern Tool

```bash
# All connections
ss

# Listening sockets
ss -l

# TCP connections
ss -t
ss -tl                          # TCP listening

# UDP connections
ss -u
ss -ul                          # UDP listening

# All with process info
ss -tulpn

# Show numeric (don't resolve names)
ss -n

# Show timer information
ss -o

# Extended info
ss -e

# Memory usage
ss -m
```

### Common ss Recipes

```bash
# All listening TCP with process
ss -tlnp

# All established connections
ss -t state established

# Connections to specific port
ss -t dst :443
ss -t src :22

# Connections from specific IP
ss -t src 192.168.1.100

# Count connections per state
ss -t | awk '{print $1}' | sort | uniq -c

# Find process using port
ss -tlnp | grep :80
```

## netstat (Legacy but Common)

```bash
# All connections
netstat -a

# Listening sockets
netstat -l

# TCP connections
netstat -t
netstat -tln                    # TCP listening, numeric

# With process info (requires root)
sudo netstat -tlnp

# Statistics
netstat -s

# Routing table
netstat -r

# Interface statistics
netstat -i
```

## Comparing ss and netstat

| Task | ss | netstat |
|------|-----|---------|
| TCP listening | `ss -tln` | `netstat -tln` |
| With process | `ss -tlnp` | `netstat -tlnp` |
| UDP | `ss -uln` | `netstat -uln` |
| All + process | `ss -tulnp` | `netstat -tulnp` |

**Note**: `ss` is faster and provides more information. Use it instead of `netstat`.

## lsof for Port Usage

```bash
# Find what's using port 80
sudo lsof -i :80

# Find all network connections by process
sudo lsof -i -P -n | grep LISTEN

# Find connections by process name
sudo lsof -i -P -n | grep nginx
```
"""
        return ScrapedDocument(
            id=self._generate_id("ss-netstat"),
            url="https://man7.org/linux/man-pages/man8/ss.8.html",
            title="ss and netstat - Network Connection Analysis",
            content=content,
            source=self.get_source_name(),
            category="networking",
            tags=["linux", "ss", "netstat", "networking", "sockets"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "reference", "priority": "high"}
        )
    
    def _dns_guide(self) -> ScrapedDocument:
        """DNS configuration guide."""
        content = """# Linux DNS Configuration Guide

## Check Current DNS

```bash
# resolv.conf
cat /etc/resolv.conf

# systemd-resolved status
resolvectl status
systemd-resolve --status        # Older syntax

# What's managing DNS
ls -la /etc/resolv.conf
```

## systemd-resolved (Modern Ubuntu/Fedora)

```bash
# Status
resolvectl status

# Query DNS
resolvectl query google.com

# Flush cache
resolvectl flush-caches

# Statistics
resolvectl statistics
```

### Configure systemd-resolved

```bash
# Edit config
sudo nano /etc/systemd/resolved.conf
```

```ini
[Resolve]
DNS=8.8.8.8 8.8.4.4
FallbackDNS=1.1.1.1 1.0.0.1
DNSSEC=allow-downgrade
DNSOverTLS=opportunistic
```

```bash
sudo systemctl restart systemd-resolved
```

## NetworkManager DNS

```bash
# Check current DNS
nmcli dev show | grep DNS

# Set DNS for connection
nmcli con mod "Wired connection 1" ipv4.dns "8.8.8.8 8.8.4.4"
nmcli con mod "Wired connection 1" ipv4.ignore-auto-dns yes
nmcli con up "Wired connection 1"
```

## Manual /etc/resolv.conf

```bash
# Direct edit (may be overwritten)
sudo nano /etc/resolv.conf
```

```
nameserver 8.8.8.8
nameserver 8.8.4.4
search example.com
options timeout:2 attempts:3
```

### Prevent Overwriting

```bash
# Make immutable
sudo chattr +i /etc/resolv.conf

# Remove immutable
sudo chattr -i /etc/resolv.conf
```

## DNS Testing Tools

### dig
```bash
# Basic query
dig google.com

# Specific record type
dig google.com MX
dig google.com AAAA
dig google.com TXT

# Short answer only
dig +short google.com

# Use specific DNS server
dig @8.8.8.8 google.com

# Trace resolution
dig +trace google.com

# Reverse lookup
dig -x 8.8.8.8
```

### nslookup
```bash
nslookup google.com
nslookup -type=MX google.com
nslookup google.com 8.8.8.8
```

### host
```bash
host google.com
host -t MX google.com
host 8.8.8.8
```

## Local DNS (/etc/hosts)

```bash
sudo nano /etc/hosts
```

```
127.0.0.1       localhost
192.168.1.100   myserver.local myserver
192.168.1.101   database.local
```

## DNS Caching

### systemd-resolved cache
```bash
resolvectl flush-caches
resolvectl statistics
```

### nscd (Name Service Cache Daemon)
```bash
sudo apt install nscd
sudo systemctl enable nscd
sudo systemctl start nscd

# Flush cache
sudo nscd -i hosts
```
"""
        return ScrapedDocument(
            id=self._generate_id("dns-guide"),
            url="synthetic://dns-configuration",
            title="Linux DNS Configuration Guide",
            content=content,
            source=self.get_source_name(),
            category="networking",
            tags=["linux", "dns", "networking", "resolv.conf"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _iptables_guide(self) -> ScrapedDocument:
        """iptables firewall guide."""
        content = """# iptables Firewall Guide

## Concepts

- **Tables**: filter (default), nat, mangle, raw
- **Chains**: INPUT, OUTPUT, FORWARD, PREROUTING, POSTROUTING
- **Targets**: ACCEPT, DROP, REJECT, LOG, MASQUERADE, DNAT, SNAT

## View Rules

```bash
# List all rules
sudo iptables -L -v -n
sudo iptables -L -v -n --line-numbers

# List specific table
sudo iptables -t nat -L -v -n

# List as commands (for backup)
sudo iptables-save
```

## Basic Rules

```bash
# Allow established connections
sudo iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Allow localhost
sudo iptables -A INPUT -i lo -j ACCEPT

# Allow SSH
sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT

# Allow HTTP/HTTPS
sudo iptables -A INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 443 -j ACCEPT

# Allow from specific IP
sudo iptables -A INPUT -s 192.168.1.100 -j ACCEPT

# Allow from subnet
sudo iptables -A INPUT -s 192.168.1.0/24 -j ACCEPT

# Drop all other incoming
sudo iptables -A INPUT -j DROP
```

## Delete Rules

```bash
# By line number
sudo iptables -L --line-numbers
sudo iptables -D INPUT 3

# By specification
sudo iptables -D INPUT -p tcp --dport 80 -j ACCEPT

# Flush all rules
sudo iptables -F
sudo iptables -t nat -F
```

## Default Policies

```bash
# Set default policies
sudo iptables -P INPUT DROP
sudo iptables -P FORWARD DROP
sudo iptables -P OUTPUT ACCEPT
```

## NAT and Masquerading

```bash
# Enable IP forwarding
echo 1 | sudo tee /proc/sys/net/ipv4/ip_forward

# Masquerade outgoing (for router)
sudo iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE

# Port forwarding
sudo iptables -t nat -A PREROUTING -i eth0 -p tcp --dport 8080 -j DNAT --to-destination 192.168.1.100:80
sudo iptables -A FORWARD -p tcp -d 192.168.1.100 --dport 80 -j ACCEPT
```

## Logging

```bash
# Log dropped packets
sudo iptables -A INPUT -j LOG --log-prefix "DROPPED: " --log-level 4
sudo iptables -A INPUT -j DROP

# View logs
sudo tail -f /var/log/kern.log | grep DROPPED
```

## Save and Restore

```bash
# Save rules
sudo iptables-save > /etc/iptables.rules

# Restore rules
sudo iptables-restore < /etc/iptables.rules

# Persist across reboots (Debian/Ubuntu)
sudo apt install iptables-persistent
sudo netfilter-persistent save
```

## Complete Example

```bash
#!/bin/bash
# Basic firewall script

# Flush existing rules
iptables -F
iptables -t nat -F

# Default policies
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT ACCEPT

# Allow loopback
iptables -A INPUT -i lo -j ACCEPT

# Allow established
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Allow SSH
iptables -A INPUT -p tcp --dport 22 -j ACCEPT

# Allow HTTP/HTTPS
iptables -A INPUT -p tcp -m multiport --dports 80,443 -j ACCEPT

# Allow ping
iptables -A INPUT -p icmp --icmp-type echo-request -j ACCEPT

# Log and drop everything else
iptables -A INPUT -j LOG --log-prefix "DROPPED: "
iptables -A INPUT -j DROP
```
"""
        return ScrapedDocument(
            id=self._generate_id("iptables-guide"),
            url="https://netfilter.org/documentation/",
            title="iptables Firewall Guide",
            content=content,
            source=self.get_source_name(),
            category="security",
            tags=["linux", "iptables", "firewall", "security", "networking"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _nftables_guide(self) -> ScrapedDocument:
        """nftables firewall guide."""
        content = """# nftables - Modern Linux Firewall

## Overview

nftables is the successor to iptables, ip6tables, arptables, and ebtables.

## Basic Commands

```bash
# List all rules
sudo nft list ruleset

# List specific table
sudo nft list table inet filter

# Flush all rules
sudo nft flush ruleset
```

## Configuration File

```bash
# /etc/nftables.conf
sudo nano /etc/nftables.conf
```

```
#!/usr/sbin/nft -f

flush ruleset

table inet filter {
    chain input {
        type filter hook input priority 0; policy drop;
        
        # Allow established
        ct state established,related accept
        
        # Allow loopback
        iif lo accept
        
        # Allow ICMP
        ip protocol icmp accept
        ip6 nexthdr icmpv6 accept
        
        # Allow SSH
        tcp dport 22 accept
        
        # Allow HTTP/HTTPS
        tcp dport { 80, 443 } accept
        
        # Log dropped
        log prefix "nftables dropped: " counter drop
    }
    
    chain forward {
        type filter hook forward priority 0; policy drop;
    }
    
    chain output {
        type filter hook output priority 0; policy accept;
    }
}
```

## Apply Configuration

```bash
# Load configuration
sudo nft -f /etc/nftables.conf

# Enable on boot
sudo systemctl enable nftables
sudo systemctl start nftables
```

## Interactive Commands

```bash
# Create table
sudo nft add table inet mytable

# Create chain
sudo nft add chain inet mytable mychain { type filter hook input priority 0 \; policy drop \; }

# Add rule
sudo nft add rule inet mytable mychain tcp dport 22 accept

# Delete rule (by handle)
sudo nft -a list ruleset    # Show handles
sudo nft delete rule inet mytable mychain handle 5

# Delete chain
sudo nft delete chain inet mytable mychain

# Delete table
sudo nft delete table inet mytable
```

## NAT with nftables

```
table inet nat {
    chain prerouting {
        type nat hook prerouting priority -100;
        
        # Port forwarding
        tcp dport 8080 dnat to 192.168.1.100:80
    }
    
    chain postrouting {
        type nat hook postrouting priority 100;
        
        # Masquerade
        oif "eth0" masquerade
    }
}
```

## Sets (Groups of IPs/Ports)

```
table inet filter {
    set trusted_ips {
        type ipv4_addr
        elements = { 192.168.1.100, 192.168.1.101, 10.0.0.0/8 }
    }
    
    set web_ports {
        type inet_service
        elements = { 80, 443, 8080 }
    }
    
    chain input {
        type filter hook input priority 0; policy drop;
        
        ip saddr @trusted_ips accept
        tcp dport @web_ports accept
    }
}
```

## Migration from iptables

```bash
# Convert iptables rules to nftables
iptables-save > iptables.rules
iptables-restore-translate -f iptables.rules > nftables.rules

# Or use compatibility layer
sudo apt install iptables-nft
```
"""
        return ScrapedDocument(
            id=self._generate_id("nftables-guide"),
            url="https://wiki.nftables.org/",
            title="nftables - Modern Linux Firewall",
            content=content,
            source=self.get_source_name(),
            category="security",
            tags=["linux", "nftables", "firewall", "security", "networking"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _ssh_guide(self) -> ScrapedDocument:
        """SSH configuration guide."""
        content = """# SSH Complete Guide

## Client Usage

```bash
# Basic connection
ssh user@hostname
ssh -p 2222 user@hostname        # Custom port

# With identity file
ssh -i ~/.ssh/mykey user@hostname

# Verbose (debugging)
ssh -v user@hostname
ssh -vvv user@hostname           # More verbose

# Execute command
ssh user@hostname "ls -la"

# Port forwarding (local)
ssh -L 8080:localhost:80 user@hostname

# Port forwarding (remote)
ssh -R 8080:localhost:80 user@hostname

# SOCKS proxy
ssh -D 1080 user@hostname

# Jump host
ssh -J jumphost user@destination
```

## SSH Keys

```bash
# Generate key pair
ssh-keygen -t ed25519 -C "your_email@example.com"
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"

# Copy key to server
ssh-copy-id user@hostname
ssh-copy-id -i ~/.ssh/mykey.pub user@hostname

# Manual copy
cat ~/.ssh/id_ed25519.pub | ssh user@host "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

## SSH Config File

```bash
# ~/.ssh/config
Host myserver
    HostName 192.168.1.100
    User admin
    Port 22
    IdentityFile ~/.ssh/mykey

Host jump
    HostName jumphost.example.com
    User jumpuser

Host internal
    HostName 10.0.0.50
    User admin
    ProxyJump jump

Host *
    ServerAliveInterval 60
    ServerAliveCountMax 3
    AddKeysToAgent yes
```

## Server Configuration

```bash
# /etc/ssh/sshd_config
sudo nano /etc/ssh/sshd_config
```

### Security Hardening

```
# Disable root login
PermitRootLogin no

# Disable password authentication
PasswordAuthentication no
PubkeyAuthentication yes

# Limit users
AllowUsers admin deploy
AllowGroups sshusers

# Change port (security through obscurity)
Port 2222

# Limit authentication attempts
MaxAuthTries 3
MaxSessions 2

# Idle timeout
ClientAliveInterval 300
ClientAliveCountMax 2

# Disable forwarding if not needed
AllowTcpForwarding no
X11Forwarding no
```

```bash
# Apply changes
sudo sshd -t                     # Test config
sudo systemctl restart sshd
```

## SSH Agent

```bash
# Start agent
eval $(ssh-agent)

# Add key
ssh-add ~/.ssh/id_ed25519
ssh-add -l                       # List keys

# Add with timeout
ssh-add -t 3600 ~/.ssh/id_ed25519

# Remove key
ssh-add -d ~/.ssh/id_ed25519
ssh-add -D                       # Remove all
```

## SCP and SFTP

```bash
# Copy file to remote
scp file.txt user@host:/path/
scp -r directory/ user@host:/path/

# Copy from remote
scp user@host:/path/file.txt ./
scp -r user@host:/path/dir/ ./

# SFTP interactive
sftp user@host
> put localfile
> get remotefile
> ls
> cd /path
> bye
```

## Troubleshooting

```bash
# Verbose connection
ssh -vvv user@host

# Check server logs
sudo tail -f /var/log/auth.log
sudo journalctl -u sshd -f

# Test configuration
sudo sshd -t

# Check permissions
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub
chmod 600 ~/.ssh/authorized_keys
```
"""
        return ScrapedDocument(
            id=self._generate_id("ssh-guide"),
            url="https://man.openbsd.org/ssh",
            title="SSH Complete Guide",
            content=content,
            source=self.get_source_name(),
            category="security",
            tags=["linux", "ssh", "security", "networking", "remote"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _troubleshooting_guide(self) -> ScrapedDocument:
        """Network troubleshooting guide."""
        content = """# Network Troubleshooting Guide

## Systematic Approach

1. **Physical/Link** - Is the cable connected? Is the interface up?
2. **IP** - Do we have an IP address?
3. **Routing** - Can we reach the gateway?
4. **DNS** - Can we resolve names?
5. **Application** - Is the service responding?

## Layer 1-2: Physical/Link

```bash
# Check interface status
ip link show
ethtool eth0

# Check for link
cat /sys/class/net/eth0/carrier    # 1 = link, 0 = no link
cat /sys/class/net/eth0/operstate  # up/down

# Bring interface up
sudo ip link set eth0 up
```

## Layer 3: IP/Routing

```bash
# Check IP address
ip addr show
ip -4 addr show                     # IPv4 only

# Check routing table
ip route show
ip route get 8.8.8.8               # How to reach IP

# Test gateway
ping -c 3 $(ip route | grep default | awk '{print $3}')

# Test external IP
ping -c 3 8.8.8.8
```

## Layer 4: Transport

```bash
# Test TCP port
nc -zv hostname 80
telnet hostname 80

# Check listening ports
ss -tlnp

# Test specific port
curl -v telnet://hostname:port
```

## DNS

```bash
# Test DNS resolution
nslookup google.com
dig google.com
host google.com

# Use specific DNS server
dig @8.8.8.8 google.com

# Check /etc/resolv.conf
cat /etc/resolv.conf
```

## Common Issues

### No IP Address
```bash
# Check DHCP client
sudo dhclient eth0
journalctl -u NetworkManager

# Check netplan
sudo netplan apply
```

### Can't Reach Gateway
```bash
# Verify gateway
ip route | grep default

# Check ARP
ip neigh show
ping gateway_ip
```

### DNS Not Working
```bash
# Test with IP (bypasses DNS)
ping 8.8.8.8

# Check DNS config
cat /etc/resolv.conf
resolvectl status

# Flush DNS cache
resolvectl flush-caches
```

### Slow Network
```bash
# Check for packet loss
ping -c 100 destination

# Check MTU
ping -c 3 -M do -s 1472 destination

# Check for duplex mismatch
ethtool eth0

# Check bandwidth
iperf3 -c server_ip
```

## Diagnostic Commands

```bash
# Trace route
traceroute google.com
mtr google.com                      # Interactive

# Check for firewall blocks
sudo iptables -L -v -n
sudo nft list ruleset

# Check for SELinux/AppArmor
getenforce
aa-status

# Network statistics
netstat -s
ss -s
```

## Packet Capture

```bash
# tcpdump basics
sudo tcpdump -i eth0
sudo tcpdump -i eth0 port 80
sudo tcpdump -i eth0 host 192.168.1.100
sudo tcpdump -i eth0 -w capture.pcap

# Analyze with tshark
tshark -r capture.pcap
```
"""
        return ScrapedDocument(
            id=self._generate_id("network-troubleshooting"),
            url="synthetic://network-troubleshooting",
            title="Network Troubleshooting Guide",
            content=content,
            source=self.get_source_name(),
            category="troubleshooting",
            tags=["linux", "networking", "troubleshooting", "debug"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "troubleshooting", "priority": "high"}
        )
    
    def _tcpdump_guide(self) -> ScrapedDocument:
        """tcpdump packet capture guide."""
        content = """# tcpdump Packet Capture Guide

## Basic Usage

```bash
# Capture on interface
sudo tcpdump -i eth0

# Capture with details
sudo tcpdump -i eth0 -v
sudo tcpdump -i eth0 -vv
sudo tcpdump -i eth0 -vvv

# Don't resolve names (faster)
sudo tcpdump -i eth0 -n
sudo tcpdump -i eth0 -nn          # Don't resolve ports either

# Capture to file
sudo tcpdump -i eth0 -w capture.pcap

# Read from file
tcpdump -r capture.pcap
```

## Filters

### By Host
```bash
sudo tcpdump -i eth0 host 192.168.1.100
sudo tcpdump -i eth0 src host 192.168.1.100
sudo tcpdump -i eth0 dst host 192.168.1.100
```

### By Port
```bash
sudo tcpdump -i eth0 port 80
sudo tcpdump -i eth0 src port 80
sudo tcpdump -i eth0 dst port 80
sudo tcpdump -i eth0 portrange 80-443
```

### By Protocol
```bash
sudo tcpdump -i eth0 tcp
sudo tcpdump -i eth0 udp
sudo tcpdump -i eth0 icmp
sudo tcpdump -i eth0 arp
```

### By Network
```bash
sudo tcpdump -i eth0 net 192.168.1.0/24
```

### Combining Filters
```bash
# AND
sudo tcpdump -i eth0 host 192.168.1.100 and port 80

# OR
sudo tcpdump -i eth0 port 80 or port 443

# NOT
sudo tcpdump -i eth0 not port 22

# Complex
sudo tcpdump -i eth0 'host 192.168.1.100 and (port 80 or port 443)'
```

## Output Options

```bash
# Show packet contents (ASCII)
sudo tcpdump -i eth0 -A

# Show packet contents (hex and ASCII)
sudo tcpdump -i eth0 -X

# Limit packet length
sudo tcpdump -i eth0 -s 100         # First 100 bytes
sudo tcpdump -i eth0 -s 0           # Full packet

# Limit capture count
sudo tcpdump -i eth0 -c 100         # Stop after 100 packets

# Timestamps
sudo tcpdump -i eth0 -tttt          # Full timestamp
```

## Common Recipes

```bash
# HTTP traffic
sudo tcpdump -i eth0 -A -s 0 'tcp port 80 and (((ip[2:2] - ((ip[0]&0xf)<<2)) - ((tcp[12]&0xf0)>>2)) != 0)'

# DNS queries
sudo tcpdump -i eth0 -n port 53

# HTTPS handshakes
sudo tcpdump -i eth0 'tcp port 443 and (tcp[((tcp[12] & 0xf0) >> 2)] = 0x16)'

# SSH traffic
sudo tcpdump -i eth0 port 22

# ICMP (ping)
sudo tcpdump -i eth0 icmp

# SYN packets only
sudo tcpdump -i eth0 'tcp[tcpflags] & (tcp-syn) != 0'

# Find network scanner
sudo tcpdump -i eth0 'tcp[tcpflags] & tcp-syn != 0 and tcp[tcpflags] & tcp-ack == 0'
```

## Rotate Captures

```bash
# Rotate every 100MB, keep 10 files
sudo tcpdump -i eth0 -w capture.pcap -C 100 -W 10

# Rotate every hour
sudo tcpdump -i eth0 -w 'capture_%Y%m%d_%H%M%S.pcap' -G 3600
```
"""
        return ScrapedDocument(
            id=self._generate_id("tcpdump-guide"),
            url="https://www.tcpdump.org/manpages/tcpdump.1.html",
            title="tcpdump Packet Capture Guide",
            content=content,
            source=self.get_source_name(),
            category="networking",
            tags=["linux", "tcpdump", "networking", "packet-capture", "debug"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "reference", "priority": "medium"}
        )
    
    def _generate_id(self, name: str) -> str:
        """Generate document ID."""
        import hashlib
        return hashlib.md5(f"networking-docs:{name}".encode()).hexdigest()[:16]


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate networking documentation")
    parser.add_argument("--output-dir", default="data/linux/networking-docs")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    
    config = ScraperConfig(output_dir=Path(args.output_dir))
    scraper = NetworkingDocsScraper(config)
    
    docs = scraper.scrape()
    scraper.save_documents(docs, "networking_docs.jsonl")
