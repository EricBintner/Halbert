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
]
