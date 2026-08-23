# macOS Knowledge Base

**Phase 25: macOS Platform Support**

This directory contains documentation for the macOS version of Halbert.
Only included in macOS App Store builds.

## Collections

### Core macOS

| Collection | Source | Docs | Status |
|------------|--------|------|--------|
| `man-pages` | Local macOS system | 7,310 | ✅ |
| `homebrew` | brew.sh, formulae.brew.sh | 8,777 | ✅ |
| `support` | SS64, synthetic guides | 93 | ✅ |

### System Administration

| Collection | Source | Priority | Status |
|------------|--------|----------|--------|
| `unified-logging` | Apple developer docs | Medium | ⬜ |
| `networksetup` | man pages | Medium | ✅ (in man-pages) |
| `pmset-power` | man pages, forums | Medium | ✅ (in man-pages) |
| `defaults-system` | defaults command guide | Medium | ✅ (in man-pages) |

### Security

| Collection | Source | Priority | Status |
|------------|--------|----------|--------|
| `gatekeeper-sip` | man pages, synthetic guides | High | ✅ (in support) |
| `filevault` | man pages | Medium | ✅ (in man-pages) |
| `tcc-privacy` | TCC database, permissions | Low | ⬜ |
| `keychain` | man pages | Low | ✅ (in man-pages) |

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
| `timemachine` | man pages, synthetic guides | High | ✅ (in man-pages + support) |
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
