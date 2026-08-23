# BSD Knowledge Base

**Phase 25: macOS Platform Support**

This directory contains BSD-related documentation shared between macOS and potential BSD support.
Included in macOS builds (macOS is BSD-derived).

## Collections

### BSD Fundamentals

| Collection | Source | Docs | Status |
|------------|--------|------|--------|
| `freebsd-handbook` | docs.freebsd.org | 41 | ✅ |
| `freebsd-man-pages` | man.freebsd.org | 185 | ✅ |
| `bsd-networking` | FreeBSD handbook networking | - | ✅ (in handbook) |
| `bsd-permissions` | FreeBSD file permissions | - | ✅ (in handbook) |
| `bsd-filesystem` | UFS/ZFS basics | - | ✅ (in handbook) |

### UNIX Concepts

| Collection | Source | Priority | Status |
|------------|--------|----------|--------|
| `unix-signals` | Signal handling | Low | ⬜ |
| `unix-processes` | Process management | Low | ⬜ |
| `unix-pipes` | Pipes and redirection | Low | ⬜ |

## Relevance to macOS

macOS is derived from BSD (specifically, Darwin which includes FreeBSD components).
Understanding BSD concepts helps with:

- File permissions (chmod, chown)
- Network configuration
- Process management
- Shell scripting

## Build Separation

This directory is:
- ✅ Included in macOS builds
- ❌ Excluded from Linux builds

See `config/platforms.yml` for build configuration.
