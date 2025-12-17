"""
Linux Security Documentation Scraper.

Phase 27: RAG Coverage

Comprehensive security guides covering:
- User and permission management
- SELinux basics
- Audit logging
- Hardening checklists
- Security tools
"""

import logging
from typing import List
from datetime import datetime
from pathlib import Path

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class SecurityDocsScraper(BaseScraper):
    """Generates comprehensive Linux security documentation."""
    
    def __init__(self, config: ScraperConfig):
        super().__init__(config)
    
    def get_source_name(self) -> str:
        return "security-docs"
    
    def scrape(self) -> List[ScrapedDocument]:
        """Generate security documentation."""
        logger.info("Generating security documentation...")
        
        documents = []
        documents.extend(self._generate_guides())
        
        logger.info(f"Total security documents: {len(documents)}")
        return documents
    
    def _generate_guides(self) -> List[ScrapedDocument]:
        """Generate all security guides."""
        guides = []
        
        guides.append(self._users_permissions_guide())
        guides.append(self._sudo_guide())
        guides.append(self._selinux_guide())
        guides.append(self._audit_guide())
        guides.append(self._hardening_guide())
        guides.append(self._fail2ban_guide())
        guides.append(self._encryption_guide())
        guides.append(self._security_scanning_guide())
        
        return guides
    
    def _users_permissions_guide(self) -> ScrapedDocument:
        """Users and permissions guide."""
        content = """# Linux Users and Permissions Guide

## User Management

```bash
# Add user
sudo useradd username
sudo useradd -m username           # With home directory
sudo useradd -m -s /bin/bash user  # With shell
sudo adduser username              # Interactive (Debian)

# Delete user
sudo userdel username
sudo userdel -r username           # Remove home dir too

# Modify user
sudo usermod -aG group username    # Add to group
sudo usermod -s /bin/zsh username  # Change shell
sudo usermod -L username           # Lock account
sudo usermod -U username           # Unlock account

# Change password
passwd                             # Own password
sudo passwd username               # Other user
sudo passwd -l username            # Lock password
sudo passwd -e username            # Expire (force change)

# User info
id username
groups username
whoami
```

## Group Management

```bash
# Add group
sudo groupadd groupname

# Delete group
sudo groupdel groupname

# Add user to group
sudo usermod -aG groupname username
sudo gpasswd -a username groupname

# Remove user from group
sudo gpasswd -d username groupname

# List groups
groups
cat /etc/group
getent group groupname
```

## File Permissions

```bash
# View permissions
ls -l file
ls -la directory

# Permission format: rwxrwxrwx
# Owner-Group-Others
# r=read(4), w=write(2), x=execute(1)

# chmod - change mode
chmod 755 file                     # rwxr-xr-x
chmod 644 file                     # rw-r--r--
chmod +x file                      # Add execute
chmod -w file                      # Remove write
chmod u+x file                     # Owner execute
chmod g+w file                     # Group write
chmod o-r file                     # Others no read
chmod -R 755 directory             # Recursive

# chown - change owner
sudo chown user file
sudo chown user:group file
sudo chown -R user:group directory

# chgrp - change group
sudo chgrp group file
```

## Special Permissions

```bash
# SUID (4) - Run as file owner
chmod u+s file
chmod 4755 file
# Example: /usr/bin/passwd

# SGID (2) - Run as file group / inherit group on dirs
chmod g+s file
chmod 2755 directory

# Sticky bit (1) - Only owner can delete (on dirs)
chmod +t directory
chmod 1777 /tmp
```

## ACLs (Access Control Lists)

```bash
# View ACL
getfacl file

# Set ACL
setfacl -m u:username:rwx file     # User permission
setfacl -m g:groupname:rx file     # Group permission
setfacl -m o::r file               # Others

# Default ACL (for new files in directory)
setfacl -d -m u:username:rwx directory

# Remove ACL
setfacl -x u:username file
setfacl -b file                    # Remove all ACLs

# Copy ACL
getfacl file1 | setfacl --set-file=- file2
```

## umask

```bash
# View current umask
umask

# Set umask
umask 022                          # Default files: 644, dirs: 755
umask 077                          # Default files: 600, dirs: 700

# In ~/.bashrc for permanent
echo "umask 027" >> ~/.bashrc
```

## Important Files

```bash
/etc/passwd        # User accounts
/etc/shadow        # Encrypted passwords
/etc/group         # Group definitions
/etc/gshadow       # Group passwords
/etc/login.defs    # Login defaults
/etc/sudoers       # Sudo configuration
```
"""
        return ScrapedDocument(
            id=self._generate_id("users-permissions"),
            url="synthetic://users-permissions",
            title="Linux Users and Permissions Guide",
            content=content,
            source=self.get_source_name(),
            category="security",
            tags=["linux", "users", "permissions", "security", "chmod"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _sudo_guide(self) -> ScrapedDocument:
        """sudo configuration guide."""
        content = """# sudo Configuration Guide

## Basic Usage

```bash
sudo command                       # Run as root
sudo -u user command               # Run as specific user
sudo -i                            # Root shell (login)
sudo -s                            # Root shell (current env)
sudo -l                            # List allowed commands
sudo -v                            # Extend timeout
sudo -k                            # Invalidate session
```

## sudoers File

```bash
# ALWAYS edit with visudo
sudo visudo

# Or edit drop-in file
sudo visudo -f /etc/sudoers.d/myconfig
```

### Syntax

```
user host=(runas) commands
%group host=(runas) commands
```

### Examples

```sudoers
# Allow all commands
username ALL=(ALL:ALL) ALL

# Allow specific command
username ALL=(ALL) /usr/bin/apt update

# No password required
username ALL=(ALL) NOPASSWD: ALL
username ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart nginx

# Allow group
%admin ALL=(ALL) ALL
%wheel ALL=(ALL) ALL

# Multiple commands
username ALL=(ALL) /usr/bin/apt, /usr/bin/systemctl

# Wildcards
username ALL=(ALL) /usr/bin/apt *

# Deny command
username ALL=(ALL) ALL, !/usr/bin/su

# Command aliases
Cmnd_Alias WEB = /usr/bin/systemctl restart nginx, /usr/bin/systemctl reload nginx
username ALL=(ALL) WEB
```

## Drop-in Configuration

```bash
# Create file in /etc/sudoers.d/
sudo visudo -f /etc/sudoers.d/username

# Content
username ALL=(ALL) NOPASSWD: /usr/bin/docker
```

## Security Options

```sudoers
# Require password for each command
Defaults timestamp_timeout=0

# Log to file
Defaults logfile=/var/log/sudo.log

# Secure path
Defaults secure_path="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# Require TTY
Defaults requiretty

# Environment variables
Defaults env_keep += "EDITOR VISUAL"
```

## Troubleshooting

```bash
# Check syntax
sudo visudo -c

# Debug sudo
sudo -l -U username

# View sudo logs
sudo grep sudo /var/log/auth.log
sudo journalctl | grep sudo
```
"""
        return ScrapedDocument(
            id=self._generate_id("sudo-guide"),
            url="https://www.sudo.ws/docs/",
            title="sudo Configuration Guide",
            content=content,
            source=self.get_source_name(),
            category="security",
            tags=["linux", "sudo", "security", "permissions"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _selinux_guide(self) -> ScrapedDocument:
        """SELinux basics guide."""
        content = """# SELinux Basics Guide

## Overview

SELinux (Security-Enhanced Linux) provides mandatory access control (MAC) on top of standard Linux permissions.

## Check Status

```bash
# Current mode
getenforce
sestatus

# Modes:
# Enforcing - policies enforced
# Permissive - policies not enforced, only logged
# Disabled - SELinux off
```

## Change Mode

```bash
# Temporarily (until reboot)
sudo setenforce 0                  # Permissive
sudo setenforce 1                  # Enforcing

# Permanently
sudo nano /etc/selinux/config
# Set SELINUX=enforcing|permissive|disabled
```

## Contexts

```bash
# View file context
ls -Z file
ls -laZ directory

# View process context
ps auxZ

# View user context
id -Z
```

### Context Format
```
user:role:type:level
system_u:object_r:httpd_sys_content_t:s0
```

## Managing File Contexts

```bash
# Change context temporarily
chcon -t httpd_sys_content_t /var/www/html/file

# Restore default context
restorecon -v /var/www/html/file
restorecon -Rv /var/www/html/      # Recursive

# View default context
semanage fcontext -l | grep /var/www

# Add permanent context rule
sudo semanage fcontext -a -t httpd_sys_content_t "/mywebroot(/.*)?"
sudo restorecon -Rv /mywebroot/
```

## Booleans

```bash
# List all booleans
getsebool -a
getsebool -a | grep httpd

# Get specific boolean
getsebool httpd_can_network_connect

# Set boolean (temporary)
sudo setsebool httpd_can_network_connect on

# Set boolean (permanent)
sudo setsebool -P httpd_can_network_connect on
```

## Common Booleans

```bash
# HTTP
httpd_can_network_connect          # Allow outgoing connections
httpd_can_network_connect_db       # Allow database connections
httpd_enable_cgi                   # Allow CGI scripts
httpd_use_nfs                      # Allow NFS content

# SSH
ssh_sysadm_login                   # Allow sysadm_u SSH

# NFS
nfs_export_all_ro                  # Export any file read-only
nfs_export_all_rw                  # Export any file read-write
```

## Troubleshooting

```bash
# View denials in audit log
sudo ausearch -m AVC -ts recent
sudo ausearch -m AVC | audit2why

# Generate policy module
sudo ausearch -m AVC | audit2allow -M mypolicy
sudo semodule -i mypolicy.pp

# Install troubleshooting tools
sudo yum install setroubleshoot-server  # RHEL/CentOS
sudo journalctl -t setroubleshoot
```

## Ports

```bash
# List port contexts
sudo semanage port -l | grep http

# Add port
sudo semanage port -a -t http_port_t -p tcp 8080

# Modify port
sudo semanage port -m -t http_port_t -p tcp 8080

# Delete port
sudo semanage port -d -t http_port_t -p tcp 8080
```
"""
        return ScrapedDocument(
            id=self._generate_id("selinux-guide"),
            url="https://selinuxproject.org/",
            title="SELinux Basics Guide",
            content=content,
            source=self.get_source_name(),
            category="security",
            tags=["linux", "selinux", "security", "mac", "rhel"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _audit_guide(self) -> ScrapedDocument:
        """Audit logging guide."""
        content = """# Linux Audit System Guide

## Overview

The Linux Audit system tracks security-relevant events on the system.

## Service Management

```bash
# Status
sudo systemctl status auditd

# Start/stop
sudo systemctl start auditd
sudo systemctl stop auditd

# Configuration
/etc/audit/auditd.conf
/etc/audit/rules.d/
```

## Viewing Audit Logs

```bash
# Search audit log
sudo ausearch -k keyword
sudo ausearch -m USER_LOGIN
sudo ausearch -ua username
sudo ausearch -ts today
sudo ausearch -ts recent

# Generate report
sudo aureport
sudo aureport --summary
sudo aureport --login
sudo aureport --file
sudo aureport --exec
sudo aureport --failed
```

## Audit Rules

```bash
# List current rules
sudo auditctl -l

# Load rules from file
sudo auditctl -R /etc/audit/rules.d/audit.rules

# Delete all rules
sudo auditctl -D
```

### Rule Syntax

```bash
# Watch file
sudo auditctl -w /etc/passwd -p wa -k passwd_changes
# -w = path to watch
# -p = permissions (r=read, w=write, x=execute, a=attribute)
# -k = key for searching

# Watch directory
sudo auditctl -w /etc/ssh/ -p wa -k ssh_config

# System call
sudo auditctl -a always,exit -F arch=b64 -S execve -k commands
```

### Permanent Rules

```bash
# /etc/audit/rules.d/audit.rules

# First rule - delete all
-D

# Buffer size
-b 8192

# Failure mode (0=silent, 1=printk, 2=panic)
-f 1

# Watch passwd file
-w /etc/passwd -p wa -k identity
-w /etc/group -p wa -k identity
-w /etc/shadow -p wa -k identity
-w /etc/sudoers -p wa -k sudoers

# Watch SSH config
-w /etc/ssh/sshd_config -p wa -k sshd_config

# Monitor commands
-a always,exit -F arch=b64 -S execve -k commands

# Monitor network connections
-a always,exit -F arch=b64 -S connect -F a2!=110 -k network

# Lock rules (prevent changes)
-e 2
```

## Common Searches

```bash
# Failed logins
sudo ausearch -m USER_LOGIN --success no

# File access
sudo ausearch -f /etc/passwd

# User actions
sudo ausearch -ua root -ts today

# Commands executed
sudo ausearch -k commands -ts today

# With interpretation
sudo ausearch -i -k passwd_changes
```

## Reports

```bash
# Summary
sudo aureport --summary

# Login report
sudo aureport -l

# Failed events
sudo aureport --failed

# File access
sudo aureport -f

# User report
sudo aureport -u

# Executable report
sudo aureport -x
```
"""
        return ScrapedDocument(
            id=self._generate_id("audit-guide"),
            url="https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/8/html/security_hardening/auditing-the-system_security-hardening",
            title="Linux Audit System Guide",
            content=content,
            source=self.get_source_name(),
            category="security",
            tags=["linux", "audit", "security", "logging"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "medium"}
        )
    
    def _hardening_guide(self) -> ScrapedDocument:
        """System hardening checklist."""
        content = """# Linux System Hardening Checklist

## User Security

```bash
# [ ] Disable root login
sudo passwd -l root

# [ ] Strong password policy
# /etc/security/pwquality.conf
minlen = 12
dcredit = -1
ucredit = -1
lcredit = -1
ocredit = -1

# [ ] Password aging
sudo chage -M 90 -m 7 -W 14 username

# [ ] Remove unused users
sudo userdel username

# [ ] Audit sudo access
sudo cat /etc/sudoers.d/*
```

## SSH Hardening

```bash
# /etc/ssh/sshd_config

PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
MaxSessions 2
ClientAliveInterval 300
ClientAliveCountMax 2
AllowUsers admin deploy
Protocol 2
X11Forwarding no
PermitEmptyPasswords no
```

## Network Security

```bash
# [ ] Enable firewall
sudo ufw enable
sudo systemctl enable firewalld

# [ ] Disable unused services
sudo systemctl disable cups
sudo systemctl disable avahi-daemon

# [ ] Disable IPv6 if not needed
# /etc/sysctl.conf
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1

# [ ] Network parameters
# /etc/sysctl.conf
net.ipv4.ip_forward = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.log_martians = 1
net.ipv4.tcp_syncookies = 1
net.ipv4.icmp_echo_ignore_broadcasts = 1
```

## File System

```bash
# [ ] Set proper permissions
chmod 700 /root
chmod 600 /etc/shadow
chmod 644 /etc/passwd

# [ ] Find world-writable files
find / -perm -0002 -type f 2>/dev/null

# [ ] Find SUID/SGID files
find / -perm /6000 -type f 2>/dev/null

# [ ] Secure mount options
# /etc/fstab
/tmp     tmpfs    defaults,noexec,nosuid,nodev    0 0
/var/tmp none     /tmp     bind                    0 0

# [ ] Remove unused packages
sudo apt autoremove
sudo dnf autoremove
```

## Logging and Auditing

```bash
# [ ] Enable audit daemon
sudo systemctl enable auditd

# [ ] Configure log rotation
# /etc/logrotate.d/

# [ ] Central log collection
# /etc/rsyslog.conf

# [ ] Enable process accounting
sudo apt install acct
sudo systemctl enable acct
```

## Updates

```bash
# [ ] Enable automatic security updates
sudo apt install unattended-upgrades
sudo dpkg-reconfigure unattended-upgrades

# [ ] Regular update schedule
sudo crontab -e
# 0 3 * * * apt update && apt upgrade -y
```

## Kernel Hardening

```bash
# /etc/sysctl.conf

# Disable core dumps
fs.suid_dumpable = 0

# ASLR
kernel.randomize_va_space = 2

# Restrict dmesg
kernel.dmesg_restrict = 1

# Restrict kernel pointer
kernel.kptr_restrict = 2

# Apply changes
sudo sysctl -p
```

## Service Hardening

```bash
# [ ] List running services
systemctl list-units --type=service --state=running

# [ ] Disable unnecessary services
sudo systemctl disable --now bluetooth
sudo systemctl disable --now cups

# [ ] Use systemd security features
# In unit files:
ProtectSystem=strict
ProtectHome=yes
NoNewPrivileges=yes
PrivateTmp=yes
```

## Verification Tools

```bash
# CIS Benchmark check
sudo apt install lynis
sudo lynis audit system

# Rootkit check
sudo apt install rkhunter chkrootkit
sudo rkhunter --check
sudo chkrootkit
```
"""
        return ScrapedDocument(
            id=self._generate_id("hardening-checklist"),
            url="synthetic://hardening-checklist",
            title="Linux System Hardening Checklist",
            content=content,
            source=self.get_source_name(),
            category="security",
            tags=["linux", "security", "hardening", "checklist"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "checklist", "priority": "high"}
        )
    
    def _fail2ban_guide(self) -> ScrapedDocument:
        """fail2ban configuration guide."""
        content = """# fail2ban Configuration Guide

## Overview

fail2ban monitors log files for failed login attempts and bans offending IPs.

## Installation

```bash
# Debian/Ubuntu
sudo apt install fail2ban

# RHEL/CentOS
sudo dnf install fail2ban

# Start service
sudo systemctl enable --now fail2ban
```

## Configuration

```bash
# Don't edit jail.conf directly
# Create local override
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
sudo nano /etc/fail2ban/jail.local
```

### Basic Configuration

```ini
# /etc/fail2ban/jail.local

[DEFAULT]
# Ban duration (seconds, or use 1h, 1d, etc.)
bantime = 1h

# Time window for failures
findtime = 10m

# Max failures before ban
maxretry = 3

# What to ban
banaction = iptables-multiport

# Email notifications
destemail = admin@example.com
sender = fail2ban@example.com
mta = sendmail
action = %(action_mwl)s
```

### SSH Jail

```ini
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
findtime = 600
```

### Web Server Jails

```ini
[nginx-http-auth]
enabled = true
filter = nginx-http-auth
port = http,https
logpath = /var/log/nginx/error.log

[nginx-botsearch]
enabled = true
filter = nginx-botsearch
port = http,https
logpath = /var/log/nginx/access.log

[apache-auth]
enabled = true
port = http,https
logpath = /var/log/apache2/error.log
```

## Commands

```bash
# Status
sudo fail2ban-client status
sudo fail2ban-client status sshd

# List banned IPs
sudo fail2ban-client get sshd banip

# Unban IP
sudo fail2ban-client set sshd unbanip 192.168.1.100
sudo fail2ban-client unban 192.168.1.100

# Ban IP manually
sudo fail2ban-client set sshd banip 192.168.1.100

# Reload configuration
sudo fail2ban-client reload

# Check filter regex
sudo fail2ban-regex /var/log/auth.log /etc/fail2ban/filter.d/sshd.conf
```

## Custom Filter

```ini
# /etc/fail2ban/filter.d/myapp.conf
[Definition]
failregex = ^.* Failed login from <HOST>.*$
            ^.* Invalid password from <HOST>.*$
ignoreregex =
```

## Whitelist IPs

```ini
[DEFAULT]
ignoreip = 127.0.0.1/8 ::1 192.168.1.0/24 10.0.0.0/8
```

## Logging

```bash
# View fail2ban log
sudo tail -f /var/log/fail2ban.log

# Current bans
sudo iptables -L -n | grep f2b
```
"""
        return ScrapedDocument(
            id=self._generate_id("fail2ban-guide"),
            url="https://www.fail2ban.org/",
            title="fail2ban Configuration Guide",
            content=content,
            source=self.get_source_name(),
            category="security",
            tags=["linux", "fail2ban", "security", "brute-force"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _encryption_guide(self) -> ScrapedDocument:
        """Encryption guide."""
        content = """# Linux Encryption Guide

## GPG (GNU Privacy Guard)

### Key Management

```bash
# Generate key pair
gpg --full-generate-key

# List keys
gpg --list-keys
gpg --list-secret-keys

# Export public key
gpg --export -a "Your Name" > public.key
gpg --export --armor keyid > public.key

# Import public key
gpg --import public.key

# Export private key (backup)
gpg --export-secret-keys -a "Your Name" > private.key

# Delete key
gpg --delete-key keyid
gpg --delete-secret-key keyid
```

### File Encryption

```bash
# Encrypt file (with public key)
gpg -e -r "recipient@email.com" file.txt

# Encrypt file (symmetric/password)
gpg -c file.txt

# Decrypt file
gpg -d file.txt.gpg > file.txt
gpg file.txt.gpg

# Sign file
gpg --sign file.txt
gpg --clearsign file.txt      # Readable signature

# Verify signature
gpg --verify file.txt.sig
```

## OpenSSL

### Symmetric Encryption

```bash
# Encrypt with password
openssl enc -aes-256-cbc -salt -pbkdf2 -in file.txt -out file.enc

# Decrypt
openssl enc -aes-256-cbc -d -pbkdf2 -in file.enc -out file.txt

# Base64 encode
openssl base64 -in file.txt -out file.b64
openssl base64 -d -in file.b64 -out file.txt
```

### Hashing

```bash
# Generate hash
openssl dgst -sha256 file.txt
sha256sum file.txt

# Verify hash
sha256sum -c checksums.txt
```

### Certificates

```bash
# Generate self-signed certificate
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \\
    -keyout private.key -out certificate.crt

# Generate CSR
openssl req -new -newkey rsa:2048 -nodes \\
    -keyout private.key -out request.csr

# View certificate
openssl x509 -in certificate.crt -text -noout
```

## LUKS Disk Encryption

### Create Encrypted Volume

```bash
# Format with LUKS
sudo cryptsetup luksFormat /dev/sdb1

# Open encrypted volume
sudo cryptsetup open /dev/sdb1 encrypted_vol

# Create filesystem
sudo mkfs.ext4 /dev/mapper/encrypted_vol

# Mount
sudo mount /dev/mapper/encrypted_vol /mnt/secure

# Close when done
sudo umount /mnt/secure
sudo cryptsetup close encrypted_vol
```

### Key Management

```bash
# Add additional key
sudo cryptsetup luksAddKey /dev/sdb1

# Remove key
sudo cryptsetup luksRemoveKey /dev/sdb1

# Backup header
sudo cryptsetup luksHeaderBackup /dev/sdb1 \\
    --header-backup-file luks-header.bak
```

### Auto-mount at Boot

```bash
# /etc/crypttab
encrypted_vol /dev/sdb1 none luks

# /etc/fstab
/dev/mapper/encrypted_vol /mnt/secure ext4 defaults 0 2
```

## eCryptfs

```bash
# Install
sudo apt install ecryptfs-utils

# Encrypt home directory
sudo ecryptfs-migrate-home -u username

# Mount encrypted directory
mount -t ecryptfs /secret /secret

# Unmount
umount /secret
```

## age (Modern Alternative)

```bash
# Install
sudo apt install age

# Generate key
age-keygen -o key.txt

# Encrypt
age -r age1... file.txt > file.age
age -p file.txt > file.age     # Password

# Decrypt
age -d -i key.txt file.age > file.txt
```
"""
        return ScrapedDocument(
            id=self._generate_id("encryption-guide"),
            url="synthetic://encryption",
            title="Linux Encryption Guide",
            content=content,
            source=self.get_source_name(),
            category="security",
            tags=["linux", "encryption", "gpg", "luks", "security"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _security_scanning_guide(self) -> ScrapedDocument:
        """Security scanning tools guide."""
        content = """# Linux Security Scanning Tools

## Lynis (System Audit)

```bash
# Install
sudo apt install lynis

# Run audit
sudo lynis audit system

# Output to file
sudo lynis audit system --report-file /tmp/report.txt

# Show only warnings
sudo lynis audit system | grep Warning
```

## ClamAV (Antivirus)

```bash
# Install
sudo apt install clamav clamav-daemon

# Update signatures
sudo freshclam

# Scan directory
clamscan -r /home/
clamscan -r --infected /var/www/

# Remove infected files
clamscan -r --remove /path/

# Scan and log
clamscan -r /home/ -l /var/log/clamscan.log
```

## rkhunter (Rootkit Hunter)

```bash
# Install
sudo apt install rkhunter

# Update
sudo rkhunter --update

# Check system
sudo rkhunter --check

# Skip prompts
sudo rkhunter --check --skip-keypress
```

## chkrootkit

```bash
# Install
sudo apt install chkrootkit

# Run check
sudo chkrootkit

# Quiet mode
sudo chkrootkit -q
```

## OpenVAS/GVM (Vulnerability Scanner)

```bash
# Install (varies by distro)
sudo apt install gvm

# Setup
sudo gvm-setup

# Start services
sudo gvm-start

# Access web interface
# https://localhost:9392
```

## Nmap (Network Scanner)

```bash
# Basic scan
nmap hostname

# Service detection
nmap -sV hostname

# OS detection
nmap -O hostname

# All ports
nmap -p- hostname

# Aggressive scan
nmap -A hostname

# Scan network
nmap 192.168.1.0/24

# Output to file
nmap -oN output.txt hostname
nmap -oX output.xml hostname
```

## Nikto (Web Server Scanner)

```bash
# Install
sudo apt install nikto

# Scan web server
nikto -h http://hostname

# Scan HTTPS
nikto -h https://hostname

# Save output
nikto -h hostname -o report.html -Format html
```

## AIDE (File Integrity)

```bash
# Install
sudo apt install aide

# Initialize database
sudo aideinit
sudo mv /var/lib/aide/aide.db.new /var/lib/aide/aide.db

# Check integrity
sudo aide --check

# Update database after changes
sudo aide --update
```

## Regular Security Routine

```bash
# Weekly security check script
#!/bin/bash

echo "=== Security Audit $(date) ==="

# Update security databases
freshclam
rkhunter --update

# Run scans
lynis audit system --quiet
rkhunter --check --skip-keypress
chkrootkit -q

# Check for updates
apt update
apt list --upgradable

# Check listening ports
ss -tlnp

# Check failed logins
grep "Failed password" /var/log/auth.log | tail -20

# Check disk usage
df -h

echo "=== Audit Complete ==="
```
"""
        return ScrapedDocument(
            id=self._generate_id("security-scanning"),
            url="synthetic://security-scanning",
            title="Linux Security Scanning Tools",
            content=content,
            source=self.get_source_name(),
            category="security",
            tags=["linux", "security", "scanning", "audit", "vulnerability"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "medium"}
        )
    
    def _generate_id(self, name: str) -> str:
        """Generate document ID."""
        import hashlib
        return hashlib.md5(f"security-docs:{name}".encode()).hexdigest()[:16]


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate security documentation")
    parser.add_argument("--output-dir", default="data/linux/security-docs")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    
    config = ScraperConfig(output_dir=Path(args.output_dir))
    scraper = SecurityDocsScraper(config)
    
    docs = scraper.scrape()
    scraper.save_documents(docs, "security_docs.jsonl")
