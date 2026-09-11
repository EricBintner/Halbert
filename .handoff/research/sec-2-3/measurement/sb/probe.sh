#!/bin/sh
# Probe harness: run each capability check inside whatever sandbox wraps us.
# Prints PASS/FAIL per probe. Called as: sandbox-exec -f X.sb /bin/sh probe.sh
p() { printf '%-22s %s\n' "$1" "$2"; }

if head -c 40 "$HOME/.ssh/id_ed25519" >/dev/null 2>&1; then p ssh-private-key READABLE; else p ssh-private-key denied; fi
if head -c 8 "$HOME/.local/state/halbert/api-token" >/dev/null 2>&1; then p halbert-api-token READABLE; else p halbert-api-token denied; fi
if ls "$HOME/Library/Application Support/Google/Chrome" >/dev/null 2>&1; then p chrome-profile READABLE; else p chrome-profile denied; fi
if ls "$HOME/Library/Keychains" >/dev/null 2>&1; then p keychain-dir READABLE; else p keychain-dir denied; fi
if echo x > "$HOME/.sandbox_probe_tmp" 2>/dev/null; then p home-write WRITABLE; rm -f "$HOME/.sandbox_probe_tmp"; else p home-write denied; fi
if echo x > "$SBX_WRITABLE/probe" 2>/dev/null; then p writable-path WRITABLE; rm -f "$SBX_WRITABLE/probe"; else p writable-path denied; fi
if (exec 3<>/dev/tcp/1.1.1.1/80) 2>/dev/null; then p tcp-outbound OPEN; else p tcp-outbound denied; fi
if /usr/bin/nc -z -G 2 1.1.1.1 80 >/dev/null 2>&1; then p nc-outbound OPEN; else p nc-outbound denied; fi

# Diagnostics the agent legitimately needs
ps aux >/dev/null 2>&1   && p ps ok || p ps BROKEN
df -h  >/dev/null 2>&1   && p df ok || p df BROKEN
ls /etc >/dev/null 2>&1  && p ls-etc ok || p ls-etc BROKEN
/usr/bin/uptime >/dev/null 2>&1 && p uptime ok || p uptime BROKEN
/usr/sbin/system_profiler SPHardwareDataType >/dev/null 2>&1 && p system_profiler ok || p system_profiler BROKEN
/usr/bin/vm_stat >/dev/null 2>&1 && p vm_stat ok || p vm_stat BROKEN
/bin/cat /etc/hosts >/dev/null 2>&1 && p cat-etc-hosts ok || p cat-etc-hosts BROKEN
/usr/bin/awk 'BEGIN{}' >/dev/null 2>&1 && p awk ok || p awk BROKEN
/usr/bin/python3 -c 'pass' >/dev/null 2>&1 && p python3 ok || p python3 BROKEN
/usr/bin/log show --last 1m --style compact >/dev/null 2>&1 && p log-show ok || p log-show BROKEN
/bin/launchctl list >/dev/null 2>&1 && p launchctl ok || p launchctl BROKEN
