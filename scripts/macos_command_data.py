# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Halbert-authored macOS command reference content.

Original reference material written for Halbert's RAG corpus, covering the 87
macOS commands previously sourced from CC BY-NC 4.0 third-party pages
(LEG-CRIT-01). Written against the BSD userland and Apple utilities shipped
with macOS 13 Ventura through macOS 15 Sequoia.

Rendered into JSONL by `scripts/generate_macos_command_guides.py`.

Entry schema:
    command   : str            — must match `metadata.command` in the corpus
    tagline   : str            — one-line description
    summary   : str            — a paragraph of orientation
    synopsis  : list[str]      — usage lines
    options   : list[(str,str)]
    examples  : list[(str,str)] — (command line, what it does)
    notes     : list[str]      — macOS-specific behaviour worth knowing
    see_also  : list[str]
    tags      : list[str]
    category  : str            — defaults to "command_reference"
"""

COMMANDS = [
    {
        "command": "awk",
        "tagline": "pattern-directed scanning and text processing",
        "summary": (
            "awk reads input line by line, splits each line into fields, and runs the "
            "program you give it against every line that matches a pattern. macOS ships "
            "the One True Awk (BWK awk), not GNU gawk, so gawk extensions such as "
            "`gensub()`, `asort()`, and `--posix`-only flags are unavailable. For "
            "sysadmin work it is the fastest way to reduce columnar output — `ps`, "
            "`df`, `netstat`, log lines — down to the field you actually want."
        ),
        "synopsis": [
            "awk [-F sepstring] [-v var=value] 'program' [file ...]",
            "awk [-F sepstring] -f progfile [file ...]",
        ],
        "options": [
            ("-F sep", "Set the input field separator; accepts a regex, e.g. `-F'[,:]'`"),
            ("-v var=value", "Assign a variable before the program runs"),
            ("-f progfile", "Read the awk program from a file instead of the command line"),
            ("--version", "Print the awk version (useful to confirm you are on BWK awk, not gawk)"),
        ],
        "examples": [
            ("ps aux | awk '{print $2, $11}'", "Print PID and command from ps output"),
            ("awk -F: '$3 >= 500 {print $1}' /etc/passwd", "Local users with UID 500 or higher"),
            ("df -h | awk 'NR>1 && $5+0 > 80 {print $9, $5}'", "Filesystems over 80% full"),
            ("awk '{sum += $1} END {print sum}' sizes.txt", "Sum the first column"),
            ("awk 'NR % 2 == 0' file.txt", "Print every second line"),
            ("log show --last 1h | awk '/error/ {c++} END {print c+0}'", "Count error lines in the last hour of unified logs"),
        ],
        "notes": [
            "macOS awk is BWK awk. If a script needs gawk features, `brew install gawk` and call `gawk` explicitly rather than assuming `awk` is GNU.",
            "Field `$0` is the whole line; `NF` is the field count; `NR` is the record number. `$NF` is the last field — handy when column position varies.",
            "Numeric comparison against a string field needs a nudge: `$5+0 > 80` forces numeric context on values like `81%`.",
        ],
        "see_also": ["sed", "grep", "cut", "sort"],
        "tags": ["text-processing", "scripting", "fields"],
    },
    {
        "command": "brew",
        "tagline": "Homebrew package manager for macOS",
        "summary": (
            "brew installs, upgrades and removes command-line tools (formulae) and GUI "
            "applications (casks) outside of the App Store. On Apple Silicon it installs "
            "under /opt/homebrew; on Intel under /usr/local. Knowing which prefix a "
            "machine uses is the single most common source of \"command not found\" "
            "confusion after a migration, because a Rosetta shell and a native shell see "
            "different prefixes."
        ),
        "synopsis": [
            "brew install [--cask] formula|cask ...",
            "brew uninstall [--zap] formula|cask",
            "brew update && brew upgrade [formula]",
            "brew list | brew info | brew doctor",
        ],
        "options": [
            ("install", "Install a formula (CLI) or, with `--cask`, an application"),
            ("uninstall [--zap]", "Remove; `--zap` also removes cask preferences and support files"),
            ("update", "Refresh Homebrew itself and the formula definitions"),
            ("upgrade [name]", "Upgrade everything, or just the named package"),
            ("info name", "Show version, dependencies, caveats and install path"),
            ("list --versions", "List installed packages with versions"),
            ("doctor", "Diagnose a broken Homebrew installation"),
            ("cleanup [-n]", "Delete stale downloads and old versions; `-n` previews"),
            ("services list|start|stop", "Manage launchd services installed by formulae"),
            ("--prefix", "Print the Homebrew prefix for this machine"),
        ],
        "examples": [
            ("brew --prefix", "Show whether this is an Apple Silicon (/opt/homebrew) or Intel (/usr/local) install"),
            ("brew install ripgrep jq", "Install two CLI tools"),
            ("brew install --cask visual-studio-code", "Install a GUI application"),
            ("brew upgrade && brew cleanup", "Upgrade everything and reclaim disk space"),
            ("brew services restart postgresql@16", "Restart a Homebrew-managed background service"),
            ("brew list --versions | grep -i python", "Which Pythons are installed via brew"),
            ("brew doctor", "Diagnose PATH, permissions and linkage problems"),
        ],
        "notes": [
            "Homebrew is not an Apple product and is not installed by default. `brew` requires the Command Line Tools; `xcode-select --install` first on a fresh machine.",
            "On Apple Silicon, add `eval \"$(/opt/homebrew/bin/brew shellenv)\"` to your shell profile. A shell started under Rosetta will find the Intel prefix instead and appear to have different packages installed.",
            "`brew services` writes launchd plists into ~/Library/LaunchAgents. Services started this way do not run before login; use a LaunchDaemon for that.",
            "`brew cleanup` can free tens of gigabytes on a long-lived machine — check with `brew cleanup -n` first.",
        ],
        "see_also": ["pkgutil", "installer", "launchctl", "xcode-select"],
        "tags": ["package-management", "homebrew", "software"],
        "category": "package_management",
    },
    {
        "command": "caffeinate",
        "tagline": "prevent the system from sleeping",
        "summary": (
            "caffeinate holds a power assertion so the Mac stays awake. With no arguments "
            "it blocks idle sleep until you interrupt it; given a command it holds the "
            "assertion only for as long as that command runs, which is the correct way to "
            "protect a long build, rsync or backup from a sleep-induced failure."
        ),
        "synopsis": [
            "caffeinate [-dismu] [-t timeout] [command [args ...]]",
        ],
        "options": [
            ("-d", "Prevent the display from sleeping"),
            ("-i", "Prevent idle system sleep"),
            ("-m", "Prevent disks from idle-sleeping"),
            ("-s", "Prevent system sleep while on AC power"),
            ("-u", "Declare user activity — wakes the display, honours `-t`"),
            ("-t seconds", "Hold the assertion for this many seconds then exit"),
            ("-w pid", "Hold the assertion until the given process exits"),
        ],
        "examples": [
            ("caffeinate -i make -j8", "Keep the machine awake for the duration of a build"),
            ("caffeinate -dims", "Block display, idle, disk and system sleep until Ctrl-C"),
            ("caffeinate -t 3600", "Stay awake for one hour"),
            ("caffeinate -w $(pgrep -x rsync)", "Stay awake until the running rsync finishes"),
            ("caffeinate -u -t 1", "Wake the display as if the user touched the keyboard"),
        ],
        "notes": [
            "caffeinate cannot defeat a closed lid on most Macs — clamshell sleep is enforced below the assertion layer unless an external display and power are attached.",
            "Inspect who else is holding assertions with `pmset -g assertions`; a stuck app there is the usual reason a Mac \"won't sleep\".",
            "Wrapping a command (`caffeinate -i cmd`) is safer than a bare `caffeinate &` because the assertion is released automatically when the job ends.",
        ],
        "see_also": ["pmset", "launchctl", "log"],
        "tags": ["power", "sleep", "energy"],
        "category": "power_management",
    },
    {
        "command": "cat",
        "tagline": "concatenate and print files",
        "summary": (
            "cat copies its input to standard output. It is used to view small files, to "
            "join files together, and — with a here-document — to write files from a "
            "script. macOS ships the BSD version, whose flags differ from GNU coreutils: "
            "there is no `-A`, and `-n`/`-b` behave subtly differently."
        ),
        "synopsis": [
            "cat [-benstuv] [file ...]",
            "cat > file <<'EOF' ... EOF",
        ],
        "options": [
            ("-n", "Number every output line"),
            ("-b", "Number only non-blank lines"),
            ("-s", "Squeeze runs of blank lines into one"),
            ("-e", "Show line endings as `$` (implies -v)"),
            ("-t", "Show tabs as `^I` (implies -v)"),
            ("-v", "Show non-printing characters visibly"),
            ("-u", "Unbuffered output — useful when piping a live file"),
        ],
        "examples": [
            ("cat /etc/hosts", "Print a file"),
            ("cat part1.txt part2.txt > whole.txt", "Join two files into one"),
            ("cat -n script.sh", "Print with line numbers to match an error message"),
            ("cat -v suspicious.txt | head", "Reveal stray control characters or CRLF endings"),
            ("cat > ~/notes.txt <<'EOF'\nfirst line\nEOF", "Write a file from a shell script without an editor"),
            ("sudo cat /var/log/install.log | tail -50", "Read a root-owned log"),
        ],
        "notes": [
            "`cat file | grep x` is a wasted process — `grep x file` does the same. Reviewers call this a Useless Use of Cat.",
            "For files that may be large, prefer `less`; `cat` on a multi-gigabyte log will flood the terminal.",
            "BSD cat has no `-A`. The closest equivalent is `cat -vet`.",
        ],
        "see_also": ["less", "head", "tail", "pbcopy"],
        "tags": ["files", "text", "io"],
    },
    {
        "command": "cd",
        "tagline": "change the working directory",
        "summary": (
            "cd is a shell builtin, not a program — it has to be, because a child process "
            "cannot change its parent's working directory. In zsh (the macOS default "
            "shell since Catalina) it also drives the directory stack, so `cd -` returns "
            "to the previous directory and `cd -2` reaches further back."
        ),
        "synopsis": [
            "cd [-L|-P] [directory]",
            "cd -",
        ],
        "options": [
            ("(no argument)", "Change to $HOME"),
            ("-", "Change to the previous directory ($OLDPWD)"),
            ("-L", "Follow symlinks logically — keep the symlinked path in $PWD (default)"),
            ("-P", "Resolve symlinks physically — $PWD becomes the real path"),
        ],
        "examples": [
            ("cd ~/Documents", "Change into a directory under your home"),
            ("cd -", "Jump back to where you just were"),
            ("cd ..", "Move up one level"),
            ("cd -P /tmp", "Enter /tmp with symlinks resolved (on macOS /tmp is a symlink to /private/tmp)"),
            ("cd \"$(dirname \"$0\")\"", "In a script, move to the script's own directory"),
        ],
        "notes": [
            "`which cd` finds nothing useful because cd is a builtin; use `type cd`.",
            "On macOS /tmp, /var and /etc are symlinks into /private. `cd /etc && pwd` prints /etc, but `cd -P /etc && pwd` prints /private/etc — this trips up scripts that compare paths.",
            "A `cd` inside a subshell or a pipeline does not affect the parent shell. Use `cd dir && cmd` rather than `(cd dir; cmd)` when the change should persist for later commands.",
            "Directories under ~/Documents, ~/Desktop and ~/Downloads are TCC-protected: a script run from an unapproved terminal may get \"Operation not permitted\" even as your own user.",
        ],
        "see_also": ["pwd", "ls", "find"],
        "tags": ["shell", "navigation", "builtin"],
    },
    {
        "command": "chmod",
        "tagline": "change file mode bits and ACLs",
        "summary": (
            "chmod sets permission bits — read, write, execute for owner, group and others "
            "— either numerically (755) or symbolically (u+x). On macOS it also manages "
            "POSIX.1e ACLs, which HFS+/APFS supports and which override the classic mode "
            "bits. An unexpected `+` at the end of `ls -l` output means an ACL is present "
            "and the mode bits alone are not telling you the whole story."
        ),
        "synopsis": [
            "chmod [-fhv] [-R [-H|-L|-P]] mode file ...",
            "chmod [-R] +a|-a|=a# \"user:name allow|deny perms\" file",
        ],
        "options": [
            ("-R", "Recurse into directories"),
            ("-h", "Change the symlink itself rather than its target"),
            ("-v", "Verbose — report each change"),
            ("-f", "Suppress error messages"),
            ("+a \"...\"", "Append an ACL entry"),
            ("-a \"...\"", "Remove a matching ACL entry"),
            ("-N", "Strip all ACLs from the file"),
            ("-E", "Read ACLs from standard input"),
        ],
        "examples": [
            ("chmod 755 script.sh", "Owner may write; everyone may read and execute"),
            ("chmod u+x,go-w script.sh", "Add execute for the owner, drop write for group and others"),
            ("chmod -R 750 ~/private", "Recursively restrict a tree to owner and group"),
            ("chmod 600 ~/.ssh/id_ed25519", "The permissions ssh insists on for a private key"),
            ("chmod +a \"staff allow read,execute\" /Users/Shared/tools", "Grant a group access via ACL"),
            ("chmod -N /Users/Shared/tools", "Remove all ACLs, leaving only the mode bits"),
            ("ls -le /Users/Shared", "Show mode bits and the ACL entries behind the trailing +"),
        ],
        "notes": [
            "A trailing `+` in `ls -l` means an ACL exists. Read it with `ls -le`; mode bits alone can be misleading.",
            "chmod cannot alter files protected by System Integrity Protection (/System, /usr except /usr/local, /bin, /sbin) even as root. `csrutil status` tells you whether SIP is on.",
            "Directories need execute (`x`) to be traversed, not just read. 644 on a directory makes it unusable.",
            "Copying with `cp -p` or `ditto` preserves modes; a plain `cp` applies your umask instead.",
        ],
        "see_also": ["chown", "ls", "ditto", "csrutil"],
        "tags": ["permissions", "security", "acl"],
        "category": "security",
    },
    {
        "command": "chown",
        "tagline": "change file owner and group",
        "summary": (
            "chown reassigns the user and/or group that owns a file. Only root may give a "
            "file away to another user, so in practice it is a sudo command. It is the "
            "standard fix after copying files out of a Time Machine backup, an external "
            "drive, or another Mac, where the numeric UIDs may not match the local user."
        ),
        "synopsis": [
            "chown [-fhv] [-R [-H|-L|-P]] owner[:group] file ...",
            "chown [-R] :group file ...",
        ],
        "options": [
            ("-R", "Recurse into directories"),
            ("-h", "Change the symlink itself, not its target"),
            ("-v", "Report each change"),
            ("-f", "Do not report failures"),
            ("-L", "With -R, follow all symlinks encountered"),
            ("-P", "With -R, never follow symlinks (default)"),
        ],
        "examples": [
            ("sudo chown $(whoami) file.txt", "Take ownership of a file"),
            ("sudo chown -R $(whoami):staff ~/Restored", "Reclaim a restored folder for your account"),
            ("sudo chown root:wheel /usr/local/bin/helper", "Give a helper binary root ownership"),
            ("sudo chown :admin shared.txt", "Change only the group"),
            ("ls -ln file.txt", "Show numeric UID/GID — the mismatch that usually motivates chown"),
        ],
        "notes": [
            "macOS user accounts are normally in the `staff` group, not a per-user group as on Linux. `$(whoami):staff` is the usual target.",
            "Files restored from another Mac often carry that machine's UID. `ls -ln` shows a bare number instead of a name when no local account matches.",
            "If the volume is mounted with ownership disabled, chown silently has no effect. Check with `mount` or re-enable via Finder's Get Info → \"Ignore ownership on this volume\".",
            "chown clears setuid and setgid bits on the file as a security measure — reapply with chmod if the binary needs them.",
        ],
        "see_also": ["chmod", "ls", "id", "diskutil"],
        "tags": ["permissions", "ownership", "security"],
        "category": "security",
    },
    {
        "command": "codesign",
        "tagline": "create, verify and inspect code signatures",
        "summary": (
            "codesign signs binaries, bundles and installer components with a Developer ID "
            "or ad-hoc identity, and verifies existing signatures. On Apple Silicon every "
            "executable must carry at least an ad-hoc signature to run at all, which makes "
            "codesign part of ordinary troubleshooting rather than a release-only tool."
        ),
        "synopsis": [
            "codesign -s identity [-f] [--options runtime] [--entitlements file] path",
            "codesign -dv [--verbose=4] [--entitlements -] path",
            "codesign --verify [--deep] [--strict] path",
        ],
        "options": [
            ("-s identity", "Sign with this identity; `-s -` means ad-hoc"),
            ("-f", "Replace an existing signature"),
            ("-dv --verbose=4", "Display signature details: identifier, TeamID, flags, hashes"),
            ("--verify --deep --strict", "Verify the signature, including nested code"),
            ("--options runtime", "Enable the hardened runtime (required for notarization)"),
            ("--entitlements file", "Sign with the entitlements in this plist"),
            ("--entitlements -", "With -d, print the embedded entitlements"),
            ("--remove-signature", "Strip the signature entirely"),
            ("--timestamp", "Include a secure timestamp (required for notarization)"),
        ],
        "examples": [
            ("codesign -dv --verbose=4 /Applications/Foo.app", "Inspect an app's signature, TeamID and runtime flags"),
            ("codesign --verify --deep --strict /Applications/Foo.app", "Verify a bundle and everything nested inside it"),
            ("codesign -d --entitlements - /Applications/Foo.app", "Dump the entitlements an app was signed with"),
            ("codesign -f -s - ./mybinary", "Ad-hoc sign a locally built binary so it runs on Apple Silicon"),
            ("codesign -f -s \"Developer ID Application: Name (TEAMID)\" --options runtime --timestamp Foo.app", "Sign for distribution with the hardened runtime"),
            ("security find-identity -v -p codesigning", "List the signing identities available in the keychain"),
        ],
        "notes": [
            "\"code has no resources but signature indicates they must be present\" almost always means the bundle was modified after signing — re-sign rather than patching.",
            "Signing must happen inside-out: frameworks and helpers first, the outer .app last. `--deep` signing is discouraged by Apple for release builds.",
            "Ad-hoc signatures (`-s -`) satisfy the Apple Silicon load requirement but not Gatekeeper. Distribution needs a Developer ID plus notarization.",
            "codesign verifies; `spctl -a -vv` is what actually predicts whether Gatekeeper will let the app launch.",
        ],
        "see_also": ["spctl", "security", "xattr", "pkgutil"],
        "tags": ["code-signing", "security", "notarization", "gatekeeper"],
        "category": "security",
    },
    {
        "command": "cp",
        "tagline": "copy files and directories",
        "summary": (
            "cp copies files. The BSD version on macOS differs from GNU cp in ways that "
            "matter: `-R` rather than `-r` is the documented recursive flag, trailing "
            "slashes on the source change the result, and extended attributes and resource "
            "forks are only preserved with `-p` (or by using ditto). For anything "
            "involving macOS metadata, ditto or rsync is the safer tool."
        ),
        "synopsis": [
            "cp [-R] [-afinpvX] source ... target",
        ],
        "options": [
            ("-R", "Copy directories recursively"),
            ("-p", "Preserve mode, timestamps, ownership where permitted, and ACLs/xattrs"),
            ("-a", "Archive mode — equivalent to -pRP"),
            ("-i", "Prompt before overwriting"),
            ("-n", "Never overwrite an existing file"),
            ("-f", "Force — remove an existing destination and try again"),
            ("-v", "Print each file as it is copied"),
            ("-c", "Clone the file with APFS copy-on-write when possible"),
            ("-X", "Do not copy extended attributes or resource forks"),
        ],
        "examples": [
            ("cp report.txt report.bak", "Copy a single file"),
            ("cp -R ~/Projects/site ~/Backups/", "Copy a directory tree"),
            ("cp -pv config.yml config.yml.orig", "Copy preserving timestamps, showing what happened"),
            ("cp -c huge.dmg copy.dmg", "APFS clone — instant, uses no extra space until one copy changes"),
            ("cp -n *.jpg ~/Pictures/", "Copy without clobbering anything already there"),
        ],
        "notes": [
            "`cp -R dir target` and `cp -R dir/ target` differ: with the trailing slash the *contents* are copied, without it the directory itself is.",
            "Plain cp drops extended attributes, Finder tags and resource forks. Use `cp -p`, `ditto`, or `rsync -aX` when metadata matters.",
            "On APFS, `cp -c` creates a copy-on-write clone: it completes instantly and consumes no additional space until one side is modified.",
            "cp will not copy into SIP-protected locations even under sudo.",
        ],
        "see_also": ["ditto", "mv", "tar", "rm"],
        "tags": ["files", "copy", "apfs"],
    },
    {
        "command": "csrutil",
        "tagline": "configure System Integrity Protection",
        "summary": (
            "csrutil reports and changes the state of System Integrity Protection, the "
            "kernel-enforced policy that stops even root from modifying system files, "
            "loading unsigned kexts, or attaching a debugger to Apple binaries. Status can "
            "be read from a normal boot; changing it requires booting into recoveryOS, by "
            "design — a compromised running system must not be able to disable its own "
            "protection."
        ),
        "synopsis": [
            "csrutil status",
            "csrutil enable | disable            # recoveryOS only",
            "csrutil authenticated-root status|disable   # recoveryOS only",
        ],
        "options": [
            ("status", "Print whether SIP is enabled, and which protections are off"),
            ("enable", "Re-enable SIP (recoveryOS only)"),
            ("disable", "Disable SIP (recoveryOS only)"),
            ("authenticated-root status", "Report whether the signed system volume seal is enforced"),
            ("clear", "Reset SIP configuration to the default (recoveryOS only)"),
        ],
        "examples": [
            ("csrutil status", "Check SIP from a normal boot"),
            ("csrutil authenticated-root status", "Check whether the sealed system volume is intact"),
            ("csrutil enable", "Re-enable SIP after maintenance, from recoveryOS"),
        ],
        "notes": [
            "To reach recoveryOS: Apple Silicon — shut down, then press and hold the power button until \"Loading startup options\"; Intel — restart holding Command-R. Then open Terminal from the Utilities menu.",
            "Disabling SIP weakens the machine substantially and can block Apple Pay, some DRM playback, and enterprise compliance checks. Re-enable it as soon as the task is done.",
            "\"unknown (Custom Configuration)\" means some protections were selectively disabled — run `csrutil status` in recoveryOS for the itemised list.",
            "Since Big Sur the system volume is a sealed, cryptographically signed snapshot. Modifying it needs `csrutil authenticated-root disable` as well as SIP off, and breaks the seal until the volume is re-sealed.",
        ],
        "see_also": ["spctl", "codesign", "diskutil", "sw_vers"],
        "tags": ["sip", "security", "recovery", "system-integrity"],
        "category": "security",
    },
    {
        "command": "curl",
        "tagline": "transfer data from or to a server",
        "summary": (
            "curl speaks HTTP(S), FTP, SFTP and a dozen other protocols from the command "
            "line. It ships with macOS and, since Monterey, is built against Apple's own "
            "TLS stack, so it trusts the System keychain — which is why a certificate that "
            "works in Safari also works in curl, and why a corporate MITM proxy certificate "
            "installed in the keychain is picked up automatically."
        ),
        "synopsis": [
            "curl [options] url ...",
            "curl -X METHOD -H 'Header: value' -d 'body' url",
        ],
        "options": [
            ("-o file / -O", "Write to a named file / to the remote filename"),
            ("-L", "Follow redirects"),
            ("-I", "Fetch headers only (HEAD)"),
            ("-s / -sS", "Silent / silent but still show errors"),
            ("-f", "Fail with a non-zero exit status on HTTP errors instead of printing the error page"),
            ("-H 'K: V'", "Add a request header (repeatable)"),
            ("-d data / --data-binary", "Send a request body (implies POST)"),
            ("-X METHOD", "Set the HTTP method explicitly"),
            ("-u user:pass", "HTTP basic authentication"),
            ("-k", "Skip TLS certificate verification — diagnostics only"),
            ("-w '%{http_code}'", "Print selected transfer variables when done"),
            ("--connect-timeout / --max-time", "Bound connection setup / the whole transfer"),
        ],
        "examples": [
            ("curl -fsSL https://example.com/install.sh -o install.sh", "Download a script safely, failing loudly on HTTP errors"),
            ("curl -I https://example.com", "Inspect response headers and status without the body"),
            ("curl -s -w '%{http_code}\\n' -o /dev/null https://example.com", "Print just the status code"),
            ("curl -H 'Authorization: Bearer $TOKEN' -H 'Content-Type: application/json' -d '{\"a\":1}' https://api.example.com/v1/items", "POST JSON with an auth header"),
            ("curl -v https://internal.example.com 2>&1 | grep -i 'issuer\\|subject'", "Diagnose which certificate a TLS endpoint presents"),
            ("curl --retry 3 --max-time 60 -O https://example.com/big.tar.gz", "Download with retries and a hard time limit"),
        ],
        "notes": [
            "Prefer `-fsSL` for scripted downloads: without `-f`, curl exits 0 and writes an HTML error page to your file.",
            "macOS curl uses the System and login keychains for trust. A proxy certificate added via Keychain Access is honoured with no extra flags; `-k` should never be the permanent fix.",
            "Piping a downloaded script straight into a shell executes whatever the server returns. Download, read, then run.",
            "For a quick check of an interface-specific route, `--interface en0` forces the request out of a chosen NIC.",
        ],
        "see_also": ["dig", "ping", "netstat", "security"],
        "tags": ["network", "http", "download", "tls"],
        "category": "networking",
    },
    {
        "command": "cut",
        "tagline": "extract selected fields or character ranges from each line",
        "summary": (
            "cut slices each input line by byte, character or delimiter-separated field. "
            "It is the simplest tool for pulling one column out of structured text, and "
            "when it is not enough — because fields are separated by runs of whitespace, "
            "or you need reordering — awk is the next step up."
        ),
        "synopsis": [
            "cut -f list [-d delim] [-s] [file ...]",
            "cut -c list [file ...]",
            "cut -b list [file ...]",
        ],
        "options": [
            ("-f list", "Select fields, e.g. `1`, `1,3`, `2-`, `-3`"),
            ("-d delim", "Field delimiter — a single character, default TAB"),
            ("-c list", "Select character positions"),
            ("-b list", "Select byte positions"),
            ("-s", "Suppress lines that contain no delimiter"),
            ("-n", "With -b, do not split multibyte characters"),
        ],
        "examples": [
            ("cut -d: -f1 /etc/passwd", "List usernames"),
            ("cut -d, -f1,3 data.csv", "Take the first and third CSV columns"),
            ("cut -c1-8 log.txt", "Take the first eight characters of each line (a timestamp prefix)"),
            ("who | cut -d' ' -f1 | sort -u", "Distinct logged-in users"),
            ("cut -d: -f1,7 /etc/passwd | grep -v false", "Users with a real login shell"),
        ],
        "notes": [
            "cut's delimiter is exactly one character. Columns separated by variable whitespace (`ps`, `df`) need `awk '{print $2}'` or a `tr -s ' '` first.",
            "There is no way to reorder fields: `cut -f3,1` still prints field 1 then field 3. Use awk for reordering.",
            "BSD cut has no `--complement`; invert selections with awk instead.",
        ],
        "see_also": ["awk", "sed", "tr", "sort"],
        "tags": ["text-processing", "fields", "columns"],
    },
    {
        "command": "defaults",
        "tagline": "read and write macOS user defaults (preferences)",
        "summary": (
            "defaults is the command-line interface to the preferences system that backs "
            "every .plist under ~/Library/Preferences and /Library/Preferences. It reads, "
            "writes and deletes keys in a domain, where a domain is usually an app's "
            "bundle identifier. It is how you script settings that have no UI, and how you "
            "reset an application whose preferences have become corrupt."
        ),
        "synopsis": [
            "defaults read [domain [key]]",
            "defaults write domain key [-type] value",
            "defaults delete domain [key]",
            "defaults domains | defaults find word",
        ],
        "options": [
            ("read domain [key]", "Print a whole domain or one key"),
            ("read-type domain key", "Report the value's type"),
            ("write domain key value", "Set a value (string unless a type flag is given)"),
            ("-bool true|false", "Write a boolean"),
            ("-int N / -float N", "Write a number"),
            ("-array v1 v2 / -dict k v", "Write a collection"),
            ("delete domain [key]", "Remove a key, or the entire domain"),
            ("domains", "List every domain present"),
            ("find word", "Search all domains for a key, value or domain matching a word"),
            ("-currentHost / -host name", "Operate on the per-host preference store"),
            ("export domain path", "Dump a domain to a plist file"),
        ],
        "examples": [
            ("defaults read com.apple.finder", "Dump every Finder preference"),
            ("defaults write com.apple.finder AppleShowAllFiles -bool true && killall Finder", "Show hidden files in Finder"),
            ("defaults write com.apple.screencapture location ~/Screenshots", "Change where screenshots are saved"),
            ("defaults write NSGlobalDomain KeyRepeat -int 2", "Speed up key repeat system-wide"),
            ("defaults delete com.example.app", "Reset a misbehaving app's preferences entirely"),
            ("defaults find autohide", "Find which domains have a key mentioning autohide"),
            ("sudo defaults write /Library/Preferences/com.apple.loginwindow GuestEnabled -bool false", "Disable the guest account (system domain)"),
        ],
        "notes": [
            "cfprefsd caches preferences. An app that is running may overwrite your change on quit — quit the app first, or `killall cfprefsd` after writing.",
            "Domains for system-wide settings live in /Library/Preferences and need sudo plus a full path rather than a bare bundle id.",
            "`defaults write` with no type flag stores a string. Writing `-bool true` and writing `true` are not the same, and apps that expect a boolean will ignore the string.",
            "Sandboxed apps keep preferences inside their container: ~/Library/Containers/<bundle-id>/Data/Library/Preferences.",
            "Since macOS 12, `defaults read` on a domain you do not own may return nothing rather than an error, thanks to preference sandboxing.",
        ],
        "see_also": ["plutil", "pkgutil", "launchctl", "open"],
        "tags": ["preferences", "plist", "configuration"],
        "category": "system_admin",
    },
    {
        "command": "df",
        "tagline": "report filesystem disk space usage",
        "summary": (
            "df shows how much space each mounted filesystem has. On APFS the output "
            "surprises people: volumes in the same container share free space, so several "
            "volumes each report the same large \"Available\" figure. Local Time Machine "
            "snapshots also occupy space that df counts as used but Finder may not show."
        ),
        "synopsis": [
            "df [-h|-H|-k|-m|-g] [-i] [-l] [-T type] [file|filesystem ...]",
        ],
        "options": [
            ("-h", "Human-readable sizes in powers of 1024"),
            ("-H", "Human-readable in powers of 1000, matching Finder"),
            ("-k / -m / -g", "Report in kilobytes / megabytes / gigabytes"),
            ("-i", "Also show inode usage"),
            ("-l", "Local filesystems only — skips network mounts that may hang"),
            ("-T type", "Restrict to filesystems of a given type, e.g. `-T apfs`"),
            ("-Y", "Include APFS snapshot and purgeable detail (macOS 11+)"),
        ],
        "examples": [
            ("df -h", "Human-readable usage for every mount"),
            ("df -h /", "Usage for the volume holding the root filesystem"),
            ("df -hl", "Skip network mounts — avoids a hang when a server is unreachable"),
            ("df -h | awk 'NR>1 && $5+0 > 85 {print $9, $5}'", "Volumes over 85% full"),
            ("df -h .", "Which volume the current directory lives on, and its free space"),
        ],
        "notes": [
            "APFS volumes in one container share free space. Four volumes each reporting 200 GB free means 200 GB total, not 800 GB.",
            "Space that df calls used may be reclaimable local Time Machine snapshots — list them with `tmutil listlocalsnapshots /` and delete with `tmutil deletelocalsnapshots`.",
            "Finder reports GB in powers of 1000; `df -H` matches Finder, `df -h` matches most other Unix tooling.",
            "df measures the filesystem; `du` measures a directory tree. They legitimately disagree when files are deleted but still held open by a process.",
        ],
        "see_also": ["du", "diskutil", "tmutil", "mount"],
        "tags": ["storage", "disk", "filesystem", "apfs"],
        "category": "storage",
    },
    {
        "command": "diff",
        "tagline": "compare files line by line",
        "summary": (
            "diff reports what would have to change to turn the first file into the "
            "second. macOS ships the BSD/Apple version, which supports unified output "
            "(`-u`) and recursive directory comparison but not every GNU extension. In "
            "practice it is used to compare a configuration file with its distributed "
            "default, or two directory trees after a migration."
        ),
        "synopsis": [
            "diff [-u|-c|-y] [-iwbB] [-r] file1 file2",
            "diff -r dir1 dir2",
        ],
        "options": [
            ("-u", "Unified format — the diff style used by patch and version control"),
            ("-c", "Context format"),
            ("-y", "Side-by-side output"),
            ("-r", "Recursively compare directories"),
            ("-q", "Report only whether files differ"),
            ("-i", "Ignore case"),
            ("-w / -b", "Ignore all whitespace / ignore whitespace amount"),
            ("-B", "Ignore blank lines"),
            ("-N", "With -r, treat absent files as empty"),
            ("-x pattern", "Exclude files matching a pattern"),
        ],
        "examples": [
            ("diff -u old.conf new.conf", "Unified diff of two config files"),
            ("diff -rq ~/site ~/site.bak", "List which files differ between two trees, without the contents"),
            ("diff -u <(sort a.txt) <(sort b.txt)", "Compare two files ignoring line order"),
            ("diff -y --suppress-common-lines a.txt b.txt", "Side-by-side, differences only"),
            ("diff -u file.orig file > fix.patch", "Produce a patch file"),
        ],
        "notes": [
            "Exit status is meaningful: 0 = identical, 1 = differences, >1 = error. Scripts should test for 1 specifically.",
            "Process substitution (`<(cmd)`) works in zsh and bash on macOS and is the neat way to diff command output rather than files.",
            "For binary files diff only says \"binary files differ\"; use `cmp -l` for byte offsets.",
            "FileMerge (`opendiff`) ships with Xcode and gives a graphical three-way merge from the same command line.",
        ],
        "see_also": ["sort", "cmp", "grep", "sed"],
        "tags": ["text-processing", "compare", "patch"],
    },
    {
        "command": "dig",
        "tagline": "DNS lookup utility",
        "summary": (
            "dig queries DNS servers directly and prints the full response. It bypasses "
            "the macOS resolver cache and mDNSResponder entirely, which makes it the right "
            "tool for \"is this a DNS problem or a caching problem?\" — compare `dig` "
            "against `dscacheutil -q host`, which does go through the system resolver."
        ),
        "synopsis": [
            "dig [@server] name [type] [+options]",
            "dig -x address",
        ],
        "options": [
            ("@server", "Query this nameserver instead of the system default"),
            ("type", "Record type: A, AAAA, MX, TXT, NS, CNAME, SOA, SRV, ANY"),
            ("-x addr", "Reverse lookup for an IP address"),
            ("+short", "Print just the answer"),
            ("+trace", "Trace delegation from the root servers down"),
            ("+noall +answer", "Show only the answer section"),
            ("+tcp", "Use TCP instead of UDP"),
            ("+dnssec", "Request DNSSEC records"),
            ("+time=N +tries=N", "Timeout and retry control"),
        ],
        "examples": [
            ("dig example.com +short", "Just the A records"),
            ("dig @1.1.1.1 example.com", "Ask a specific resolver — bypasses the local network's DNS"),
            ("dig MX example.com +short", "Mail exchangers"),
            ("dig -x 93.184.216.34 +short", "Reverse lookup"),
            ("dig +trace example.com", "Follow the delegation chain to find where resolution breaks"),
            ("dig TXT _dmarc.example.com +short", "Read a DMARC policy record"),
        ],
        "notes": [
            "dig does not use /etc/resolv.conf the way you might expect on macOS: the system resolver configuration is managed by configd and is visible via `scutil --dns`.",
            "dig ignores /etc/hosts. If a name resolves in the browser but not in dig, check /etc/hosts and the search domains from `scutil --dns`.",
            "To test what applications will actually get, use `dscacheutil -q host -a name hostname`, which consults the system resolver and cache.",
            "Flush the resolver cache after a DNS change: `sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder`.",
        ],
        "see_also": ["scutil", "dscacheutil", "ping", "networksetup"],
        "tags": ["network", "dns", "diagnostics"],
        "category": "networking",
    },
    {
        "command": "diskutil",
        "tagline": "manage disks, volumes and APFS containers",
        "summary": (
            "diskutil is the command-line half of Disk Utility. It lists devices, mounts "
            "and unmounts, erases and partitions, and manages APFS containers, volumes, "
            "snapshots and encryption. Every destructive subcommand takes a device "
            "identifier such as disk3s2 — read `diskutil list` carefully before typing "
            "one, because these operations do not ask twice."
        ),
        "synopsis": [
            "diskutil list [device]",
            "diskutil info [-plist] device",
            "diskutil mount|unmount|eject device",
            "diskutil apfs subcommand ...",
            "diskutil verifyVolume|repairVolume device",
        ],
        "options": [
            ("list", "Show all disks, partitions and APFS volumes with identifiers"),
            ("info device", "Detailed information about one device or volume"),
            ("mount / unmount / unmountDisk", "Mount or unmount a volume, or a whole disk"),
            ("eject device", "Unmount and power down removable media"),
            ("apfs list", "Show APFS containers and the volumes inside them"),
            ("apfs addVolume container APFS name", "Add a volume to an existing container"),
            ("apfs deleteVolume device", "Delete an APFS volume"),
            ("apfs resizeContainer device size", "Grow or shrink a container"),
            ("eraseDisk fs name device", "Erase and reformat an entire disk"),
            ("verifyVolume / repairVolume", "Check or repair a filesystem"),
            ("apfs unlockVolume / lockVolume", "Unlock or lock a FileVault-encrypted volume"),
            ("secureErase level device", "Multi-pass erase (rotational media only)"),
        ],
        "examples": [
            ("diskutil list", "Identify every disk and its device node before doing anything else"),
            ("diskutil info disk3s2", "Type, size, mount point, filesystem and UUID for one volume"),
            ("diskutil apfs list", "Container layout, roles and space sharing"),
            ("diskutil unmountDisk /dev/disk4", "Unmount every volume on an external drive"),
            ("diskutil eraseDisk APFS \"Backup\" /dev/disk4", "Erase an external drive as APFS"),
            ("diskutil apfs addVolume disk1 APFS Scratch", "Add a volume that shares the container's free space"),
            ("diskutil verifyVolume /", "Verify the boot volume (read-only check, safe while running)"),
        ],
        "notes": [
            "Device identifiers are not stable across reboots or re-plugging. Always re-run `diskutil list` immediately before a destructive command.",
            "The startup volume cannot be repaired while booted from it — `repairVolume /` will refuse. Boot into recoveryOS and run Disk Utility or `diskutil` from there.",
            "APFS volumes in one container share free space, so \"resize\" is usually unnecessary — add or delete volumes instead.",
            "`diskutil secureErase` is meaningless on SSDs and refuses to run on many of them; for flash storage, encryption plus erasing the key (which is what erasing a FileVault volume does) is the effective method.",
            "`diskutil apfs listSnapshots /` reveals Time Machine local snapshots that are consuming space.",
        ],
        "see_also": ["df", "hdiutil", "tmutil", "csrutil"],
        "tags": ["storage", "disk", "apfs", "partition"],
        "category": "storage",
    },
    {
        "command": "ditto",
        "tagline": "copy files and directories preserving macOS metadata",
        "summary": (
            "ditto copies hierarchies while keeping the metadata plain cp drops: extended "
            "attributes, resource forks, ACLs, Finder flags and, with `--rsrc`/`--extattr` "
            "defaults, everything a bundle needs to remain launchable. It is Apple's own "
            "tool for duplicating .app bundles, and it can also create or expand archives."
        ),
        "synopsis": [
            "ditto [-V] [--rsrc] [--extattr] [--acl] source ... destination",
            "ditto -c -k [--sequesterRsrc] [--keepParent] source archive.zip",
            "ditto -x -k archive.zip destination",
        ],
        "options": [
            ("-V", "Verbose — list every file copied"),
            ("-v", "Print one line per directory copied"),
            ("--rsrc / --norsrc", "Preserve / drop resource forks (preserve is the default)"),
            ("--extattr / --noextattr", "Preserve / drop extended attributes"),
            ("--acl / --noacl", "Preserve / drop ACLs"),
            ("-c -k src archive.zip", "Create a PKZip archive"),
            ("-x -k archive.zip dest", "Extract a PKZip archive"),
            ("--keepParent", "Include the source directory itself in the archive"),
            ("--sequesterRsrc", "Store resource forks in a __MACOSX folder for cross-platform zips"),
            ("--arch arch", "Thin universal binaries to a single architecture while copying"),
        ],
        "examples": [
            ("ditto ~/Projects/site ~/Backups/site", "Copy a tree with all metadata intact"),
            ("ditto /Applications/Foo.app /Volumes/Share/Foo.app", "Duplicate an app bundle without breaking its signature"),
            ("ditto -c -k --keepParent Foo.app Foo.zip", "Zip an app bundle the way Apple's notarization workflow expects"),
            ("ditto -x -k Foo.zip /Applications", "Extract a zip preserving macOS metadata"),
            ("ditto -V --arch arm64 Foo.app FooArm.app", "Copy while thinning a universal binary to Apple Silicon only"),
        ],
        "notes": [
            "ditto merges into an existing destination rather than replacing it — it never deletes files that are only in the destination. For a mirror, use `rsync -a --delete`.",
            "`ditto -c -k --keepParent` is the supported way to zip a signed bundle for notarization; the Finder's \"Compress\" produces an equivalent archive, `zip -r` does not.",
            "Unlike cp, `ditto src dst` copies the *contents* of src into dst; there is no trailing-slash subtlety to remember.",
            "Copying across to a filesystem that cannot hold extended attributes (FAT32, some SMB shares) silently drops them; ditto warns with `-V`.",
        ],
        "see_also": ["cp", "tar", "xattr", "codesign"],
        "tags": ["files", "copy", "archive", "metadata"],
    },
    {
        "command": "dscacheutil",
        "tagline": "query and flush the Directory Service cache",
        "summary": (
            "dscacheutil asks the macOS directory services layer the same questions "
            "applications ask: resolve this host, look up this user, find this group. "
            "Because it goes through the system resolver and its cache, it shows what apps "
            "actually see — unlike dig, which talks to DNS servers directly. It is also "
            "the documented way to flush the DNS cache."
        ),
        "synopsis": [
            "dscacheutil -q category [-a key value]",
            "dscacheutil -flushcache",
            "dscacheutil -cachedump [-entries category]",
            "dscacheutil -statistics",
        ],
        "options": [
            ("-q category", "Query a category: user, group, host, service, protocol, mount"),
            ("-a key value", "Restrict the query, e.g. `-a name apple.com`"),
            ("-flushcache", "Flush the Directory Service cache, including DNS"),
            ("-cachedump", "Dump cache contents (needs sudo for detail)"),
            ("-statistics", "Show cache hit/miss counters"),
            ("-configuration", "Print the current Directory Service search policy"),
        ],
        "examples": [
            ("dscacheutil -q host -a name example.com", "Resolve a hostname the way applications will"),
            ("dscacheutil -q user -a name alice", "Show a user record including UID, shell and home"),
            ("dscacheutil -q group -a name admin", "List the members of the admin group"),
            ("sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder", "The full DNS cache flush on modern macOS"),
            ("dscacheutil -q user | grep -A3 '^name: '", "Enumerate local user records"),
        ],
        "notes": [
            "Flushing DNS properly takes both halves: `sudo dscacheutil -flushcache` and `sudo killall -HUP mDNSResponder`. Either alone leaves stale entries behind on current releases.",
            "If dscacheutil resolves a name but dig does not (or vice versa), the difference is /etc/hosts, search domains or the resolver cache — `scutil --dns` shows the resolver configuration.",
            "`dscacheutil -q user` only returns records the local node knows. For a directory-bound Mac, `dscl` against the /Active Directory node gives the authoritative answer.",
        ],
        "see_also": ["dscl", "dig", "scutil", "id"],
        "tags": ["directory-services", "dns", "cache", "users"],
        "category": "networking",
    },
    {
        "command": "dscl",
        "tagline": "Directory Service command line utility",
        "summary": (
            "dscl browses and edits directory nodes — the local database at /Local/Default "
            "that holds users and groups, and any network directory the Mac is bound to. "
            "It is the supported way to create users, inspect group membership and read "
            "attributes that no GUI exposes. Its syntax is a small filesystem-like "
            "language: a node, a path, and a verb."
        ),
        "synopsis": [
            "dscl [node] -read path [key ...]",
            "dscl [node] -list path [key]",
            "dscl [node] -create path key value",
            "dscl [node] -append|-delete path key value",
            "dscl localhost -list /",
        ],
        "options": [
            ("-read path [key]", "Read all attributes, or one attribute"),
            ("-list path [key]", "List records under a path"),
            ("-search path key value", "Find records whose attribute matches"),
            ("-create path key value", "Create a record or set an attribute"),
            ("-append path key value", "Add a value to a multi-valued attribute"),
            ("-delete path [key [value]]", "Delete a record, attribute or single value"),
            ("-passwd path [password]", "Set a password"),
            ("-authonly user", "Verify a password without changing anything"),
            (". (dot)", "Shorthand for the local node, /Local/Default"),
        ],
        "examples": [
            ("dscl . -list /Users | grep -v '^_'", "List real user accounts, hiding system accounts"),
            ("dscl . -read /Users/alice", "Every attribute of a local user"),
            ("dscl . -read /Users/alice UniqueID NFSHomeDirectory UserShell", "The three attributes that usually matter"),
            ("dscl . -list /Groups/admin GroupMembership", "Who is an administrator"),
            ("sudo dscl . -append /Groups/admin GroupMembership bob", "Grant admin rights to a user"),
            ("sudo dscl . -delete /Groups/admin GroupMembership bob", "Revoke admin rights"),
            ("dscl . -search /Users UniqueID 501", "Find which account owns UID 501"),
            ("dscl localhost -list /", "List the directory nodes this Mac can see"),
        ],
        "notes": [
            "Creating a fully working user needs several attributes (UniqueID, PrimaryGroupID, NFSHomeDirectory, UserShell, RealName) plus a password and a home directory — a single `-create` is not enough. `sysadminctl -addUser` handles the whole sequence.",
            "UIDs below 500 are system accounts and hidden from the login window; conventional local users start at 501.",
            "Changes to /Local/Default take effect immediately, but a directory-bound Mac may need `dscacheutil -flushcache` before the change is visible to applications.",
            "Interactive mode (`dscl .` with no verb) gives a shell with cd/ls/cat for exploring the directory tree.",
        ],
        "see_also": ["dscacheutil", "id", "passwd", "who"],
        "tags": ["directory-services", "users", "groups", "accounts"],
        "category": "system_admin",
    },
    {
        "command": "du",
        "tagline": "display disk usage for files and directories",
        "summary": (
            "du walks a directory tree and adds up how much space its files occupy. It "
            "answers \"what is filling this disk?\" where df only answers \"how full is "
            "it?\". The BSD version on macOS defaults to 512-byte blocks, so `-h` or `-k` "
            "is almost always wanted."
        ),
        "synopsis": [
            "du [-h|-k|-m|-g] [-s] [-d depth] [-x] [-a] [file ...]",
        ],
        "options": [
            ("-h", "Human-readable sizes"),
            ("-s", "Summarise — one total per argument"),
            ("-d N", "Report totals down to depth N"),
            ("-a", "Report every file, not just directories"),
            ("-x", "Do not cross filesystem boundaries"),
            ("-c", "Print a grand total"),
            ("-I pattern", "Ignore files matching a pattern"),
        ],
        "examples": [
            ("du -sh ~/Downloads", "Total size of one directory"),
            ("du -h -d1 ~ | sort -h | tail -20", "The twenty largest things directly in your home directory"),
            ("sudo du -xh -d1 / | sort -h | tail", "Largest top-level directories on the boot volume"),
            ("du -sh */ | sort -h", "Rank the subdirectories of the current directory"),
            ("du -ah . | sort -h | tail -20", "Twenty largest individual files in a tree"),
        ],
        "notes": [
            "Run against system paths, du floods stderr with permission errors. Append `2>/dev/null` or use sudo.",
            "du reports space actually allocated, so a sparse file or an APFS clone reports far less than its apparent size — this is why `du` and Finder's Get Info can disagree.",
            "du and df disagree when a deleted file is still held open by a running process; `lsof +L1` finds those.",
            "`sort -h` (human-numeric) is available on macOS and is what makes du output readable.",
        ],
        "see_also": ["df", "find", "ls", "diskutil"],
        "tags": ["storage", "disk-usage", "files"],
        "category": "storage",
    },
    {
        "command": "env",
        "tagline": "run a command in a modified environment, or print the environment",
        "summary": (
            "With no arguments env prints the current environment. Given assignments and a "
            "command, it runs that command with the environment changed — without "
            "affecting the calling shell. Its other common role is in shebang lines, where "
            "`#!/usr/bin/env python3` finds the interpreter on PATH instead of hard-coding "
            "a path that differs between Intel and Apple Silicon Homebrew prefixes."
        ),
        "synopsis": [
            "env [-i] [-u name] [name=value ...] [command [args ...]]",
        ],
        "options": [
            ("-i", "Start from an empty environment"),
            ("-u name", "Remove a variable before running the command"),
            ("name=value", "Set a variable for the command only"),
            ("-S string", "Split the string into arguments — lets a shebang pass multiple args"),
        ],
        "examples": [
            ("env", "Print the whole environment"),
            ("env | sort | grep -i proxy", "Check which proxy variables are set"),
            ("env PATH=/usr/bin:/bin ./script.sh", "Run with a restricted PATH"),
            ("env -i /bin/zsh --norcs", "Start a shell with a completely clean environment for debugging"),
            ("env -u HTTP_PROXY curl https://example.com", "Bypass a proxy variable for one command"),
            ("#!/usr/bin/env python3", "Shebang that resolves the interpreter from PATH"),
        ],
        "notes": [
            "`/usr/bin/env python3` is the portable shebang on macOS precisely because Python lives in different places depending on Homebrew prefix, pyenv, or Xcode's Command Line Tools.",
            "GUI applications launched from the Dock do not inherit your shell's environment. Use a LaunchAgent with EnvironmentVariables, or `launchctl setenv`, for variables a GUI app must see.",
            "`env -i` is the fastest way to prove that a failure is caused by something in your environment rather than the program itself.",
        ],
        "see_also": ["export", "launchctl", "sudo", "sysctl"],
        "tags": ["shell", "environment", "scripting"],
    },
    {
        "command": "export",
        "tagline": "mark shell variables for export to child processes",
        "summary": (
            "export is a shell builtin that flags a variable so child processes inherit it. "
            "A variable set without export exists only in the current shell. On macOS the "
            "default shell is zsh, so persistent exports belong in ~/.zshrc (interactive "
            "shells) or ~/.zprofile (login shells) — not ~/.bash_profile, which zsh never "
            "reads."
        ),
        "synopsis": [
            "export name=value ...",
            "export name ...",
            "export -p",
        ],
        "options": [
            ("name=value", "Set and export in one step"),
            ("name", "Export an already-set variable"),
            ("-p", "List all exported variables"),
            ("-n name", "(bash) Remove the export attribute, keeping the value"),
        ],
        "examples": [
            ("export PATH=\"/opt/homebrew/bin:$PATH\"", "Put the Apple Silicon Homebrew prefix first on PATH"),
            ("export EDITOR=nano", "Set the editor used by git, crontab and others"),
            ("export HTTPS_PROXY=http://proxy.example.com:8080", "Route CLI tools through a proxy"),
            ("export -p | grep -i lang", "Check the locale variables currently exported"),
            ("export JAVA_HOME=$(/usr/libexec/java_home -v 17)", "Point JAVA_HOME at a specific installed JDK"),
        ],
        "notes": [
            "zsh reads ~/.zshenv always, ~/.zprofile for login shells, ~/.zshrc for interactive shells. Terminal.app starts login shells by default, so both .zprofile and .zshrc run.",
            "An export in a script does not survive back into the calling shell. Use `source script.sh` (or `. script.sh`) when the variables must persist.",
            "Never export secrets in a shell profile on a shared machine — the environment of any process is readable by its owner via `ps eww <pid>`.",
            "For GUI apps, exports in shell profiles have no effect; use `launchctl setenv NAME value` or a LaunchAgent.",
        ],
        "see_also": ["env", "launchctl", "sudo"],
        "tags": ["shell", "environment", "builtin", "zsh"],
    },
    {
        "command": "find",
        "tagline": "walk a directory tree looking for files",
        "summary": (
            "find evaluates an expression against every file in a hierarchy and acts on the "
            "matches. macOS ships BSD find: the path comes before the tests, `-delete` and "
            "`-execdir` exist but some GNU predicates do not, and `-E` enables extended "
            "regular expressions. For content search across indexed volumes, mdfind is "
            "faster; find is what works on unindexed volumes and inside excluded paths."
        ),
        "synopsis": [
            "find [-E] [-x] path ... [expression]",
            "find path -name pattern -exec command {} \;",
        ],
        "options": [
            ("-name / -iname pattern", "Match the filename, case-sensitively or not"),
            ("-path pattern", "Match against the whole path"),
            ("-type f|d|l", "Restrict to files, directories or symlinks"),
            ("-size +100M", "Files larger than a size"),
            ("-mtime -7 / -mmin -60", "Modified in the last 7 days / 60 minutes"),
            ("-newer file", "Modified more recently than a reference file"),
            ("-user name / -perm mode", "Match owner or permissions"),
            ("-maxdepth N / -mindepth N", "Bound the descent"),
            ("-x", "Do not cross filesystem boundaries"),
            ("-exec cmd {} \; / +", "Run a command per match / batched"),
            ("-delete", "Delete matches — put it last, and dry-run without it first"),
            ("-print0", "NUL-separated output for `xargs -0`"),
        ],
        "examples": [
            ("find . -name '*.log' -mtime +30", "Log files not modified in the last month"),
            ("find ~/Downloads -type f -size +500M", "Large files clogging Downloads"),
            ("find . -name '.DS_Store' -delete", "Remove Finder metadata files from a tree"),
            ("find /Applications -maxdepth 1 -name '*.app' -print0 | xargs -0 -n1 basename", "List installed applications"),
            ("find . -type f -name '*.tmp' -exec rm {} +", "Batch-delete matching files efficiently"),
            ("sudo find /var/log -type f -mtime -1 -ls", "Log files touched in the last day, with details"),
            ("find -E . -regex '.*\\.(jpg|png)'", "Extended regex matching on macOS find"),
        ],
        "notes": [
            "BSD find requires the path first: `find . -name x`, never `find -name x .`.",
            "Run any `-delete` expression once without `-delete` (or with `-print`) to see exactly what it matches. There is no undo.",
            "TCC protects ~/Desktop, ~/Documents and ~/Downloads: find run from an unapproved terminal reports \"Operation not permitted\" even for your own files. Grant Full Disk Access to the terminal to silence it.",
            "`-exec cmd {} +` batches arguments and is far faster than `\;`, which forks once per file.",
            "Spotlight-indexed searches by content or metadata are much faster with mdfind; find still wins on unindexed volumes, network mounts and exact permission tests.",
        ],
        "see_also": ["mdfind", "grep", "xargs", "du"],
        "tags": ["files", "search", "filesystem"],
    },
    {
        "command": "ftp",
        "tagline": "File Transfer Protocol client",
        "summary": (
            "ftp opens an interactive session against an FTP server. Apple removed the "
            "bundled ftp and telnet clients in macOS 10.13 High Sierra, so on a modern Mac "
            "`ftp` is either absent or a Homebrew build (`brew install inetutils` or "
            "`tnftp`). FTP transmits credentials and data in clear text and should be "
            "treated as a legacy protocol: use sftp or scp, both of which ship with macOS, "
            "unless a remote system genuinely offers nothing else."
        ),
        "synopsis": [
            "ftp [-inv] [host [port]]",
            "ftp ftp://user:password@host/path",
        ],
        "options": [
            ("-i", "Turn off interactive prompting during multi-file transfers"),
            ("-n", "Do not attempt auto-login using ~/.netrc"),
            ("-v", "Verbose — show server responses and transfer statistics"),
            ("-p", "Use passive mode (usually required behind NAT or a firewall)"),
            ("open host", "Connect from within an interactive session"),
            ("get / put / mget / mput", "Transfer one or many files"),
            ("binary / ascii", "Set the transfer mode — binary for anything non-text"),
            ("passive", "Toggle passive mode inside a session"),
        ],
        "examples": [
            ("which ftp || brew install tnftp", "Check whether an ftp client exists, and install one if not"),
            ("ftp -p ftp.example.com", "Connect in passive mode"),
            ("sftp user@example.com", "The supported, encrypted replacement that ships with macOS"),
            ("curl -u user:pass ftp://example.com/file.txt -o file.txt", "Fetch one FTP file without an interactive client"),
            ("scp file.txt user@example.com:/path/", "Copy a file over SSH instead of FTP"),
        ],
        "notes": [
            "macOS has shipped without ftp and telnet since 10.13. Their absence is deliberate, not a broken install.",
            "FTP sends usernames, passwords and file contents unencrypted. On any untrusted network, treat an FTP login as disclosed.",
            "Active-mode FTP needs inbound connections back to the client and rarely survives NAT; passive mode (`-p`) is the default choice.",
            "curl speaks FTP, FTPS and SFTP and is already installed — for scripted one-off transfers it removes the need for an ftp client entirely.",
        ],
        "see_also": ["curl", "netstat", "ping"],
        "tags": ["network", "transfer", "legacy"],
        "category": "networking",
    },
    {
        "command": "grep",
        "tagline": "search input for lines matching a pattern",
        "summary": (
            "grep prints the lines of its input that match a regular expression. macOS "
            "ships BSD grep, which supports the common GNU flags (-r, -i, -n, -E, -o, "
            "--include) but not every one — notably `-P` (Perl regex) is missing, which is "
            "the single most common cause of a Linux script failing on a Mac."
        ),
        "synopsis": [
            "grep [-EFilnrvwc] [-A|-B|-C num] pattern [file ...]",
            "grep -r --include='*.py' pattern directory",
        ],
        "options": [
            ("-i", "Case-insensitive"),
            ("-r / -R", "Recurse into directories (-R follows symlinks)"),
            ("-n", "Prefix each match with its line number"),
            ("-v", "Invert — print non-matching lines"),
            ("-w / -x", "Match whole words / whole lines"),
            ("-c", "Count matching lines instead of printing them"),
            ("-l / -L", "List files with matches / without matches"),
            ("-E", "Extended regular expressions (same as egrep)"),
            ("-F", "Fixed strings, no regex (same as fgrep) — faster and safer for literals"),
            ("-o", "Print only the matched part"),
            ("-A n / -B n / -C n", "Show n lines after / before / around each match"),
            ("--include / --exclude glob", "Filter which files -r visits"),
            ("-q", "Quiet — exit status only, useful in `if` tests"),
        ],
        "examples": [
            ("grep -rn 'TODO' src/", "Find TODOs with file and line numbers"),
            ("grep -i error /var/log/system.log | tail -20", "Recent errors in a log"),
            ("grep -rl --include='*.swift' 'NSUserDefaults' .", "Which Swift files still use an old API"),
            ("ps aux | grep -v grep | grep node", "Find node processes without matching the grep itself"),
            ("grep -C3 'panic' crash.log", "See three lines of context around each panic"),
            ("grep -Fq 'needle' file && echo found", "Literal search used as a test"),
            ("grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+' version.txt", "Extract just the version numbers"),
        ],
        "notes": [
            "BSD grep has no `-P`. Translate Perl-style patterns to `-E`, or install GNU grep with `brew install grep` and call `ggrep`.",
            "`grep -r` on macOS follows the BSD convention of not following symlinks; use `-R` when you want them followed.",
            "Piping `ps aux` into grep always matches the grep process itself. `pgrep -fl node` avoids the problem entirely.",
            "Colour is not on by default: add `--color=auto`, or set `GREP_OPTIONS` — deprecated — better, alias grep in ~/.zshrc.",
        ],
        "see_also": ["awk", "sed", "find", "mdfind"],
        "tags": ["text-processing", "search", "regex"],
    },
    {
        "command": "hdiutil",
        "tagline": "manipulate disk images (DMG, ISO, sparse bundles)",
        "summary": (
            "hdiutil creates, attaches, detaches, converts and verifies disk images. It is "
            "how DMG installers are built and inspected, how encrypted containers are "
            "created without FileVault, and how an ISO gets attached for reading. Attaching "
            "an image makes it appear as a device in `diskutil list` just like physical "
            "media."
        ),
        "synopsis": [
            "hdiutil attach [-nobrowse] [-readonly] [-mountpoint path] image",
            "hdiutil detach device",
            "hdiutil create -size N -fs FS -volname NAME image.dmg",
            "hdiutil convert source -format FMT -o output",
            "hdiutil info | hdiutil verify image",
        ],
        "options": [
            ("attach image", "Mount a disk image"),
            ("-nobrowse", "Mount without showing the volume in the Finder sidebar"),
            ("-readonly", "Attach read-only"),
            ("-mountpoint path", "Mount at a chosen path instead of /Volumes"),
            ("detach device", "Unmount and detach; add `-force` if something holds it open"),
            ("create -size N -fs APFS -volname NAME", "Create a blank image"),
            ("create -srcfolder dir -o image.dmg", "Create an image from a folder"),
            ("-encryption AES-256 -stdinpass", "Create an encrypted image, password from stdin"),
            ("convert -format UDZO|UDRW|UDTO", "Convert to compressed / read-write / CD master"),
            ("info", "List currently attached images and their devices"),
            ("verify image", "Verify an image's checksums"),
            ("compact image.sparsebundle", "Reclaim free space inside a sparse bundle"),
        ],
        "examples": [
            ("hdiutil attach ~/Downloads/App.dmg", "Mount a downloaded installer"),
            ("hdiutil attach -nobrowse -readonly image.iso", "Attach an ISO quietly for scripted access"),
            ("hdiutil detach /Volumes/App", "Unmount when done"),
            ("hdiutil create -size 2g -fs APFS -volname Scratch ~/scratch.dmg", "Create a 2 GB scratch image"),
            ("hdiutil create -encryption AES-256 -stdinpass -size 500m -fs APFS -volname Vault ~/vault.dmg", "Create an encrypted container"),
            ("hdiutil create -srcfolder ./Release -o Release.dmg", "Package a folder as a DMG"),
            ("hdiutil convert rw.dmg -format UDZO -o distribution.dmg", "Compress a read-write image for distribution"),
            ("hdiutil info | grep -A2 image-path", "See which images are currently attached"),
        ],
        "notes": [
            "\"Resource busy\" on detach means a process still has the volume open; `lsof +D /Volumes/Name` finds it, or use `hdiutil detach -force`.",
            "UDZO is the compressed read-only format used for distribution; UDRW is read-write. A DMG built for distribution should be converted to UDZO and then signed and notarized.",
            "A .sparsebundle grows on demand and is what Time Machine uses for network destinations; `hdiutil compact` reclaims space after deleting files inside it.",
            "Attached images appear in `diskutil list` as ordinary disks, so diskutil verbs work on them — which also means a careless `eraseDisk` can target one.",
        ],
        "see_also": ["diskutil", "ditto", "tmutil", "codesign"],
        "tags": ["storage", "disk-image", "dmg", "encryption"],
        "category": "storage",
    },
    {
        "command": "head",
        "tagline": "print the first lines or bytes of a file",
        "summary": (
            "head shows the beginning of its input — by default the first ten lines. It is "
            "the quickest way to look at a file's header, sample a large CSV, or truncate "
            "noisy command output to something readable."
        ),
        "synopsis": [
            "head [-n count | -c bytes] [file ...]",
        ],
        "options": [
            ("-n N", "Print the first N lines"),
            ("-c N", "Print the first N bytes"),
            ("-q / -v", "Never / always print the filename header when given several files"),
        ],
        "examples": [
            ("head /var/log/install.log", "First ten lines of a log"),
            ("head -n 1 data.csv", "Just the CSV header row"),
            ("head -c 512 disk.img | xxd | head", "Inspect the first sector of an image"),
            ("ls -t ~/Downloads | head -5", "Five most recently modified downloads"),
            ("head -n 20 *.txt", "First 20 lines of each file, with filename headers"),
        ],
        "notes": [
            "BSD head accepts `-n 20`; the older `head -20` form also works but is not portable.",
            "Piping head into a slow producer terminates that producer with SIGPIPE once head has what it needs — that is normal, not an error.",
            "For the end of a file use tail; to follow a growing log use `tail -f` or `log stream`.",
        ],
        "see_also": ["tail", "less", "cat", "wc"],
        "tags": ["text", "files", "io"],
    },
    {
        "command": "hostname",
        "tagline": "print or set the system hostname",
        "summary": (
            "hostname reports the machine's name. On macOS this is deceptively layered: "
            "there are three separate names — HostName, LocalHostName (Bonjour) and "
            "ComputerName (the Finder-visible one) — all managed by scutil. Setting the "
            "name with `hostname` alone does not survive a reboot; scutil is the durable "
            "route."
        ),
        "synopsis": [
            "hostname [-fs]",
            "sudo scutil --set HostName|LocalHostName|ComputerName name",
        ],
        "options": [
            ("(no argument)", "Print the current hostname"),
            ("-s", "Print the short name, up to the first dot"),
            ("-f", "Print the fully qualified name"),
            ("scutil --get NAME", "Read one of the three macOS name values"),
            ("scutil --set NAME value", "Set one of them persistently (needs sudo)"),
        ],
        "examples": [
            ("hostname", "Print the current name"),
            ("hostname -s", "Short name only"),
            ("scutil --get ComputerName", "The name shown in Sharing preferences and the Finder sidebar"),
            ("scutil --get LocalHostName", "The Bonjour name, reachable as name.local"),
            ("sudo scutil --set ComputerName \"Studio Mac\"", "Set the friendly name"),
            ("sudo scutil --set LocalHostName studio-mac", "Set the Bonjour name (no spaces allowed)"),
            ("sudo scutil --set HostName studio-mac.example.com", "Set the fully qualified hostname"),
        ],
        "notes": [
            "Set all three names when renaming a Mac, or tools will disagree about what the machine is called.",
            "LocalHostName may contain only letters, digits and hyphens — spaces are rejected because it becomes name.local on the network.",
            "If HostName is unset, macOS derives the hostname from DHCP or falls back to LocalHostName, which is why a Mac's prompt sometimes changes when it moves networks.",
            "A change to ComputerName takes effect immediately; the shell prompt only updates in new shells.",
        ],
        "see_also": ["scutil", "networksetup", "systemsetup", "uname"],
        "tags": ["network", "identity", "configuration"],
        "category": "networking",
    },
    {
        "command": "id",
        "tagline": "print user and group identity",
        "summary": (
            "id shows the UID, primary GID and group memberships of a user — yours by "
            "default. It is the fastest answer to \"am I an admin on this machine?\", since "
            "membership of the `admin` group is what grants sudo rights on macOS."
        ),
        "synopsis": [
            "id [user]",
            "id -u|-g|-G|-p|-P [-n] [user]",
        ],
        "options": [
            ("(no argument)", "Full identity of the current user"),
            ("-u", "Numeric effective user ID"),
            ("-g", "Numeric effective group ID"),
            ("-G", "All group IDs"),
            ("-n", "Print names instead of numbers (with -u, -g or -G)"),
            ("-p", "Human-readable format"),
            ("-P", "Output in /etc/passwd format"),
            ("user", "Report on another account instead"),
        ],
        "examples": [
            ("id", "Your UID, GID and every group you belong to"),
            ("id -un", "Just your username"),
            ("id -Gn | tr ' ' '\\n' | grep -x admin", "Test whether you are an administrator"),
            ("id alice", "Another user's identity"),
            ("id -u", "Numeric UID — 0 means you are root"),
        ],
        "notes": [
            "On macOS, sudo rights come from membership of the `admin` group, not from a sudoers entry per user. `id -Gn` is the check that matters.",
            "Regular accounts have UID 501 and up; `_`-prefixed system accounts sit below 500 and are hidden from the login window.",
            "The primary group is `staff` (GID 20) for ordinary users, unlike Linux distributions that create a group per user.",
            "Under sudo, `id -u` returns 0 while `logname` still returns the original user — useful when a script must know who invoked it.",
        ],
        "see_also": ["whoami", "dscl", "who", "sudo"],
        "tags": ["users", "groups", "identity", "permissions"],
    },
    {
        "command": "ifconfig",
        "tagline": "configure and inspect network interfaces",
        "summary": (
            "ifconfig lists network interfaces with their addresses, MAC addresses, MTU and "
            "status. On macOS it remains the quickest read-only view of the network stack, "
            "but changes made with it are not persistent and are not known to the system "
            "configuration database — networksetup is the supported tool for durable "
            "changes."
        ),
        "synopsis": [
            "ifconfig [-a] [-L] [interface]",
            "sudo ifconfig interface [inet address netmask mask] [up|down]",
        ],
        "options": [
            ("-a", "Show all interfaces including those that are down"),
            ("interface", "Show one interface, e.g. en0"),
            ("up / down", "Bring an interface up or down (needs sudo)"),
            ("inet addr netmask mask", "Set an IPv4 address temporarily"),
            ("ether addr", "Set the MAC address on interfaces that allow it"),
            ("mtu N", "Set the MTU"),
            ("-L", "Show address lifetimes for IPv6"),
        ],
        "examples": [
            ("ifconfig", "Every active interface with addresses"),
            ("ifconfig en0", "Just the primary Ethernet/Wi-Fi interface"),
            ("ifconfig en0 | awk '/inet /{print $2}'", "Extract the IPv4 address"),
            ("ifconfig -a | grep -E '^[a-z]|status'", "Interface names and link status at a glance"),
            ("sudo ifconfig en0 down && sudo ifconfig en0 up", "Bounce an interface"),
            ("ifconfig | grep ether", "MAC addresses of all interfaces"),
        ],
        "notes": [
            "en0 is usually Wi-Fi on laptops and Ethernet on desktops — do not assume. `networksetup -listallhardwareports` maps names to hardware.",
            "Anything set with ifconfig is lost at reboot or when the network location changes, because configd re-applies the stored configuration. Use `networksetup` for persistent settings.",
            "macOS randomises the Wi-Fi MAC address for some networks by default; the address ifconfig shows may not be the hardware address.",
            "utun interfaces are VPN tunnels; awdl0 is Apple Wireless Direct Link (AirDrop/Handoff); bridge0 is usually Internet Sharing or a VM network.",
        ],
        "see_also": ["networksetup", "netstat", "ipconfig", "scutil"],
        "tags": ["network", "interface", "diagnostics"],
        "category": "networking",
    },
    {
        "command": "installer",
        "tagline": "install macOS packages (.pkg) from the command line",
        "summary": (
            "installer applies a .pkg or .mpkg to a target volume without the graphical "
            "Installer app. It is the mechanism behind scripted deployments and MDM "
            "installs. Most system-level packages need root, and every package's scripts "
            "run with the privileges of the installer process — so read what you are "
            "installing before running it as root."
        ),
        "synopsis": [
            "sudo installer -pkg package.pkg -target /",
            "installer -pkginfo -pkg package.pkg",
            "installer -volinfo",
        ],
        "options": [
            ("-pkg path", "The package to install"),
            ("-target /", "Target volume; `/` is the boot volume, or `CurrentUserHomeDirectory`"),
            ("-verbose / -verboseR", "Human-readable / machine-readable progress"),
            ("-dumplog", "Write full installer output to stdout"),
            ("-pkginfo", "Describe the package without installing"),
            ("-volinfo", "List volumes eligible as targets"),
            ("-showChoicesXML", "Print the installation choices in a distribution package"),
            ("-applyChoiceChangesXML file", "Install with a customised choice set"),
            ("-allowUntrusted", "Install a package whose signature is expired or absent"),
        ],
        "examples": [
            ("installer -pkginfo -pkg ~/Downloads/Tool.pkg", "Inspect a package before installing it"),
            ("sudo installer -pkg ~/Downloads/Tool.pkg -target /", "Install system-wide"),
            ("sudo installer -verboseR -pkg Tool.pkg -target / 2>&1 | tee install.log", "Install with machine-readable progress, captured"),
            ("installer -showChoicesXML -pkg Suite.pkg > choices.xml", "See what a multi-choice package offers"),
            ("pkgutil --pkgs | grep -i tool", "Confirm afterwards that the receipt was written"),
        ],
        "notes": [
            "`-target /` is a volume, not a directory. Passing an arbitrary path fails with a confusing error.",
            "`-allowUntrusted` bypasses signature checking — acceptable for an internally built package you produced, not for a download.",
            "Installation writes a receipt; `pkgutil --pkgs`, `--files` and `--forget` are how you audit and undo what a package placed on disk.",
            "Packages can run preinstall and postinstall scripts as root. `pkgutil --expand-full Tool.pkg /tmp/tool` extracts them for review.",
        ],
        "see_also": ["pkgutil", "brew", "softwareupdate", "codesign"],
        "tags": ["package-management", "installation", "deployment"],
        "category": "package_management",
    },
    {
        "command": "ipconfig",
        "tagline": "query DHCP and interface addressing state",
        "summary": (
            "macOS's ipconfig is not the Windows tool of the same name — it is a small "
            "utility for querying and manipulating the DHCP client. It answers "
            "\"what address did DHCP give me, and what else did the server say?\", and can "
            "force a lease renewal without toggling the interface."
        ),
        "synopsis": [
            "ipconfig getifaddr interface",
            "ipconfig getpacket interface",
            "sudo ipconfig set interface DHCP|BOOTP|NONE",
            "ipconfig getsummary interface",
        ],
        "options": [
            ("getifaddr en0", "Print the current IPv4 address, or nothing if unconfigured"),
            ("getpacket en0", "Dump the full DHCP response, including options"),
            ("getv6packet en0", "The DHCPv6 equivalent"),
            ("getsummary en0", "Summarise the interface's configuration state"),
            ("set en0 DHCP", "Force a DHCP renewal (needs sudo)"),
            ("set en0 NONE", "Remove the interface's configuration"),
            ("getoption en0 domain_name_server", "Read a single DHCP option"),
            ("waitall", "Block until all interfaces have finished configuring"),
        ],
        "examples": [
            ("ipconfig getifaddr en0", "The current IPv4 address of en0 — empty output means no address"),
            ("ipconfig getpacket en0", "Full DHCP lease detail: router, DNS, lease time, server identifier"),
            ("sudo ipconfig set en0 DHCP", "Renew the DHCP lease"),
            ("ipconfig getoption en0 domain_name_server", "Which DNS servers DHCP handed out"),
            ("ipconfig getsummary en0 | grep -i ssid", "Which Wi-Fi network the interface is on"),
        ],
        "notes": [
            "`ipconfig getifaddr` printing nothing and exiting non-zero is the standard scripted test for \"this interface has no IPv4 address\".",
            "Self-assigned 169.254.x.x addresses mean DHCP failed. `ipconfig getpacket` will be empty; check the cable, the Wi-Fi association, or the DHCP server.",
            "This is a DHCP client tool. To change an interface's configuration persistently use `networksetup -setdhcp` or `-setmanual`.",
            "The DHCP options in `getpacket` are the ground truth when a network hands out unexpected DNS servers or search domains.",
        ],
        "see_also": ["networksetup", "ifconfig", "scutil", "dig"],
        "tags": ["network", "dhcp", "addressing"],
        "category": "networking",
    },
    {
        "command": "kill",
        "tagline": "send a signal to a process",
        "summary": (
            "kill sends a signal to a process by PID. Despite the name, most signals ask "
            "politely: the default TERM lets a process clean up, while KILL cannot be "
            "caught and leaves temporary files and locks behind. On macOS, killing a "
            "launchd-managed process usually just makes launchd restart it — the right "
            "tool there is launchctl."
        ),
        "synopsis": [
            "kill [-signal] pid ...",
            "kill -l",
            "killall [-signal] name",
        ],
        "options": [
            ("-TERM (default, 15)", "Ask the process to terminate; it may clean up first"),
            ("-KILL (9)", "Terminate immediately; cannot be caught or ignored"),
            ("-HUP (1)", "Hang up — many daemons reload their configuration on this"),
            ("-INT (2)", "Interrupt, as if Ctrl-C were pressed"),
            ("-QUIT (3)", "Quit and dump core"),
            ("-STOP / -CONT", "Suspend / resume a process"),
            ("-USR1 / -USR2", "Application-defined signals"),
            ("-l", "List signal names and numbers"),
            ("-0", "Send no signal — tests whether the PID exists and you may signal it"),
        ],
        "examples": [
            ("kill 4321", "Ask process 4321 to exit cleanly"),
            ("kill -9 4321", "Force termination when TERM has been ignored"),
            ("kill -HUP $(pgrep -x mDNSResponder)", "Reload a daemon's configuration"),
            ("killall Finder", "Restart the Finder"),
            ("kill -0 4321 && echo running", "Test whether a PID exists"),
            ("pkill -f 'node server.js'", "Kill by command line rather than PID"),
        ],
        "notes": [
            "Always try TERM before KILL. `kill -9` skips cleanup: databases lose in-flight writes, lock files persist, and shared memory can leak.",
            "A process listed as `Z` (zombie) in ps cannot be killed — it is already dead and waiting for its parent to reap it. Signal the parent instead.",
            "Killing a launchd job just triggers a restart if KeepAlive is set. Use `launchctl bootout` or `launchctl kill` to stop it properly.",
            "You may only signal your own processes unless you are root; \"Operation not permitted\" against your own process usually means it is protected by SIP.",
        ],
        "see_also": ["ps", "top", "launchctl", "log"],
        "tags": ["process", "signals", "troubleshooting"],
        "category": "system_admin",
    },
    {
        "command": "launchctl",
        "tagline": "control launchd, the macOS service manager",
        "summary": (
            "launchctl is the interface to launchd, which starts and supervises every "
            "daemon, agent and login item on macOS — the role systemd plays on Linux. Its "
            "syntax changed substantially in 10.10: the modern subcommands take a domain "
            "target such as `gui/501` or `system`, and the old `load`/`unload` verbs are "
            "deprecated even though they still work."
        ),
        "synopsis": [
            "launchctl list [label]",
            "launchctl bootstrap domain plist / launchctl bootout domain[/label]",
            "launchctl enable|disable domain/label",
            "launchctl kickstart [-k] domain/label",
            "launchctl print domain[/label]",
        ],
        "options": [
            ("list [label]", "List loaded jobs, or show one job's dictionary"),
            ("print gui/$UID/label", "Detailed state, including last exit status and environment"),
            ("bootstrap gui/$UID path.plist", "Load a job into a domain"),
            ("bootout gui/$UID/label", "Unload a job"),
            ("enable / disable domain/label", "Persist whether a job may run"),
            ("kickstart -k domain/label", "Start a job now; `-k` restarts it if already running"),
            ("kill SIGNAL domain/label", "Send a signal to a running job"),
            ("setenv NAME value", "Set an environment variable for GUI-launched apps"),
            ("getenv NAME", "Read such a variable"),
            ("dumpstate", "Dump launchd's entire state (very large)"),
            ("load / unload", "Legacy verbs, superseded by bootstrap/bootout"),
        ],
        "examples": [
            ("launchctl list | grep -i backup", "Find a loaded job by name"),
            ("launchctl print gui/$UID/com.example.agent", "Full state of a user agent, including why it last exited"),
            ("launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.example.agent.plist", "Load a user agent"),
            ("launchctl bootout gui/$UID/com.example.agent", "Unload it"),
            ("sudo launchctl bootstrap system /Library/LaunchDaemons/com.example.daemon.plist", "Load a system daemon"),
            ("launchctl kickstart -k gui/$UID/com.example.agent", "Restart an agent to pick up a changed plist"),
            ("launchctl setenv JAVA_HOME /Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home", "Make a variable visible to GUI apps"),
        ],
        "notes": [
            "Three plist locations, three meanings: ~/Library/LaunchAgents (this user, after login), /Library/LaunchAgents (all users, after login), /Library/LaunchDaemons (system, before login, runs as root).",
            "The second column of `launchctl list` is the last exit status. A non-zero value there is the first thing to check when a job \"does nothing\".",
            "Editing a plist has no effect until the job is reloaded — `bootout` then `bootstrap`, or `kickstart -k`.",
            "Third-party daemons need the plist owned by root:wheel with mode 644, or launchd refuses to load it.",
            "`launchctl setenv` affects apps launched afterwards, not ones already running, and does not persist across reboot.",
        ],
        "see_also": ["kill", "log", "defaults", "plutil"],
        "tags": ["launchd", "services", "daemons", "agents"],
        "category": "service_management",
    },
    {
        "command": "less",
        "tagline": "page through text one screen at a time",
        "summary": (
            "less displays text a screen at a time and lets you scroll, search and follow. "
            "It is the default pager for man pages and git output on macOS. Unlike `more` "
            "it can move backwards, and unlike `cat` it does not load the whole file, so "
            "it opens a multi-gigabyte log instantly."
        ),
        "synopsis": [
            "less [-NSRi] [+/pattern] [file ...]",
            "command | less",
        ],
        "options": [
            ("-N", "Show line numbers"),
            ("-S", "Chop long lines instead of wrapping (scroll sideways with arrows)"),
            ("-R", "Pass through ANSI colour escapes"),
            ("-i / -I", "Case-insensitive search (unless the pattern has capitals / always)"),
            ("-X", "Do not clear the screen on exit — leaves the output visible"),
            ("-F", "Quit immediately if the content fits on one screen"),
            ("+F", "Start in follow mode, like `tail -f`"),
            ("+/pattern", "Open at the first match"),
        ],
        "examples": [
            ("less /var/log/install.log", "Page through a log"),
            ("less -NS wide-output.txt", "Line numbers, no wrapping, scroll sideways"),
            ("log show --last 1h | less -R", "Page colourised command output"),
            ("less +F /var/log/system.log", "Follow a growing file; Ctrl-C returns to normal paging"),
            ("less +/error app.log", "Jump straight to the first occurrence of 'error'"),
            ("git log | less -X", "Keep the output on screen after quitting"),
        ],
        "notes": [
            "Inside less: `/pattern` searches forward, `?pattern` back, `n`/`N` repeat, `g`/`G` jump to start/end, `q` quits, `-` toggles an option live.",
            "`less +F` is `tail -f` with the ability to stop and scroll back — Ctrl-C leaves follow mode without losing your place.",
            "Set `export LESS='-R -i -F -X'` in ~/.zshrc for sensible defaults across man, git and other tools that call the pager.",
            "macOS ships an older less than Homebrew's; if a feature in a tutorial is missing, check `less --version`.",
        ],
        "see_also": ["tail", "head", "cat", "log"],
        "tags": ["text", "pager", "files"],
    },
    {
        "command": "lipo",
        "tagline": "inspect and manipulate universal (multi-architecture) binaries",
        "summary": (
            "lipo reports which architectures a Mach-O binary contains, extracts one, or "
            "combines several into a universal binary. Since the Apple Silicon transition "
            "it has become an everyday diagnostic: \"why is this running under Rosetta?\" is "
            "usually answered by `lipo -archs` showing x86_64 only."
        ),
        "synopsis": [
            "lipo -info | -detailed_info file",
            "lipo -archs file",
            "lipo -thin arch input -output output",
            "lipo -create a b -output universal",
            "lipo -remove arch input -output output",
        ],
        "options": [
            ("-info", "One-line summary of the architectures present"),
            ("-detailed_info", "Per-architecture offsets, sizes and alignment"),
            ("-archs", "Just the architecture names, space separated"),
            ("-thin arch", "Extract a single architecture"),
            ("-create", "Combine single-architecture files into a universal binary"),
            ("-remove arch", "Drop one architecture"),
            ("-output path", "Where to write the result (required for -thin/-create/-remove)"),
        ],
        "examples": [
            ("lipo -archs /Applications/Foo.app/Contents/MacOS/Foo", "Which architectures an app supports"),
            ("lipo -info $(which python3)", "Check whether a CLI tool is universal"),
            ("lipo -thin arm64 universal_bin -output arm64_bin", "Extract the Apple Silicon slice"),
            ("lipo -create x86_64_bin arm64_bin -output universal_bin", "Build a universal binary"),
            ("lipo -remove x86_64 universal_bin -output arm64_only", "Halve a binary's size by dropping Intel support"),
            ("file /Applications/Foo.app/Contents/MacOS/Foo", "A quicker read when you only need the summary"),
        ],
        "notes": [
            "`arm64` is Apple Silicon; `x86_64` is Intel; `arm64e` is the pointer-authenticated ABI used by system binaries and kernel extensions.",
            "An app showing only x86_64 runs under Rosetta 2 on Apple Silicon — that is the performance answer people are usually looking for.",
            "Modifying a binary with lipo invalidates its code signature. Re-sign afterwards with `codesign -f -s -` at minimum.",
            "`ditto --arch arm64` thins while copying, which is often more convenient than lipo for whole app bundles.",
        ],
        "see_also": ["codesign", "ditto", "uname", "sysctl"],
        "tags": ["binaries", "architecture", "apple-silicon", "rosetta"],
        "category": "hardware",
    },
    {
        "command": "ln",
        "tagline": "create hard and symbolic links",
        "summary": (
            "ln creates a second name for a file. A hard link is another directory entry "
            "pointing at the same inode — indistinguishable from the original, and valid "
            "only within one filesystem. A symbolic link is a small file holding a path, "
            "which may cross filesystems and may dangle. Almost all day-to-day use is "
            "`ln -s`."
        ),
        "synopsis": [
            "ln [-s] [-f|-i] [-h] [-v] source [target]",
            "ln -s source_dir/ target_dir",
        ],
        "options": [
            ("-s", "Create a symbolic link rather than a hard link"),
            ("-f", "Replace an existing target"),
            ("-i", "Prompt before replacing"),
            ("-h / -n", "Do not follow a symlink that is already at the target path"),
            ("-v", "Report what was linked"),
            ("-F", "With -s -f, remove an existing target directory"),
        ],
        "examples": [
            ("ln -s /opt/homebrew/bin/python3.12 ~/bin/python3", "Point a convenient name at a versioned binary"),
            ("ln -sfn /Volumes/External/Media ~/Media", "Replace an existing symlink safely (note -n)"),
            ("ln -s \"$PWD/config.yml\" ~/.config/app/config.yml", "Link a dotfile to a repo copy — use an absolute path"),
            ("ls -l ~/Media", "Show what a symlink points at"),
            ("ln original.txt hardlink.txt", "Create a hard link — both names share one inode"),
            ("find . -type l ! -exec test -e {} \; -print", "Find broken symlinks in a tree"),
        ],
        "notes": [
            "`ln -sf` without `-n` follows an existing symlinked directory and creates the new link *inside* it. `ln -sfn` is almost always what you meant.",
            "Relative symlink targets are resolved relative to the link's directory, not your working directory — a common source of links that break when moved.",
            "macOS aliases (created in the Finder) are not symlinks; command-line tools cannot follow them. Only `ln -s` links work from a shell.",
            "Hard links cannot span volumes and cannot point at directories. Time Machine's older HFS+ backups used directory hard links, a private filesystem feature not exposed by ln.",
        ],
        "see_also": ["ls", "cp", "find", "ditto"],
        "tags": ["files", "links", "filesystem"],
    },
    {
        "command": "log",
        "tagline": "query and stream the macOS unified logging system",
        "summary": (
            "Since Sierra, macOS logging is a structured, in-memory-plus-on-disk store "
            "rather than a set of text files, and `log` is the only way to read it. "
            "`log show` queries history, `log stream` follows live. Its predicate language "
            "is the essential skill: without a filter, the volume of messages is unusable."
        ),
        "synopsis": [
            "log show [--last 1h] [--predicate 'expr'] [--info] [--debug]",
            "log stream [--predicate 'expr'] [--level info|debug]",
            "log collect [--last 1h] --output trace.logarchive",
        ],
        "options": [
            ("show", "Query historical log data"),
            ("stream", "Follow log messages as they are emitted"),
            ("--last 1h|30m|2d", "Restrict to a recent window"),
            ("--start / --end 'YYYY-MM-DD HH:MM:SS'", "Explicit time bounds"),
            ("--predicate 'expr'", "NSPredicate filter over subsystem, process, category, message"),
            ("--info / --debug", "Include info-level / debug-level messages (excluded by default)"),
            ("--style syslog|json|compact", "Output format"),
            ("--process name|pid", "Restrict to one process"),
            ("collect --output f.logarchive", "Export an archive for offline analysis or support"),
            ("--predicate 'eventMessage CONTAINS \"x\"'", "Substring match on the message text"),
        ],
        "examples": [
            ("log show --last 30m --predicate 'eventMessage CONTAINS \"error\"'", "Recent errors across the system"),
            ("log stream --predicate 'process == \"kernel\"'", "Follow kernel messages live"),
            ("log show --last 1h --predicate 'subsystem == \"com.apple.network\"' --info", "Network subsystem messages including info level"),
            ("log stream --level debug --predicate 'processImagePath CONTAINS \"MyApp\"'", "Debug one application"),
            ("log show --last boot --predicate 'senderImagePath CONTAINS \"launchd\"'", "What launchd did since the last boot"),
            ("log collect --last 2h --output ~/Desktop/trace.logarchive", "Package logs to send to a vendor"),
            ("log show --predicate 'eventMessage CONTAINS \"Sleep\"' --last 1d --style compact", "Investigate sleep/wake behaviour"),
        ],
        "notes": [
            "Info and debug messages are excluded from `log show` unless you pass `--info` / `--debug`. Missing messages are usually this, not a logging failure.",
            "Many system messages are redacted as `<private>`. Apple's logging profile can unredact them for debugging; that is a deliberate privacy control.",
            "`log show` over a long window is slow and memory-hungry. Always bound it with `--last` and a predicate.",
            "/var/log/system.log still exists but carries only a small legacy subset. Anything modern is in the unified log.",
            "Predicate fields worth knowing: process, processImagePath, subsystem, category, eventMessage, senderImagePath, messageType.",
        ],
        "see_also": ["launchctl", "tail", "system_profiler", "kill"],
        "tags": ["logging", "diagnostics", "troubleshooting", "unified-logging"],
        "category": "logging",
    },
    {
        "command": "ls",
        "tagline": "list directory contents",
        "summary": (
            "ls lists files. The BSD version on macOS has flags GNU ls lacks — notably "
            "`-@` for extended attributes and `-e` for ACLs — and lacks some GNU ones such "
            "as `--color` (macOS uses `-G` instead). Those two macOS-specific flags are "
            "what turn ls from a listing tool into a permissions diagnostic."
        ),
        "synopsis": [
            "ls [-@aAeFGhilnOrRStU] [file ...]",
        ],
        "options": [
            ("-l", "Long format: mode, links, owner, group, size, date, name"),
            ("-a / -A", "Include dotfiles / include dotfiles except . and .."),
            ("-h", "Human-readable sizes (with -l)"),
            ("-t / -S", "Sort by modification time / by size"),
            ("-r", "Reverse the sort order"),
            ("-R", "Recurse into subdirectories"),
            ("-G", "Colourise the output (macOS spelling of --color)"),
            ("-@", "Show extended attributes"),
            ("-e", "Show ACL entries"),
            ("-O", "Show macOS file flags (hidden, uchg, restricted)"),
            ("-n", "Numeric UID/GID instead of names"),
            ("-F", "Append a type indicator: / directory, * executable, @ symlink"),
            ("-d", "List a directory itself rather than its contents"),
        ],
        "examples": [
            ("ls -lah", "The everyday listing: long, all files, human sizes"),
            ("ls -lt | head", "Most recently modified files first"),
            ("ls -le /Users/Shared", "Reveal the ACLs behind a trailing + in the mode column"),
            ("ls -l@ ~/Downloads/installer.dmg", "Show extended attributes, including the quarantine flag"),
            ("ls -lO /System/Library/CoreServices", "Show macOS file flags such as `restricted` (SIP)"),
            ("ls -ld /tmp", "Inspect the directory itself — reveals that /tmp is a symlink"),
            ("ls -lS ~/Movies | head", "Largest files in a directory"),
        ],
        "notes": [
            "A trailing `+` in the mode column means an ACL is present — `ls -le` shows it. An `@` means extended attributes — `ls -l@` or `xattr -l` shows those.",
            "The `restricted` flag in `ls -lO` output marks SIP-protected files that root cannot modify.",
            "macOS uses `-G` for colour; `--color` is a GNU flag and errors out. `export CLICOLOR=1` makes colour the default.",
            "`ls` output is not safe to parse in scripts when filenames may contain spaces or newlines; use `find -print0 | xargs -0` instead.",
        ],
        "see_also": ["find", "xattr", "chmod", "du"],
        "tags": ["files", "listing", "permissions"],
    },
    {
        "command": "mdfind",
        "tagline": "search the Spotlight index from the command line",
        "summary": (
            "mdfind runs a Spotlight query and prints matching paths. Because it consults "
            "an index rather than walking the filesystem, it searches file *contents* "
            "across an entire volume in a fraction of a second — something find cannot do. "
            "The trade-off is that it only knows what Spotlight has indexed."
        ),
        "synopsis": [
            "mdfind [-onlyin dir] [-name name] [-live] [-count] query",
            "mdfind \"kMDItemAttribute == value\"",
        ],
        "options": [
            ("query", "Free-text query, matched against content and metadata"),
            ("-onlyin dir", "Restrict the search to a directory tree"),
            ("-name name", "Match on filename only"),
            ("-count", "Print the number of matches instead of the paths"),
            ("-live", "Keep running and report updates as they happen"),
            ("-literal", "Treat the query as a literal metadata expression"),
            ("-0", "NUL-separate results for `xargs -0`"),
            ("-s name", "Run a saved search"),
        ],
        "examples": [
            ("mdfind -name Halbert.png", "Find a file by name anywhere on indexed volumes"),
            ("mdfind -onlyin ~/Documents 'annual report'", "Full-text search inside a folder"),
            ("mdfind \"kMDItemContentType == 'com.adobe.pdf'\" -onlyin ~/Downloads", "Every PDF in Downloads"),
            ("mdfind \"kMDItemFSSize > 1000000000\" -onlyin /Users", "Files larger than 1 GB"),
            ("mdfind \"kMDItemKind == 'Application'\" -count", "How many applications Spotlight knows about"),
            ("mdfind -0 'invoice' | xargs -0 ls -l", "Feed results safely into another command"),
            ("mdfind \"kMDItemFSCreationDate >= \\$time.today\"", "Files created today"),
        ],
        "notes": [
            "mdfind only finds what is indexed. Excluded folders (Spotlight Privacy list), unindexed external drives and system directories return nothing — that is not a bug.",
            "Use `mdutil -s /Volumes/Name` to check whether a volume is indexed at all before concluding a file is missing.",
            "`mdls file` shows every metadata attribute of one file — the way to learn which kMDItem key to query.",
            "Content search only works for file types with a Spotlight importer; source code and plain text are covered, many binary formats are not.",
        ],
        "see_also": ["mdls", "mdutil", "find", "grep"],
        "tags": ["spotlight", "search", "metadata", "files"],
    },
    {
        "command": "mdls",
        "tagline": "list the Spotlight metadata attributes of a file",
        "summary": (
            "mdls dumps every metadata attribute Spotlight holds for a file: content type, "
            "dates, dimensions, duration, where it was downloaded from, and dozens more. "
            "It is both a forensic tool — `kMDItemWhereFroms` records a download's origin "
            "URL — and the reference you consult when building an mdfind query."
        ),
        "synopsis": [
            "mdls [-name attribute] [-raw] [-nullMarker text] file ...",
        ],
        "options": [
            ("(no options)", "Print every attribute and value"),
            ("-name attr", "Print one attribute (repeatable)"),
            ("-raw", "Print values without formatting — for scripts"),
            ("-nullMarker text", "What to print for missing values with -raw"),
            ("-plist path", "Write the attributes as a plist"),
        ],
        "examples": [
            ("mdls ~/Downloads/installer.dmg", "Every attribute of a downloaded file"),
            ("mdls -name kMDItemWhereFroms ~/Downloads/installer.dmg", "The URL a file was downloaded from"),
            ("mdls -name kMDItemContentType report.pdf", "The UTI of a file"),
            ("mdls -name kMDItemPixelWidth -name kMDItemPixelHeight photo.jpg", "Image dimensions without opening it"),
            ("mdls -raw -name kMDItemFSSize big.iso", "Size as a bare number for a script"),
            ("mdls -name kMDItemDurationSeconds movie.mp4", "Media duration"),
        ],
        "notes": [
            "`kMDItemWhereFroms` and the `com.apple.metadata:kMDItemWhereFroms` extended attribute record where a download came from — useful when auditing an unexpected file.",
            "Attributes come from Spotlight importers. A file on an unindexed volume returns almost nothing; check with `mdutil -s`.",
            "The attribute names mdls prints are exactly the keys mdfind queries accept, which makes mdls the natural first step when writing a query.",
            "`(null)` means the attribute does not apply to this file type, not that the value is empty.",
        ],
        "see_also": ["mdfind", "mdutil", "xattr", "plutil"],
        "tags": ["spotlight", "metadata", "files", "forensics"],
    },
    {
        "command": "mdutil",
        "tagline": "manage the Spotlight index on a volume",
        "summary": (
            "mdutil turns Spotlight indexing on or off per volume, reports index status, "
            "and forces a rebuild. It is the fix for the two classic Spotlight complaints: "
            "\"search finds nothing\" (indexing disabled or index corrupt) and \"my Mac is "
            "slow and mds_stores is using all the CPU\" (an index rebuild in progress)."
        ),
        "synopsis": [
            "mdutil -s volume",
            "sudo mdutil -i on|off volume",
            "sudo mdutil -E volume",
            "sudo mdutil -a -i off",
        ],
        "options": [
            ("-s", "Report indexing status for a volume"),
            ("-i on|off", "Enable or disable indexing"),
            ("-E", "Erase and rebuild the index"),
            ("-a", "Apply to all volumes"),
            ("-p", "Publish (flush) the index to disk"),
            ("-t", "Show indexing progress detail (recent macOS)"),
            ("-X", "Remove the index without rebuilding (recent macOS)"),
        ],
        "examples": [
            ("mdutil -s /", "Is the boot volume indexed?"),
            ("mdutil -as", "Status for every mounted volume"),
            ("sudo mdutil -E /", "Erase and rebuild the index of the boot volume"),
            ("sudo mdutil -i off /Volumes/Scratch", "Stop indexing a scratch or backup volume"),
            ("sudo mdutil -i on /Volumes/Data", "Re-enable indexing"),
            ("ps aux | grep mds_stores", "Confirm an index rebuild is what is consuming CPU"),
        ],
        "notes": [
            "A rebuild (`-E`) can take hours on a large volume and will keep mds and mds_stores busy the whole time. Start it when the machine is not needed.",
            "\"Indexing disabled\" on an external drive is often intentional — Time Machine destinations and clone targets are normally excluded.",
            "The Spotlight Privacy list in System Settings and mdutil are separate mechanisms; a folder can be excluded there while the volume is indexed.",
            "The index lives in /.Spotlight-V100 at the root of each volume; `sudo mdutil -X` removes it outright on recent releases.",
        ],
        "see_also": ["mdfind", "mdls", "diskutil", "log"],
        "tags": ["spotlight", "index", "maintenance", "performance"],
        "category": "system_admin",
    },
    {
        "command": "mkdir",
        "tagline": "create directories",
        "summary": (
            "mkdir creates directories. Two flags carry almost all of its practical value: "
            "`-p` creates intermediate directories and does not complain if the target "
            "already exists, which makes scripts idempotent, and `-m` sets permissions "
            "atomically rather than leaving a window where the directory is world-readable."
        ),
        "synopsis": [
            "mkdir [-pv] [-m mode] directory ...",
        ],
        "options": [
            ("-p", "Create parent directories as needed; no error if it already exists"),
            ("-m mode", "Set permissions at creation time"),
            ("-v", "Print each directory created"),
        ],
        "examples": [
            ("mkdir project", "Create one directory"),
            ("mkdir -p ~/src/app/config", "Create a nested path in one step"),
            ("mkdir -m 700 ~/.secrets", "Create a private directory without a permissions race"),
            ("mkdir -pv ~/backups/{daily,weekly,monthly}", "Brace expansion creates several at once"),
            ("mkdir -p \"$HOME/Library/Application Support/MyApp\"", "Idempotent setup line for a script"),
        ],
        "notes": [
            "`mkdir -p` is the idempotent form — it succeeds when the directory already exists, so scripts do not need a preceding test.",
            "`mkdir -m 700` is safer than `mkdir` followed by `chmod 700`: the latter leaves a brief window at the umask default.",
            "Brace expansion (`{a,b,c}`) is a shell feature, so it works in zsh and bash but not when mkdir is invoked directly by another program.",
            "Creating directories under /System or other SIP-protected paths fails even with sudo.",
        ],
        "see_also": ["rmdir", "chmod", "ln", "touch"],
        "tags": ["files", "directories"],
    },
    {
        "command": "mv",
        "tagline": "move or rename files and directories",
        "summary": (
            "mv renames a file, or moves it to another directory. Within one filesystem it "
            "is instantaneous — only the directory entry changes. Across filesystems it is "
            "a copy followed by a delete, which means it can fail part-way and takes as "
            "long as the data is large. It silently overwrites the destination unless you "
            "ask it not to."
        ),
        "synopsis": [
            "mv [-f|-i|-n] [-v] source ... target",
        ],
        "options": [
            ("-i", "Prompt before overwriting"),
            ("-n", "Never overwrite an existing file"),
            ("-f", "Overwrite without prompting (the default)"),
            ("-v", "Print each move"),
            ("-h", "Do not follow a symlink at the target path"),
        ],
        "examples": [
            ("mv draft.txt final.txt", "Rename a file"),
            ("mv ~/Downloads/*.pdf ~/Documents/Invoices/", "Move matching files into a directory"),
            ("mv -n new/* existing/", "Move without clobbering anything already present"),
            ("mv -iv old_project ~/Archive/", "Move a directory, prompting and reporting"),
            ("mv \"file with spaces.txt\" renamed.txt", "Quote paths containing spaces"),
        ],
        "notes": [
            "mv overwrites the destination without asking by default. Add `-i` interactively or `-n` in scripts; there is no undo.",
            "Moving across volumes copies then deletes, so an interrupted move can leave a partial file at the destination. Prefer `rsync --remove-source-files` for large cross-volume moves.",
            "mv preserves extended attributes and ACLs within a filesystem; across filesystems the same caveats as cp apply.",
            "A file whose name begins with `-` needs `mv -- -weird.txt normal.txt` or `mv ./-weird.txt ...`.",
        ],
        "see_also": ["cp", "rm", "ditto", "ln"],
        "tags": ["files", "rename", "move"],
    },
    {
        "command": "netstat",
        "tagline": "show network connections, routes and interface statistics",
        "summary": (
            "netstat reports sockets, routing tables and per-interface counters. On macOS "
            "the BSD version does not accept `-p tcp` combined with process names the way "
            "Linux's does — to map a port to a process, `lsof -i` is the tool. netstat "
            "remains the fastest way to read the routing table and spot interface errors."
        ),
        "synopsis": [
            "netstat -an [-p proto]",
            "netstat -rn",
            "netstat -i / netstat -s",
        ],
        "options": [
            ("-a", "Show all sockets, including listening ones"),
            ("-n", "Numeric addresses and ports — avoids slow reverse lookups"),
            ("-r", "Show the routing table"),
            ("-i", "Per-interface packet and error counters"),
            ("-s", "Per-protocol statistics"),
            ("-p proto", "Restrict to a protocol: tcp, udp, icmp"),
            ("-f inet|inet6", "Restrict to an address family"),
            ("-b", "Show bytes in/out per interface (with -i)"),
        ],
        "examples": [
            ("netstat -an | grep LISTEN", "Every listening socket"),
            ("netstat -rn", "The routing table, including the default gateway"),
            ("netstat -rn | grep default", "Just the default route — the quickest 'which way out?' check"),
            ("netstat -i", "Interface counters; non-zero Ierrs/Oerrs points at a cabling or driver fault"),
            ("netstat -s -p tcp | head -20", "TCP statistics: retransmits, resets, failed connections"),
            ("lsof -nP -iTCP -sTCP:LISTEN", "Which process owns each listening port — netstat cannot tell you on macOS"),
        ],
        "notes": [
            "BSD netstat does not show the owning process. Use `sudo lsof -i :8080` or `lsof -nP -iTCP -sTCP:LISTEN` for that.",
            "Always add `-n`. Without it netstat performs a reverse DNS lookup per address and can appear to hang.",
            "`netstat -rn` is the routing table; a missing default route explains 'connected but no internet' better than any ping.",
            "Growing values in `netstat -s -p tcp` for retransmits indicate packet loss on the path, not a problem on the Mac itself.",
        ],
        "see_also": ["ifconfig", "ping", "traceroute", "scutil"],
        "tags": ["network", "sockets", "routing", "diagnostics"],
        "category": "networking",
    },
    {
        "command": "networksetup",
        "tagline": "configure network settings persistently",
        "summary": (
            "networksetup is the scriptable equivalent of the Network pane in System "
            "Settings. Unlike ifconfig, changes it makes are stored in the system "
            "configuration database and survive reboots and network location changes. It "
            "operates on *service* names — \"Wi-Fi\", \"Ethernet\" — rather than device names "
            "like en0."
        ),
        "synopsis": [
            "networksetup -listallnetworkservices",
            "networksetup -getinfo service",
            "sudo networksetup -setdhcp service",
            "sudo networksetup -setmanual service ip mask router",
            "sudo networksetup -setdnsservers service addr ...",
        ],
        "options": [
            ("-listallnetworkservices", "List configurable services in priority order"),
            ("-listallhardwareports", "Map service names to device names and MAC addresses"),
            ("-getinfo service", "Address, mask, router and MAC for a service"),
            ("-setdhcp service", "Switch a service to DHCP"),
            ("-setmanual service ip mask router", "Set a static configuration"),
            ("-getdnsservers / -setdnsservers service ...", "Read or set DNS servers (`Empty` clears)"),
            ("-getsearchdomains / -setsearchdomains", "Read or set DNS search domains"),
            ("-setairportpower device on|off", "Turn Wi-Fi radio on or off"),
            ("-setairportnetwork device ssid [password]", "Join a Wi-Fi network"),
            ("-getairportnetwork device", "Which SSID is joined"),
            ("-listpreferredwirelessnetworks device", "Saved Wi-Fi networks"),
            ("-setwebproxy / -setsecurewebproxy service host port", "Configure HTTP/HTTPS proxies"),
            ("-ordernetworkservices ...", "Set the service priority order"),
        ],
        "examples": [
            ("networksetup -listallnetworkservices", "See the exact service names to use in other commands"),
            ("networksetup -listallhardwareports", "Map \"Wi-Fi\" to en0 (or en1) on this particular Mac"),
            ("networksetup -getinfo \"Wi-Fi\"", "Current address, mask, router and MAC"),
            ("sudo networksetup -setdnsservers \"Wi-Fi\" 1.1.1.1 9.9.9.9", "Set DNS servers persistently"),
            ("sudo networksetup -setdnsservers \"Wi-Fi\" Empty", "Revert to DHCP-supplied DNS"),
            ("sudo networksetup -setmanual \"Ethernet\" 192.168.1.50 255.255.255.0 192.168.1.1", "Assign a static address"),
            ("networksetup -getairportnetwork en0", "Which Wi-Fi network is joined"),
            ("sudo networksetup -setairportpower en0 off", "Turn the Wi-Fi radio off"),
        ],
        "notes": [
            "Service names are user-visible strings and may have been renamed. Always confirm with `-listallnetworkservices` before scripting against \"Wi-Fi\".",
            "A leading asterisk in the service list means the service is disabled.",
            "This is the persistent counterpart to ifconfig: use networksetup to change configuration, ifconfig to observe the resulting state.",
            "Passing a Wi-Fi password on the command line puts it in your shell history and in `ps` output for other users to see.",
            "Changes may take a few seconds to apply; `ipconfig getifaddr` is a good way to poll for the result.",
        ],
        "see_also": ["ifconfig", "ipconfig", "scutil", "dig"],
        "tags": ["network", "configuration", "wifi", "dns"],
        "category": "networking",
    },
    {
        "command": "open",
        "tagline": "open files, directories and URLs with the default application",
        "summary": (
            "open hands a path or URL to Launch Services, which decides what should handle "
            "it — exactly as a double-click in the Finder would. It bridges the terminal "
            "and the GUI: reveal a file in the Finder, open a URL in the browser, launch an "
            "app with arguments, or start a second instance of one."
        ),
        "synopsis": [
            "open [-a application] [-e|-t] [-R] [-n] [-g] [-W] file|url ...",
            "open .",
        ],
        "options": [
            ("(no options)", "Open with the default handler for the file type"),
            ("-a app", "Open with a named application"),
            ("-b bundle.id", "Open with an application identified by bundle id"),
            ("-e / -t", "Open in TextEdit / in the default text editor"),
            ("-R", "Reveal in the Finder instead of opening"),
            ("-n", "Open a new instance even if the app is running"),
            ("-g", "Open in the background, without stealing focus"),
            ("-W", "Wait until the application quits before returning"),
            ("-F", "Open a fresh instance, ignoring restored windows"),
            ("--args ...", "Pass the remaining arguments to the application"),
        ],
        "examples": [
            ("open .", "Open the current directory in the Finder"),
            ("open -R ~/Downloads/report.pdf", "Reveal a file in the Finder without opening it"),
            ("open https://example.com", "Open a URL in the default browser"),
            ("open -a \"Visual Studio Code\" .", "Open the current directory in a named application"),
            ("open -a Safari -n", "Start a second Safari instance"),
            ("open -e /etc/hosts", "Open a file in TextEdit"),
            ("open -b com.apple.systempreferences", "Launch an app by bundle identifier"),
            ("open \"x-apple.systempreferences:com.apple.preference.security\"", "Jump straight to a System Settings pane"),
        ],
        "notes": [
            "`open .` is the fastest bridge from a terminal path to the Finder, and `open -R` is its inverse for a single file.",
            "Editing a root-owned file with `open -e` will fail to save — TextEdit runs as you. Use `sudo nano` or an editor that can authenticate.",
            "`open -W -a App file` blocks until the app quits, which makes it usable as a $EDITOR for git commit messages.",
            "URL schemes work too: `open vscode://...`, `open mailto:...`, `open x-apple.systempreferences:...` for settings panes.",
        ],
        "see_also": ["defaults", "osascript", "pbcopy", "launchctl"],
        "tags": ["gui", "launch-services", "files", "urls"],
    },
    {
        "command": "osascript",
        "tagline": "run AppleScript and JavaScript for Automation from the shell",
        "summary": (
            "osascript executes AppleScript or JXA (JavaScript for Automation), which is "
            "how the command line reaches into GUI applications — displaying dialogs, "
            "driving Mail or Finder, or reading a running app's state. It is also the "
            "standard way for a shell script to show a native notification or prompt for "
            "input."
        ),
        "synopsis": [
            "osascript [-l language] [-e statement ...] [file] [args]",
            "osascript -e 'tell application \"Finder\" to ...'",
        ],
        "options": [
            ("-e statement", "Run a single line of script (repeatable for multi-line)"),
            ("-l AppleScript|JavaScript", "Choose the language; AppleScript is the default"),
            ("-s o|h|e|s", "Output style: object, human-readable, error handling, recompilable"),
            ("file.scpt / file.applescript", "Run a script from a file"),
            ("(trailing args)", "Passed to the script's `on run argv` handler"),
        ],
        "examples": [
            ("osascript -e 'display notification \"Build finished\" with title \"Halbert\"'", "Post a native notification from a script"),
            ("osascript -e 'display dialog \"Continue?\" buttons {\"No\",\"Yes\"} default button \"Yes\"'", "Prompt the user with a native dialog"),
            ("osascript -e 'tell application \"Finder\" to get POSIX path of (target of front window as alias)'", "Path of the frontmost Finder window"),
            ("osascript -e 'set volume output volume 25'", "Set the system output volume"),
            ("osascript -l JavaScript -e 'Application(\"Safari\").windows[0].currentTab.url()'", "Read the front Safari tab's URL with JXA"),
            ("osascript -e 'tell application \"System Events\" to keystroke \"s\" using command down'", "Send a keystroke (requires Accessibility permission)"),
            ("osascript -e 'tell app \"System Events\" to sleep'", "Put the Mac to sleep"),
        ],
        "notes": [
            "Anything that drives another application needs an Automation permission grant, and `System Events` keystroke tricks additionally need Accessibility. The prompt appears once, for the parent app — usually Terminal or your IDE — and is then remembered in TCC.",
            "In a LaunchDaemon (system context) there is no GUI session, so osascript cannot display dialogs. Use a LaunchAgent instead.",
            "Multiple `-e` flags build a multi-line script; a heredoc into `osascript` is cleaner for anything longer.",
            "`display dialog` returns the button and any text entered on stdout, so it can be captured in a shell variable.",
        ],
        "see_also": ["open", "defaults", "launchctl", "security"],
        "tags": ["automation", "applescript", "gui", "scripting"],
    },
    {
        "command": "passwd",
        "tagline": "change a user's password",
        "summary": (
            "passwd changes the login password of an account. On macOS the password is "
            "held in the directory services database, not /etc/shadow, and it is also the "
            "key that unlocks the login keychain and — on a FileVault-enabled Mac — the "
            "volume itself. Changing it by the wrong route leaves those out of sync."
        ),
        "synopsis": [
            "passwd [user]",
            "sudo passwd user",
            "sysadminctl -resetPasswordFor user -newPassword pass",
        ],
        "options": [
            ("(no argument)", "Change your own password; prompts for the old one first"),
            ("user", "Change another user's password (requires root)"),
            ("-i directory", "Specify the directory node (`file`, `NIS`, `opendirectory`)"),
            ("-u user", "Specify the user for the chosen infrastructure"),
        ],
        "examples": [
            ("passwd", "Change your own password interactively"),
            ("sudo passwd alice", "Reset another user's password as an administrator"),
            ("dscl . -authonly alice", "Verify a password without changing it"),
            ("sudo sysadminctl -resetPasswordFor alice -newPassword '...' -adminUser admin -adminPassword '...'", "Reset a password non-interactively, the supported modern route"),
        ],
        "notes": [
            "Resetting another user's password with sudo does *not* update their login keychain — the next login will prompt \"the system was unable to unlock your keychain\". They must enter the old password once, or the keychain must be reset.",
            "On a FileVault Mac, the password is also a volume unlock credential. Use System Settings or `sysadminctl` so the FileVault key is updated too; a mismatched password can leave the account unable to unlock at boot.",
            "Password policy (length, complexity) may be enforced by an MDM profile; `pwpolicy -getaccountpolicies` shows what is in force.",
            "Passing a password on the command line exposes it in shell history and in `ps` output.",
        ],
        "see_also": ["dscl", "security", "id", "su"],
        "tags": ["users", "passwords", "security", "keychain"],
        "category": "security",
    },
    {
        "command": "pbcopy",
        "tagline": "copy standard input to the macOS clipboard",
        "summary": (
            "pbcopy reads standard input and places it on the pasteboard, making command "
            "output pasteable into any application. It is one half of a pair with pbpaste "
            "and is one of the most quietly useful macOS-only commands — the reason so many "
            "macOS instructions end in `| pbcopy`."
        ),
        "synopsis": [
            "command | pbcopy [-pboard general|ruler|find|font]",
        ],
        "options": [
            ("-pboard name", "Target a specific pasteboard; `general` is the normal clipboard"),
            ("-Prefer txt|rtf|ps", "Preferred flavour when the input could be interpreted several ways"),
        ],
        "examples": [
            ("cat ~/.ssh/id_ed25519.pub | pbcopy", "Copy a public key ready to paste into a web form"),
            ("pwd | pbcopy", "Copy the current path"),
            ("git log -1 --format=%H | pbcopy", "Copy the latest commit hash"),
            ("system_profiler SPHardwareDataType | pbcopy", "Copy hardware details for a support ticket"),
            ("pbpaste | tr 'A-Z' 'a-z' | pbcopy", "Lowercase the clipboard in place"),
            ("ioreg -l | grep -i serial | pbcopy", "Copy diagnostic output without selecting it by hand"),
        ],
        "notes": [
            "pbcopy copies exactly what it receives, trailing newline included. `printf '%s' \"$x\" | pbcopy` avoids the stray newline when pasting into a password field.",
            "It reads standard input only — `pbcopy file.txt` does nothing useful; use `pbcopy < file.txt`.",
            "Over SSH, pbcopy runs on the *remote* Mac. To reach the local clipboard, pipe through ssh in the other direction or use your terminal's clipboard integration.",
            "Copying a secret puts it on the pasteboard where any running app can read it; clear it afterwards with `: | pbcopy`.",
        ],
        "see_also": ["pbpaste", "open", "osascript"],
        "tags": ["clipboard", "pasteboard", "io"],
    },
    {
        "command": "pbpaste",
        "tagline": "write the macOS clipboard contents to standard output",
        "summary": (
            "pbpaste prints whatever is on the pasteboard, letting shell commands consume "
            "what you just copied from a GUI app. Combined with pbcopy it turns the "
            "clipboard into an ordinary Unix pipe endpoint, which is the trick behind most "
            "\"transform the clipboard\" one-liners."
        ),
        "synopsis": [
            "pbpaste [-pboard general|ruler|find|font] [-Prefer txt|rtf|ps]",
        ],
        "options": [
            ("-pboard name", "Read from a specific pasteboard"),
            ("-Prefer txt|rtf|ps", "Preferred flavour when several are available"),
        ],
        "examples": [
            ("pbpaste", "Print the clipboard"),
            ("pbpaste > snippet.txt", "Save the clipboard to a file"),
            ("pbpaste | wc -l", "Count the lines you just copied"),
            ("pbpaste | jq .", "Pretty-print copied JSON"),
            ("pbpaste | pbcopy", "Strip formatting — round-tripping through plain text"),
            ("pbpaste -Prefer txt | grep -i error", "Search copied log output"),
        ],
        "notes": [
            "By default pbpaste returns the plain-text flavour. Rich text copied from a word processor comes through as its text representation unless you ask for `-Prefer rtf`.",
            "`pbpaste | pbcopy` is the quickest way to strip formatting from copied text before pasting into an editor.",
            "Non-text clipboard contents (an image copied from Preview) produce nothing useful; check with `osascript -e 'clipboard info'`.",
            "Over SSH, pbpaste reads the remote Mac's clipboard, not yours.",
        ],
        "see_also": ["pbcopy", "open", "osascript"],
        "tags": ["clipboard", "pasteboard", "io"],
    },
    {
        "command": "ping",
        "tagline": "test reachability with ICMP echo requests",
        "summary": (
            "ping sends ICMP echo requests and reports which come back and how long they "
            "took. It answers three questions at once: does the name resolve, is the host "
            "reachable, and what is the latency and loss on the path. On macOS ping runs "
            "forever unless you bound it with `-c`."
        ),
        "synopsis": [
            "ping [-c count] [-i interval] [-t timeout] [-s size] [-S source] host",
        ],
        "options": [
            ("-c N", "Stop after N packets"),
            ("-i N", "Seconds between packets (sub-second intervals need root)"),
            ("-t N", "Stop after N seconds"),
            ("-s N", "Payload size in bytes — used for MTU testing"),
            ("-D", "Set the Don't Fragment bit"),
            ("-S addr", "Send from a specific source address"),
            ("-n", "Numeric output only, no reverse lookups"),
            ("-q", "Quiet — summary only"),
        ],
        "examples": [
            ("ping -c 4 example.com", "Four packets and a summary"),
            ("ping -c 3 $(netstat -rn | awk '/^default/{print $2; exit}')", "Ping the default gateway"),
            ("ping -c 100 -i 0.2 -q 1.1.1.1", "Twenty-second loss test, summary only"),
            ("ping -c 3 -s 1472 -D example.com", "Probe for an MTU problem — 1472 + 28 = 1500"),
            ("ping -c 1 -t 2 host.local || echo unreachable", "Scriptable reachability check with a timeout"),
        ],
        "notes": [
            "Many hosts and firewalls drop ICMP. \"No reply\" proves nothing on its own — test the actual service port with `nc -vz host port` before concluding the host is down.",
            "Without `-c` or `-t`, ping runs until interrupted. Ctrl-C prints the loss and latency summary.",
            "A ping to the gateway succeeding while a ping to 1.1.1.1 fails isolates the fault beyond your LAN; if the IP works but the name does not, it is DNS.",
            "The `-D` flag with a tuned `-s` is the classic path-MTU test: the largest size that gets through, plus 28 bytes of header, is the path MTU.",
        ],
        "see_also": ["traceroute", "netstat", "dig", "ifconfig"],
        "tags": ["network", "diagnostics", "icmp", "latency"],
        "category": "networking",
    },
    {
        "command": "pkgutil",
        "tagline": "query and manage installer packages and receipts",
        "summary": (
            "pkgutil works with the receipts macOS keeps for every installed .pkg. It "
            "answers what a package installed, where, and when — and can forget a receipt "
            "so a stubborn installer will run again. It also expands and flattens package "
            "archives, which is how you inspect what a package will do before running it."
        ),
        "synopsis": [
            "pkgutil --pkgs [regex]",
            "pkgutil --pkg-info id / --files id",
            "sudo pkgutil --forget id",
            "pkgutil --expand-full pkg dir / --flatten dir pkg",
        ],
        "options": [
            ("--pkgs [regex]", "List installed package identifiers"),
            ("--pkg-info id", "Version, install date and install location"),
            ("--files id", "Every file the package installed, relative to its location"),
            ("--file-info path", "Which package claims a given file"),
            ("--forget id", "Remove the receipt (does not delete files)"),
            ("--expand pkg dir / --expand-full pkg dir", "Unpack a package for inspection"),
            ("--flatten dir pkg", "Repackage an expanded directory"),
            ("--check-signature pkg", "Verify a package's signature"),
            ("--verbose", "More detail in listings"),
        ],
        "examples": [
            ("pkgutil --pkgs | grep -i vendor", "Find a vendor's installed packages"),
            ("pkgutil --pkg-info com.example.tool", "Version and install date"),
            ("pkgutil --files com.example.tool", "Every file the package placed on disk"),
            ("pkgutil --files com.example.tool | sed 's|^|/|' | xargs -I{} sudo rm -f {}", "Manual uninstall, after reviewing the file list"),
            ("sudo pkgutil --forget com.example.tool", "Forget the receipt so the installer will run again"),
            ("pkgutil --check-signature ~/Downloads/Tool.pkg", "Verify who signed a package before installing"),
            ("pkgutil --expand-full ~/Downloads/Tool.pkg /tmp/tool && ls /tmp/tool", "Inspect the scripts a package will run as root"),
        ],
        "notes": [
            "`--forget` removes only the receipt. Files stay on disk; list them with `--files` first and remove them deliberately.",
            "`--files` returns paths relative to the package's install location — prefix them with the value from `--pkg-info` before deleting anything.",
            "`--expand-full` is the right first move for an unfamiliar .pkg: preinstall and postinstall scripts run as root, and this is how you read them beforehand.",
            "Receipts live in /var/db/receipts. A package that \"is already installed\" but is clearly missing usually has a stale receipt there.",
        ],
        "see_also": ["installer", "brew", "codesign", "spctl"],
        "tags": ["package-management", "receipts", "uninstall"],
        "category": "package_management",
    },
    {
        "command": "plutil",
        "tagline": "inspect, validate and convert property list files",
        "summary": (
            "plutil reads and rewrites .plist files, which macOS uses for preferences, "
            "launchd jobs, app metadata and much else. Most plists on disk are binary and "
            "unreadable in a text editor; plutil converts them to XML or JSON, checks their "
            "syntax before launchd rejects them, and can edit individual keys."
        ),
        "synopsis": [
            "plutil -lint file.plist",
            "plutil -p file.plist",
            "plutil -convert xml1|binary1|json file.plist [-o out]",
            "plutil -extract keypath raw|xml1|json file.plist",
            "plutil -replace keypath -type value file.plist",
        ],
        "options": [
            ("-lint", "Validate syntax — do this before loading any launchd plist"),
            ("-p", "Print in a human-readable form (not valid plist output)"),
            ("-convert fmt", "Convert to xml1, binary1, json or swift"),
            ("-o path", "Write elsewhere instead of converting in place; `-` means stdout"),
            ("-extract keypath fmt", "Pull one value out"),
            ("-insert / -replace keypath -type value", "Add or change a key"),
            ("-remove keypath", "Delete a key"),
            ("-type", "Report the top-level type"),
        ],
        "examples": [
            ("plutil -p /Applications/Safari.app/Contents/Info.plist | head -20", "Read a binary plist without converting it"),
            ("plutil -lint ~/Library/LaunchAgents/com.example.agent.plist", "Catch a syntax error before launchd does"),
            ("plutil -convert xml1 -o - settings.plist", "Print a binary plist as XML without modifying the file"),
            ("plutil -extract CFBundleShortVersionString raw /Applications/Safari.app/Contents/Info.plist", "Read an app's version string"),
            ("plutil -convert json -o - config.plist | jq .", "Convert to JSON and query with jq"),
            ("plutil -replace RunAtLoad -bool true com.example.agent.plist", "Change one key in place"),
        ],
        "notes": [
            "`plutil -p` output looks like JSON but is not — it is a display format. Use `-convert json` when a machine has to read it.",
            "`plutil -lint` is the single best habit when writing launchd jobs: launchd's own error for a malformed plist is unhelpfully vague.",
            "Editing a preferences plist directly can be overwritten by cfprefsd. Use `defaults write` for preference domains, plutil for standalone plists such as launchd jobs and Info.plist.",
            "Converting in place with `-convert binary1` is safe and shrinks large plists; converting to `xml1` makes them diffable in version control.",
        ],
        "see_also": ["defaults", "launchctl", "pkgutil", "mdls"],
        "tags": ["plist", "configuration", "xml", "json"],
        "category": "system_admin",
    },
    {
        "command": "pmset",
        "tagline": "configure power management and inspect power state",
        "summary": (
            "pmset controls sleep, display sleep, wake schedules and hibernation, and "
            "reports what is currently keeping the Mac awake. Settings are stored per power "
            "source — battery, charger, UPS — so a change usually needs to say which one it "
            "applies to. `pmset -g assertions` is the definitive answer to \"why won't this "
            "Mac sleep?\"."
        ),
        "synopsis": [
            "pmset -g [live|assertions|log|sched|batt|custom]",
            "sudo pmset -a|-b|-c|-u setting value",
            "sudo pmset repeat wakeorpoweron MTWRFSU HH:MM:SS",
        ],
        "options": [
            ("-g", "Show current settings"),
            ("-g assertions", "Show power assertions and which process holds each"),
            ("-g log", "Sleep/wake history — why the Mac woke and what stopped it sleeping"),
            ("-g batt", "Battery charge, state and time remaining"),
            ("-g sched", "Scheduled wake and power events"),
            ("-a / -b / -c / -u", "Apply to all sources / battery / charger / UPS"),
            ("sleep N / displaysleep N", "Idle minutes before system or display sleep (0 disables)"),
            ("disksleep N", "Idle minutes before disks spin down"),
            ("standby 0|1 / hibernatemode N", "Standby and hibernation behaviour"),
            ("womp 0|1", "Wake for network access (Wake on LAN)"),
            ("powernap 0|1", "Allow Power Nap"),
            ("schedule / repeat", "One-off or recurring wake and shutdown events"),
        ],
        "examples": [
            ("pmset -g", "Current power settings for the active source"),
            ("pmset -g assertions", "Which process is preventing sleep right now"),
            ("pmset -g log | grep -i 'wake reason' | tail -20", "Why the Mac has been waking up"),
            ("pmset -g batt", "Battery percentage and whether it is charging"),
            ("sudo pmset -c displaysleep 30 sleep 0", "On mains: display off after 30 minutes, never sleep"),
            ("sudo pmset -b sleep 10 displaysleep 5", "On battery: aggressive sleep"),
            ("sudo pmset repeat wakeorpoweron MTWRF 08:30:00", "Wake every weekday morning"),
            ("sudo pmset -a womp 1", "Enable Wake on LAN"),
        ],
        "notes": [
            "`pmset -g assertions` names the process holding each assertion — that is how you find the app (often a browser or a backup agent) keeping the machine awake.",
            "Settings are per power source. `pmset -a` changes all of them; `-b` and `-c` are usually what you want on a laptop.",
            "`sleep 0` means never sleep, not sleep immediately.",
            "Apple Silicon Macs ignore several Intel-era keys (hibernatemode, standbydelay); they appear in output but do nothing.",
            "Scheduled wake events survive reboot and are visible in `pmset -g sched`; clear them with `sudo pmset repeat cancel`.",
        ],
        "see_also": ["caffeinate", "system_profiler", "log", "sysctl"],
        "tags": ["power", "sleep", "battery", "energy"],
        "category": "power_management",
    },
    {
        "command": "ps",
        "tagline": "report a snapshot of running processes",
        "summary": (
            "ps prints the processes running at the instant it is invoked. macOS ships BSD "
            "ps, so the classic `ps aux` works but some GNU/procps options do not. It is "
            "the tool for a scriptable snapshot; `top` is the tool for watching change over "
            "time."
        ),
        "synopsis": [
            "ps aux",
            "ps -ef",
            "ps -p pid -o pid,ppid,%cpu,%mem,command",
        ],
        "options": [
            ("a", "Processes of all users"),
            ("u", "User-oriented format with CPU and memory percentages"),
            ("x", "Include processes without a controlling terminal"),
            ("-e", "Every process (System V style)"),
            ("-f", "Full format, including the parent PID"),
            ("-p pid", "One process"),
            ("-u user", "Processes of a given user"),
            ("-o fields", "Choose output columns: pid, ppid, %cpu, %mem, rss, etime, user, command"),
            ("-r / -m", "Sort by CPU usage / by memory usage"),
            ("-w / -ww", "Wider output — do not truncate long command lines"),
            ("ww eww pid", "Show a process's environment as well"),
        ],
        "examples": [
            ("ps aux | head", "The standard snapshot"),
            ("ps aux -r | head -10", "Ten heaviest CPU consumers"),
            ("ps aux -m | head -10", "Ten heaviest memory consumers"),
            ("ps -p 4321 -o pid,ppid,user,etime,command", "Details of one process, including how long it has run"),
            ("ps -ef | grep -i [n]ode", "Find node processes without matching grep itself"),
            ("ps -o command= -p $(pgrep -x Safari | head -1)", "Full command line of a running app"),
            ("ps auxww | grep -v grep | grep helper", "Untruncated command lines when the interesting part is at the end"),
        ],
        "notes": [
            "BSD-style flags (`aux`) take no dash; System V-style flags (`-ef`) do. Mixing them produces confusing errors.",
            "Command lines are truncated to the terminal width unless you add `ww`.",
            "`%CPU` in ps is an average over the process's lifetime, not an instantaneous reading — `top` is the right tool for current load.",
            "`pgrep`/`pkill` avoid the grep-matches-itself problem entirely and accept `-f` to match the full command line.",
        ],
        "see_also": ["top", "kill", "launchctl", "log"],
        "tags": ["process", "monitoring", "diagnostics"],
        "category": "system_admin",
    },
    {
        "command": "pwd",
        "tagline": "print the working directory",
        "summary": (
            "pwd prints the directory you are currently in. On macOS the distinction "
            "between its logical and physical forms matters more than on most systems, "
            "because /tmp, /etc and /var are all symlinks into /private — so the same "
            "location has two legitimate names."
        ),
        "synopsis": [
            "pwd [-L|-P]",
        ],
        "options": [
            ("-L", "Logical — the path as you navigated it, symlinks intact (default)"),
            ("-P", "Physical — symlinks resolved to real paths"),
        ],
        "examples": [
            ("pwd", "Current directory"),
            ("cd /tmp && pwd -P", "Prints /private/tmp — the real location behind the symlink"),
            ("echo \"$PWD\"", "The shell variable holding the same value, no subprocess needed"),
            ("basename \"$PWD\"", "Just the current directory's name"),
            ("cd \"$(dirname \"$(pwd -P)\")\"", "Move to the physical parent, avoiding symlink surprises"),
        ],
        "notes": [
            "`pwd` is both a shell builtin and /bin/pwd. The builtin honours the shell's idea of the path; the binary always reports the physical one unless given -L.",
            "Scripts that compare paths should normalise with `pwd -P`, or /tmp and /private/tmp will look like different directories.",
            "$PWD is maintained by the shell and avoids forking a process — preferable inside loops.",
            "If the current directory is deleted while you are in it, pwd fails; `cd .` will not recover, but `cd $HOME` will.",
        ],
        "see_also": ["cd", "ls", "find"],
        "tags": ["shell", "navigation", "builtin"],
    },
    {
        "command": "rm",
        "tagline": "remove files and directories",
        "summary": (
            "rm deletes files. There is no Trash and no undo — the data is gone as soon as "
            "the last link to it is removed and no process holds it open. The two habits "
            "that prevent disasters: never type a wildcard next to a slash without reading "
            "the line back, and prefer `-i` or a dry run with `ls` when the pattern is "
            "generated rather than typed."
        ),
        "synopsis": [
            "rm [-f|-i] [-dPRrvW] file ...",
            "rm -rf directory",
        ],
        "options": [
            ("-r / -R", "Recurse into directories"),
            ("-f", "Force — no prompts, no error for missing files"),
            ("-i", "Prompt before every removal"),
            ("-I", "Prompt once before removing more than three files or recursing"),
            ("-d", "Remove empty directories as well as files"),
            ("-v", "Report each removal"),
            ("-P", "Overwrite before unlinking (meaningless on SSDs)"),
        ],
        "examples": [
            ("rm old.txt", "Delete one file"),
            ("rm -i *.log", "Delete with a prompt for each"),
            ("rm -rI build/", "Recursive delete with a single confirmation"),
            ("ls ~/tmp/*.bak && rm ~/tmp/*.bak", "Look at what the glob matches before deleting it"),
            ("find . -name '*.tmp' -print -delete", "Print and delete in one pass, so the log shows exactly what went"),
            ("rm -- -weird-file", "Delete a file whose name starts with a dash"),
        ],
        "notes": [
            "`rm -rf /` and its near misses (`rm -rf $VAR/` with VAR unset) are the classic catastrophes. Quote and test variables: `rm -rf \"${DIR:?}/\"` refuses to run if DIR is empty.",
            "rm bypasses the Trash entirely. To move to the Trash instead, use Finder, or `osascript -e 'tell app \"Finder\" to delete POSIX file \"...\"'`.",
            "SIP-protected paths refuse deletion even under sudo — that is by design, not a permissions bug.",
            "`-P` overwriting is pointless on flash storage because of wear levelling; for real erasure, rely on FileVault and destroy the key.",
            "Deleting a file that a process still has open frees no space until that process exits — `lsof +L1` finds these.",
        ],
        "see_also": ["rmdir", "mv", "find", "diskutil"],
        "tags": ["files", "delete", "destructive"],
    },
    {
        "command": "rmdir",
        "tagline": "remove empty directories",
        "summary": (
            "rmdir removes a directory only if it is empty, which makes it the safe "
            "counterpart to `rm -r`. Its refusal to delete anything containing files is a "
            "feature: scripts that clean up their own scratch directories can use it "
            "without risking data."
        ),
        "synopsis": [
            "rmdir [-p] [-v] directory ...",
        ],
        "options": [
            ("-p", "Also remove parent directories that become empty"),
            ("-v", "Report each removal"),
        ],
        "examples": [
            ("rmdir empty_dir", "Remove one empty directory"),
            ("rmdir -p a/b/c", "Remove c, then b, then a, stopping at the first non-empty one"),
            ("find . -type d -empty -delete", "Remove every empty directory in a tree, deepest first"),
            ("rmdir -v build 2>/dev/null || echo 'not empty'", "Safe cleanup that reports rather than forcing"),
        ],
        "notes": [
            "\"Directory not empty\" on a directory that looks empty usually means a hidden file — check with `ls -a`. A stray .DS_Store is the usual culprit.",
            "rmdir is preferable to `rm -r` in scripts precisely because it fails loudly instead of deleting unexpected content.",
            "`find . -type d -empty -delete` processes depth-first, so nested empty directories collapse in one pass.",
        ],
        "see_also": ["rm", "mkdir", "find", "ls"],
        "tags": ["files", "directories", "cleanup"],
    },
    {
        "command": "screencapture",
        "tagline": "capture the screen to a file, the clipboard or a stream",
        "summary": (
            "screencapture is the command-line side of the screenshot system. It can grab "
            "the whole screen, a window, or an interactive selection, with or without the "
            "shadow and cursor, and it can send the result straight to the clipboard. It is "
            "what scripted documentation and automated bug reports use."
        ),
        "synopsis": [
            "screencapture [-cimwWxo] [-t format] [-T seconds] [-R x,y,w,h] [file]",
            "screencapture -V seconds -v movie.mov",
        ],
        "options": [
            ("(default)", "Capture the whole screen to the given file"),
            ("-c", "Send the capture to the clipboard instead of a file"),
            ("-i", "Interactive selection — drag a region, or press space for window mode"),
            ("-w", "Window capture mode"),
            ("-W", "Start interactive mode in window selection"),
            ("-o", "In window mode, omit the drop shadow"),
            ("-x", "Silent — no camera shutter sound"),
            ("-T seconds", "Delay before capturing"),
            ("-R x,y,w,h", "Capture an explicit rectangle"),
            ("-t png|jpg|pdf|tiff", "Output format"),
            ("-m", "Capture only the main display"),
            ("-D n", "Capture display number n"),
            ("-V seconds -v file.mov", "Record video for a duration"),
            ("-l windowid", "Capture a specific window by id"),
        ],
        "examples": [
            ("screencapture ~/Desktop/shot.png", "Capture the whole screen"),
            ("screencapture -i ~/Desktop/region.png", "Drag out a region interactively"),
            ("screencapture -c -i", "Interactive capture straight to the clipboard"),
            ("screencapture -T 5 -x ~/Desktop/delayed.png", "Silent capture after a five-second delay"),
            ("screencapture -R 0,0,1280,720 -t jpg ~/Desktop/corner.jpg", "Capture a fixed rectangle as JPEG"),
            ("screencapture -w -o ~/Desktop/window.png", "Capture a window without its drop shadow"),
            ("screencapture -V 10 -v ~/Desktop/clip.mov", "Record a ten-second screen movie"),
        ],
        "notes": [
            "Screen Recording permission is required: the first run prompts, and until the calling app (Terminal, iTerm, your IDE) is approved in Privacy & Security, captures come out as an empty desktop image.",
            "`defaults write com.apple.screencapture location ~/Screenshots && killall SystemUIServer` changes where interactive Cmd-Shift-3 screenshots land.",
            "In `-i` mode, press space to switch to window selection, Escape to cancel — the exit status is non-zero when cancelled, which scripts should check.",
            "Video recording (`-v`) has no audio option; use QuickTime or a dedicated tool if sound is needed.",
        ],
        "see_also": ["open", "osascript", "defaults", "pbcopy"],
        "tags": ["screenshot", "capture", "gui", "media"],
    },
    {
        "command": "scutil",
        "tagline": "manage system configuration parameters",
        "summary": (
            "scutil is the interface to configd, the dynamic store that holds macOS's live "
            "network and identity configuration. It is the authoritative source for the "
            "machine's names, the active DNS resolver configuration, the current network "
            "state and proxy settings — all of which are invisible to the classic Unix "
            "files a Linux admin would reach for."
        ),
        "synopsis": [
            "scutil --get ComputerName|LocalHostName|HostName",
            "sudo scutil --set NAME value",
            "scutil --dns | --proxy | --nwi",
            "scutil (interactive: list, show, n.add)",
        ],
        "options": [
            ("--get NAME", "Read ComputerName, LocalHostName or HostName"),
            ("--set NAME value", "Set one of them persistently (needs sudo)"),
            ("--dns", "Show the full resolver configuration, per interface and per domain"),
            ("--proxy", "Show current proxy settings"),
            ("--nwi", "Network information: which interfaces are usable, and their rank"),
            ("--nc list|status|start|stop", "Manage VPN (network connection) services"),
            ("-r host", "Reachability of a host or address"),
            ("(interactive)", "`list`, `show key`, `watch` — browse the dynamic store live"),
        ],
        "examples": [
            ("scutil --get ComputerName", "The Finder-visible machine name"),
            ("scutil --dns | head -30", "Which resolvers are used for which domains — the real DNS configuration"),
            ("scutil --nwi", "Which interface currently carries traffic and whether IPv4/IPv6 are usable"),
            ("scutil --proxy", "Active proxy settings, including PAC file URL"),
            ("scutil -r example.com", "Whether a host is reachable according to the system's own reachability API"),
            ("sudo scutil --set ComputerName \"Studio Mac\"", "Rename the Mac"),
            ("scutil --nc list", "List configured VPN services and their status"),
            ("echo 'show State:/Network/Global/IPv4' | scutil", "Query the dynamic store non-interactively"),
        ],
        "notes": [
            "/etc/resolv.conf on macOS is a generated compatibility file and is often incomplete. `scutil --dns` is the real resolver configuration, including per-domain resolvers pushed by VPNs.",
            "When a VPN 'breaks DNS', `scutil --dns` shows the split-DNS scoping that is responsible.",
            "The three names (ComputerName, LocalHostName, HostName) serve different subsystems — set all three when renaming a machine.",
            "The interactive mode's `watch` command shows configuration changes live, which is the fastest way to see what happens when a network cable is plugged in.",
        ],
        "see_also": ["networksetup", "dscacheutil", "dig", "hostname"],
        "tags": ["network", "configuration", "dns", "configd"],
        "category": "networking",
    },
    {
        "command": "security",
        "tagline": "administer keychains, keys, certificates and trust settings",
        "summary": (
            "security is the command-line interface to the Keychain and the trust store. "
            "It reads and writes passwords, imports and exports certificates and keys, "
            "lists code-signing identities, and manages which roots the system trusts. It "
            "is how CI scripts get at signing certificates, and how you audit what a "
            "keychain contains."
        ),
        "synopsis": [
            "security find-generic-password -s service [-w]",
            "security add-generic-password -a account -s service -w password",
            "security find-identity -v -p codesigning",
            "security list-keychains | unlock-keychain | create-keychain",
            "security import cert.p12 -k keychain -T /usr/bin/codesign",
        ],
        "options": [
            ("find-generic-password -s name [-w]", "Find a password item; `-w` prints just the secret"),
            ("find-internet-password -s host [-w]", "The same for website/server credentials"),
            ("add-generic-password -a acct -s svc -w pw", "Store a password"),
            ("delete-generic-password -s svc", "Remove one"),
            ("find-identity -v -p codesigning", "List usable code-signing identities"),
            ("find-certificate -a -c name -p", "Export matching certificates as PEM"),
            ("import file -k keychain -T app", "Import a certificate or key, allowing an app to use it"),
            ("list-keychains [-s ...]", "Show or set the keychain search list"),
            ("unlock-keychain [-p pass] path", "Unlock a keychain (CI needs this)"),
            ("create-keychain -p pass path", "Create a keychain"),
            ("set-keychain-settings [-lut N]", "Lock settings — timeout, lock on sleep"),
            ("add-trusted-cert -d -r trustRoot -k keychain cert.cer", "Trust a root certificate"),
            ("cms -D -i file", "Decode a CMS/PKCS#7 signed message such as a provisioning profile"),
        ],
        "examples": [
            ("security find-identity -v -p codesigning", "Which signing identities are available — the first check when codesign fails"),
            ("security find-generic-password -s 'my-service' -w", "Print a stored password to stdout"),
            ("security add-generic-password -a \"$USER\" -s deploy-token -w 'secret'", "Store a token in the login keychain"),
            ("security find-certificate -a -c 'Developer ID' -p", "Export matching certificates as PEM"),
            ("security unlock-keychain -p \"$KEYCHAIN_PASS\" ~/Library/Keychains/build.keychain-db", "Unlock a keychain in CI before signing"),
            ("sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ca.cer", "Trust an internal CA system-wide"),
            ("security dump-keychain | grep -i svce", "Enumerate the items in the default keychain"),
        ],
        "notes": [
            "`security find-generic-password -w` prints a secret to stdout, where it lands in shell history and logs. In scripts, consume it directly rather than assigning it to an exported variable.",
            "CI machines need an explicit `create-keychain` / `unlock-keychain` / `list-keychains -s` sequence: the default login keychain is locked when there is no GUI session.",
            "`-T /usr/bin/codesign` on import grants that tool access without a UI prompt; without it, signing hangs waiting for an invisible dialog.",
            "Trusting a root with `add-trusted-cert` at system scope affects every user and every application — the same power a MITM proxy needs.",
            "The login keychain unlocks with the login password. Resetting a password with `sudo passwd` desynchronises them and the keychain stops unlocking.",
        ],
        "see_also": ["codesign", "spctl", "passwd", "curl"],
        "tags": ["keychain", "certificates", "security", "code-signing"],
        "category": "security",
    },
    {
        "command": "sed",
        "tagline": "stream editor for filtering and transforming text",
        "summary": (
            "sed applies editing commands to a stream of text — substitute, delete, insert, "
            "print selected lines. macOS ships BSD sed, whose differences from GNU sed bite "
            "constantly: `-i` requires an explicit backup suffix, `\\+` and `\\?` are not "
            "supported without `-E`, and `\\n` in a replacement does not mean newline."
        ),
        "synopsis": [
            "sed [-Ealn] [-i extension] 'command' [file ...]",
            "sed -e 'cmd1' -e 'cmd2' file",
            "sed -f script.sed file",
        ],
        "options": [
            ("-i ''", "Edit in place with no backup — the empty argument is mandatory on macOS"),
            ("-i .bak", "Edit in place, keeping file.bak"),
            ("-E", "Extended regular expressions (+, ?, |, grouping without backslashes)"),
            ("-n", "Suppress automatic printing; pair with `p`"),
            ("-e cmd", "Add a command (repeatable)"),
            ("-f file", "Read commands from a script file"),
            ("-a", "With `w`, defer file creation until the write happens"),
        ],
        "examples": [
            ("sed 's/old/new/' file.txt", "Replace the first match on each line"),
            ("sed 's/old/new/g' file.txt", "Replace every match"),
            ("sed -i '' 's/8080/9090/g' config.yml", "Edit in place on macOS — note the empty argument after -i"),
            ("sed -i .bak 's/DEBUG/INFO/' app.conf", "Edit in place keeping app.conf.bak"),
            ("sed -n '10,20p' large.log", "Print lines 10 to 20"),
            ("sed '/^#/d;/^$/d' config.conf", "Strip comments and blank lines"),
            ("sed -E 's/([0-9]{4})-([0-9]{2})-([0-9]{2})/\\3\\/\\2\\/\\1/' dates.txt", "Reorder date components with extended regex"),
            ("sed -n '$=' file.txt", "Count lines"),
        ],
        "notes": [
            "`sed -i 's/a/b/' file` fails on macOS with \"invalid command code\" — BSD sed reads the next argument as the backup suffix. Write `sed -i '' 's/a/b/' file`.",
            "A portable script that must run on both macOS and Linux should write to a temporary file and move it, rather than trying to make `-i` behave the same in both.",
            "Use a different delimiter when the pattern contains slashes: `sed 's|/usr/local|/opt/homebrew|g'`.",
            "`brew install gnu-sed` provides `gsed` with GNU semantics if a script depends on them.",
            "Multi-line operations are painful in BSD sed; reach for awk or perl instead.",
        ],
        "see_also": ["awk", "grep", "tr", "cut"],
        "tags": ["text-processing", "regex", "editing"],
    },
    {
        "command": "softwareupdate",
        "tagline": "check for and install macOS software updates",
        "summary": (
            "softwareupdate is the command-line front end to Apple's update mechanism. It "
            "lists available updates, installs them individually or all at once, and can "
            "manage automatic-update settings. It is the tool MDM scripts and remote "
            "administrators use, since it works over SSH where the GUI does not."
        ),
        "synopsis": [
            "softwareupdate --list",
            "sudo softwareupdate --install label [--restart]",
            "sudo softwareupdate --install --all --agree-to-license",
            "softwareupdate --install-rosetta --agree-to-license",
        ],
        "options": [
            ("-l, --list", "List available updates"),
            ("-i label, --install label", "Install a specific update by label"),
            ("-i -a, --install --all", "Install everything available"),
            ("-r, --recommended", "Only recommended updates"),
            ("-R, --restart", "Restart automatically if an update requires it"),
            ("--install-rosetta", "Install Rosetta 2 on Apple Silicon"),
            ("--fetch-full-installer --full-installer-version X", "Download a full macOS installer"),
            ("--background", "Start a background download"),
            ("--ignore label", "Ignore an update (deprecated on recent macOS)"),
            ("--agree-to-license", "Required for unattended installs"),
            ("--verbose", "More detail"),
        ],
        "examples": [
            ("softwareupdate --list", "See what is available"),
            ("sudo softwareupdate -i -a -R --agree-to-license", "Install everything and restart if needed"),
            ("sudo softwareupdate -i 'Safari17.0'", "Install one named update"),
            ("softwareupdate --install-rosetta --agree-to-license", "Install Rosetta 2 non-interactively on Apple Silicon"),
            ("sudo softwareupdate --fetch-full-installer --full-installer-version 14.6", "Download a full macOS installer to /Applications"),
            ("defaults read /Library/Preferences/com.apple.SoftwareUpdate AutomaticCheckEnabled", "Check whether automatic update checking is on"),
        ],
        "notes": [
            "Major macOS upgrades on Apple Silicon require an authenticated user with a Secure Token — a plain `sudo softwareupdate` over SSH will refuse. Pass `--user` and `--stdinpass`, or run it from a logged-in session.",
            "Update labels change with every release; always take them from a fresh `--list` rather than hard-coding them.",
            "`-R` restarts without warning anyone logged in. On a shared or production machine, schedule it.",
            "Rosetta 2 installation is the one case where `--agree-to-license` is genuinely routine — it is how scripted setups avoid an interactive prompt on Apple Silicon.",
        ],
        "see_also": ["sw_vers", "installer", "pkgutil", "system_profiler"],
        "tags": ["updates", "maintenance", "deployment"],
        "category": "system_admin",
    },
    {
        "command": "sort",
        "tagline": "sort lines of text",
        "summary": (
            "sort orders lines, optionally by a chosen field and with numeric, "
            "human-numeric or version-aware comparison. Paired with uniq it is the standard "
            "way to count occurrences in log output. macOS ships BSD sort, which does "
            "support `-h` and `-V` but whose locale handling differs from GNU."
        ),
        "synopsis": [
            "sort [-bdfnrhuV] [-k field] [-t sep] [-o out] [file ...]",
        ],
        "options": [
            ("-n", "Numeric sort"),
            ("-h", "Human-numeric — understands 1K, 5M, 2G"),
            ("-V", "Version sort — 1.10 after 1.9"),
            ("-r", "Reverse order"),
            ("-u", "Output only unique lines"),
            ("-k N[,M]", "Sort by field N (through M)"),
            ("-t sep", "Field separator"),
            ("-f", "Case-insensitive"),
            ("-b", "Ignore leading blanks"),
            ("-o file", "Write to a file (safe to be the input file)"),
            ("-c", "Check whether the input is already sorted"),
            ("-m", "Merge already-sorted files"),
        ],
        "examples": [
            ("sort names.txt", "Plain alphabetical sort"),
            ("sort -u emails.txt", "Sorted and deduplicated"),
            ("du -h ~/* | sort -h | tail", "Largest items, human sizes ordered correctly"),
            ("sort -t: -k3 -n /etc/passwd", "Sort the password file by numeric UID"),
            ("awk '{print $1}' access.log | sort | uniq -c | sort -rn | head", "Top client addresses in a log"),
            ("sort -V versions.txt", "Order version strings correctly"),
            ("sort -k2,2 -k1,1n data.txt", "Sort by the second field, then numerically by the first"),
        ],
        "notes": [
            "`sort | uniq -c | sort -rn` is the canonical frequency count; uniq only collapses *adjacent* duplicates, so the first sort is mandatory.",
            "Sort order depends on locale. `LC_ALL=C sort` gives byte order and is what scripts should use for reproducibility.",
            "`-h` and `-V` exist in macOS sort — useful, because many portability guides assume they are GNU-only.",
            "`sort -o file file` is safe; `sort file > file` truncates the file before reading it.",
        ],
        "see_also": ["uniq", "awk", "cut", "wc"],
        "tags": ["text-processing", "sorting"],
    },
    {
        "command": "spctl",
        "tagline": "manage Gatekeeper assessment policy",
        "summary": (
            "spctl queries and configures Gatekeeper, the subsystem that decides whether "
            "downloaded software may run. Its most useful mode is assessment: asking, "
            "before you distribute an app, whether a clean Mac would let it open. That is "
            "the check that catches missing notarization, which codesign alone cannot tell "
            "you."
        ),
        "synopsis": [
            "spctl -a -vv path",
            "spctl --status",
            "sudo spctl --master-disable | --master-enable",
            "spctl --assess --type install package.pkg",
        ],
        "options": [
            ("-a, --assess", "Assess whether Gatekeeper would allow this"),
            ("-vv", "Verbose — prints the originating rule and the signing authority"),
            ("--type execute|install|open", "Assessment type: app, installer package, or document"),
            ("--status", "Report whether assessment is enabled"),
            ("--master-disable / --master-enable", "Turn Gatekeeper off / on (needs sudo)"),
            ("--add --label name path", "Add a rule allowing something specific"),
            ("--list", "List assessment rules"),
            ("--remove --label name", "Remove a rule"),
        ],
        "examples": [
            ("spctl -a -vv /Applications/Foo.app", "Would Gatekeeper allow this app to open?"),
            ("spctl --status", "Is Gatekeeper assessment enabled?"),
            ("spctl -a -vv --type install ~/Downloads/Tool.pkg", "Assess an installer package"),
            ("spctl -a -vv --type open --context context:primary-signature document.dmg", "Assess a disk image"),
            ("xattr -d com.apple.quarantine ~/Downloads/tool", "Remove the quarantine flag from something you trust"),
            ("sudo spctl --master-disable", "Restore the \"Anywhere\" option in Security settings — re-enable when done"),
        ],
        "notes": [
            "\"rejected (the code is valid but does not seem to be an app)\" for a bare binary is expected — Gatekeeper assessment applies to bundles and packages, not loose executables.",
            "\"source=Notarized Developer ID\" is the pass you want before shipping. \"source=Unnotarized Developer ID\" means it is signed but will be blocked on a user's Mac.",
            "Gatekeeper only assesses files carrying the com.apple.quarantine extended attribute. Anything built locally is unquarantined and runs regardless.",
            "`--master-disable` weakens the machine and, since Sequoia, the setting is more tightly controlled — prefer removing the quarantine attribute from a specific file.",
        ],
        "see_also": ["codesign", "xattr", "csrutil", "pkgutil"],
        "tags": ["gatekeeper", "security", "notarization", "quarantine"],
        "category": "security",
    },
    {
        "command": "su",
        "tagline": "switch to another user",
        "summary": (
            "su starts a shell as another user, prompting for that user's password. On "
            "macOS the root account is disabled by default and has no password, so `su` "
            "with no argument fails on a stock machine — sudo is the intended route to "
            "elevated privileges."
        ),
        "synopsis": [
            "su [-] [-m] [user] [-c command]",
        ],
        "options": [
            ("-", "Simulate a full login: run login scripts, change directory to their home"),
            ("-m", "Preserve the current environment"),
            ("-c command", "Run one command as that user"),
            ("(no user)", "Switch to root"),
            ("-l", "Same as `-`"),
        ],
        "examples": [
            ("su - alice", "Full login shell as alice"),
            ("sudo su -", "Become root via sudo, which does not require a root password"),
            ("sudo -u alice -i", "The preferred alternative — a login shell as alice, authorised by your own password"),
            ("su -c 'whoami' alice", "Run one command as another user"),
            ("sudo -l", "Check what your account is permitted to do before escalating"),
        ],
        "notes": [
            "The root account is disabled on macOS by default. `su` with no user prompts for a root password that does not exist; use `sudo -i` instead.",
            "`sudo -u user -i` is preferable to `su - user` in administration: it authenticates with *your* password and is logged, whereas su needs the target account's password.",
            "Always use `su -` rather than bare `su` when you want the target user's environment — otherwise you keep your own PATH and variables, which causes confusing failures.",
            "A GUI-related command run via su often fails because the session context (and TCC permissions) belong to the logged-in user, not the shell.",
        ],
        "see_also": ["sudo", "id", "passwd", "dscl"],
        "tags": ["users", "privileges", "security"],
        "category": "security",
    },
    {
        "command": "sudo",
        "tagline": "execute a command as another user, usually root",
        "summary": (
            "sudo runs one command with elevated privileges after authenticating with your "
            "own password. On macOS, authority comes from membership of the `admin` group "
            "rather than per-user sudoers entries. Since Sonoma, Touch ID can authenticate "
            "sudo through a supported PAM configuration."
        ),
        "synopsis": [
            "sudo command [args]",
            "sudo -u user command",
            "sudo -i | sudo -s",
            "sudo -e file",
        ],
        "options": [
            ("-u user", "Run as another user instead of root"),
            ("-i", "Run a login shell as the target user"),
            ("-s", "Run a shell, keeping most of the current environment"),
            ("-E", "Preserve the environment (if policy allows)"),
            ("-k", "Forget the cached credential immediately"),
            ("-v", "Refresh the credential timestamp without running a command"),
            ("-l", "List what you are permitted to run"),
            ("-e file", "Edit a file safely as root (sudoedit)"),
            ("-H", "Set HOME to the target user's home"),
            ("-n", "Non-interactive — fail rather than prompt"),
        ],
        "examples": [
            ("sudo systemsetup -getremotelogin", "Run a privileged query"),
            ("sudo -l", "See what your account may run"),
            ("sudo -u _www ls /Library/WebServer", "Act as a service account"),
            ("sudo -e /etc/hosts", "Edit a system file safely — edits a copy, then installs it"),
            ("sudo -k", "Drop cached credentials at the end of a sensitive script"),
            ("sudo -v && long_script.sh", "Prime the credential so a long script does not stall on a prompt"),
        ],
        "notes": [
            "Administrator rights come from the `admin` group: `id -Gn | grep -w admin`. There is normally no per-user sudoers entry to inspect.",
            "Touch ID for sudo: add `auth sufficient pam_tid.so` to /etc/pam.d/sudo_local (Sonoma and later provide the file and it survives updates). Editing /etc/pam.d/sudo directly is overwritten by macOS updates.",
            "Always edit sudoers with `sudo visudo` — a syntax error saved directly can lock you out of sudo entirely.",
            "`sudo` does not grant TCC privacy permissions. A root shell still cannot read ~/Documents unless the terminal app has Full Disk Access.",
            "sudo does not defeat SIP: /System stays read-only for root.",
        ],
        "see_also": ["su", "id", "csrutil", "security"],
        "tags": ["privileges", "security", "administration"],
        "category": "security",
    },
    {
        "command": "sw_vers",
        "tagline": "print macOS version information",
        "summary": (
            "sw_vers reports the operating system name, version and build. It is the "
            "canonical scripted version check on macOS — more reliable than parsing "
            "`uname -r`, which gives the Darwin kernel version rather than the marketing "
            "release everybody talks about."
        ),
        "synopsis": [
            "sw_vers [-productName|-productVersion|-buildVersion|-productVersionExtra]",
        ],
        "options": [
            ("(no options)", "Print name, version and build"),
            ("-productName", "\"macOS\""),
            ("-productVersion", "The version number, e.g. 15.1"),
            ("-buildVersion", "The build identifier, e.g. 24B83"),
            ("-productVersionExtra", "Rapid Security Response suffix, e.g. (a)"),
        ],
        "examples": [
            ("sw_vers", "Full version summary"),
            ("sw_vers -productVersion", "Just the version, for scripts"),
            ("[ \"$(sw_vers -productVersion | cut -d. -f1)\" -ge 14 ] && echo 'Sonoma or later'", "Gate a script on the major version"),
            ("echo \"$(sw_vers -productVersion) ($(sw_vers -buildVersion))\"", "Version and build for a bug report"),
            ("uname -r", "The Darwin kernel version — related but not the same thing"),
        ],
        "notes": [
            "Darwin kernel versions and macOS releases are different numbering schemes; `sw_vers -productVersion` is what version checks should use.",
            "On Big Sur and later, a binary built against an older SDK may see 10.16 instead of 11.x for compatibility. Running sw_vers directly from a shell is unaffected.",
            "The build version identifies the exact release, including Rapid Security Responses, and is what Apple support asks for.",
            "`system_profiler SPSoftwareDataType` gives the same information plus uptime, boot volume and kernel details.",
        ],
        "see_also": ["uname", "system_profiler", "softwareupdate", "sysctl"],
        "tags": ["version", "system-info"],
        "category": "system_admin",
    },
    {
        "command": "sysctl",
        "tagline": "read and write kernel state variables",
        "summary": (
            "sysctl exposes the kernel's tunable and informational variables — CPU model "
            "and core count, memory size, network stack parameters, security feature flags. "
            "Reading is unrestricted; writing needs root, and most writes do not persist "
            "across a reboot. On Apple Silicon the hw.optional.arm.* keys are the reliable "
            "way to detect CPU features."
        ),
        "synopsis": [
            "sysctl name ...",
            "sysctl -a",
            "sudo sysctl -w name=value",
        ],
        "options": [
            ("-a", "List every variable (very long)"),
            ("-n", "Print only the value, not the name"),
            ("-w name=value", "Set a variable (needs root)"),
            ("-b", "Print the value in raw binary form"),
            ("name", "Read one or more named variables"),
        ],
        "examples": [
            ("sysctl -n machdep.cpu.brand_string", "CPU model name"),
            ("sysctl -n hw.ncpu hw.physicalcpu hw.logicalcpu", "Core counts"),
            ("sysctl -n hw.memsize | awk '{print $1/1024/1024/1024\" GB\"}'", "Installed RAM in gigabytes"),
            ("sysctl -n hw.optional.arm64", "1 on Apple Silicon, absent or 0 on Intel"),
            ("sysctl kern.boottime", "When the machine last booted"),
            ("sysctl -a | grep -i vm.swapusage", "Current swap usage"),
            ("sudo sysctl -w net.inet.ip.forwarding=1", "Enable IP forwarding until the next reboot"),
        ],
        "notes": [
            "`sysctl -w` changes are lost at reboot. Persist them with a plist in /Library/LaunchDaemons that applies them at boot, or /etc/sysctl.conf where still honoured.",
            "`sysctl -n hw.optional.arm64` returning 1 is the cleanest Apple Silicon test; `uname -m` reports `x86_64` when the shell itself is running under Rosetta.",
            "SIP blocks many writes even for root — a \"Operation not permitted\" on a sysctl write usually means the variable is SIP-protected.",
            "`sysctl -a` output is enormous; pipe through grep, and remember that variable names are hierarchical (hw., kern., net., vm., machdep., security.).",
        ],
        "see_also": ["uname", "system_profiler", "sw_vers", "lipo"],
        "tags": ["kernel", "system-info", "tuning", "hardware"],
        "category": "system_admin",
    },
    {
        "command": "system_profiler",
        "tagline": "report detailed system hardware and software configuration",
        "summary": (
            "system_profiler is the command-line version of System Information. It reports "
            "everything from the serial number and memory configuration to attached USB "
            "devices, installed applications, Wi-Fi environment and power adapter details. "
            "Naming a data type is essential — the full report takes minutes and produces "
            "megabytes."
        ),
        "synopsis": [
            "system_profiler [-json|-xml] [-detailLevel mini|basic|full] [dataType ...]",
            "system_profiler -listDataTypes",
        ],
        "options": [
            ("-listDataTypes", "List every available data type"),
            ("SPHardwareDataType", "Model, chip, cores, memory, serial number"),
            ("SPSoftwareDataType", "macOS version, kernel, uptime, boot volume"),
            ("SPStorageDataType", "Volumes, capacities, filesystems"),
            ("SPUSBDataType", "USB device tree"),
            ("SPDisplaysDataType", "GPUs and attached displays"),
            ("SPPowerDataType", "Battery health, cycle count, adapter"),
            ("SPNetworkDataType / SPAirPortDataType", "Network interfaces / Wi-Fi environment"),
            ("SPApplicationsDataType", "Installed applications (slow)"),
            ("SPInstallHistoryDataType", "What has been installed and when"),
            ("-json / -xml", "Machine-readable output"),
            ("-detailLevel mini", "Omit personal information — safe to share"),
        ],
        "examples": [
            ("system_profiler SPHardwareDataType", "Model identifier, chip, memory and serial number"),
            ("system_profiler SPSoftwareDataType", "OS version, kernel, uptime"),
            ("system_profiler SPPowerDataType | grep -A3 'Health Information'", "Battery cycle count and condition"),
            ("system_profiler -json SPStorageDataType | jq '.SPStorageDataType[].size_in_bytes'", "Machine-readable storage report"),
            ("system_profiler SPUSBDataType | grep -B2 -A6 'Product ID'", "Identify an attached USB device"),
            ("system_profiler -detailLevel mini SPHardwareDataType", "Hardware summary with the serial number withheld"),
            ("system_profiler SPInstallHistoryDataType | head -40", "Recent install history when diagnosing a change"),
        ],
        "notes": [
            "Always name a data type. A bare `system_profiler` collects everything and can take several minutes.",
            "Reports include the serial number and hardware UUID; use `-detailLevel mini` before sharing output publicly.",
            "`-json` output is stable enough to parse with jq, unlike the human-readable form.",
            "SPAirPortDataType includes a scan of nearby networks with signal strengths — the quickest Wi-Fi survey without extra tools.",
        ],
        "see_also": ["sysctl", "sw_vers", "diskutil", "pmset"],
        "tags": ["system-info", "hardware", "diagnostics", "inventory"],
        "category": "hardware",
    },
    {
        "command": "tail",
        "tagline": "print the last lines of a file, optionally following it",
        "summary": (
            "tail shows the end of a file — by default ten lines — and with `-f` keeps "
            "printing as the file grows. It is the reflex for watching a log. On macOS one "
            "caveat dominates: most system logging no longer lands in text files, so "
            "`tail -f /var/log/system.log` shows very little and `log stream` is what you "
            "actually want."
        ),
        "synopsis": [
            "tail [-n count | -c bytes] [-f|-F] [-r] [file ...]",
        ],
        "options": [
            ("-n N", "Print the last N lines; `-n +N` starts at line N"),
            ("-c N", "Print the last N bytes"),
            ("-f", "Follow — keep printing as the file grows"),
            ("-F", "Follow, and reopen the file if it is rotated or replaced"),
            ("-r", "Print the file in reverse order"),
            ("-q / -v", "Never / always print filename headers"),
        ],
        "examples": [
            ("tail -n 50 /var/log/install.log", "Last fifty lines of the installer log"),
            ("tail -f ~/Library/Logs/MyApp/app.log", "Watch an application log live"),
            ("tail -F /var/log/nginx/error.log", "Follow across log rotation"),
            ("tail -n +2 data.csv", "Skip the header row"),
            ("tail -r log.txt | head -20", "Twenty most recent lines, newest first"),
            ("log stream --predicate 'process == \"MyApp\"'", "The unified-logging equivalent of tail -f on macOS"),
        ],
        "notes": [
            "`-f` follows a file descriptor and goes silent when the file is rotated; `-F` follows the *name* and reopens. On a rotating log, always use `-F`.",
            "macOS system logs live in the unified log, not text files. `log stream` and `log show` replace tail for anything Apple writes.",
            "`tail -f` on several files prefixes each block with a header, which makes multi-log watching workable without extra tools.",
            "`less +F` gives the same live view but lets you stop, scroll back, and resume.",
        ],
        "see_also": ["head", "less", "log", "grep"],
        "tags": ["text", "logs", "monitoring"],
        "category": "logging",
    },
    {
        "command": "tar",
        "tagline": "create and extract archive files",
        "summary": (
            "tar bundles a directory tree into a single archive, optionally compressed. "
            "macOS ships bsdtar (libarchive) presented as `tar`, which transparently reads "
            "gzip, bzip2, xz and even zip archives without needing the matching flag. Its "
            "main macOS wrinkle is the ._ AppleDouble files it creates to carry extended "
            "attributes, which confuse recipients on other platforms."
        ),
        "synopsis": [
            "tar -czf archive.tar.gz directory",
            "tar -xzf archive.tar.gz [-C destination]",
            "tar -tzf archive.tar.gz",
        ],
        "options": [
            ("-c / -x / -t", "Create / extract / list"),
            ("-f file", "Archive filename (`-` for stdin/stdout)"),
            ("-z / -j / -J", "gzip / bzip2 / xz compression"),
            ("-v", "Verbose — list files as they are processed"),
            ("-C dir", "Change to a directory first"),
            ("--exclude pattern", "Skip matching paths"),
            ("--strip-components N", "Drop N leading path components on extraction"),
            ("--disable-copyfile", "Do not write ._ AppleDouble files (macOS)"),
            ("-p", "Preserve permissions on extraction"),
        ],
        "examples": [
            ("tar -czf backup.tar.gz ~/Projects", "Create a gzip-compressed archive"),
            ("tar -xzf backup.tar.gz -C /tmp/restore", "Extract into a specific directory"),
            ("tar -tzf backup.tar.gz | head", "List an archive's contents before extracting"),
            ("COPYFILE_DISABLE=1 tar -czf clean.tar.gz site/", "Create an archive without macOS ._ files"),
            ("tar -czf logs.tar.gz --exclude='*.tmp' logs/", "Archive while skipping temporary files"),
            ("tar -xzf release.tar.gz --strip-components=1", "Extract, dropping the archive's top-level directory"),
            ("tar -cf - src | (cd /dest && tar -xf -)", "Copy a tree through a pipe, preserving structure"),
        ],
        "notes": [
            "macOS tar writes ._filename AppleDouble entries to preserve extended attributes. Set `COPYFILE_DISABLE=1` or pass `--disable-copyfile` when the archive will be opened on Linux or Windows.",
            "bsdtar auto-detects compression on extraction, so `tar -xf archive.tar.bz2` works without `-j`. Creation still needs the explicit flag.",
            "Always list (`-t`) an untrusted archive before extracting: a maliciously crafted archive can contain absolute or `../` paths.",
            "For macOS application bundles, `ditto -c -k` produces an archive Apple's tooling expects; tar is fine for source trees and data.",
        ],
        "see_also": ["ditto", "hdiutil", "cp", "xattr"],
        "tags": ["archive", "compression", "backup", "files"],
        "category": "backup",
    },
    {
        "command": "tmutil",
        "tagline": "control Time Machine backups",
        "summary": (
            "tmutil drives Time Machine from the command line: start and stop backups, add "
            "and remove destinations, manage exclusions, list and delete snapshots, and "
            "restore files. It is the only way to reach several features — notably local "
            "snapshot management, which is what you need when APFS snapshots are quietly "
            "consuming a disk."
        ),
        "synopsis": [
            "tmutil status | startbackup [--block] | stopbackup",
            "tmutil listbackups | latestbackup",
            "sudo tmutil setdestination /Volumes/Backup",
            "tmutil listlocalsnapshots / / sudo tmutil deletelocalsnapshots date",
            "tmutil restore source destination",
        ],
        "options": [
            ("status", "Current backup activity and progress"),
            ("startbackup [--block] [--auto]", "Begin a backup; `--block` waits for completion"),
            ("stopbackup", "Cancel a running backup"),
            ("enable / disable", "Turn automatic backups on or off (needs sudo)"),
            ("destinationinfo", "Show configured destinations"),
            ("setdestination [-a] path", "Set (or add, with -a) a backup destination"),
            ("addexclusion [-p] path", "Exclude a path — `-p` makes it a fixed-path exclusion"),
            ("removeexclusion path / isexcluded path", "Remove or test an exclusion"),
            ("listbackups / latestbackup", "Enumerate backups on the destination"),
            ("listlocalsnapshots /", "List local APFS snapshots"),
            ("deletelocalsnapshots date|all", "Delete local snapshots (needs sudo)"),
            ("thinlocalsnapshots / urgency", "Reclaim local snapshot space"),
            ("restore src dst", "Restore a file or directory from a backup"),
            ("compare", "Compare the current state with a backup"),
        ],
        "examples": [
            ("tmutil status", "Is a backup running, and how far along is it?"),
            ("sudo tmutil startbackup --block", "Run a backup now and wait for it to finish"),
            ("tmutil destinationinfo", "Which destinations are configured"),
            ("tmutil listlocalsnapshots /", "Local snapshots consuming space on the boot volume"),
            ("sudo tmutil thinlocalsnapshots / 21474836480 4", "Reclaim about 20 GB by thinning local snapshots"),
            ("sudo tmutil deletelocalsnapshots 2026-08-20-120000", "Delete one specific local snapshot"),
            ("sudo tmutil addexclusion -p ~/VMs", "Permanently exclude a directory from backups"),
            ("tmutil isexcluded ~/Downloads", "Check whether a path is excluded"),
        ],
        "notes": [
            "\"Disk full\" on a Mac with an apparently healthy Time Machine is frequently local APFS snapshots. `tmutil listlocalsnapshots /` then `thinlocalsnapshots` reclaims the space.",
            "Local snapshots are taken hourly even without a backup destination attached, and are normally purged automatically when free space runs low.",
            "Most tmutil verbs that change configuration need sudo, and some also need the terminal to have Full Disk Access under Privacy & Security.",
            "`tmutil restore` preserves metadata and is safer than dragging files out of a backup in the Finder.",
        ],
        "see_also": ["diskutil", "df", "hdiutil", "log"],
        "tags": ["backup", "time-machine", "snapshots", "storage"],
        "category": "backup",
    },
    {
        "command": "top",
        "tagline": "display and update sorted process information",
        "summary": (
            "top shows processes ordered by resource usage and refreshes continuously. The "
            "macOS version differs noticeably from Linux's: sorting is `-o`, the memory "
            "columns reflect the compressed-memory system, and `-l` gives a fixed number of "
            "samples suitable for scripts."
        ),
        "synopsis": [
            "top [-o key] [-n count] [-s delay] [-l samples] [-pid pid] [-U user]",
        ],
        "options": [
            ("-o key", "Sort by cpu, mem, vsize, pid, time, threads"),
            ("-O key", "Secondary sort key"),
            ("-n N", "Show only the top N processes"),
            ("-s N", "Seconds between refreshes"),
            ("-l N", "Take N samples then exit (`-l 1` for a one-shot snapshot)"),
            ("-pid N", "Monitor one process"),
            ("-U user", "Only this user's processes"),
            ("-stats list", "Choose which columns to display"),
            ("-R", "Do not traverse the process tree (faster)"),
        ],
        "examples": [
            ("top -o cpu", "Interactive view sorted by CPU"),
            ("top -o mem -n 10 -l 1", "One-shot snapshot of the ten biggest memory users"),
            ("top -l 2 -s 1 | grep -E '^(CPU|PhysMem)'", "Sample CPU and memory summary lines for a script"),
            ("top -pid $(pgrep -x Safari | head -1)", "Watch one process"),
            ("top -U $(whoami) -o cpu", "Only your own processes"),
        ],
        "notes": [
            "The first sample's CPU numbers are meaningless (there is no previous sample to compare with). Use `-l 2` and read the second sample in scripts.",
            "macOS memory columns are not Linux's: MEM is resident size, COMPRESSED shows compressed memory. \"Memory pressure\" in the summary is a better health indicator than free memory, which macOS deliberately keeps low.",
            "Interactive keys: `o` change sort, `q` quit, `?` help.",
            "Activity Monitor is the same data with a GUI; `top -l 1` is the scriptable equivalent.",
        ],
        "see_also": ["ps", "kill", "sysctl", "log"],
        "tags": ["process", "monitoring", "performance"],
        "category": "system_admin",
    },
    {
        "command": "touch",
        "tagline": "create empty files or update timestamps",
        "summary": (
            "touch creates a file if it does not exist and updates its access and "
            "modification times if it does. Beyond the obvious use of making an empty file, "
            "it is how you set a reference timestamp for `find -newer` comparisons and how "
            "you force build systems to consider a file changed."
        ),
        "synopsis": [
            "touch [-acm] [-r reffile] [-t [[CC]YY]MMDDhhmm[.SS]] file ...",
        ],
        "options": [
            ("-a / -m", "Change only the access time / only the modification time"),
            ("-c", "Do not create the file if it does not exist"),
            ("-r file", "Copy timestamps from a reference file"),
            ("-t stamp", "Set an explicit time, e.g. 202608251200"),
            ("-d datetime", "Set the time from an ISO 8601 string"),
            ("-h", "Act on a symlink rather than its target"),
        ],
        "examples": [
            ("touch newfile.txt", "Create an empty file"),
            ("touch -r template.txt copy.txt", "Give one file another's timestamps"),
            ("touch -t 202601011200 backdated.txt", "Set an explicit timestamp"),
            ("touch marker && find . -newer marker", "Find everything modified since a moment you chose"),
            ("touch -c existing.log", "Update the timestamp only if the file already exists"),
            ("touch src/*.c && make", "Force a rebuild"),
        ],
        "notes": [
            "touch cannot change the creation time (birthtime) on APFS; only access and modification. `SetFile -d` from the Xcode tools can, where it still works.",
            "Creating a reference file and using `find -newer` is more reliable than `-mtime`, which counts in whole days.",
            "`touch` on a file inside a TCC-protected folder from an unapproved terminal fails with \"Operation not permitted\" even for your own user.",
            "`ls -lU` shows creation time on macOS, which is not what `touch` manipulates.",
        ],
        "see_also": ["find", "ls", "mkdir", "stat"],
        "tags": ["files", "timestamps"],
    },
    {
        "command": "tr",
        "tagline": "translate or delete characters",
        "summary": (
            "tr maps one set of characters onto another, squeezes repeats, or deletes "
            "characters entirely. It operates on standard input only, character by "
            "character — it knows nothing about lines or words — which makes it the right "
            "tool for case conversion, whitespace normalisation, and stripping stray "
            "carriage returns from files that came from Windows."
        ),
        "synopsis": [
            "tr [-Ccsu] string1 string2",
            "tr -d string",
            "tr -s string",
        ],
        "options": [
            ("string1 string2", "Translate characters in the first set to the second"),
            ("-d", "Delete characters in the set"),
            ("-s", "Squeeze repeated characters into one"),
            ("-c / -C", "Complement the set — act on everything *not* listed"),
            ("-u", "Unbuffered output"),
        ],
        "examples": [
            ("tr 'a-z' 'A-Z' < file.txt", "Uppercase a file"),
            ("tr -d '\\r' < windows.txt > unix.txt", "Strip carriage returns from a CRLF file"),
            ("tr -s ' ' < spaced.txt", "Collapse runs of spaces"),
            ("echo 'a,b,c' | tr ',' '\\n'", "Split a comma-separated list onto separate lines"),
            ("tr -cd '[:print:]\\n' < messy.txt", "Delete every non-printable character"),
            ("LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 24", "Generate a random alphanumeric string"),
        ],
        "notes": [
            "tr reads standard input only. `tr 'a' 'b' file.txt` treats file.txt as a second set argument — use `< file.txt`.",
            "Character classes need the full bracket form: `[:upper:]`, `[:digit:]`, `[:space:]`.",
            "With a multibyte locale, byte-oriented operations can mangle UTF-8. Prefix with `LC_ALL=C` when you mean bytes.",
            "`tr -d '\\r'` is the quickest CRLF fix; `file yourfile` confirms whether the line endings really are the problem.",
        ],
        "see_also": ["sed", "awk", "cut", "sort"],
        "tags": ["text-processing", "characters", "encoding"],
    },
    {
        "command": "traceroute",
        "tagline": "trace the network path to a host",
        "summary": (
            "traceroute reveals each router between you and a destination by sending "
            "packets with increasing TTLs. It answers \"where does the connection break "
            "down?\" — whether the fault is on your LAN, at your ISP, or deep in the "
            "internet. Asterisks in the output mean a hop declined to reply, which is "
            "common and usually harmless."
        ),
        "synopsis": [
            "traceroute [-I|-P proto] [-n] [-m maxttl] [-q nqueries] [-w wait] host",
            "traceroute6 host",
        ],
        "options": [
            ("-n", "Numeric output — skip reverse DNS, much faster"),
            ("-I", "Use ICMP echo instead of UDP probes"),
            ("-P TCP", "Use TCP probes — often the only kind that gets through a firewall"),
            ("-p port", "Destination port"),
            ("-m N", "Maximum hops (default 64)"),
            ("-q N", "Probes per hop (default 3)"),
            ("-w N", "Seconds to wait per probe"),
            ("-a", "Show the AS number of each hop"),
            ("-s addr", "Source address to send from"),
        ],
        "examples": [
            ("traceroute -n example.com", "Fast numeric trace"),
            ("traceroute -I -n 1.1.1.1", "Trace with ICMP probes, which more routers answer"),
            ("sudo traceroute -P TCP -p 443 example.com", "Trace using TCP to port 443, past UDP-blocking firewalls"),
            ("traceroute -n -m 15 example.com", "Limit the trace to fifteen hops"),
            ("traceroute6 -n ipv6.example.com", "Trace an IPv6 path"),
            ("traceroute -a -n example.com", "Show which networks (AS numbers) the path crosses"),
        ],
        "notes": [
            "Asterisks mean a hop did not reply to the probe, not that the packet was dropped. Only sustained loss at every subsequent hop indicates a real break.",
            "The first hop is your gateway. If it already times out or is wrong, the problem is local — check `netstat -rn`.",
            "Latency rising at one hop and staying flat afterwards is normal (that router deprioritised your probe). Latency rising and staying high for all later hops is a real problem on that link.",
            "TCP mode needs root but is far more informative on paths where UDP and ICMP are filtered.",
        ],
        "see_also": ["ping", "netstat", "dig", "ifconfig"],
        "tags": ["network", "diagnostics", "routing", "latency"],
        "category": "networking",
    },
    {
        "command": "uname",
        "tagline": "print system and kernel information",
        "summary": (
            "uname reports the kernel name, version and machine architecture. On macOS it "
            "describes Darwin, not the marketing release — `uname -r` gives something like "
            "24.1.0, not 15.1. For the macOS version use sw_vers; for architecture, be "
            "aware that `uname -m` reports what the *process* is running as, so a Rosetta "
            "shell says x86_64 on Apple Silicon."
        ),
        "synopsis": [
            "uname [-amnprsv]",
        ],
        "options": [
            ("-s", "Kernel name — \"Darwin\""),
            ("-r", "Kernel release, e.g. 24.1.0"),
            ("-v", "Kernel version string, including build date"),
            ("-m", "Machine hardware name: arm64 or x86_64"),
            ("-p", "Processor architecture"),
            ("-n", "Network node hostname"),
            ("-a", "Everything"),
        ],
        "examples": [
            ("uname -a", "Full system summary"),
            ("uname -m", "arm64 on Apple Silicon, x86_64 on Intel (or under Rosetta)"),
            ("uname -r", "Darwin kernel release"),
            ("[ \"$(uname -s)\" = \"Darwin\" ] && echo macOS", "Portable OS test in a shell script"),
            ("sysctl -n hw.optional.arm64", "The reliable Apple Silicon test, unaffected by Rosetta"),
            ("arch", "Which architecture the current process is running as"),
        ],
        "notes": [
            "`uname -m` reflects the process, not the hardware. A shell launched under Rosetta reports x86_64 on an M-series Mac — `sysctl -n hw.optional.arm64` tells the truth.",
            "Darwin kernel versions do not map linearly to macOS releases; do not derive one from the other. Use `sw_vers -productVersion`.",
            "`uname -n` returns the hostname, which on macOS is whichever of the three scutil names is currently in effect.",
            "In portable scripts, `uname -s` is the standard way to branch between Darwin and Linux.",
        ],
        "see_also": ["sw_vers", "sysctl", "system_profiler", "hostname"],
        "tags": ["system-info", "kernel", "architecture"],
        "category": "system_admin",
    },
    {
        "command": "uniq",
        "tagline": "report or filter repeated adjacent lines",
        "summary": (
            "uniq collapses or counts *adjacent* duplicate lines. That word does all the "
            "work: uniq will not find duplicates scattered through a file, so it is almost "
            "always preceded by sort. The `sort | uniq -c | sort -rn` idiom is the standard "
            "way to rank anything by frequency."
        ),
        "synopsis": [
            "uniq [-cdu] [-i] [-f fields] [-s chars] [input [output]]",
        ],
        "options": [
            ("-c", "Prefix each line with the number of occurrences"),
            ("-d", "Print only lines that are duplicated"),
            ("-u", "Print only lines that appear exactly once"),
            ("-i", "Case-insensitive comparison"),
            ("-f N", "Ignore the first N fields when comparing"),
            ("-s N", "Ignore the first N characters when comparing"),
        ],
        "examples": [
            ("sort access.log | uniq -c | sort -rn | head", "Most frequent lines in a log"),
            ("sort emails.txt | uniq -d", "Addresses that appear more than once"),
            ("sort ids.txt | uniq -u", "Entries that appear exactly once"),
            ("awk '{print $1}' access.log | sort | uniq -c | sort -rn | head -20", "Top twenty client addresses"),
            ("cut -d, -f2 data.csv | sort -f | uniq -ci", "Case-insensitive frequency count of a CSV column"),
        ],
        "notes": [
            "uniq only compares neighbouring lines. Without a preceding `sort`, scattered duplicates go unnoticed — the single most common mistake with this command.",
            "`sort -u` is faster than `sort | uniq` when you only need deduplication and not counts.",
            "`-f` and `-s` skip fields or characters before comparing, which lets you ignore a timestamp prefix and deduplicate on the message body.",
            "The count from `-c` is right-aligned and padded, so pipe through `sort -rn` rather than `sort -r` to rank correctly.",
        ],
        "see_also": ["sort", "wc", "awk", "cut"],
        "tags": ["text-processing", "deduplication", "counting"],
    },
    {
        "command": "wc",
        "tagline": "count lines, words, characters and bytes",
        "summary": (
            "wc counts. With no options it prints lines, words and bytes; with `-l` just "
            "lines, which is its overwhelmingly most common use — how many matches did that "
            "grep find, how many files does that find return, how big is this log."
        ),
        "synopsis": [
            "wc [-clmw] [file ...]",
        ],
        "options": [
            ("-l", "Count lines"),
            ("-w", "Count words"),
            ("-c", "Count bytes"),
            ("-m", "Count characters (differs from -c for UTF-8)"),
            ("-L", "Length of the longest line"),
        ],
        "examples": [
            ("wc -l access.log", "How many lines in a log"),
            ("grep -c error app.log", "Count matches directly — faster than piping grep into wc"),
            ("find . -name '*.py' | wc -l", "How many Python files in a tree"),
            ("ls -1 ~/Downloads | wc -l", "How many items in a directory"),
            ("wc -l *.txt | tail -1", "Total lines across several files"),
            ("cat file.txt | wc -l", "Note: piping loses the filename from the output"),
        ],
        "notes": [
            "BSD wc pads its numbers with leading spaces. `wc -l < file` (redirect rather than argument) gives a clean number with no filename, which is what scripts want.",
            "`grep -c` counts matching lines without a second process and is preferable to `grep ... | wc -l`.",
            "A file whose last line has no trailing newline is counted as one line short — `wc -l` counts newline characters, not lines of text.",
            "`-m` and `-c` differ for non-ASCII text; use `-m` when you mean characters.",
        ],
        "see_also": ["grep", "sort", "uniq", "find"],
        "tags": ["text-processing", "counting"],
    },
    {
        "command": "who",
        "tagline": "show who is logged in",
        "summary": (
            "who lists login sessions with their terminal and login time. On macOS a "
            "graphical login shows as `console`, while each Terminal tab and SSH session "
            "gets its own ttys device — so a single user working locally with several tabs "
            "legitimately appears many times."
        ),
        "synopsis": [
            "who [-aHTu] [am i]",
            "w",
        ],
        "options": [
            ("(no options)", "User, terminal, login time and origin"),
            ("-H", "Print column headings"),
            ("-u", "Include idle time and process id"),
            ("-T", "Show whether the terminal accepts messages"),
            ("-a", "Everything available"),
            ("am i", "Show only your own session"),
            ("-b", "Time of the last system boot"),
        ],
        "examples": [
            ("who", "Current login sessions"),
            ("who -Hu", "Sessions with headings and idle times"),
            ("who am i", "Your own session and where it came from"),
            ("who -b", "When the system last booted"),
            ("w", "Sessions plus load average and what each user is running"),
            ("last | head -20", "Recent login history from the accounting file"),
        ],
        "notes": [
            "`console` is the graphical login session; `ttys00N` entries are Terminal tabs and SSH sessions.",
            "The origin field shows the remote host for SSH sessions, which makes `who` a quick check for unexpected remote logins.",
            "Under sudo, `whoami` returns root but `who am i` still shows the original user — the distinction matters in scripts that need to know who invoked them.",
            "`last` reads the wtmp accounting file for historical logins; `who` only shows current ones.",
        ],
        "see_also": ["whoami", "id", "w", "last"],
        "tags": ["users", "sessions", "monitoring"],
    },
    {
        "command": "whoami",
        "tagline": "print the effective username",
        "summary": (
            "whoami prints the username of the effective user — who the shell is acting as "
            "right now. Under sudo that is root, which is exactly what makes it useful as "
            "a guard at the top of a script that must, or must not, be run with elevated "
            "privileges."
        ),
        "synopsis": [
            "whoami",
        ],
        "options": [
            ("(no options)", "Print the effective username"),
        ],
        "examples": [
            ("whoami", "Your effective username"),
            ("sudo whoami", "Prints root — confirms sudo is working"),
            ("[ \"$(whoami)\" = root ] || { echo 'run with sudo'; exit 1; }", "Require root in a script"),
            ("[ \"$(id -u)\" -eq 0 ] && echo 'running as root'", "The more portable form of the same test"),
            ("logname", "Who originally logged in, regardless of sudo"),
        ],
        "notes": [
            "whoami reports the *effective* user. Under sudo it says root; `logname` or `$SUDO_USER` gives the person who invoked it.",
            "`id -u` is the more portable root test in scripts — `whoami` does not exist on every Unix.",
            "In a launchd daemon the effective user is whatever the plist's UserName specifies, which is root unless set otherwise.",
            "$USER can be stale or spoofed in an inherited environment; whoami asks the system.",
        ],
        "see_also": ["who", "id", "sudo", "su"],
        "tags": ["users", "identity", "scripting"],
    },
    {
        "command": "xattr",
        "tagline": "display and manipulate extended attributes",
        "summary": (
            "xattr reads, writes and deletes the extended attributes macOS attaches to "
            "files — Finder tags, download provenance, and above all "
            "`com.apple.quarantine`, the flag that makes Gatekeeper challenge a downloaded "
            "application. Removing that attribute is the documented fix for \"cannot be "
            "opened because the developer cannot be verified\", and should only be done for "
            "software you actually trust."
        ),
        "synopsis": [
            "xattr [-l] [-r] file ...",
            "xattr -d attribute file",
            "xattr -w attribute value file",
            "xattr -c file",
        ],
        "options": [
            ("(no options)", "List attribute names"),
            ("-l", "List names and values"),
            ("-p name", "Print one attribute's value"),
            ("-w name value", "Write an attribute"),
            ("-d name", "Delete an attribute"),
            ("-c", "Clear all attributes"),
            ("-r", "Recurse into directories"),
            ("-s", "Act on symlinks themselves"),
        ],
        "examples": [
            ("xattr ~/Downloads/tool.dmg", "Which extended attributes a downloaded file carries"),
            ("xattr -l ~/Downloads/tool.dmg", "Attribute names and values, including the origin URL"),
            ("xattr -d com.apple.quarantine ~/Downloads/Tool.app", "Clear the quarantine flag from software you trust"),
            ("xattr -dr com.apple.quarantine ~/Downloads/Tool.app", "Clear it recursively from a bundle"),
            ("xattr -c file.txt", "Remove every extended attribute"),
            ("xattr -p com.apple.metadata:kMDItemWhereFroms file | xxd | head", "Inspect the binary plist recording where a file came from"),
            ("ls -l@ ~/Downloads", "Spot which files have extended attributes at all"),
        ],
        "notes": [
            "`com.apple.quarantine` is what triggers Gatekeeper. Removing it bypasses that check — do it only for software whose provenance you have verified yourself.",
            "Attributes are lost when a file crosses a filesystem that cannot store them (FAT32, some network shares), and when archived with plain zip.",
            "`ls -l@` marks files with extended attributes; `ls -le` shows ACLs. They are different mechanisms.",
            "Some attributes are SIP-protected on system files and cannot be modified even as root.",
        ],
        "see_also": ["spctl", "codesign", "ls", "mdls"],
        "tags": ["metadata", "quarantine", "gatekeeper", "files"],
        "category": "security",
    },
    {
        "command": "xcode-select",
        "tagline": "manage the active developer directory and Command Line Tools",
        "summary": (
            "xcode-select decides which developer toolchain the command line uses: the "
            "standalone Command Line Tools, or a full Xcode installation. Getting this "
            "wrong is behind a large share of macOS build failures — missing headers, "
            "\"xcrun: error: invalid active developer path\", and compilers that cannot find "
            "an SDK."
        ),
        "synopsis": [
            "xcode-select -p",
            "xcode-select --install",
            "sudo xcode-select -s /Applications/Xcode.app/Contents/Developer",
            "sudo xcode-select -r",
        ],
        "options": [
            ("-p, --print-path", "Print the active developer directory"),
            ("--install", "Install the Command Line Tools"),
            ("-s path, --switch path", "Set the active developer directory (needs sudo)"),
            ("-r, --reset", "Reset to the default location"),
            ("--version", "Print the xcode-select version"),
        ],
        "examples": [
            ("xcode-select -p", "Which toolchain is active"),
            ("xcode-select --install", "Install the Command Line Tools — needed before Homebrew or git"),
            ("sudo xcode-select -s /Applications/Xcode.app/Contents/Developer", "Point the command line at full Xcode"),
            ("sudo xcode-select -s /Library/Developer/CommandLineTools", "Point it back at the standalone tools"),
            ("sudo xcode-select -r", "Reset to the default after a broken switch"),
            ("xcrun --show-sdk-path", "Confirm the SDK the active toolchain resolves to"),
        ],
        "notes": [
            "\"invalid active developer path\" after a macOS upgrade means the tools were removed. `xcode-select --install` fixes it; `sudo xcode-select -r` fixes a bad switch.",
            "/Library/Developer/CommandLineTools is the standalone toolchain; a path inside Xcode.app is the full one. Simulators, Metal tooling and some SDKs only exist in the latter.",
            "Homebrew requires the Command Line Tools and will refuse to build formulae from source without them.",
            "Switching the active directory affects every tool that goes through xcrun — clang, git, make, swift.",
        ],
        "see_also": ["xcrun", "brew", "codesign", "sw_vers"],
        "tags": ["development", "xcode", "toolchain"],
        "category": "system_admin",
    },
    {
        "command": "xcrun",
        "tagline": "locate and run developer tools from the active toolchain",
        "summary": (
            "xcrun finds a developer tool in the active SDK and runs it. Rather than "
            "hard-coding a path to clang or simctl, you ask xcrun, and it resolves the "
            "right binary for the toolchain xcode-select has selected. It is also the front "
            "end for notarization (`xcrun notarytool`) and simulator control (`xcrun "
            "simctl`)."
        ),
        "synopsis": [
            "xcrun [--sdk sdkname] tool [args]",
            "xcrun --find tool",
            "xcrun --show-sdk-path | --show-sdk-version",
        ],
        "options": [
            ("--find tool", "Print the full path to a tool without running it"),
            ("--run tool", "Run the tool (the default when a tool is named)"),
            ("--sdk name", "Use a specific SDK: macosx, iphoneos, iphonesimulator"),
            ("--show-sdk-path", "Path to the active SDK"),
            ("--show-sdk-version", "Version of the active SDK"),
            ("--toolchain name", "Use a named toolchain"),
            ("-l, --log", "Log what xcrun actually executes"),
        ],
        "examples": [
            ("xcrun --find clang", "Where clang actually lives in the active toolchain"),
            ("xcrun --show-sdk-path", "The SDK path a compiler will use"),
            ("xcrun clang -o hello hello.c", "Compile using the active toolchain"),
            ("xcrun simctl list devices", "List iOS simulators"),
            ("xcrun notarytool submit App.zip --keychain-profile AC_PASSWORD --wait", "Submit a build for notarization and wait for the result"),
            ("xcrun stapler staple App.app", "Attach the notarization ticket to a bundle"),
            ("xcrun --sdk iphoneos --show-sdk-version", "Version of a specific SDK"),
        ],
        "notes": [
            "`xcrun: error: invalid active developer path` means the toolchain xcode-select points at is missing — reinstall with `xcode-select --install`.",
            "notarytool replaced the retired altool; a keychain profile created with `xcrun notarytool store-credentials` avoids putting an app-specific password in scripts.",
            "simctl and the iOS SDKs require full Xcode, not just the Command Line Tools.",
            "`xcrun --find` is the reliable way for a build script to locate a tool without assuming a path that differs between Command Line Tools and Xcode installs.",
        ],
        "see_also": ["xcode-select", "codesign", "spctl", "lipo"],
        "tags": ["development", "xcode", "notarization", "toolchain"],
        "category": "system_admin",
    },
]
