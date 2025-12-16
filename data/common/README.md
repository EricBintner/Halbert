# Common Knowledge Base

**Phase 25: Cross-Platform Support**

This directory contains documentation applicable to ALL platforms (Linux and macOS).
Included in both Linux and macOS builds.

## Collections to Build

### Shell & Scripting

| Collection | Source | Priority | Status |
|------------|--------|----------|--------|
| `bash-guide` | GNU Bash manual | High | ⬜ |
| `zsh-guide` | Zsh documentation | High | ⬜ |
| `shell-scripting` | Advanced Bash scripting | Medium | ⬜ |
| `awk-sed` | Text processing | Low | ⬜ |

### Version Control

| Collection | Source | Priority | Status |
|------------|--------|----------|--------|
| `git-docs` | git-scm.com | High | ⬜ |
| `git-workflows` | Common workflows | Medium | ⬜ |
| `github-cli` | gh CLI documentation | Low | ⬜ |

### Text Editors

| Collection | Source | Priority | Status |
|------------|--------|----------|--------|
| `vim-guide` | Vim documentation | Medium | ⬜ |
| `neovim-docs` | Neovim docs | Medium | ⬜ |

### Remote Access

| Collection | Source | Priority | Status |
|------------|--------|----------|--------|
| `ssh-guide` | OpenSSH documentation | High | ⬜ |
| `gpg-keys` | GnuPG guide | Medium | ⬜ |
| `ssh-config` | SSH configuration | Medium | ⬜ |

### Containers

| Collection | Source | Priority | Status |
|------------|--------|----------|--------|
| `docker-docs` | Docker documentation | High | ⬜ |
| `docker-compose` | Compose reference | Medium | ⬜ |
| `container-basics` | Container concepts | Medium | ⬜ |

### Development

| Collection | Source | Priority | Status |
|------------|--------|----------|--------|
| `python-dev` | Python documentation | Medium | ⬜ |
| `venv-guide` | Virtual environments | Medium | ⬜ |
| `pip-guide` | pip usage | Low | ⬜ |

### General UNIX

| Collection | Source | Priority | Status |
|------------|--------|----------|--------|
| `cron-guide` | Cron job syntax | Medium | ⬜ |
| `regex-guide` | Regular expressions | Medium | ⬜ |
| `file-permissions` | chmod/chown basics | Medium | ⬜ |

## Why Common?

These topics work identically (or nearly so) on both Linux and macOS:
- Bash/Zsh scripting
- Git commands
- SSH configuration
- Docker usage
- Vim/Neovim

Including them in `common/` avoids duplication between platforms.

## File Format

Same JSONL format as platform-specific collections:

```json
{
  "id": "git-basics",
  "url": "https://git-scm.com/docs/gittutorial",
  "title": "Git Tutorial",
  "content": "...",
  "source": "git-docs",
  "category": "version_control",
  "platform": "common",
  "scraped_at": "2024-01-15T10:00:00Z"
}
```

**Important**: All documents should include `"platform": "common"` field.

## Build Separation

This directory is:
- ✅ Included in Linux builds
- ✅ Included in macOS builds

See `config/platforms.yml` for build configuration.
