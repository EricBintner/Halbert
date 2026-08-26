# Third-Party Licenses & Attribution Notices

**Effective date:** 2026-08-25
**Scope:** All third-party content and software bundled with, retrieved by, or
depended on by Halbert.

This document satisfies the attribution requirements of the permissive and
share-alike licenses under which Halbert's third-party content is distributed.
It is the canonical reference cited by `data/manifest.json` and rendered in the
dashboard "About / Legal Notices" panel.

---

## 1. Halbert Itself

| Field | Value |
| :--- | :--- |
| Project | Halbert |
| License | GNU General Public License v3.0 ([GPL-3.0](https://www.gnu.org/licenses/gpl-3.0.en.html)) |
| Copyright | (C) 2024-2026 Eric Bintner and Halbert Contributors |
| Source | https://github.com/EricBintner/Halbert |

See [`LICENSE.md`](./LICENSE.md) for the project license summary and rationale.

---

## 2. RAG Knowledge Corpus — Data Sources

The Halbert RAG corpus contains 28,869 documents drawn from 13 upstream
sources. Each source carries its own license, summarized below. Full license
texts are linked. **Attribution is required** for all sources marked as such.

### 2.1 Arch Linux Wiki

| Field | Value |
| :--- | :--- |
| Source | Arch Linux Wiki (hannah-eee dataset + curated extensions) |
| Bucket | `data/linux/` |
| Documents | 2,397 |
| License | **GNU Free Documentation License 1.3** |
| License URL | https://www.gnu.org/licenses/fdl-1.3.html |
| Upstream | https://wiki.archlinux.org/ |
| `mac_build` | `false` (copyleft — excluded from macOS commercial bundles) |
| Attribution | Required. "Arch Wiki content licensed under GNU FDL 1.3, © Arch Linux contributors." |

### 2.2 Linux Man Pages

| Field | Value |
| :--- | :--- |
| Source | Linux man-pages project |
| Bucket | `data/linux/man-pages/` |
| Documents | 4,368 (after fragment merge & dedup) |
| License | **Various permissive** — GPL, BSD-2-Clause, BSD-3-Clause, MIT, per-page |
| License URL | https://www.kernel.org/doc/man-pages/licenses.html |
| Upstream | https://www.kernel.org/doc/man-pages/ |
| `mac_build` | `true` |
| Attribution | Per-page; see the `LICENSE` section at the bottom of each man page. |

### 2.3 TLDR Pages

| Field | Value |
| :--- | :--- |
| Source | TLDR pages (Common, Linux, macOS, BSD) |
| Bucket | `data/common/tldr/`, `data/linux/tldr/`, `data/macos/tldr/`, `data/bsd/tldr/` |
| Documents | 7,049 |
| License | **Creative Commons Attribution 4.0 International (CC BY 4.0)** |
| License URL | https://creativecommons.org/licenses/by/4.0/legalcode |
| Upstream | https://tldr.sh/ , https://github.com/tldr-pages/tldr |
| `mac_build` | `true` |
| Attribution | Required. "TLDR pages content licensed under CC BY 4.0, © TLDR contributors." |

### 2.4 Common Tools Documentation

| Field | Value |
| :--- | :--- |
| Source | Cross-platform core tools (git, devtools, shell, python, docker, containers, aws-cli) |
| Bucket | `data/common/` |
| Documents | 68 |
| License | **Various permissive** — GPL, Apache 2.0, MIT, BSD, CC BY 4.0 (per-project) |
| `mac_build` | `true` |
| Attribution | Per upstream project. Git docs: GPL-2.0; Docker docs: Apache 2.0; AWS CLI docs: Apache 2.0. |

### 2.5 Linux System Documentation

| Field | Value |
| :--- | :--- |
| Source | Linux system guides (systemd, networking, security, storage, backup, monitoring, kernel, etc.) |
| Bucket | `data/linux/` (multiple subdirectories) |
| Documents | 243 |
| License | **Various permissive** — GPL, CC BY-SA 4.0, Apache 2.0, MIT (per-source) |
| `mac_build` | `true` |
| Attribution | Per upstream project. systemd docs: LGPL-2.1+; kernel docs: GPL-2.0. |

### 2.6 Vendor & Distro Documentation

| Field | Value |
| :--- | :--- |
| Source | Docker, Kubernetes, Helm, NVIDIA, ROCm, Ubuntu |
| Bucket | `data/linux/vendor-docs/`, `data/linux/kubernetes-docs/`, `data/linux/ubuntu-docs/`, etc. |
| Documents | 82 |
| License | **Various permissive** — Apache 2.0 (Docker, K8s, Helm), CC BY-SA 3.0 (Ubuntu) |
| `mac_build` | `true` |
| Attribution | Per upstream project. |

### 2.7 Homebrew

| Field | Value |
| :--- | :--- |
| Source | Homebrew package manager documentation, formulas, and casks |
| Bucket | `data/macos/homebrew/` |
| Documents | 8,777 |
| License | **BSD-2-Clause** |
| License URL | https://opensource.org/licenses/BSD-2-Clause |
| Upstream | https://docs.brew.sh/ , https://github.com/Homebrew/brew |
| `mac_build` | `true` |
| `linux_build` | `false` |
| Attribution | Required. "Homebrew content © Homebrew contributors, licensed under BSD-2-Clause." |

### 2.8 macOS Man Pages

| Field | Value |
| :--- | :--- |
| Source | macOS man pages (extracted from local system) |
| Bucket | `data/macos/man-pages/` |
| Documents | 5,280 (deduped, cleaned) |
| License | **Mixed** — BSD pages: BSD-2-Clause/BSD-3-Clause; Apple-authored pages: Apple Public Source License 2.0 (APSL 2.0) |
| License URLs | https://opensource.org/licenses/BSD-3-Clause , https://opensource.org/licenses/APSL-2.0.php |
| Upstream | macOS system `/usr/share/man/` |
| `mac_build` | `true` |
| `linux_build` | `false` |
| Attribution | Required. BSD pages: "© The Regents of the University of California." Apple pages: "© Apple Inc., under APSL 2.0." |

### 2.9 macOS Support (SS64 + Synthetic)

| Field | Value |
| :--- | :--- |
| Source | SS64 macOS command reference + Halbert-authored synthetic guides |
| Bucket | `data/macos/support/` |
| Documents | 104 |
| License | **Mixed** — SS64: CC BY-NC 4.0 (Non-Commercial); Synthetic guides: Halbert / GPL-3.0 |
| License URL | https://creativecommons.org/licenses/by-nc/4.0/legalcode |
| Upstream | https://ss64.com/mac/ |
| `mac_build` | `true` (synthetic only — **SS64 must be excluded from paid/commercial bundles**) |
| `linux_build` | `false` |
| Attribution | Required. "SS64 content © Simon Sheppard, licensed under CC BY-NC 4.0 (non-commercial)." |
| **Quarantine** | SS64 content is non-commercial. See `LEG-CRIT-01` in the action plan. |

### 2.10 Ask Different (Stack Exchange)

| Field | Value |
| :--- | :--- |
| Source | Ask Different (apple.stackexchange.com) high-voted Q&A |
| Bucket | `data/macos/ask-different/` |
| Documents | 269 |
| License | **Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)** |
| License URL | https://creativecommons.org/licenses/by-sa/4.0/legalcode |
| Upstream | https://apple.stackexchange.com/ |
| `mac_build` | `true` |
| `linux_build` | `false` |
| Attribution | **Required.** Per Stack Exchange CC BY-SA 4.0 policy: link to the original question, link to author profile, list author display name. Each JSONL record preserves `url` and `metadata.author`. |

### 2.11 MacPorts Guide

| Field | Value |
| :--- | :--- |
| Source | MacPorts Guide |
| Bucket | `data/macos/macports-guide/` |
| Documents | 10 |
| License | **BSD-like (MacPorts Project)** |
| Upstream | https://guide.macports.org/ , https://github.com/macports/macports-guide |
| `mac_build` | `true` |
| `linux_build` | `false` |
| Attribution | Required. "MacPorts Guide © The MacPorts Project." |

### 2.12 FreeBSD Handbook

| Field | Value |
| :--- | :--- |
| Source | FreeBSD Handbook |
| Bucket | `data/bsd/freebsd-handbook/` |
| Documents | 41 |
| License | **FreeBSD Documentation License** |
| License URL | https://www.freebsd.org/copyright/freebsd-doc-license/ |
| Upstream | https://docs.freebsd.org/en/books/handbook/ |
| `mac_build` | `true` |
| `linux_build` | `true` |
| Attribution | Required. "FreeBSD Handbook © The FreeBSD Documentation Project." |

### 2.13 FreeBSD Man Pages

| Field | Value |
| :--- | :--- |
| Source | FreeBSD man pages (BSD commands shared with macOS) |
| Bucket | `data/bsd/freebsd-man-pages/` |
| Documents | 181 |
| License | **FreeBSD Documentation License** (page text) + **BSD-2-Clause** (underlying code) |
| License URL | https://www.freebsd.org/copyright/freebsd-doc-license/ |
| Upstream | https://www.freebsd.org/cgi/man.cgi |
| `mac_build` | `true` |
| `linux_build` | `true` |
| Attribution | Required. "FreeBSD man pages © The FreeBSD Documentation Project." |

### 2.14 Corpus Totals

| Bucket | Documents | macOS build | Linux build |
| :--- | ---: | :---: | :---: |
| `data/linux/` | 7,090 | No (copyleft + platform) | Yes |
| `data/macos/` | 14,441 | Yes (SS64 excluded from paid) | No |
| `data/bsd/` | 222 | Yes | Yes |
| `data/common/` | 7,117 | Yes | Yes |
| **Total** | **28,869** | | |

See `data/manifest.json` for the authoritative per-source manifest with
`mac_build` / `linux_build` flags and per-source paths.

---

## 3. Software Dependencies

Halbert depends on the following third-party software libraries. Each is
distributed under its own license; this section reproduces the required
attribution and license references.

### 3.1 Python (Backend)

| Package | License | Purpose |
| :--- | :--- | :--- |
| `fastapi` | MIT | HTTP API framework |
| `uvicorn` | BSD-3-Clause | ASGI server |
| `pydantic` | MIT | Data validation |
| `chromadb` | Apache 2.0 | Vector database (legacy RAG path, being retired) |
| `sentence-transformers` | Apache 2.0 | Embedding models (legacy RAG path) |
| `apscheduler` | MIT | Background job scheduling |
| `requests` | Apache 2.0 | HTTP client |
| `httpx` | BSD-3-Clause | Async HTTP client |
| `pyyaml` | MIT | YAML parsing |
| `rich` | MIT | Terminal formatting |
| `haloysius` | GPL-3.0 | Cognitive core (project-internal) |
| `nomic-embed-text-v1.5` (model) | Apache 2.0 | Embedding model (SourcePrep CodeIndex) |

### 3.2 Rust (Tauri Desktop Shell)

| Crate | License | Purpose |
| :--- | :--- | :--- |
| `tauri` | Apache 2.0 / MIT | Desktop application shell |
| `sysinfo` | MIT | System information collection |
| `serde` | MIT / Apache 2.0 | Serialization |
| `tokio` | MIT | Async runtime |

### 3.3 Node / TypeScript (Frontend)

| Package | License | Purpose |
| :--- | :--- | :--- |
| `react` | MIT | UI framework |
| `vite` | MIT | Build tooling |
| `tailwindcss` | MIT | Utility CSS |
| `radix-ui` | MIT | Headless UI primitives |
| `monaco-editor` | MIT | Code editor |
| `xterm` | MIT | Terminal emulator |
| `lucide-react` | ISC | Icon set |

### 3.4 Bundled Binaries

| Binary | License | Purpose |
| :--- | :--- | :--- |
| `halbert-api-{arch}` | GPL-3.0 | Pre-built FastAPI server shipped in the Tauri bundle |
| `sourceprep` (optional) | GPL-3.0 | Code-awareness daemon (user-installed) |

### 3.5 Source Files Derived from Third-Party Code

Most of the repository is first-party and tagged `SPDX-License-Identifier:
GPL-3.0-or-later`. The files below were copied from, or closely derived from,
third-party code and keep the upstream license identifier in their header so
that the upstream copyright and permission notice is retained.

| Files | Upstream | License |
| :--- | :--- | :--- |
| `halbert_core/halbert_core/dashboard/frontend/src/components/ui/` — `badge.tsx`, `button.tsx`, `card.tsx`, `dropdown-menu.tsx`, `input.tsx`, `label.tsx`, `progress.tsx`, `sheet.tsx`, `tabs.tsx`; `src/lib/utils.ts` | [shadcn/ui](https://ui.shadcn.com) — Copyright (c) 2023 shadcn | MIT |
| `dashboard/routes/llm.py` (Ollama Cloud candidate list), `frontend/src/types/llm.ts`, `frontend/src/components/llm/*` (unified model picker) | SourcePrep `@prep/ui` (same author) | GPL-3.0 |

MIT License text retained for the shadcn/ui-derived files:

> Copyright (c) 2023 shadcn
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all
> copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.

Supporting libraries used by those files: `class-variance-authority`
(Apache-2.0), `clsx` (MIT), `tailwind-merge` (MIT), `@radix-ui/*` (MIT).

---

## 4. Attribution Notice for Redistributions

When redistributing Halbert — in source or binary form, including via the Mac
App Store or LemonSqueezy — you must include:

1. This `THIRD-PARTY-LICENSES.md` file.
2. The `LICENSE.md` summary and a pointer to the full GPL-3.0 text.
3. The `PRIVACY.md` and `DISCLAIMER.md` notices.
4. For any corpus subset included in the binary: the per-source attribution
   lines from §2 above, with the upstream URL preserved in the JSONL `url`
   field of each record.
5. For any model weights bundled with the binary: the licence text, the
   NOTICE sentence and the display notice that model's licence prescribes
   (§5 below).

---

## 5. Model Licences and Attribution

Halbert does not bundle, recommend, or list AI models. You choose a model from
whatever your runtime (Ollama, MLX, LM Studio, or a cloud API) already serves,
and the licence for that model is between you and its publisher. Halbert's
part is to make the licence visible:

- **Where the licence comes from.** Ollama attaches each model's licence text
  to the model itself (`ollama show <model> --license`; `POST /api/show` →
  `license`). `halbert_core/halbert_core/model/attribution.py` reads that text
  and extracts the licence name, any user-facing display notice the licence
  requires (some publisher "community" licences require a fixed phrase on a
  related website, UI, or documentation page), the sentence a NOTICE file must
  carry if the weights are redistributed, and whether the licence is
  non-commercial. Detection is by licence wording, not by model name, so no
  list of models is kept anywhere in the code.
- **Where it is shown.** The model picker (Settings → AI Models) shows the
  licence and the required notice next to the selected model;
  `halbert model-list-all` and `halbert model-router-status` print them; the
  About / Legal Notices panel lists the licences of the models in use.
- **Hosted providers.** For cloud endpoints Halbert shows the provider's terms
  of service instead; prompts and context leave the machine — see
  [`PRIVACY.md`](./PRIVACY.md).

Because Halbert ships no weights, redistribution obligations (copies of the
licence, NOTICE files, acceptable-use pass-through) do not attach to the
Halbert release. A future build that bundles weights must include, for each
bundled model, the licence text, the NOTICE sentence the licence prescribes,
and the display notice — all of which `attribution.py` reports for that model.

---

## 6. Cross-References

- [`LICENSE.md`](./LICENSE.md) — Halbert's own GPL-3.0 license summary
- [`PRIVACY.md`](./PRIVACY.md) — Zero-telemetry privacy policy
- [`DISCLAIMER.md`](./DISCLAIMER.md) — Autonomous action liability waiver
- [`TRADEMARKS.md`](./TRADEMARKS.md) — Third-party trademark notices
- [`LEGAL-AND-LICENSING-TODO.md`](./LEGAL-AND-LICENSING-TODO.md) — Compliance action plan
- [`../RAG-DATA-SOURCES-2026-08-24.md`](../RAG-DATA-SOURCES-2026-08-24.md) — Per-source scraping reference
- `data/manifest.json` — Authoritative corpus manifest with per-source license tags
