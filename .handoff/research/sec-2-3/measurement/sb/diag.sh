#!/bin/sh
t() { n="$1"; shift; if "$@" >/dev/null 2>&1; then printf '  %-14s ok\n' "$n"; else printf '  %-14s BROKEN\n' "$n"; fi; }
t uname       /usr/bin/uname -a
t sw_vers     /usr/bin/sw_vers
t sysctl      /usr/sbin/sysctl -n hw.ncpu
t ifconfig    /sbin/ifconfig -a
t netstat     /usr/sbin/netstat -rn
t diskutil    /usr/sbin/diskutil list
t du          /usr/bin/du -sh /private/etc
t lsof        /usr/sbin/lsof -p 1
t syslog      /usr/bin/syslog -k Sender kernel
t systemlog   /bin/cat /private/var/log/system.log
t pgrep       /usr/bin/pgrep -l launchd
t sysdiag     /usr/sbin/system_profiler SPSoftwareDataType
t nettop      /usr/bin/nettop -L 1
t iostat      /usr/sbin/iostat -c 1
t hostname    /bin/hostname
t id          /usr/bin/id
t stat        /usr/bin/stat /private/etc/hosts
t grep        /usr/bin/grep -q root /private/etc/passwd
t sed         /usr/bin/sed -n 1p /private/etc/hosts
t perl        /usr/bin/perl -e 'print 1'
t sqlite3     /usr/bin/sqlite3 -version
t openssl     /usr/bin/openssl version
