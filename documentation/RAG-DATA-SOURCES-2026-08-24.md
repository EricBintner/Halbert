# RAG Data Sources and Scraping Reference

**Created:** 2026-08-24
**Status:** Living document. Update when sources are added or scraping
approaches change.
**Purpose:** Document every data source in the Halbert RAG corpus, how it
was scraped, what license it carries, and how it can be re-scraped or
updated. This is the reference for building an automated refresh pipeline
(CI/CD monthly update) and for publishing the corpus to HuggingFace as
app-specific datasets.

**Reads with:**
- `data/manifest.json` (the corpus manifest with counts and licenses)
- `config/approved_sources.yml` (the domain trust tiers)
- `halbert_core/halbert_core/rag/scrapers/` (the scraper implementations)
- `scripts/urls.*.yml` (URL lists for the URL-based scrapers)
- `.handoff/RAG-OPTIMIZATION-PLAN-2026-08-23.md` (the cleanup plan)

---

## 1. Corpus Overview

The Halbert RAG corpus is a system administration knowledge base covering
Linux, macOS, and BSD. It is organized into four platform buckets:

| Bucket | Purpose | Included in macOS build? | Included in Linux build? |
|--------|---------|--------------------------|--------------------------|
| `data/linux/` | Linux-specific docs | No (copyleft + platform mismatch) | Yes |
| `data/macos/` | macOS-specific docs | Yes | No |
| `data/bsd/` | BSD docs (shared with macOS) | Yes | Yes |
| `data/common/` | Cross-platform tools (git, ssh, bash) | Yes | Yes |

**Current corpus (post-cleanup, 2026-08-23):**

| Source | Docs | Bucket | License |
|--------|------|--------|---------|
| Arch Wiki (hannah-eee + extensions) | 2,397 | linux | GNU FDL 1.3 |
| Linux man pages | 4,368 | linux | Various (GPL, BSD, MIT) |
| TLDR pages (common) | 4,616 | common | CC BY 4.0 |
| TLDR pages (linux) | 2,032 | linux | CC BY 4.0 |
| TLDR pages (macos) | 371 | macos | CC BY 4.0 |
| TLDR pages (bsd) | 30 | bsd | CC BY 4.0 |
| Common tools docs | 68 | common | Various (permissive) |
| Linux system docs | 243 | linux | Various (permissive, CC BY-SA) |
| Vendor/distro docs | 82 | linux | Various (permissive) |
| Homebrew | 8,777 | macos | BSD-2-Clause |
| macOS man pages | 5,280 | macos | Various (BSD, APSL 2.0) |
| macOS support (SS64 + synthetic) | 104 | macos | CC BY-NC 4.0 (SS64), Halbert (synthetic) |
| Ask Different | 269 | macos | CC BY-SA 4.0 |
| MacPorts Guide | 10 | macos | BSD-like |
| FreeBSD Handbook | 41 | bsd | FreeBSD Documentation License |
| FreeBSD man pages | 181 | bsd | FreeBSD Documentation License |
| **Total** | **28,869** | | |

---

## 2. HuggingFace Dataset Plan

The corpus will be published as three HuggingFace datasets, matching the
platform buckets. Each dataset is a JSONL file (or set of files) with the
unified schema:

```json
{
  "id": "string",
  "url": "string",
  "title": "string",
  "content": "string",
  "source": "string",
  "category": "string",
  "tags": ["string"],
  "scraped_at": "ISO-8601",
  "metadata": {}
}
```

### Dataset 1: `halbert-rag-linux`

**Contents:** All `data/linux/` and `data/common/` JSONL files.
**Approximate size:** ~9,200 docs (after dedup).
**License:** Mixed — GNU FDL (Arch Wiki), CC BY 4.0 (TLDR), various
permissive (man pages, vendor docs). See per-source licenses below.
**Update cadence:** Monthly.
**Files:**
- `linux_man_pages.jsonl` — Linux man pages
- `arch_wiki.jsonl` — Arch Wiki (hannah-eee dataset + extensions)
- `tldr_linux.jsonl` — TLDR Linux pages
- `tldr_common.jsonl` — TLDR common pages
- `system_docs.jsonl` — Merged Linux system docs (systemd, networking, etc.)
- `vendor_docs.jsonl` — Vendor/distro docs (Docker, K8s, NVIDIA, Ubuntu)
- `common_tools.jsonl` — Cross-platform tools (git, shell, docker, etc.)

### Dataset 2: `halbert-rag-macos`

**Contents:** All `data/macos/` and `data/bsd/` JSONL files.
**Approximate size:** ~15,000 docs (Homebrew dominates).
**License:** Mixed — BSD-2-Clause (Homebrew), BSD/APSL (macOS man pages),
CC BY-SA 4.0 (Ask Different), CC BY-NC 4.0 (SS64 — exclude from commercial
builds), FreeBSD Documentation License.
**Update cadence:** Monthly.
**Files:**
- `macos_man_pages.jsonl` — macOS man pages
- `homebrew.jsonl` — Homebrew formulas, casks, and docs
- `macos_support.jsonl` — SS64 command reference + synthetic guides
- `ask_different.jsonl` — Ask Different Q&A
- `macports_guide.jsonl` — MacPorts Guide
- `freebsd_handbook.jsonl` — FreeBSD Handbook
- `freebsd_man_pages.jsonl` — FreeBSD man pages
- `tldr_macos.jsonl` — TLDR macOS pages
- `tldr_bsd.jsonl` — TLDR BSD pages

### Dataset 3: `halbert-rag-eval`

**Contents:** The retrieval eval test queries and expected source matches.
**Purpose:** Reproducible retrieval quality measurement.
**Update cadence:** When sources change or new domains are added.
**Files:**
- `eval_queries.jsonl` — 20-50 test queries with expected sources

---

## 3. Source-by-Source Scraping Reference

Each source below documents: what it is, where it comes from, how to
re-scrape it, the scraper file, the output path, the license, and update
notes for the automation pipeline.

---

### 3.1 Arch Wiki

| Field | Value |
|-------|-------|
| **What** | Arch Linux Wiki — comprehensive Linux sysadmin documentation |
| **Source URL** | `https://wiki.archlinux.org` |
| **Scraper** | `halbert_core/halbert_core/rag/scrapers/arch_wiki.py` (`ArchWikiScraper`) |
| **Output** | `data/linux/arch-wiki/arch_wiki.jsonl` |
| **Docs** | 2,397 (2,331 main + 43 extensions + 23 more-arch) |
| **License** | GNU FDL 1.3 |
| **mac_build** | No (copyleft) |

**How it was scraped:**
The scraper uses the Arch Wiki MediaWiki API (`/api.php`) to enumerate
pages in target categories (System_administration, Networking, Security,
etc.) plus a list of priority pages (Systemd, fstab, SSH, etc.). Each
page is fetched and the HTML is converted to plain text with section
headings preserved.

**Re-scrape command:**
```bash
.venv/bin/python -m halbert_core.rag.scrapers.arch_wiki \
  --output data/linux/arch-wiki/arch_wiki.jsonl \
  --max-pages 2500
```

**Alternative (cleaner dataset):**
The `hannah-eee/arch-wiki-docs` HuggingFace dataset is a pre-cleaned
version of the Arch Wiki with ~10K English pages. It was used to
supplement our scrape. Download:
```bash
.venv/bin/python -c "
from datasets import load_dataset
ds = load_dataset('hannah-eee/arch-wiki-docs', split='train')
# Convert to JSONL with unified schema
"
```

**Update notes:**
- Arch Wiki changes frequently. Monthly re-scrape is worthwhile.
- The MediaWiki API has rate limits. The scraper has a 1-second delay
  between requests.
- The hannah-eee dataset is updated less frequently. Check HuggingFace
  for the last update date.
- The `arch-wiki-ext/` and `more-arch/` files are curated extensions
  from URL lists in `scripts/urls.arch-wiki-extended.yml` and
  `scripts/urls.more-arch.yml`.

---

### 3.2 Linux Man Pages

| Field | Value |
|-------|-------|
| **What** | Linux system man pages (sections 1-8) |
| **Source** | Local system (`man` command on a Linux host) |
| **Scraper** | `halbert_core/halbert_core/rag/scrapers/linux_man.py` (`LinuxManPageExtractor`) |
| **Output** | `data/linux/man-pages/man_pages.jsonl` |
| **Docs** | 4,368 (after cleaning: backspace artifacts stripped, empties removed, deduped) |
| **License** | Various (GPL, BSD, MIT — per man page) |
| **mac_build** | Yes (man pages are reference, not platform-specific binaries) |

**How it was scraped:**
The extractor runs `man -w` to list all man page paths on the system,
then reads each page's raw source (groff/troff) and converts to plain
text using `man -l <path>`. The output includes the section number,
command name, and full text.

**Re-scrape command:**
```bash
# Must run on a Linux host with man pages installed
.venv/bin/python -m halbert_core.rag.scrapers.linux_man \
  --output data/linux/man-pages/man_pages.jsonl

# Then clean formatting artifacts:
.venv/bin/python scripts/clean_man_pages.py \
  --input data/linux/man-pages/man_pages.jsonl \
  --output data/linux/man-pages/man_pages.jsonl
```

**Update notes:**
- Man pages change when packages are installed/updated. Re-scrape after
  a system update.
- The `clean_man_pages.py` script strips backspace (`\b`) formatting
  artifacts from `man` output. Always run it after extraction.
- This must run on a Linux host. It cannot run on macOS (different man
  page set).
- For the HuggingFace dataset, this is a snapshot. Re-scraping requires
  a Linux environment.

---

### 3.3 TLDR Pages

| Field | Value |
|-------|-------|
| **What** | TLDR simplified command summaries with examples |
| **Source URL** | `https://github.com/tldr-pages/tldr` |
| **Scraper** | Manual conversion from the GitHub repo |
| **Output** | `data/common/tldr/tldr.jsonl`, `data/linux/tldr/tldr.jsonl`, `data/macos/tldr/tldr.jsonl`, `data/bsd/tldr/tldr.jsonl` |
| **Docs** | 7,049 total (4,616 common + 2,032 linux + 371 macos + 30 bsd) |
| **License** | CC BY 4.0 |
| **mac_build** | Yes |

**How it was scraped:**
The TLDR pages were cloned from `github.com/tldr-pages/tldr` and
converted to JSONL. Each page is a markdown file
(`pages/common/command.md`, `pages/linux/command.md`, etc.) that was
parsed into the unified schema with the command name as the title and
the markdown content as the content field.

**Re-scrape command:**
```bash
git clone --depth 1 https://github.com/tldr-pages/tldr /tmp/tldr
.venv/bin/python scripts/tldr_to_jsonl.py \
  --input /tmp/tldr/pages \
  --output-common data/common/tldr/tldr.jsonl \
  --output-linux data/linux/tldr/tldr.jsonl \
  --output-macos data/macos/tldr/tldr.jsonl \
  --output-bsd data/bsd/tldr/tldr.jsonl
```

**Update notes:**
- TLDR pages are community-edited on GitHub. Monthly re-clone captures
  new commands and updates.
- The conversion script (`scripts/tldr_to_jsonl.py`) needs to be written
  if it doesn't exist yet — the initial conversion was done manually.
- The `pages/` directory structure maps directly to our platform buckets:
  `pages/common/` → `data/common/tldr/`, `pages/linux/` → `data/linux/tldr/`,
  `pages/osx/` → `data/macos/tldr/`, `pages/freebsd/` → `data/bsd/tldr/`.

---

### 3.4 Homebrew

| Field | Value |
|-------|-------|
| **What** | Homebrew formulas, casks, and official documentation |
| **Source URLs** | `https://formulae.brew.sh/api/formula.json`, `https://formulae.brew.sh/api/cask.json`, `https://docs.brew.sh` |
| **Scraper** | `halbert_core/halbert_core/rag/scrapers/homebrew.py` (`HomebrewScraper`) |
| **Output** | `data/macos/homebrew/homebrew.jsonl` |
| **Docs** | 8,777 (formulas + casks + doc pages) |
| **License** | BSD-2-Clause |
| **mac_build** | Yes |

**How it was scraped:**
The scraper fetches the Homebrew formula JSON API
(`formulae.brew.sh/api/formula.json`) which returns all formulas with
name, description, homepage, dependencies, etc. It also fetches the
cask JSON API for GUI applications. Additionally, it scrapes selected
documentation pages from `docs.brew.sh` (FAQ, Installation, Formula
Cookbook, etc.).

**Re-scrape command:**
```bash
.venv/bin/python -m halbert_core.rag.scrapers.homebrew \
  --output data/macos/homebrew/homebrew.jsonl \
  --max-formulas 0  # 0 = all
```

**Update notes:**
- Homebrew formulas change daily. Monthly re-scrape is essential.
- The JSON API is fast (single request for all formulas). No rate
  limiting needed.
- The cask API is similarly fast.
- Doc pages from `docs.brew.sh` change less frequently.

---

### 3.5 macOS Man Pages

| Field | Value |
|-------|-------|
| **What** | macOS system man pages (sections 1-8) |
| **Source** | Local macOS system (`man` command) |
| **Scraper** | `halbert_core/halbert_core/rag/scrapers/macos_man.py` (`MacOSManPageExtractor`) |
| **Output** | `data/macos/man-pages/macos_man_pages.jsonl` |
| **Docs** | 5,280 (after cleaning and dedup) |
| **License** | Various (BSD for BSD-derived, APSL 2.0 for Apple-specific) |
| **mac_build** | Yes |

**How it was scraped:**
Same approach as Linux man pages: `man -w` to list all paths, then
`man -l <path>` to render each page to text. The `clean_man_pages.py`
script was run to strip backspace formatting artifacts.

**Re-scrape command:**
```bash
# Must run on macOS
.venv/bin/python -m halbert_core.rag.scrapers.macos_man \
  --output data/macos/man-pages/macos_man_pages.jsonl

# Clean formatting:
.venv/bin/python scripts/clean_man_pages.py \
  --input data/macos/man-pages/macos_man_pages.jsonl \
  --output data/macos/man-pages/macos_man_pages.jsonl
```

**Update notes:**
- macOS man pages change with OS updates. Re-scrape after a macOS
  version upgrade.
- Must run on macOS. Cannot run on Linux.
- For the HuggingFace dataset, this is a snapshot tied to a macOS
  version. Note the macOS version in the dataset card.

---

### 3.6 macOS Support (SS64 + Synthetic Guides)

| Field | Value |
|-------|-------|
| **What** | SS64 macOS command reference + Halbert-authored synthetic guides |
| **Source URL** | `https://ss64.com/osx` (SS64), synthetic (Halbert-authored) |
| **Scraper** | `halbert_core/halbert_core/rag/scrapers/macos_support.py` (`MacOSSupportScraper`) |
| **Output** | `data/macos/support/macos_support.jsonl` |
| **Docs** | 104 (SS64 command pages + 11+ synthetic guides) |
| **License** | CC BY-NC 4.0 (SS64 — non-commercial only), Halbert (synthetic guides) |
| **mac_build** | Yes (but SS64 content must be excluded from paid App Store builds) |

**How it was scraped:**
The SS64 scraper fetches each command page from `ss64.com/osx/<command>.html`
for a curated list of ~90 macOS commands. The HTML is parsed to extract
the command syntax, description, and examples.

The synthetic guides are Halbert-authored documentation for topics not
well-covered by existing sources: APFS, Apple Silicon, notarization, MDM,
recovery mode, user management, software update, Spotlight, diagnostics,
Gatekeeper/SIP, Keychain, etc. These are generated as structured markdown
with sections, examples, and verification steps.

**Re-scrape command:**
```bash
.venv/bin/python -m halbert_core.rag.scrapers.macos_support \
  --output data/macos/support/macos_support.jsonl
```

**Update notes:**
- SS64 updates occasionally. Check `ss64.com/osx` for changes.
- Synthetic guides are version-controlled in the scraper file. They
  change when the scraper code changes, not via web scraping.
- The SS64 license (CC BY-NC 4.0) prohibits commercial use. The
  synthetic guides are Halbert's own content and can be licensed freely.

---

### 3.7 Ask Different (apple.stackexchange.com)

| Field | Value |
|-------|-------|
| **What** | High-voted Q&A from Apple Stack Exchange |
| **Source URL** | `https://api.stackexchange.com/2.3` (Stack Exchange API) |
| **Scraper** | `halbert_core/halbert_core/rag/scrapers/ask_different.py` (`AskDifferentScraper`) |
| **Output** | `data/macos/ask-different/ask_different.jsonl` |
| **Docs** | 269 (high-voted Q&A with accepted answers) |
| **License** | CC BY-SA 4.0 (attribution required) |
| **mac_build** | Yes |

**How it was scraped:**
The scraper uses the Stack Exchange API to fetch questions tagged with
macOS-relevant tags (macos, macbook, terminal, homebrew, launchd, disk-
utility, time-machine, filevault, gatekeeper, sip, keychain, apple-
silicon, rosetta, etc.). For each question, it fetches the accepted
answer (or top-voted answer if no accepted answer). The Q&A pair is
combined into a single document.

**Re-scrape command:**
```bash
.venv/bin/python -m halbert_core.rag.scrapers.ask_different \
  --output data/macos/ask-different/ask_different.jsonl \
  --max-questions 300
```

**Update notes:**
- The Stack Exchange API has rate limits (300 requests/second without
  a key, 10,000/day with a key). The scraper has a delay between
  requests.
- An API key (`SE_API_KEY`) increases the rate limit. Set it as an
  environment variable.
- New Q&A is posted daily. Monthly re-scrape captures new high-voted
  questions.
- The scraper filters by score (minimum 10) to get quality content.
- CC BY-SA 4.0 requires attribution. Each document includes the
  question URL.

---

### 3.8 MacPorts Guide

| Field | Value |
|-------|-------|
| **What** | MacPorts package manager guide |
| **Source URL** | `https://guide.macports.org/` |
| **Scraper** | `halbert_core/halbert_core/rag/scrapers/macports_guide.py` (`MacPortsGuideScraper`) |
| **Output** | `data/macos/macports-guide/macports_guide.jsonl` |
| **Docs** | 10 (chapters of the guide) |
| **License** | BSD-like (MacPorts Project) |
| **mac_build** | Yes |

**How it was scraped:**
The scraper fetches chapter pages from `guide.macports.org` using a
curated list of chapter paths. The HTML is parsed to extract the
chapter title and content.

**Re-scrape command:**
```bash
.venv/bin/python -m halbert_core.rag.scrapers.macports_guide \
  --output data/macos/macports-guide/macports_guide.jsonl
```

**Update notes:**
- The MacPorts guide changes infrequently. Annual re-scrape is
  sufficient.
- Many URLs returned 404 during the initial scrape, indicating the
  site structure has changed. The chapter list may need updating.

---

### 3.9 FreeBSD Handbook

| Field | Value |
|-------|-------|
| **What** | FreeBSD Handbook — comprehensive BSD sysadmin documentation |
| **Source URL** | `https://docs.freebsd.org/en/books/handbook/` |
| **Scraper** | `halbert_core/halbert_core/rag/scrapers/freebsd_handbook.py` (`FreeBSDHandbookScraper`) |
| **Output** | `data/bsd/freebsd-handbook/freebsd_handbook.jsonl` |
| **Docs** | 41 (chapters) |
| **License** | FreeBSD Documentation License (redistribution with attribution) |
| **mac_build** | Yes |

**How it was scraped:**
The scraper fetches each chapter of the FreeBSD Handbook by its slug
(introduction, installation, network-communication, etc.). The HTML is
parsed to extract the chapter title, section headings, and content.

**Re-scrape command:**
```bash
.venv/bin/python -m halbert_core.rag.scrapers.freebsd_handbook \
  --output data/bsd/freebsd-handbook/freebsd_handbook.jsonl
```

**Update notes:**
- The FreeBSD Handbook is updated with each FreeBSD release. Re-scrape
  after a major FreeBSD release (every ~2 years).
- The chapter list is hardcoded in the scraper. Verify the chapter
  list hasn't changed.

---

### 3.10 FreeBSD Man Pages

| Field | Value |
|-------|-------|
| **What** | FreeBSD man pages for BSD commands shared with macOS |
| **Source URL** | `https://man.freebsd.org/cgi/man.cgi` |
| **Scraper** | `halbert_core/halbert_core/rag/scrapers/freebsd_man.py` (`FreeBSDManPagesScraper`) |
| **Output** | `data/bsd/freebsd-man-pages/freebsd_man_pages.jsonl` |
| **Docs** | 181 (curated set of BSD commands) |
| **License** | FreeBSD Documentation License |
| **mac_build** | Yes |

**How it was scraped:**
The scraper fetches man pages from `man.freebsd.org` for a curated list
of ~90 BSD commands (cat, chmod, cp, df, dmesg, etc.) across sections 1,
5, and 8. The HTML man page is parsed to extract the plain text.

**Re-scrape command:**
```bash
.venv/bin/python -m halbert_core.rag.scrapers.freebsd_man \
  --output data/bsd/freebsd-man-pages/freebsd_man_pages.jsonl
```

**Update notes:**
- FreeBSD man pages change with each release. Re-scrape after a FreeBSD
  release.
- The command list is hardcoded. Add new commands as needed.

---

### 3.11 Stack Overflow / Server Fault / Unix & Linux SE

| Field | Value |
|-------|-------|
| **What** | High-voted Q&A from Stack Overflow, Server Fault, and Unix & Linux SE |
| **Source URL** | `https://api.stackexchange.com/2.3` |
| **Scrapers** | `stackoverflow.py`, `serverfault.py`, `unix_se.py` |
| **Output** | Not currently in the cleaned corpus (were in older JSONL files, may have been removed during dedup) |
| **License** | CC BY-SA 4.0 |
| **mac_build** | Yes |

**How they were scraped:**
Each scraper uses the Stack Exchange API with site-specific tags:
- Stack Overflow: linux, systemd, bash, shell, ssh, networking, firewall,
  sudo, cron, systemctl, permissions, disk-space, filesystem, kernel
- Server Fault: linux, ubuntu, centos, rhel, debian, nginx, apache,
  networking, dns, ssl, tls, certificates, ssh, backup, monitoring
- Unix & Linux SE: linux, bash, shell, systemd, networking, ssh,
  permissions, filesystems, package-management, apt, yum, dnf, grub,
  kernel, cron

**Re-scrape command:**
```bash
.venv/bin/python -m halbert_core.rag.scrapers.stackoverflow \
  --output data/linux/stackoverflow/stackoverflow.jsonl \
  --max-questions 100 --min-score 10

.venv/bin/python -m halbert_core.rag.scrapers.serverfault \
  --output data/linux/serverfault/serverfault.jsonl \
  --max-questions 100 --min-score 10

.venv/bin/python -m halbert_core.rag.scrapers.unix_se \
  --output data/linux/unix-se/unix_se.jsonl \
  --max-questions 100 --min-score 10
```

**Update notes:**
- These were scraped early in the project but may not be in the current
  cleaned corpus. Check if they were removed during dedup.
- Same API rate limits as Ask Different.
- An API key is strongly recommended for these — they fetch many
  questions across many tags.

---

### 3.12 Linux System Docs (Synthetic + URL-Scraped)

| Field | Value |
|-------|-------|
| **What** | Linux system administration guides covering systemd, networking, security, filesystems, backup, monitoring, logging, performance, scheduling, containers, etc. |
| **Source** | Mixed: some scraped from URLs (flatpak.org, docs.docker.com, etc.), most are synthetic (Halbert-authored guides) |
| **Scrapers** | `systemd_docs.py`, `networking_docs.py`, `security_docs.py`, `filesystem_docs.py`, `shell_docs.py`, `logging_docs.py`, `performance_docs.py`, `scheduling_docs.py`, `containers_docs.py`, `snap_docs.py`, `flatpak_docs.py`, `appimage_docs.py`, `ubuntu_docs.py`, etc. |
| **Output** | Multiple files under `data/linux/` (243 docs total across 26 subdirectories) |
| **License** | Various (permissive, CC BY-SA for scraped content) |
| **mac_build** | Yes |

**How they were scraped:**
Most of these scrapers generate synthetic guides — they don't scrape a
URL. They produce structured documentation from hardcoded knowledge:
command references, troubleshooting guides, configuration examples,
best practices. A few (flatpak_docs.py, snap_docs.py) fetch a small
number of pages from official docs.

The URL-based scrapers use URL lists in `scripts/urls.*.yml`:
- `urls.systemd.yml`, `urls.systemd-extended.yml`
- `urls.network.yml`
- `urls.security.yml`
- `urls.filesystems.yml`
- `urls.logging.yml`
- `urls.monitoring.yml`
- `urls.backup-tools.yml`
- `urls.docker.yml`
- `urls.kubernetes.yml`, `urls.helm-k8s.yml`
- `urls.ubuntu-server.yml`
- `urls.aws-cli.yml`
- `urls.devtools.yml`
- `urls.python-tools.yml`
- etc.

**Re-scrape command:**
```bash
# Run all Linux system doc scrapers:
bash scripts/rag_scrape_all.sh

# Or individually:
.venv/bin/python -m halbert_core.rag.scrapers.systemd_docs \
  --output data/linux/systemd-docs/systemd_docs.jsonl
```

**Update notes:**
- Synthetic guides change when the scraper code changes. They don't
  need web scraping.
- URL-scraped docs should be re-scraped monthly to catch official doc
  updates.
- The URL lists in `scripts/urls.*.yml` are the source of truth for
  what gets scraped.

---

### 3.13 Common Tools Docs

| Field | Value |
|-------|-------|
| **What** | Cross-platform tools: git, shell, python, docker, containers, devtools, aws-cli |
| **Source** | Mixed: synthetic guides + URL-scraped pages |
| **Scrapers** | `git_docs.py`, `shell_docs.py`, `python_tools_docs.py` (if exists), `containers_docs.py`, `docker_docs.py`, `devtools_docs.py`, `aws_cli_docs.py` (if exists) |
| **Output** | `data/common/git-docs/`, `data/common/shell-docs/`, `data/common/docker-docs/`, `data/common/containers-docs/`, `data/common/devtools-docs/`, `data/common/python-tools-docs/`, `data/common/aws-cli/` |
| **Docs** | 68 total |
| **License** | Various (permissive) |
| **mac_build** | Yes |

**How they were scraped:**
Same approach as Linux system docs — mostly synthetic guides with some
URL-scraped content. These were moved from `data/linux/` to `data/common/`
because the tools (git, docker, bash, etc.) work identically on Linux
and macOS.

**Update notes:**
- Synthetic guides change with scraper code.
- URL-scraped pages should be re-scraped monthly.

---

### 3.14 Vendor and Distro Docs

| Field | Value |
|-------|-------|
| **What** | Vendor/distro documentation: Docker, Kubernetes, Helm, NVIDIA CUDA, AMD ROCm, Ubuntu |
| **Source URLs** | `docs.docker.com`, `kubernetes.io`, `helm.sh`, `docs.nvidia.com`, `rocm.docs.amd.com`, `help.ubuntu.com` |
| **Scrapers** | URL-based scraping using `scripts/urls.docker.yml`, `urls.kubernetes.yml`, `urls.helm-k8s.yml`, `urls.nvidia.yml`, `urls.rocm.yml`, `urls.ubuntu-server.yml` |
| **Output** | `data/linux/vendor-docs/`, `data/linux/kubernetes-docs/`, `data/linux/helm-k8s/`, `data/linux/nvidia-docs/`, `data/linux/rocm-docs/`, `data/linux/ubuntu-docs/`, `data/linux/ubuntu-server/` |
| **Docs** | 82 total |
| **License** | Various (permissive) |
| **mac_build** | Yes |

**How they were scraped:**
URL-based scraping: the URL lists in `scripts/urls.*.yml` define which
pages to fetch. The generic scraper fetches each URL, parses the HTML,
and extracts the main content.

**Update notes:**
- Vendor docs change frequently (especially Kubernetes and Docker).
  Monthly re-scrape is worthwhile.
- URL lists may break when vendors restructure their docs. Check for
  404s and update the URL lists.

---

## 4. Scraping Infrastructure

### 4.1 Base scraper class

All scrapers inherit from `BaseScraper` (`halbert_core/halbert_core/rag/scrapers/base.py`):

```python
class ScraperConfig:
    output_dir: Path
    rate_limit_delay: float = 1.0  # seconds between requests
    max_retries: int = 3
    timeout: int = 30
    user_agent: str = "Halbert/1.0 (Educational Purpose)"
    respect_robots_txt: bool = True

class ScrapedDocument:
    id: str
    url: str
    title: str
    content: str
    source: str
    category: str
    tags: list[str]
    scraped_at: str
    metadata: dict
```

Every scraper produces `ScrapedDocument` objects which are serialized to
JSONL with the unified schema.

### 4.2 Shell scripts

- `scripts/rag_scrape_all.sh` — runs all Linux scrapers
- `scripts/scrape_macos.sh` — runs all macOS scrapers
- `scripts/build-linux.sh` — builds the Linux RAG index
- `scripts/dev-restart.sh` — restarts the dev environment

### 4.3 URL config files

URL-based scrapers use YAML files in `scripts/urls.*.yml`:

```yaml
urls:
  - https://docs.docker.com/reference/cli/docker/
  - https://docs.docker.com/reference/cli/docker/container/
```

These are consumed by the generic URL scraper (in `rag_scrape_all.sh`)
to fetch and convert pages.

### 4.4 HuggingFace dataset download

`scripts/download_hf_datasets.py` downloads datasets from HuggingFace:
- `tmskss/linux-man-pages-tldr-summarized` (481 examples)
- `harpomaxx/unix-commands` (100 examples)
- `Dam-Buty/arch-wiki` (12,657 examples)
- `hannah-eee/arch-wiki-docs` (clean Arch Wiki, ~10K pages)

These were used to supplement the web-scraped content. The hannah-eee
dataset is the cleanest Arch Wiki source.

### 4.5 Merge and cleanup scripts

- `scripts/merge_rag_data.py` — merges multiple JSONL files
- `scripts/quick_merge_rag.py` — faster merge
- `scripts/clean_man_pages.py` — strips backspace formatting from man pages
- `scripts/arch_wiki_dedup.py` — deduplicates Arch Wiki pages
- `scripts/verify_rag_coverage.py` — verifies corpus coverage

---

## 5. Automation Pipeline Design (Future)

### 5.1 Monthly refresh workflow

```
1. Clone TLDR pages from GitHub
2. Re-scrape Homebrew formulas + casks (API, fast)
3. Re-scrape Arch Wiki (MediaWiki API, ~30 min)
4. Re-scrape FreeBSD Handbook + man pages (~5 min)
5. Re-scrape Ask Different (Stack Exchange API, ~10 min)
6. Re-scrape MacPorts Guide (~2 min)
7. Re-scrape SS64 macOS commands (~5 min)
8. Re-scrape URL-based vendor docs (~15 min)
9. Re-scrape Linux man pages (requires Linux host)
10. Re-scrape macOS man pages (requires macOS host)
11. Run clean_man_pages.py on both man page sets
12. Run normalize_schema.py across all JSONL
13. Run dedup_corpus.py (cross-source dedup)
14. Run manpage_near_dedup.py (macOS/FreeBSD overlap)
15. Convert to markdown (jsonl_to_markdown.py)
16. Rebuild SourcePrep index (prep build)
17. Run corpus_quality_gate.py (20 test queries)
18. Update manifest.json with new counts
19. Publish to HuggingFace (3 datasets)
20. Commit changes, tag release
```

### 5.2 CI/CD considerations

- **Linux man pages** require a Linux runner (GitHub Actions ubuntu-latest)
- **macOS man pages** require a macOS runner (GitHub Actions macos-latest)
- **Stack Exchange API** needs an API key (`SE_API_KEY` secret)
- **Rate limiting** is built into the base scraper (1-second delay)
- **HuggingFace upload** needs a write token (`HF_TOKEN` secret)
- **SourcePrep build** needs the `prep` CLI installed on the runner
- **Total runtime:** ~1-2 hours for a full refresh

### 5.3 Proposed GitHub Actions workflow

```yaml
name: RAG Corpus Refresh
on:
  schedule:
    - cron: '0 0 1 * *'  # 1st of each month at midnight
  workflow_dispatch: {}

jobs:
  scrape-linux:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -r requirements.txt
      - run: .venv/bin/python -m halbert_core.rag.scrapers.linux_man --output data/linux/man-pages/man_pages.jsonl
      - run: .venv/bin/python scripts/clean_man_pages.py --input data/linux/man-pages/man_pages.jsonl
      - run: bash scripts/rag_scrape_all.sh
      - uses: actions/upload-artifact@v4
        with:
          name: linux-data
          path: data/linux/

  scrape-macos:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -r requirements.txt
      - run: .venv/bin/python -m halbert_core.rag.scrapers.macos_man --output data/macos/man-pages/macos_man_pages.jsonl
      - run: .venv/bin/python scripts/clean_man_pages.py --input data/macos/man-pages/macos_man_pages.jsonl
      - run: .venv/bin/python -m halbert_core.rag.scrapers.homebrew --output data/macos/homebrew/homebrew.jsonl
      - run: .venv/bin/python -m halbert_core.rag.scrapers.macos_support --output data/macos/support/macos_support.jsonl
      - run: .venv/bin/python -m halbert_core.rag.scrapers.ask_different --output data/macos/ask-different/ask_different.jsonl
      - env:
          SE_API_KEY: ${{ secrets.SE_API_KEY }}
      - uses: actions/upload-artifact@v4
        with:
          name: macos-data
          path: data/macos/

  scrape-cross-platform:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -r requirements.txt
      - run: git clone --depth 1 https://github.com/tldr-pages/tldr /tmp/tldr
      - run: .venv/bin/python scripts/tldr_to_jsonl.py --input /tmp/tldr/pages
      - run: .venv/bin/python -m halbert_core.rag.scrapers.freebsd_handbook --output data/bsd/freebsd-handbook/freebsd_handbook.jsonl
      - run: .venv/bin/python -m halbert_core.rag.scrapers.freebsd_man --output data/bsd/freebsd-man-pages/freebsd_man_pages.jsonl
      - run: .venv/bin/python -m halbert_core.rag.scrapers.macports_guide --output data/macos/macports-guide/macports_guide.jsonl
      - uses: actions/upload-artifact@v4
        with:
          name: cross-platform-data
          path: data/

  merge-and-publish:
    needs: [scrape-linux, scrape-macos, scrape-cross-platform]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -r requirements.txt
      - uses: actions/download-artifact@v4
      - run: .venv/bin/python scripts/normalize_schema.py --input data/ --dry-run
      - run: .venv/bin/python scripts/dedup_corpus.py --input data/
      - run: .venv/bin/python scripts/corpus_quality_gate.py
      - run: .venv/bin/python scripts/update_manifest.py
      - name: Publish to HuggingFace
        env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
        run: |
          .venv/bin/python scripts/publish_to_hf.py \
            --linux-data data/linux/ data/common/ \
            --dataset halbert-rag-linux
          .venv/bin/python scripts/publish_to_hf.py \
            --macos-data data/macos/ data/bsd/ \
            --dataset halbert-rag-macos
      - run: |
          git config user.name "RAG Refresh Bot"
          git config user.email "rag-refresh@halbert.local"
          git add data/ data/manifest.json
          git commit -m "Monthly RAG corpus refresh ($(date +%Y-%m))"
          git push
```

### 5.4 Scripts that need to be written

The following scripts are referenced in the automation pipeline but don't
exist yet:

| Script | Purpose |
|--------|---------|
| `scripts/tldr_to_jsonl.py` | Convert TLDR GitHub repo to JSONL |
| `scripts/normalize_schema.py` | Normalize all JSONL to unified schema |
| `scripts/dedup_corpus.py` | Cross-source exact dedup |
| `scripts/manpage_near_dedup.py` | macOS/FreeBSD man page near-dedup |
| `scripts/corpus_quality_gate.py` | 20 test queries against SourcePrep |
| `scripts/update_manifest.py` | Update manifest.json with actual counts |
| `scripts/publish_to_hf.py` | Publish JSONL to HuggingFace datasets |
| `scripts/refresh_all.sh` | Orchestrate the full monthly refresh |

---

## 6. License Summary

| Source | License | Commercial use? | Attribution required? |
|--------|---------|-----------------|----------------------|
| Arch Wiki | GNU FDL 1.3 | Yes (copyleft — derivatives must be FDL) | Yes |
| Linux man pages | Various (GPL, BSD, MIT) | Depends on page | Yes |
| TLDR pages | CC BY 4.0 | Yes | Yes |
| Homebrew | BSD-2-Clause | Yes | Yes |
| macOS man pages | Various (BSD, APSL 2.0) | Yes (BSD), APSL has restrictions | Yes |
| SS64 | CC BY-NC 4.0 | **No** (non-commercial only) | Yes |
| Synthetic guides | Halbert (project license) | Yes | No |
| Ask Different | CC BY-SA 4.0 | Yes (copyleft — share-alike) | Yes |
| MacPorts Guide | BSD-like | Yes | Yes |
| FreeBSD Handbook | FreeBSD Documentation License | Yes | Yes |
| FreeBSD man pages | FreeBSD Documentation License | Yes | Yes |
| Stack Overflow | CC BY-SA 4.0 | Yes (copyleft) | Yes |
| Server Fault | CC BY-SA 4.0 | Yes (copyleft) | Yes |
| Unix & Linux SE | CC BY-SA 4.0 | Yes (copyleft) | Yes |
| Vendor docs (Docker, K8s, etc.) | Various (mostly Apache 2.0 or CC) | Yes | Yes |

**Important:** SS64 content (CC BY-NC 4.0) must be excluded from any
paid/commercial build (e.g., Mac App Store). The synthetic guides are
Halbert-authored and can replace SS64 content for commercial builds.

---

## 7. Quality Notes

### 7.1 Known issues (post-cleanup)

- The manifest previously claimed 59,878 docs; actual count was 30,749.
  This has been corrected in manifest v2.0.0.
- 1,902 empty docs were removed (concentrated in Linux man pages).
- 7,307 exact duplicates were removed (23.8% of corpus).
- Linux man pages had backspace formatting artifacts (`\b`) from the
  `man` command. These were stripped with `clean_man_pages.py`.
- 91 commands appear in both macOS and FreeBSD man pages with different
  content. Both versions are kept — they're different implementations.
- The MacPorts guide scraper had many 404s due to site structure changes.
  The chapter list needs updating.

### 7.2 Coverage gaps

- **No Debian-specific docs** (Ubuntu docs are included, but Debian Wiki
  is in approved_sources.yml tier 2 and not yet scraped).
- **No Gentoo docs** (approved but not scraped).
- **Limited BSD coverage** (only FreeBSD Handbook + man pages; no
  OpenBSD or NetBSD).
- **No Windows/Subsystem for Linux docs** (out of scope for Halbert).
- **Limited Q&A coverage** (Ask Different has 269 docs; Stack Overflow
  and Server Fault scrapers exist but output may not be in current
  corpus).

### 7.3 Future sources to consider

- Debian Wiki (`wiki.debian.org`) — tier 2, approved
- Gentoo Wiki (`wiki.gentoo.org`) — tier 2, approved
- Ubuntu Wiki (`wiki.ubuntu.com`) — tier 2, approved
- OpenBSD man pages (`man.openbsd.org`) — not yet approved
- NetBSD documentation (`netbsd.org/docs/`) — not yet approved
- Linux Kernel docs (`docs.kernel.org`) — tier 1, approved but not
  scraped
- Ansible docs (`docs.ansible.com`) — tier 1, approved but not scraped
- WireGuard docs (`wireguard.com`) — tier 1, approved but not scraped
- Tailscale docs (`tailscale.com`) — tier 1, approved but not scraped
