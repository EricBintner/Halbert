# Privacy Policy

**Effective date:** 2026-08-25
**Applies to:** Halbert core engine, Halbert Pro, the Tauri dashboard, the
`halbert` CLI, the marketing website at the Halbert domain, and any binary or
source distribution of the Halbert project.

Halbert's defining feature is **local data sovereignty**: your system state,
your conversations, and your memory never leave your machine unless you
explicitly configure a cloud model provider. This document is the formal
statement of that commitment.

---

## 1. The One-Sentence Version

**By default, Halbert collects, transmits, and shares nothing. Every byte of
data Halbert reads stays on the host it was read from.**

---

## 2. Local-First by Default

Halbert runs as a local process on your machine. The default model backend is a
local inference engine (Ollama or MLX on Apple Silicon). In the default
configuration:

- No telemetry is collected.
- No analytics are collected.
- No behavioral tracking occurs.
- No crash reports are sent anywhere.
- No "phone home" calls are made to any Halbert-controlled server.
- No usage statistics are reported.
- No account is required and no account exists.

Halbert does not embed any third-party analytics SDK (no Google Analytics, no
Sentry, no PostHog, no Mixpanel, no Amplitude, no Segment, no Hotjar). The
marketing website likewise runs no analytics scripts.

---

## 3. What Halbert Reads

To do its job, Halbert reads the following from your local system:

| Data | Source | Stored where |
| :--- | :--- | :--- |
| System profile | `uname`, `/proc`, `sysctl`, `system_profiler` | In-memory; cached summary in `~/.local/share/halbert/` |
| Service state | `systemctl`, `launchctl`, `service` | In-memory |
| Disk & filesystem state | `df`, `diskutil`, `mount` | In-memory |
| Network state | `ifconfig`, `ss`, `netstat` | In-memory |
| Package inventory | `dpkg`, `brew list`, `pacman -Q` | In-memory |
| Configuration files | `/etc/**`, `~/.config/**`, `/Library/LaunchDaemons/**` | Read into context; copies staged into `~/.local/share/halbert/sourceprep/host/` for indexing |
| Logs | `journalctl`, `log show` | Read into context; not persisted by Halbert |
| Your chat messages | The dashboard / CLI input | Persisted in `~/.local/share/halbert/memory/` |
| Halbert's own responses | Generated locally | Persisted in `~/.local/share/halbert/memory/` |
| RAG corpus | `data/**` (shipped in the repo) | Indexed in `~/.local/share/halbert/sourceprep/` |

All of the above stays on your machine. None of it is transmitted anywhere by
Halbert in the default configuration.

---

## 4. Where Halbert Stores Data

Halbert uses XDG Base Directory conventions. On a typical Linux install:

| Path | Contents |
| :--- | :--- |
| `~/.local/share/halbert/` | Memory, vector index, staged host config, SourcePrep project |
| `~/.config/halbert/` | User configuration (`config.yml`, `policy.yml`) |
| `~/.cache/halbert/` | Embedding model cache, transient scratch |

On macOS the equivalent paths live under `~/Library/Application Support/halbert/`,
`~/Library/Preferences/halbert/`, and `~/Library/Caches/halbert/` per Apple
conventions.

You can inspect, export, or delete any of this data at any time. Halbert ships
no obfuscation and no DRM. To wipe Halbert's local state:

```bash
rm -rf ~/.local/share/halbert ~/.config/halbert ~/.cache/halbert
```

---

## 5. Cloud API Mode (Optional, Off by Default)

Halbert supports optional configuration of cloud model providers — OpenAI,
Anthropic, Google, and other OpenAI-compatible endpoints — for users who want
higher-quality reasoning than a local model can provide.

**When you enable a cloud provider, the privacy posture changes.** This is the
only path by which your data leaves your machine.

### 5.1 What is sent

When a cloud model is selected for a given turn, Halbert sends to the provider:

- Your chat message for that turn.
- The assembled context for that turn — which may include excerpts of your
  system profile, configuration files, service state, log snippets, and
  retrieved RAG chunks.
- The system prompt and any persona instructions in effect.

### 5.2 What is not sent

- Your full filesystem.
- Your full memory history (only the context window for the current turn).
- Your credentials, API keys, or secrets (these are filtered out of context by
  the safety adapters before transmission).
- Anything from turns that use a local model.

### 5.3 Provider terms

Each cloud provider processes your data under that provider's own terms of
service and privacy policy. Halbert's maintainers are not a party to that
relationship and have no visibility into, or control over, what the provider
does with your data — including whether the provider retains it, logs it, or
uses it for model training. **Review the provider's policy before enabling
cloud mode on systems that process sensitive, regulated, or restricted data.**

| Provider | Privacy policy |
| :--- | :--- |
| OpenAI | https://openai.com/policies/privacy-policy |
| Anthropic | https://www.anthropic.com/legal/privacy |
| Google | https://policies.google.com/privacy |

### 5.4 Consent gate

The dashboard surfaces a confirmation dialog the first time a cloud provider is
enabled, stating that enabling cloud models sends system logs and prompts to
the named provider and should not be enabled on systems processing sensitive or
restricted data. See `LEG-MOD-02` in the action plan.

---

## 6. The Marketing Website

The Halbert marketing website (`index.html` and the Vite app under
`marketing/web/`) is a static site. It:

- Loads no analytics scripts.
- Loads no tracking pixels.
- Sets no tracking cookies. The only client-side state is the theme picker
  preference, stored in `localStorage` on the visitor's browser and never
  transmitted.
- Makes no API calls to any Halbert-controlled backend.
- The subscription input on the footer is a front-end form; submission is
  handled by the hosting provider (Netlify form handling) and is governed by
  Netlify's privacy policy, not Halbert's.

---

## 7. The RAG Corpus

The RAG corpus shipped in `data/` is a static dataset committed to git. It
contains no personal data. It contains publicly available technical
documentation under the licenses enumerated in
[`THIRD-PARTY-LICENSES.md`](./THIRD-PARTY-LICENSES.md). When Halbert retrieves
from the corpus, retrieval is local — no query is sent to any upstream source.

The corpus is also published to HuggingFace as versioned datasets
(`halbert-rag-linux`, `halbert-rag-macos`, `halbert-rag-eval`). Those datasets
contain only the same public technical documentation, with per-source license
metadata preserved in each record. See `LEG-MAJ-03`.

---

## 8. SourcePrep Daemon

Halbert optionally integrates with a local SourcePrep daemon (port 8400) for
code-awareness retrieval. The daemon is a local process. It reads files from
your local filesystem and your staged host config tree. It does not transmit
data off-host. If you have configured SourcePrep's optional cloud catalogue
feature (an LLM-based enrichment stage), that stage's data flow is governed by
SourcePrep's own privacy documentation, not this policy.

---

## 9. Children's Privacy

Halbert is not directed at children under 16 and is not intended for use by
children. Halbert does not knowingly collect any personal information from
anyone, of any age.

---

## 10. Your Rights

Because Halbert collects no personal data, the standard GDPR / CCPA data
subject rights (access, rectification, erasure, portability, objection) are
trivially satisfied: there is no personal data about you in Halbert's
possession to access, rectify, erase, port, or object to. The data on your
machine is yours; you can inspect and delete it as described in §4.

For the marketing website's Netlify-hosted subscription form, contact the
maintainer at the address in §12 to exercise any rights over the email address
you submitted.

---

## 11. Changes to This Policy

Material changes to this policy will be reflected by updating this document and
bumping the "Effective date" above. The git history of this file is the
authoritative changelog. Halbert's first-run onboarding will re-prompt for
acknowledgment if a material change is detected.

---

## 12. Contact

For privacy questions or requests, open an issue on the Halbert GitHub
repository or contact the maintainer directly via the channels listed on the
repository's `README.md`. Halbert does not operate a dedicated privacy email
address because there is no data to request.

---

## 13. Cross-References

- [`THIRD-PARTY-LICENSES.md`](./THIRD-PARTY-LICENSES.md) — Per-source license attribution
- [`DISCLAIMER.md`](./DISCLAIMER.md) — Autonomous action liability waiver
- [`TRADEMARKS.md`](./TRADEMARKS.md) — Third-party trademark notices
- [`SECURITY.md`](./SECURITY.md) — Security model and trust boundaries
- [`LEGAL-AND-LICENSING-TODO.md`](./LEGAL-AND-LICENSING-TODO.md) — Compliance action plan
