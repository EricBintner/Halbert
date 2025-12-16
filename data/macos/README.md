# macOS Knowledge Base

**Phase 25: macOS Platform Support**

This directory contains documentation for the macOS version of Halbert.
Only included in macOS App Store builds.

## Collections to Build

### Core macOS

| Collection | Source | Priority | Status |
|------------|--------|----------|--------|
| `homebrew-docs` | brew.sh, formulae.brew.sh | High | ⬜ |
| `launchd-reference` | Apple developer docs | High | ⬜ |
| `diskutil-apfs` | man pages, Apple docs | High | ⬜ |
| `macos-troubleshooting` | Apple support articles | High | ⬜ |

### System Administration

| Collection | Source | Priority | Status |
|------------|--------|----------|--------|
| `unified-logging` | Apple developer docs | Medium | ⬜ |
| `networksetup` | man pages | Medium | ⬜ |
| `pmset-power` | man pages, forums | Medium | ⬜ |
| `defaults-system` | defaults command guide | Medium | ⬜ |

### Security

| Collection | Source | Priority | Status |
|------------|--------|----------|--------|
| `gatekeeper-sip` | Apple security docs | High | ⬜ |
| `filevault` | Apple FileVault guide | Medium | ⬜ |
| `tcc-privacy` | TCC database, permissions | Low | ⬜ |
| `keychain` | Keychain services docs | Low | ⬜ |

### Apple Silicon

| Collection | Source | Priority | Status |
|------------|--------|----------|--------|
| `apple-silicon-overview` | Apple developer docs | High | ⬜ |
| `rosetta-2` | Rosetta compatibility | Medium | ⬜ |
| `mlx-optimization` | MLX framework docs | Medium | ⬜ |
| `unified-memory` | Memory management | Low | ⬜ |

### Backup & Recovery

| Collection | Source | Priority | Status |
|------------|--------|----------|--------|
| `timemachine` | Apple Time Machine docs | High | ⬜ |
| `recovery-mode` | macOS Recovery guide | Medium | ⬜ |
| `reinstall-macos` | Clean install guides | Low | ⬜ |

## Scraping Strategy

1. **Apple Developer Documentation**
   - Use developer.apple.com APIs
   - Focus on system administration topics
   - Respect rate limits

2. **Man Pages**
   - Extract from local macOS system
   - Format as markdown

3. **Homebrew**
   - formulae.brew.sh API
   - Focus on common tools

4. **Community Sources**
   - macOS tips from reputable sources
   - Stack Overflow macOS tag (high-quality only)

## File Format

Same JSONL format as Linux collections:

```json
{
  "id": "homebrew-install-guide",
  "url": "https://docs.brew.sh/Installation",
  "title": "Homebrew Installation Guide",
  "content": "...",
  "source": "homebrew-docs",
  "category": "package_management",
  "platform": "macos",
  "scraped_at": "2024-01-15T10:00:00Z"
}
```

**Important**: All documents must include `"platform": "macos"` field.

## Build Separation

This directory is:
- ✅ Included in macOS builds
- ❌ Excluded from Linux builds

See `config/platforms.yml` for build configuration.
