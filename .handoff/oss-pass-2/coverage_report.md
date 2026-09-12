# OSS pass 2 — coverage report

What the 2026-09-09 pass actually read, what it did not, and what to read next.

Sources: `merged_discoveries.json` (46 discovery units), the two 2026-09-07 syntheses
(`OSS-REVIEW-OPENCLAW-2026-09-07.md`, `OSS-REVIEW-HERMES-2026-09-07.md`), and a direct
measurement of the three origin repos taken today.

## 0. Method, and what the percentages mean

**Files in scope** = non-test source files under the directories a unit was assigned.
Excluded everywhere: `*.test.ts` / `*.test.tsx` / `*.test-support.ts` / `*.spec.*`,
`test_*.py` / `*_test.py`, anything under `tests/`, `__tests__/`, `test/`, `node_modules/`,
`dist/`, and openclaw's `src/test-fixtures|test-helpers|test-utils`. Extensions counted:
`.ts/.tsx` for openclaw; `.py` for the hermes Python trees, `.ts/.tsx` for its JS trees,
`.md` for the skill libraries; `.mjs/.ts/.js` for open-claude-code.

**Files read** = the unit's own `key_files_read` entries that resolve to a real path inside
its scope, matched exactly (no basename matching — basename matching inflated openclaw's
`extensions/` numbers roughly threefold, since a hundred extensions each own an `index.ts`).
Where this number differs from the reader's self-reported `files_read_count`, both are shown;
the gap is grep-only or partially-read files the reader counted but did not cite, and
sometimes Halbert-side files counted in the same total.

**Two caveats that matter for reading the table.**

1. *Whole-dir vs family-subset scope.* Some units owned a whole directory
   (`OC03 = src/auto-reply`, `OC23 = ui/src`); for those, read % is a true coverage number.
   Others were one family inside a directory shared with sibling units (`HM01–HM04` split
   hermes `agent/`; `OC14/OC15` split `src/agents`; `OC16/OC17` split `src/gateway`). Their
   FOCUS lists are not recoverable from the artifacts, so their read % is measured against the
   whole shared directory and is therefore a **lower bound on coverage of their own focus list,
   and an exact measure of how much of the shared directory they touched**. The basis column
   says which.
2. *The prior reviews cite far less than they read.* The two 2026-09-07 syntheses are 198 and
   134 lines and cite only 21 and 3 concrete paths between them. Those paths are counted as
   read. Everything else those reviews absorbed is invisible to this measurement, so coverage
   of the core subsystems they covered (memory promotion, policy lattice, scheduler durability,
   voice ingress, redaction, execute_code, interrupt algebra, store hardening, channels,
   session tree, permission modules, skills) is understated by an unknown amount. Treat their
   subject areas as better covered than the numbers here suggest; treat everything else as
   measured.

**Headline.** The three origin repos hold **23,959 non-test source files** in the trees this
pass was pointed at: openclaw 18,428 (`src` 9,322 · `extensions` 5,433 · `ui/src` 1,520 ·
`apps` 1,498 · `packages` 655), hermes-agent 5,235 outside `tests/`, open-claude-code 296.
The 46 units cite **1,565 distinct origin files that exist on disk** — **6.5% of the corpus**
(openclaw 4.9%, hermes 11.6%, open-claude-code 19.3%).

This was a **broad, shallow sampling pass, not a survey**. It still produced 789 candidates
(589 kept, 182 dropped, 18 unverified) plus 274 verifier-added mechanisms. Density, not
coverage, is what carried it — which is the argument for another pass rather than against one.


## 1. Coverage per unit

| unit | scope (non-test source files under its dirs) | in scope | cited read | self-reported | read % of scope | verifier-missed | basis |
|---|---|---:|---:|---:|---:|---:|---|
| `HM01-agent-turn-family` | agent/ turn+tool+error family (shared agent/ with HM02-HM04) | 267 | 45 | 45 | 16.9% | 6 | family-subset of a shared dir |
| `HM02-agent-context-prompt-family` | agent/ context+prompt family (shared) | 267 | 28 | 27 | 10.5% | 6 | family-subset of a shared dir |
| `HM03-agent-providers-credentials-usage` | agent/ provider+credential+usage family (shared) | 267 | 37 | 37 | 13.9% | 6 | family-subset of a shared dir |
| `HM04-agent-learning-verification-review` | agent/ learning+verify+curator family (shared) | 267 | 25 | 26 | 9.4% | 7 | family-subset of a shared dir |
| `HM05-delegation-subagents-kanban` | agent/ + tools/ delegation & kanban family (shared) | 1008 | 23 | 27 | 2.3% | 7 | family-subset of a shared dir |
| `HM06-tools-approval-guards` | tools/ approval+guard family (shared tools/ with HM07-HM10) | 281 | 29 | 30 | 10.3% | 5 | family-subset of a shared dir |
| `HM07-tools-terminal-files-checkpoints` | tools/ terminal+file+checkpoint family (shared) | 281 | 30 | 33 | 10.7% | 6 | family-subset of a shared dir |
| `HM08-tools-browser-web-media-voice` | tools/ browser+web+media+voice family (shared) | 281 | 20 | 33 | 7.1% | 5 | family-subset of a shared dir |
| `HM09-tools-mcp` | tools/ mcp_* family (shared) | 281 | 17 | 27 | 6.0% | 13 | family-subset of a shared dir |
| `HM10-tools-skills-second-pass` | tools/ skills_* family (shared) | 281 | 28 | 34 | 10.0% | 8 | family-subset of a shared dir |
| `HM11-gateway-core` | gateway/ core (shared with HM12) | 145 | 38 | 39 | 26.2% | 6 | family-subset of a shared dir |
| `HM12-gateway-rooms-platforms-hooks` | gateway/ rooms+platforms+hooks (shared with HM11) | 145 | 23 | 27 | 15.9% | 4 | family-subset of a shared dir |
| `HM13-state-root-files` | repo-root *.py (hermes_state*, bootstrap, watchdog...) | 39 | 20 | 20 | 51.3% | 7 | whole-dir |
| `HM14-cli-ops-lifecycle` | hermes_cli/ ops+lifecycle (shared with HM15) | 460 | 33 | 33 | 7.2% | 5 | family-subset of a shared dir |
| `HM15-cli-model-config-ux` | hermes_cli/ model+config UX (shared with HM14) | 460 | 38 | 34 | 8.3% | 8 | family-subset of a shared dir |
| `HM16-cron-second-pass` | cron/ | 22 | 17 | 35 | 77.3% | 9 | whole-dir |
| `HM17-plugins-acp-providers` | plugins/ + acp_adapter/ | 253 | 23 | 29 | 9.1% | 3 | whole-dir |
| `HM18-tui-gateway-ui-desktop-docs` | tui_gateway/ + web/src + ui-tui/src + apps/ | 1672 | 23 | 33 | 1.4% | 8 | whole-dir |
| `HM19-evals-tests-meta` | evals/ + repo-root meta docs | 118 | 32 | 34 | 27.1% | 7 | whole-dir |
| `HM20-skill-library` | skills/ + optional-skills/ | 770 | 22 | 27 | 2.9% | 6 | whole-dir |
| `OC01-infra-approvals-devices-backup` | src/infra (shared with OC02) | 810 | 38 | 34 | 4.7% | 7 | family-subset of a shared dir |
| `OC02-infra-rest` | src/infra (shared with OC01) | 810 | 28 | 29 | 3.5% | 4 | family-subset of a shared dir |
| `OC03-auto-reply` | src/auto-reply | 477 | 37 | 33 | 7.8% | 5 | whole-dir |
| `OC04-commands` | src/commands | 556 | 30 | 30 | 5.4% | 7 | whole-dir |
| `OC05-config` | src/config | 500 | 24 | 25 | 4.8% | 6 | whole-dir |
| `OC06-plugins-sdk` | src/plugins + plugin-sdk + plugin-state | 1133 | 34 | 34 | 3.0% | 6 | whole-dir |
| `OC07-cli-wizard-tui-entry` | src/cli + wizard + tui + bootstrap + interactive + entry*.ts | 542 | 20 | 27 | 3.7% | 4 | whole-dir |
| `OC08-daemon-process-worker-hooks-audit` | src/daemon+process+worker+hooks+audit+logging+node-host+status | 389 | 38 | 38 | 9.8% | 4 | whole-dir |
| `OC09-tasks-system-agent-flows-boards-claws` | src/tasks+system-agent+flows+boards+claws+trajectory+snapshot+fleet+session-cards+projects | 271 | 39 | 38 | 14.4% | 6 | whole-dir |
| `OC10-media-pipelines` | src/media* + canvas + link-understanding + transcripts + realtime-transcription | 160 | 41 | 43 | 25.6% | 8 | whole-dir |
| `OC11-talk-tts-acp-web-routing-context` | src/talk+tts+acp+context-engine+meeting-bot+routing+proxy-capture+web*+chat+memory* | 250 | 48 | 33 | 19.2% | 6 | whole-dir |
| `OC12-state-sessions-secrets-security-shared` | src/state+sessions+secrets+security+shared+model-catalog+model-picker+llm+pairing+compat+utils+types | 496 | 43 | 34 | 8.7% | 4 | whole-dir |
| `OC13-packages` | packages/* | 655 | 47 | 47 | 7.2% | 5 | whole-dir |
| `OC14-agents-second-pass-A` | src/agents (shared with OC15) | 1750 | 29 | 29 | 1.7% | 6 | family-subset of a shared dir |
| `OC15-agents-second-pass-B` | src/agents (shared with OC14) | 1750 | 23 | 27 | 1.3% | 5 | family-subset of a shared dir |
| `OC16-gateway-second-pass-A` | src/gateway (shared with OC17) | 1311 | 47 | 42 | 3.6% | 5 | family-subset of a shared dir |
| `OC17-gateway-second-pass-B` | src/gateway (shared with OC16) | 1311 | 29 | 27 | 2.2% | 5 | family-subset of a shared dir |
| `OC18-channels-cron-second-pass` | src/channels + src/cron | 463 | 56 | 55 | 12.1% | 7 | whole-dir |
| `OC19-extensions-identity-security-ops` | extensions/{a2a,acpx,admin-http-rpc,bonjour,clawrouter,device-pair,diagnostics-*,file-transfer,oc-path,onepassword,openshell,policy,raft,reef,tokenjuice,vault,visitor-access,webhooks} | 336 | 30 | 34 | 8.9% | 6 | whole-dir |
| `OC20-extensions-memory-knowledge-automation` | extensions/{memory-*,active-memory,logbook,team-reports,workboard,migrate-*,llm-task,lobster,qa-*} | 786 | 32 | 44 | 4.1% | 4 | whole-dir |
| `OC21-extensions-device-media-desktop` | extensions/{cua-computer,imessage,browser,geolocation,document-extract,diffs*,tts-local-cli,linux-node,talk-voice,voice-call,web-readability,image-generation-core,canvas,speech/tts vendors} | 631 | 32 | 34 | 5.1% | 6 | whole-dir |
| `OC22-extensions-local-providers-apps` | extensions/{ollama,llama-cpp,vllm,sglang,lmstudio,litellm,copilot-proxy} + apps/{macos,linux,swabble} | 699 | 23 | 34 | 3.3% | 6 | whole-dir |
| `OC23-control-ui` | ui/src | 1445 | 30 | 30 | 2.1% | 7 | whole-dir |
| `OC24-docs-qa-security-skills` | docs/ + qa/ + security/ + custodian-skills/ | 1436 | 32 | 47 | 2.2% | 5 | whole-dir |
| `OCC01-v2-second-look` | v2/src | 69 | 34 | 33 | 49.3% | 4 | whole-dir |
| `OCC02-archive-bundle-and-tracking-pipeline` | archive/open_claude_code + scripts/ | 210 | 20 | 27 | 9.5% | 4 | whole-dir |


### 1b. Directory-level coverage (all units and both prior reviews combined)

This is the union of every cited file across the 46 units plus the 24 paths cited by the two
2026-09-07 syntheses, measured against every non-test source file in the directory. Openclaw
`extensions/` is folded into §3 to keep this readable.


**oc src**

| dir | non-test source files | read (cited) | % |
|---|---:|---:|---:|
| `src/agents` | 1750 | 55 | 3.1% |
| `src/gateway` | 1311 | 77 | 5.9% |
| `src/infra` | 810 | 68 | 8.4% |
| `src/plugins` | 632 | 29 | 4.6% |
| `src/commands` | 556 | 30 | 5.4% |
| `src/config` | 500 | 24 | 4.8% |
| `src/plugin-sdk` | 492 | 3 | 0.6% |
| `src/auto-reply` | 477 | 37 | 7.8% |
| `src/cli` | 440 | 6 | 1.4% |
| `src/channels` | 275 | 41 | 14.9% |
| `src/cron` | 188 | 19 | 10.1% |
| `src/skills` | 144 | 1 | 0.7% |
| `src/shared` | 123 | 5 | 4.1% |
| `src/state` | 105 | 5 | 4.8% |
| `src/secrets` | 96 | 10 | 10.4% |
| `src/daemon` | 79 | 7 | 8.9% |
| `src/node-host` | 71 | 5 | 7.0% |
| `src/acp` | 67 | 5 | 7.5% |
| `src/system-agent` | 67 | 5 | 7.5% |
| `src/tasks` | 67 | 13 | 19.4% |
| `src/tui` | 66 | 5 | 7.6% |
| `src/claws` | 61 | 4 | 6.6% |
| `src/logging` | 61 | 6 | 9.8% |
| `src/meeting-bot` | 56 | 5 | 8.9% |
| `src/process` | 53 | 10 | 18.9% |
| `src/sessions` | 48 | 5 | 10.4% |
| `src/media` | 45 | 14 | 31.1% |
| `src/media-understanding` | 44 | 8 | 18.2% |
| `src/worker` | 43 | 2 | 4.7% |
| `src/security` | 40 | 3 | 7.5% |
| `src/hooks` | 39 | 4 | 10.3% |
| `src/talk` | 39 | 9 | 23.1% |
| `src/flows` | 37 | 2 | 5.4% |
| `src/wizard` | 33 | 7 | 21.2% |
| `src/tts` | 32 | 7 | 21.9% |
| `src/utils` | 30 | 0 | 0.0% |
| `src/llm` | 27 | 1 | 3.7% |
| `src/audit` | 26 | 3 | 11.5% |
| `src/transcripts` | 25 | 2 | 8.0% |
| `src/status` | 17 | 3 | 17.6% |
| `src/mcp` | 12 | 0 | 0.0% |
| `src/memory-host-sdk` | 12 | 1 | 8.3% |
| `src/context-engine` | 11 | 6 | 54.5% |
| `src/pairing` | 11 | 7 | 63.6% |
| `src/routing` | 11 | 4 | 36.4% |
| `src/proxy-capture` | 10 | 3 | 30.0% |
| `src/boards` | 9 | 3 | 33.3% |
| `src/plugin-state` | 9 | 3 | 33.3% |
| `src/trajectory` | 9 | 4 | 44.4% |
| `src/video-generation` | 9 | 0 | 0.0% |
| `src/fleet` | 8 | 2 | 25.0% |
| `src/image-generation` | 8 | 2 | 25.0% |
| `src/model-catalog` | 8 | 4 | 50.0% |
| `src/media-generation` | 7 | 3 | 42.9% |
| `src/music-generation` | 7 | 0 | 0.0% |
| `src/canvas` | 6 | 6 | 100.0% |
| `src/link-understanding` | 6 | 4 | 66.7% |
| `src/snapshot` | 6 | 3 | 50.0% |
| `src/chat` | 4 | 2 | 50.0% |
| `src/projects` | 4 | 1 | 25.0% |
| `src/types` | 4 | 0 | 0.0% |
| `src/realtime-transcription` | 3 | 2 | 66.7% |
| `src/session-cards` | 3 | 2 | 66.7% |
| `src/web-search` | 3 | 2 | 66.7% |
| `src/bootstrap` | 2 | 1 | 50.0% |
| `src/memory` | 2 | 2 | 100.0% |
| `src/model-picker` | 2 | 2 | 100.0% |
| `src/web-fetch` | 2 | 2 | 100.0% |
| `src/compat` | 1 | 1 | 100.0% |
| `src/interactive` | 1 | 1 | 100.0% |
| `src/provider-runtime` | 1 | 1 | 100.0% |
| `src/web` | 1 | 1 | 100.0% |

**oc packages**

| dir | non-test source files | read (cited) | % |
|---|---:|---:|---:|
| `packages/ai` | 156 | 0 | 0.0% |
| `packages/gateway-protocol` | 149 | 7 | 4.7% |
| `packages/memory-host-sdk` | 77 | 1 | 1.3% |
| `packages/plugin-sdk` | 56 | 0 | 0.0% |
| `packages/gateway-client` | 28 | 1 | 3.6% |
| `packages/normalization-core` | 27 | 3 | 11.1% |
| `packages/agent-core` | 25 | 4 | 16.0% |
| `packages/markdown-core` | 24 | 2 | 8.3% |
| `packages/terminal-core` | 20 | 10 | 50.0% |
| `packages/acp-core` | 13 | 2 | 15.4% |
| `packages/media-core` | 11 | 1 | 9.1% |
| `packages/model-catalog-core` | 11 | 1 | 9.1% |
| `packages/media-understanding-common` | 10 | 1 | 10.0% |
| `packages/llm-core` | 8 | 1 | 12.5% |
| `packages/session-url-contract` | 8 | 3 | 37.5% |
| `packages/net-policy` | 7 | 6 | 85.7% |
| `packages/sdk` | 7 | 0 | 0.0% |
| `packages/tool-call-repair` | 7 | 6 | 85.7% |
| `packages/media-generation-core` | 5 | 0 | 0.0% |
| `packages/mermaid-renderer` | 3 | 1 | 33.3% |
| `packages/plugin-package-contract` | 1 | 1 | 100.0% |
| `packages/retry` | 1 | 1 | 100.0% |
| `packages/workboard-contract` | 1 | 0 | 0.0% |

**oc ui/src**

| dir | non-test source files | read (cited) | % |
|---|---:|---:|---:|
| `ui/src/pages` | 720 | 12 | 1.7% |
| `ui/src/components` | 312 | 4 | 1.3% |
| `ui/src/lib` | 215 | 9 | 4.2% |
| `ui/src/app` | 109 | 2 | 1.8% |
| `ui/src/i18n` | 43 | 1 | 2.3% |
| `ui/src/plugins` | 13 | 0 | 0.0% |
| `ui/src/api` | 7 | 0 | 0.0% |
| `ui/src/lit` | 6 | 1 | 16.7% |
| `ui/src/features` | 5 | 0 | 0.0% |
| `ui/src/types` | 2 | 0 | 0.0% |
| `ui/src/styles` | 1 | 0 | 0.0% |

**oc apps**

| dir | non-test source files | read (cited) | % |
|---|---:|---:|---:|
| `apps/macos` | 569 | 7 | 1.2% |
| `apps/shared` | 350 | 0 | 0.0% |
| `apps/ios` | 281 | 0 | 0.0% |
| `apps/android` | 248 | 0 | 0.0% |
| `apps/swabble` | 27 | 0 | 0.0% |
| `apps/linux` | 19 | 0 | 0.0% |
| `apps/macos-mlx-tts` | 4 | 0 | 0.0% |

**oc extensions**

| dir | non-test source files | read (cited) | % |
|---|---:|---:|---:|
| `extensions/discord` | 430 | 0 | 0.0% |
| `extensions/qa-lab` | 357 | 1 | 0.3% |
| `extensions/codex` | 353 | 0 | 0.0% |
| `extensions/browser` | 317 | 8 | 2.5% |
| `extensions/telegram` | 300 | 0 | 0.0% |
| `extensions/matrix` | 237 | 1 | 0.4% |
| `extensions/slack` | 219 | 0 | 0.0% |
| `extensions/whatsapp` | 179 | 0 | 0.0% |
| `extensions/feishu` | 156 | 0 | 0.0% |
| `extensions/memory-core` | 154 | 10 | 6.5% |
| `extensions/msteams` | 133 | 0 | 0.0% |
| `extensions/imessage` | 112 | 5 | 4.5% |
| `extensions/workboard` | 94 | 2 | 2.1% |
| `extensions/voice-call` | 82 | 1 | 1.2% |
| `extensions/mattermost` | 77 | 0 | 0.0% |
| `extensions/signal` | 76 | 0 | 0.0% |
| `extensions/policy` | 72 | 3 | 4.2% |
| `extensions/line` | 71 | 0 | 0.0% |
| `extensions/openai` | 69 | 0 | 0.0% |
| `extensions/xai` | 63 | 0 | 0.0% |
| `extensions/zalouser` | 56 | 0 | 0.0% |
| `extensions/googlechat` | 55 | 0 | 0.0% |
| `extensions/clickclack` | 52 | 0 | 0.0% |
| `extensions/anthropic` | 50 | 0 | 0.0% |
| `extensions/buzz` | 50 | 0 | 0.0% |
| `extensions/reef` | 50 | 2 | 4.0% |
| `extensions/google-meet` | 47 | 0 | 0.0% |
| `extensions/tlon` | 47 | 0 | 0.0% |
| `extensions/memory-wiki` | 46 | 4 | 8.7% |
| `extensions/google` | 45 | 0 | 0.0% |
| `extensions/nextcloud-talk` | 44 | 0 | 0.0% |
| `extensions/nostr` | 40 | 0 | 0.0% |
| `extensions/ollama` | 40 | 5 | 12.5% |
| `extensions/zalo` | 40 | 0 | 0.0% |
| `extensions/irc` | 36 | 0 | 0.0% |
| `extensions/copilot` | 34 | 0 | 0.0% |
| `extensions/oc-path` | 34 | 1 | 2.9% |
| `extensions/file-transfer` | 32 | 3 | 9.4% |
| `extensions/team-reports` | 31 | 2 | 6.5% |
| `extensions/acpx` | 28 | 2 | 7.1% |
| `extensions/twitch` | 28 | 0 | 0.0% |
| `extensions/synology-chat` | 27 | 0 | 0.0% |
| `extensions/minimax` | 26 | 0 | 0.0% |
| `extensions/crabbox` | 25 | 0 | 0.0% |
| `extensions/diagnostics-otel` | 25 | 1 | 4.0% |
| `extensions/qa-channel` | 24 | 0 | 0.0% |
| `extensions/llama-cpp` | 23 | 2 | 8.7% |
| `extensions/sms` | 23 | 0 | 0.0% |
| `extensions/openrouter` | 22 | 0 | 0.0% |
| `extensions/zoom-meetings` | 22 | 0 | 0.0% |
| `extensions/a2a` | 21 | 1 | 4.8% |
| `extensions/cua-computer` | 21 | 7 | 33.3% |
| `extensions/migrate-hermes` | 21 | 1 | 4.8% |
| `extensions/teams-meetings` | 21 | 0 | 0.0% |
| `extensions/deepinfra` | 19 | 0 | 0.0% |
| `extensions/diffs` | 19 | 2 | 10.5% |
| `extensions/github-copilot` | 19 | 0 | 0.0% |
| `extensions/canvas` | 18 | 0 | 0.0% |
| `extensions/active-memory` | 16 | 3 | 18.8% |
| `extensions/amazon-bedrock` | 16 | 0 | 0.0% |
| `extensions/mxc` | 16 | 0 | 0.0% |
| `extensions/memory-lancedb` | 15 | 6 | 40.0% |
| `extensions/lmstudio` | 14 | 1 | 7.1% |
| `extensions/firecrawl` | 13 | 0 | 0.0% |
| `extensions/moonshot` | 13 | 0 | 0.0% |
| `extensions/elevenlabs` | 12 | 0 | 0.0% |
| `extensions/mistral` | 11 | 0 | 0.0% |
| `extensions/onepassword` | 11 | 2 | 18.2% |
| `extensions/opencode` | 11 | 0 | 0.0% |
| `extensions/parallel` | 11 | 0 | 0.0% |
| `extensions/tavily` | 11 | 0 | 0.0% |
| `extensions/migrate-claude` | 10 | 1 | 10.0% |
| `extensions/raft` | 10 | 1 | 10.0% |
| `extensions/anthropic-vertex` | 9 | 0 | 0.0% |
| `extensions/deepseek` | 9 | 0 | 0.0% |
| `extensions/device-pair` | 9 | 3 | 33.3% |
| `extensions/microsoft-foundry` | 9 | 0 | 0.0% |
| `extensions/opencode-go` | 9 | 0 | 0.0% |
| `extensions/tencent` | 9 | 0 | 0.0% |
| `extensions/vydra` | 9 | 0 | 0.0% |
| `extensions/zai` | 9 | 0 | 0.0% |
| `extensions/fal` | 8 | 0 | 0.0% |
| `extensions/logbook` | 8 | 3 | 37.5% |
| `extensions/openshell` | 8 | 1 | 12.5% |
| `extensions/qwen` | 8 | 0 | 0.0% |
| `extensions/venice` | 8 | 0 | 0.0% |
| `extensions/visitor-access` | 8 | 1 | 12.5% |
| `extensions/xiaomi` | 8 | 0 | 0.0% |
| `extensions/baseten` | 7 | 0 | 0.0% |
| `extensions/brave` | 7 | 0 | 0.0% |
| `extensions/chutes` | 7 | 0 | 0.0% |
| `extensions/duckduckgo` | 7 | 0 | 0.0% |
| `extensions/fireworks` | 7 | 0 | 0.0% |
| `extensions/imap` | 7 | 0 | 0.0% |
| `extensions/kimi-coding` | 7 | 0 | 0.0% |
| `extensions/longcat` | 7 | 0 | 0.0% |
| `extensions/meta` | 7 | 0 | 0.0% |
| `extensions/volcengine` | 7 | 0 | 0.0% |
| `extensions/beam` | 6 | 0 | 0.0% |
| `extensions/cerebras` | 6 | 0 | 0.0% |
| `extensions/cloudflare-ai-gateway` | 6 | 0 | 0.0% |
| `extensions/comfy` | 6 | 0 | 0.0% |
| `extensions/exa` | 6 | 0 | 0.0% |
| `extensions/kilocode` | 6 | 0 | 0.0% |
| `extensions/linux-node` | 6 | 2 | 33.3% |
| `extensions/lobster` | 6 | 0 | 0.0% |
| `extensions/perplexity` | 6 | 0 | 0.0% |
| `extensions/together` | 6 | 0 | 0.0% |
| `extensions/vercel-ai-gateway` | 6 | 0 | 0.0% |
| `extensions/vllm` | 6 | 2 | 33.3% |
| `extensions/webhooks` | 6 | 1 | 16.7% |
| `extensions/amazon-bedrock-mantle` | 5 | 0 | 0.0% |
| `extensions/arcee` | 5 | 0 | 0.0% |
| `extensions/byteplus` | 5 | 0 | 0.0% |
| `extensions/clawrouter` | 5 | 1 | 20.0% |
| `extensions/cohere` | 5 | 0 | 0.0% |
| `extensions/deepgram` | 5 | 0 | 0.0% |
| `extensions/featherless` | 5 | 0 | 0.0% |
| `extensions/geolocation` | 5 | 3 | 60.0% |
| `extensions/gradium` | 5 | 0 | 0.0% |
| `extensions/huggingface` | 5 | 0 | 0.0% |
| `extensions/litellm` | 5 | 1 | 20.0% |
| `extensions/searxng` | 5 | 0 | 0.0% |
| `extensions/synthetic` | 5 | 0 | 0.0% |
| `extensions/azure-speech` | 4 | 0 | 0.0% |
| `extensions/bonjour` | 4 | 3 | 75.0% |
| `extensions/diagnostics-prometheus` | 4 | 1 | 25.0% |
| `extensions/diffs-language-pack` | 4 | 0 | 0.0% |
| `extensions/fish-audio-speech` | 4 | 0 | 0.0% |
| `extensions/inworld` | 4 | 0 | 0.0% |
| `extensions/llm-task` | 4 | 0 | 0.0% |
| `extensions/microsoft` | 4 | 0 | 0.0% |
| `extensions/nvidia` | 4 | 0 | 0.0% |
| `extensions/pixverse` | 4 | 0 | 0.0% |
| `extensions/qianfan` | 4 | 0 | 0.0% |
| `extensions/test-support` | 4 | 0 | 0.0% |
| `extensions/voyage` | 4 | 0 | 0.0% |
| `extensions/admin-http-rpc` | 3 | 2 | 66.7% |
| `extensions/groq` | 3 | 0 | 0.0% |
| `extensions/sglang` | 3 | 2 | 66.7% |
| `extensions/stepfun` | 3 | 0 | 0.0% |
| `extensions/tokenjuice` | 3 | 1 | 33.3% |
| `extensions/tts-local-cli` | 3 | 2 | 66.7% |
| `extensions/vault` | 3 | 0 | 0.0% |
| `extensions/alibaba` | 2 | 0 | 0.0% |
| `extensions/copilot-proxy` | 2 | 1 | 50.0% |
| `extensions/document-extract` | 2 | 2 | 100.0% |
| `extensions/runway` | 2 | 0 | 0.0% |
| `extensions/senseaudio` | 2 | 0 | 0.0% |
| `extensions/talk-voice` | 2 | 1 | 50.0% |
| `extensions/web-readability` | 2 | 1 | 50.0% |
| `extensions/gmi` | 1 | 0 | 0.0% |
| `extensions/image-generation-core` | 1 | 1 | 100.0% |
| `extensions/novita` | 1 | 0 | 0.0% |

**hermes**

| dir | non-test source files | read (cited) | % |
|---|---:|---:|---:|
| `apps` | 1316 | 3 | 0.2% |
| `optional-skills` | 506 | 12 | 2.4% |
| `hermes_cli` | 460 | 84 | 18.3% |
| `tools` | 281 | 141 | 50.2% |
| `agent` | 267 | 144 | 53.9% |
| `skills` | 264 | 11 | 4.2% |
| `plugins` | 239 | 14 | 5.9% |
| `ui-tui/src` | 167 | 0 | 0.0% |
| `gateway` | 145 | 62 | 42.8% |
| `web/src` | 129 | 2 | 1.6% |
| `evals` | 105 | 24 | 22.9% |
| `tui_gateway` | 60 | 18 | 30.0% |
| `cron` | 22 | 17 | 77.3% |
| `acp_adapter` | 14 | 9 | 64.3% |

**occ**

| dir | non-test source files | read (cited) | % |
|---|---:|---:|---:|
| `archive` | 203 | 13 | 6.4% |
| `v2/src` | 69 | 34 | 49.3% |
| `scripts` | 7 | 7 | 100.0% |


## 2. Thin units

**The literal rule flags almost everything.** "read % under 40 or missed count over 6" selects
**45 of 46 units** — only `OCC01-v2-second-look` (49.3%, 4 missed) escapes, and the two other
units above 40% (`HM16-cron-second-pass` 77.3%, `HM13-state-root-files` 51.3%) are caught by
their missed counts (9 and 7). That result is real but not actionable: at 6.5% corpus coverage,
"thin" is the base state of this pass.

So below is the **operative** thin list — units at **under 5% of their scope** or with
**8 or more verifier-added mechanisms**. These are the units where the sampling was thin enough
that the next reader should not treat the unit as done. 21 of 46.

### Thin by coverage (under 5% of scope)

| unit | read % | what was missed |
|---|---:|---|
| `OC15-agents-second-pass-B` | 1.3% | `src/agents` is 1,750 files; OC14+OC15 read 52 between them. The verifier still added a per-tool-call decision/diagnostics split and steering-queue linearization. Everything about model-catalog projection, workspace provisioning, session dirs, run-wait, and the ~40 `agent-tools.*` variants is unread. |
| `HM18-tui-gateway-ui-desktop-docs` | 1.4% | Scope was 1,672 files (`tui_gateway/` 60 + `web/src` 129 + `ui-tui/src` 167 + `apps/` 1,316); 23 cited. `ui-tui/src` is **0% read**; `apps/desktop` essentially untouched. 8 missed mechanisms — the largest miss count outside HM09. |
| `OC14-agents-second-pass-A` | 1.7% | See OC15. The `before-tool-call` family (decision / diagnostics / state) was sampled at three files; the tool-admission surface that matters most to GATE-1 is largely unread. |
| `OC23-control-ui` | 2.1% | 30 of 1,445 `ui/src` files. `ui/src/pages` (720 files) read at 1.7%, `ui/src/components` (312) at 1.3%, `ui/src/api`, `features`, `plugins`, `types` at **0%**. The dashboard-facing repo is the least-read UI in the pass. |
| `OC24-docs-qa-security-skills` | 2.2% | 32 of 1,436. The reader went to `docs/gateway`, `docs/security`, `docs/nodes`; `docs/` as a whole (the rationale layer that several refuted audit gaps needed) is 2% covered. |
| `OC17-gateway-second-pass-B` | 2.2% | `src/gateway` is 1,311 files; OC16+OC17 cite 76. |
| `HM05-delegation-subagents-kanban` | 2.3% | Scope spans `agent/`+`tools/`+`hermes_cli/` (1,008); 23 cited. The reader's own unread_areas admit the entire `kanban_db*` locking/WAL layer, the watchers dispatcher body, and `_run_children_parallel` were read at signature level only. 7 missed, including "liveness is proven by progress, not a stopwatch" and the empty-Context thread-offload rule. |
| `HM20-skill-library` | 2.9% | 22 of 770 SKILL.md files. Skill *libraries* are cheap to skim and the verifier corrected four Halbert-state claims here that came from greps which "could not see the analog" — thin reading produced wrong Halbert state, not just missing items. |
| `OC06-plugins-sdk` | 3.0% | 34 of 1,133 (`src/plugins` 632 + `src/plugin-sdk` 492 + `src/plugin-state` 9). `src/plugin-sdk` alone is **0.6% read** — the capability/permission contract an extension is handed. |
| `OC22-extensions-local-providers-apps` | 3.3% | 23 in-scope of 699. Of its 38 cited files, 12 were Halbert-side. `apps/macos` (569 Swift files) got 7 files. This is the only unit that touched the macOS host layer at all. |
| `OC02-infra-rest` | 3.5% | `src/infra` is 810 files; OC01+OC02 cite 66. The reader's unread_areas list 18 entries. |
| `OC16-gateway-second-pass-A` | 3.6% | See OC17. |
| `OC07-cli-wizard-tui-entry` | 3.7% | 20 in-scope of 542. `src/cli` alone is **1.4% read** (6 of 440) — the whole command-surface and first-run path. |
| `OC20-extensions-memory-knowledge-automation` | 4.1% | 32 of 786, and the reader logged **23 unread_areas** — the most in the pass. `extensions/qa-lab` (357) read at 4.5%, `extensions/memory-core` (154) at 10%. |
| `OC01-infra-approvals-devices-backup` | 4.7% | See OC02; 7 missed mechanisms. |
| `OC05-config` | 4.8% | 24 of 500. The verifier's own six missed items include the config CAS/lock gap that surfaced a **live Halbert defect** (`models.yml` read-modify-write is unlocked while `being.yml` is flock-guarded, with the founder running concurrent sessions). A 5%-read unit found a real bug; the other 95% is unexamined. |

### Thin by miss count (8 or more verifier-added mechanisms)

| unit | missed | what was missed |
|---|---:|---|
| `HM09-tools-mcp` | 13 | See §5 — the reader's output was a placeholder and the verifier read the unit itself. Five high-priority absent findings, led by Halbert handing its **entire environment** to every stdio MCP subprocess (`mcp/client.py:239`). |
| `HM16-cron-second-pass` | 9 | Highest coverage in the pass (77.3% of `cron/`) and still 9 missed — evidence that miss count tracks reader lens, not just page count. |
| `HM10-tools-skills-second-pass` | 8 | Trust-tier × scan-verdict install matrix for skills, with a distinct row for agent-authored skills, among others. |
| `HM15-cli-model-config-ux` | 8 | 17 unread_areas; 38 of 460 `hermes_cli/` files. |
| `OC10-media-pipelines` | 8 | Best-covered openclaw unit after OC11 (25.6%) and still 8 missed, with 17 unread_areas. |
| `HM18-tui-gateway-ui-desktop-docs` | 8 | Also thin by coverage, above. |

**Pattern worth naming:** miss count does *not* correlate with read %. `HM16` read 77% and
missed 9; `OC15` read 1.3% and missed 5. The verifier was finding mechanisms the reader's
*framing* excluded, not mechanisms further down the file list. More pages per unit will not fix
that; a second lens on the same pages would.

## 3. Directories in no unit's scope

Totals: **123 directories holding 5,521 non-test source files** were in no unit's scope
(openclaw `src` 6 dirs / 214 files · `extensions` 94 / 3,587 · `apps` 6 / 883 · hermes 14 / 834 ·
open-claude-code 3 / 3).
Openclaw `extensions/` accounts for 94 dirs / 3,587 files of that, and most of it should stay
unread (see below). The rest is listed per root, with the assigned unit or `— none —`.

### The unassigned areas that actually matter

Four of them, in order:

1. **`openclaw/src/skills` — 144 files, 0.7% read, in no unit's scope.** Not a skill *library*:
   `src/skills/workshop/` is a complete self-improving-skill lifecycle — `curator.ts`,
   `service-propose.ts`, `proposal-origin-validation.ts`, `review-run.ts`, `apply-transition.ts`,
   `collection-rollback.ts` / `collection-restore.ts` / `collection-backup.ts`, `target-lock.ts`,
   `policy.ts`, `tool-policy-diagnostic.ts`, `revision-hash.ts`, `store-sqlite-{schema,record,
   transition,rollback}.ts`, `history-scan*.ts` (7 files), `experience-review*.ts` (5 files).
   The SK-series wave lifted CC-compatible `SKILL.md` + catalog + cache boundary + `skill_events`
   — the *format*. This is the *governance* half: how a skill gets proposed, reviewed, applied,
   locked and rolled back. Directly on SKILL-1 and KNOW-1. The single largest oversight of the
   split.
2. **`openclaw/src/mcp` — 12 files, 0% read, in no unit's scope.** The MCP **server** side:
   `channel-bridge.ts`, `channel-server.ts`, `channel-server-runtime.ts`, `channel-tools.ts`,
   `agent-session-env.ts`, `agent-session-owner.ts`, `plugin-tools-serve.ts`,
   `plugin-tools-handlers.ts`, `tools-stdio-server.ts`, `openclaw-tools-serve*.ts`. Halbert's own
   18-tool `mcp/server.py` is sitting on a founder-ruled B6 **audit** (not a rebuild), and this is
   the closest origin analog to that server — and nobody read it. `HM09` read the *client* side
   and found five high absent items; the server side got nothing.
3. **`openclaw/apps/{android,ios,shared,mobile,macos-mlx-tts}` — 883 files.** Of these only
   `apps/shared` (350) has any claim on a single-host steward (shared protocol/session types with
   the desktop app); the mobile trees are genuinely out of scope. But note the *assigned* macOS
   tree fared no better: `apps/macos` is in OC22's scope and was read at **1.2%** (7 of 569).
4. **hermes `docs/` and its siblings — 834 files across 14 unassigned top-level dirs.**
   `docs/` itself is only 21 files but holds `rfcs/`, `design/`, `security/`, `observability/`,
   `middleware/`, `kanban/`, `ADR.md`, `session-lifecycle.md`, `state-db-recovery.md`,
   `streaming-tts.md`, `chronos-managed-cron-contract.md`. Exactly one file
   (`docs/micro-compaction.md`) was read in the whole pass. Several audit gaps were refuted for
   want of origin rationale that probably lives here. `website/` (754) and `tests-js/`,
   `optional-mcps/`, `mcp-research-data/`, `nix/`, `locales/`, `native/`, `providers/`,
   `contributors/`, `datagen-config-examples/`, `docker/`, `scripts/`, `assets/` are the rest and
   are not worth reading.

### The 94 unassigned openclaw extensions — deliberately leave most of them

They fall in two families and both are low-value for this product:

- **Chat-platform adapters** (`discord` 449, `telegram` 312, `matrix` 238, `slack` 219,
  `whatsapp` 180, `feishu` 165, `msteams` 137, `mattermost` 80, `signal` 77, `line` 74,
  `zalouser` 57, `googlechat` 55, `clickclack` 52, `buzz` 50, `tlon` 47, `zalo` 47,
  `nextcloud-talk` 44, `nostr` 40, `irc` 37, plus a dozen smaller): multi-tenant group fan-out,
  per-room allowlists, bot identity. `OC03`'s reader already flagged this shape as an
  anti-pattern against single-user/single-host. Skip.
- **Model-vendor adapters** (`codex` 364, `openai` 69, `xai` 63, `anthropic` 52, `google` 46,
  `openrouter` 22, `minimax` 26, plus ~40 more): provider catalogs and hardcoded model
  identifiers. Reading these risks importing exactly what the never-bake-model-names directive
  forbids. Skip — with one exception already in scope (`OC22` covered the *local* inference
  adapters, which is the correct slice).

The genuinely defensible unassigned extensions are `qa-lab`-adjacent ops tooling and
`extensions/test-support`; neither is worth a unit.


### Full directory listing, with the unit that owned each

**openclaw/src** — 77 top-level dirs, 6 in NO unit's scope (214 non-test source files unassigned)

| dir | non-test source files | unit scope |
|---|---:|---|
| `agents` | 1750 | OC14/OC15 |
| `gateway` | 1311 | OC16/OC17 |
| `infra` | 810 | OC01/OC02 |
| `plugins` | 632 | OC06 |
| `commands` | 556 | OC04 |
| `config` | 500 | OC05 |
| `plugin-sdk` | 492 | OC06 |
| `auto-reply` | 477 | OC03 |
| `cli` | 440 | OC07 |
| `channels` | 275 | OC18 |
| `cron` | 188 | OC18 |
| `skills` | 144 | **— none —** |
| `shared` | 123 | OC12 |
| `state` | 105 | OC12 |
| `secrets` | 96 | OC12 |
| `daemon` | 79 | OC08 |
| `node-host` | 71 | OC08 |
| `acp` | 67 | OC11 |
| `system-agent` | 67 | OC09 |
| `tasks` | 67 | OC09 |
| `tui` | 66 | OC07 |
| `claws` | 61 | OC09 |
| `logging` | 61 | OC08 |
| `meeting-bot` | 56 | OC11 |
| `process` | 53 | OC08 |
| `sessions` | 48 | OC12 |
| `test-utils` | 48 | **— none —** |
| `media` | 45 | OC10 |
| `media-understanding` | 44 | OC10 |
| `worker` | 43 | OC08 |
| `security` | 40 | OC12 |
| `hooks` | 39 | OC08 |
| `talk` | 39 | OC11 |
| `flows` | 37 | OC09 |
| `wizard` | 33 | OC07 |
| `tts` | 32 | OC11 |
| `utils` | 30 | OC12 |
| `llm` | 27 | OC12 |
| `audit` | 26 | OC08 |
| `transcripts` | 25 | OC10 |
| `status` | 17 | OC08 |
| `mcp` | 12 | **— none —** |
| `memory-host-sdk` | 12 | OC11 |
| `context-engine` | 11 | OC11 |
| `pairing` | 11 | OC12 |
| `routing` | 11 | OC11 |
| `proxy-capture` | 10 | OC11 |
| `boards` | 9 | OC09 |
| `plugin-state` | 9 | OC06 |
| `test-helpers` | 9 | **— none —** |
| `trajectory` | 9 | OC09 |
| `video-generation` | 9 | OC10 |
| `fleet` | 8 | OC09 |
| `image-generation` | 8 | OC10 |
| `model-catalog` | 8 | OC12 |
| `media-generation` | 7 | OC10 |
| `music-generation` | 7 | OC10 |
| `canvas` | 6 | OC10 |
| `link-understanding` | 6 | OC10 |
| `snapshot` | 6 | OC09 |
| `chat` | 4 | OC11 |
| `projects` | 4 | OC09 |
| `types` | 4 | OC12 |
| `realtime-transcription` | 3 | OC10 |
| `session-cards` | 3 | OC09 |
| `web-search` | 3 | OC11 |
| `bootstrap` | 2 | OC07 |
| `memory` | 2 | OC11 |
| `model-picker` | 2 | OC12 |
| `web-fetch` | 2 | OC11 |
| `compat` | 1 | OC12 |
| `interactive` | 1 | OC07 |
| `provider-runtime` | 1 | OC12 |
| `test-fixtures` | 1 | **— none —** |
| `web` | 1 | OC11 |
| `docs` | 0 | OC24 |
| `scripts` | 0 | **— none —** |

**openclaw/extensions** — 154 top-level dirs, 94 in NO unit's scope (3587 non-test source files unassigned)

*In some unit's scope (60):* `a2a`(OC19), `acpx`(OC19), `active-memory`(OC20), `admin-http-rpc`(OC19), `azure-speech`(OC21), `bonjour`(OC19), `browser`(OC21), `canvas`(OC21), `clawrouter`(OC19), `comfy`(OC21), `copilot-proxy`(OC22), `cua-computer`(OC21), `deepgram`(OC21), `device-pair`(OC19), `diagnostics-otel`(OC19), `diagnostics-prometheus`(OC19), `diffs`(OC21), `diffs-language-pack`(OC21), `document-extract`(OC21), `elevenlabs`(OC21), `file-transfer`(OC19), `fish-audio-speech`(OC21), `geolocation`(OC21), `image-generation-core`(OC21), `imessage`(OC21), `inworld`(OC21), `linux-node`(OC21), `litellm`(OC22), `llama-cpp`(OC22), `llm-task`(OC20), `lmstudio`(OC22), `lobster`(OC20), `logbook`(OC20), `memory-core`(OC20), `memory-lancedb`(OC20), `memory-wiki`(OC20), `migrate-claude`(OC20), `migrate-hermes`(OC20), `oc-path`(OC19), `ollama`(OC22), `onepassword`(OC19), `openshell`(OC19), `policy`(OC19), `qa-channel`(OC20), `qa-lab`(OC20), `raft`(OC19), `reef`(OC19), `senseaudio`(OC21), `sglang`(OC22), `talk-voice`(OC21), `team-reports`(OC20), `tokenjuice`(OC19), `tts-local-cli`(OC21), `vault`(OC19), `visitor-access`(OC19), `vllm`(OC22), `voice-call`(OC21), `web-readability`(OC21), `webhooks`(OC19), `workboard`(OC20)

*__In NO unit's scope (94)__, dir(non-test files):* `discord`(430), `codex`(353), `telegram`(300), `matrix`(237), `slack`(219), `whatsapp`(179), `feishu`(156), `msteams`(133), `mattermost`(77), `signal`(76), `line`(71), `openai`(69), `xai`(63), `zalouser`(56), `googlechat`(55), `clickclack`(52), `anthropic`(50), `buzz`(50), `google-meet`(47), `tlon`(47), `google`(45), `nextcloud-talk`(44), `nostr`(40), `zalo`(40), `irc`(36), `copilot`(34), `twitch`(28), `synology-chat`(27), `minimax`(26), `crabbox`(25), `sms`(23), `openrouter`(22), `zoom-meetings`(22), `teams-meetings`(21), `deepinfra`(19), `github-copilot`(19), `amazon-bedrock`(16), `mxc`(16), `firecrawl`(13), `moonshot`(13), `mistral`(11), `opencode`(11), `parallel`(11), `tavily`(11), `anthropic-vertex`(9), `deepseek`(9), `microsoft-foundry`(9), `opencode-go`(9), `tencent`(9), `vydra`(9), `zai`(9), `fal`(8), `qwen`(8), `venice`(8), `xiaomi`(8), `baseten`(7), `brave`(7), `chutes`(7), `duckduckgo`(7), `fireworks`(7), `imap`(7), `kimi-coding`(7), `longcat`(7), `meta`(7), `volcengine`(7), `beam`(6), `cerebras`(6), `cloudflare-ai-gateway`(6), `exa`(6), `kilocode`(6), `perplexity`(6), `together`(6), `vercel-ai-gateway`(6), `amazon-bedrock-mantle`(5), `arcee`(5), `byteplus`(5), `cohere`(5), `featherless`(5), `gradium`(5), `huggingface`(5), `searxng`(5), `synthetic`(5), `microsoft`(4), `nvidia`(4), `pixverse`(4), `qianfan`(4), `test-support`(4), `voyage`(4), `groq`(3), `stepfun`(3), `alibaba`(2), `runway`(2), `gmi`(1), `novita`(1)

**openclaw/packages** — 23 top-level dirs, 0 in NO unit's scope (0 non-test source files unassigned)

| dir | non-test source files | unit scope |
|---|---:|---|
| `ai` | 156 | OC13 |
| `gateway-protocol` | 149 | OC13 |
| `memory-host-sdk` | 77 | OC13 |
| `plugin-sdk` | 56 | OC13 |
| `gateway-client` | 28 | OC13 |
| `normalization-core` | 27 | OC13 |
| `agent-core` | 25 | OC13 |
| `markdown-core` | 24 | OC13 |
| `terminal-core` | 20 | OC13 |
| `acp-core` | 13 | OC13 |
| `media-core` | 11 | OC13 |
| `model-catalog-core` | 11 | OC13 |
| `media-understanding-common` | 10 | OC13 |
| `llm-core` | 8 | OC13 |
| `session-url-contract` | 8 | OC13 |
| `net-policy` | 7 | OC13 |
| `sdk` | 7 | OC13 |
| `tool-call-repair` | 7 | OC13 |
| `media-generation-core` | 5 | OC13 |
| `mermaid-renderer` | 3 | OC13 |
| `plugin-package-contract` | 1 | OC13 |
| `retry` | 1 | OC13 |
| `workboard-contract` | 1 | OC13 |

**openclaw/apps** — 9 top-level dirs, 6 in NO unit's scope (883 non-test source files unassigned)

| dir | non-test source files | unit scope |
|---|---:|---|
| `macos` | 569 | OC22 |
| `shared` | 350 | **— none —** |
| `ios` | 281 | **— none —** |
| `android` | 248 | **— none —** |
| `swabble` | 27 | OC22 |
| `linux` | 19 | OC22 |
| `macos-mlx-tts` | 4 | **— none —** |
| `.i18n` | 0 | **— none —** |
| `mobile` | 0 | **— none —** |

**openclaw/ui/src** — 13 top-level dirs, 0 in NO unit's scope (0 non-test source files unassigned)

| dir | non-test source files | unit scope |
|---|---:|---|
| `pages` | 720 | OC23 |
| `components` | 312 | OC23 |
| `lib` | 215 | OC23 |
| `app` | 109 | OC23 |
| `test-helpers` | 84 | OC23 |
| `i18n` | 43 | OC23 |
| `plugins` | 13 | OC23 |
| `api` | 7 | OC23 |
| `lit` | 6 | OC23 |
| `features` | 5 | OC23 |
| `e2e` | 3 | OC23 |
| `types` | 2 | OC23 |
| `styles` | 1 | OC23 |

**hermes-agent (named dirs)** — 14 top-level dirs, 0 in NO unit's scope (0 non-test source files unassigned)

| dir | non-test source files | unit scope |
|---|---:|---|
| `apps` | 1395 | HM18 |
| `optional-skills` | 603 | HM20 |
| `hermes_cli` | 461 | HM14/HM15 (+HM05) |
| `skills` | 313 | HM20 |
| `ui-tui` | 308 | HM18 |
| `tools` | 283 | HM05-HM10 |
| `agent` | 268 | HM01-HM05 |
| `plugins` | 263 | HM17 |
| `gateway` | 147 | HM11/HM12 |
| `web` | 133 | HM18 |
| `evals` | 129 | HM19 |
| `tui_gateway` | 61 | HM18 |
| `cron` | 23 | HM16 |
| `acp_adapter` | 14 | HM17 |

**hermes-agent (other top-level)** — 14 top-level dirs, 14 in NO unit's scope (834 non-test source files unassigned)

| dir | non-test source files | unit scope |
|---|---:|---|
| `website` | 754 | **— none —** |
| `scripts` | 51 | **— none —** |
| `docs` | 21 | **— none —** |
| `providers` | 3 | **— none —** |
| `tests-js` | 2 | **— none —** |
| `contributors` | 1 | **— none —** |
| `docker` | 1 | **— none —** |
| `native` | 1 | **— none —** |
| `assets` | 0 | **— none —** |
| `datagen-config-examples` | 0 | **— none —** |
| `locales` | 0 | **— none —** |
| `mcp-research-data` | 0 | **— none —** |
| `nix` | 0 | **— none —** |
| `optional-mcps` | 0 | **— none —** |

**open-claude-code** — 6 top-level dirs, 3 in NO unit's scope (3 non-test source files unassigned)

| dir | non-test source files | unit scope |
|---|---:|---|
| `archive` | 217 | OCC02 |
| `v2` | 70 | OCC01 |
| `scripts` | 6 | OCC02 |
| `docs` | 3 | **— none —** |
| `assets` | 0 | **— none —** |
| `rudevolution` | 0 | **— none —** |


## 4. Ranked follow-up units

Sized like this pass: one agent, ~25–40 files. Priority is relevance to a **single-host
steward that identifies as the machine** first, unread mass second, and demonstrated density
(what the pass found from a small sample of the same tree) third.

### P1 — read these next

**`F01-macos-host-integration`** — `openclaw/apps/macos/Sources/OpenClaw/` (339 Swift files,
1.2% read). Read ~35: `LaunchAgentManager`, `AppleEventPermission`, `PermissionManager`,
`PortGuardian`, `BoundedProcess`, `ExecApprovals`, `NodePairingApprovalPrompter`,
`GatewaySleepCycleController`, `ConfigFileWatcher`, `CoalescingFSEventsWatcher`, `ConfigStore`,
`CLIInstaller` + `CLIInstallPrompter`, `ApplicationRelocator`, `NotificationManager`,
`AppLifecycleSupport`, `AppLaunchPresentationPolicy`, `ControlChannel`,
`ConnectionModeCoordinator`/`Resolver`, `ComputerActionService` + `ComputerScreen/WindowActionExecutor`,
`AudioInputDeviceObserver`, `CameraCaptureService`, `CookieSyncManager`, `AgentEventStore`.
**Why it matters:** Halbert is a macOS-resident daemon with a Tauri shell, an OS-grant
permission module (`persona/permission/os_grant.py`), screen capture, audio in, and open
APPLE-1 / DIST-1 / SHELL-1 rows. This is the only origin tree that solves *being a macOS app
that owns its host* — LaunchAgent lifecycle, TCC/Apple-Events consent, port ownership, bounded
child processes, sleep/wake, relocation, CLI install. `OC22` read seven Swift files here and every
one of its six macOS-derived candidates was kept (TCC preflight, capture-permission preflight,
missing bundle usage strings, sleep/wake lease, launch-at-login, port-owner identity); the density is proven and 332 files are untouched.
**Priority: highest.**

**`F02-agents-tool-admission`** — `openclaw/src/agents`, the tool-admission family
(~1,750 files, 3.1% read). Read ~35 by prefix: `agent-tools.before-tool-call.*` (all variants),
`agent-tool-availability`, `agent-tool-source-execution-guard`, `agent-tool-definition-adapter`,
`agent-tool-metadata`, `sender-tool-policy`, `tool-call-shared`, `core-coding-tools`,
`mcp-content` / `mcp-http-transport`, `incognito-system-prompt`, `workspace-state-identity`,
`workspace-templates`, `session-dirs`, `model-auth-markers`, `agent-steering-queue`, `run-wait`.
**Why it matters:** this is the origin's answer to "one policy pipeline across MCP and internal
tools" — the founder constraint Halbert is building toward under GATE-1/TRUST-1. Two units read
52 files here and produced 26 kept candidates — one every two files; the remaining 97% is the
densest unread mass in the corpus. **Priority: highest.**

**`F03-mcp-server-side`** — `openclaw/src/mcp` (12 files, **0% read, unassigned**) + hermes
`tools/mcp_*` remainder + `hermes_cli/mcp_catalog.py` + `packages/gateway-protocol` tool-wire
types (~30 files). **Why it matters:** MCP-1 and the founder-ruled B6 audit of Halbert's
existing 18-tool `mcp/server.py`. `HM09` covered the client and found that Halbert leaks its whole
environment to stdio children; nobody looked at what a hardened MCP *server* refuses to do —
session ownership (`agent-session-owner.ts`), env scoping (`agent-session-env.ts`), cancel
handling (`plugin-tools-handlers.cancel`), and the stdio-server boundary. Small unit, direct hit
on an open founder decision. **Priority: highest.**

**`F04-skill-workshop-governance`** — `openclaw/src/skills/workshop` (144 files, 0.7% read,
**unassigned**). Read ~35: `curator`, `service-propose`, `proposal-origin-validation`,
`proposal-bundle`, `review-run`, `review-outcome`, `apply-transition`, `target-lock`, `policy`,
`tool-policy-diagnostic`, `revision-hash`, `collection-{backup,restore,rollback,review-state,
contracts}`, `store-sqlite-{schema,record,transition,rollback}`, `store-evaluation`,
`history-scan*`, `experience-review*`, `learn-prompt`, `skills-root`, `workspace-skill-read`,
`plugin-hooks`. **Why it matters:** SKILL-1 + KNOW-1. The lifted SK-series gave Halbert the skill
*format*; this is the lifecycle — how a skill is proposed from observed history, reviewed,
applied under a lock, hash-pinned, and rolled back. For a steward that is supposed to learn its
own host without a human approving every step, this is the missing governance layer, and the
`policy.ts` / `proposal-origin-validation.ts` pair is a deterministic gate of exactly the shape
the founder constraints require. **Priority: highest.**

**`F05-origin-rationale-docs`** — hermes `docs/{rfcs,design,security,observability,middleware,
kanban}` + `docs/{ADR,session-lifecycle,state-db-recovery,streaming-tts,chronos-managed-cron-contract,
profile-routing}.md` + openclaw `src/docs` + `docs/maturity` (~30 files, 1 read in the whole pass).
**Why it matters:** cheapest unit on the list and it repairs a systematic weakness. Several
solidity-audit gaps were refuted, and several discovery candidates dropped, for want of the
origin's stated *reason* for a mechanism. Docs are also where the origin records the incidents
that produced its hardening — the "why_solid" evidence the refuters kept asking for.
**Priority: highest (best value per file).**

**`F06-config-state-durability`** — `openclaw/src/config` remainder + `src/state` + `src/sessions`
(653 files, ~5% read; ~35 files: the io/observe-recovery family, last-known-good promotion,
schema/tier validation, `config-form.constraints` counterparts, state store writers, session
persistence). **Why it matters:** CFG-1 and STATE-1, and `OC05` already turned 24 files here into
a **confirmed live Halbert defect** — `models.yml`'s read-modify-write is unlocked while
`being.yml`'s is flock-guarded, and the founder runs concurrent sessions. That is a lost-update
on the API-key store. The rest of the durability story (atomic replace, last-known-good,
polluted-placeholder gating) is unread. **Priority: highest.**

### P2 — read after P1

**`F07-gateway-auth-approval`** — `openclaw/src/gateway` second pass (1,311 files, 5.9%): the
auth, exec-approval, route-admission and streaming families. ~35 files. One door / SURF-1 /
MCP-1. The two units here produced 24 kept candidates from 76 files.

**`F08-cli-self-diagnosis-and-update`** — hermes `hermes_cli/` remainder (460 files, 18% read):
`doctor*`, `_install_repair`, `_early_recovery`, `_scan_venv_blockers`, `update_*` (lock,
contract, receipt, abort_recovery), `backup`, `archive_safe`, `process_identity`,
`resource_limits`, `context_switch_guard`. ~35 files. DIST-1 and CLI-1: a steward that claims to
*be* the machine should be able to diagnose and repair its own install, and Halbert's update path
is unbuilt.

**`F09-first-run-and-onboarding`** — `openclaw/src/cli` (440, **1.4%**) + `src/wizard` (33, 21%)
+ `src/bootstrap`. ~35 files. BIRTH-1: onboarding, naming, the first-run capability probe, and
the command surface a person meets before anything is configured.

**`F10-plugin-capability-contract`** — `openclaw/src/plugin-sdk` (492, **0.6%**) +
`packages/plugin-sdk` (56, **0%**) + `src/plugin-state` (9). ~35 files. What an extension is
*allowed* to do, expressed as a contract rather than as trust — the shape Halbert's capability
registry (`capabilities.py`) would grow into if it ever admits third-party code. FENCE-1.

**`F11-control-ui-patterns`** — `openclaw/ui/src/lib` (215, 4%) + `ui/src/pages/{sessions,
settings,activity,devices}` + `ui/src/api` (**0%**) + `ui/src/features` (**0%**). ~35 files.
SURF-1: the dashboard is Halbert's only human surface and this is the least-read UI in the pass
(2.1%). Note the constraint filter: take the state/streaming/deep-link patterns, not the visual
language (Halbert has its own tokens and a no-emoji rule).

**`F12-hermes-plugin-runtime`** — hermes `plugins/` (239 files, **5.9%**): `plugin_loader.py`,
`plugin_storage.py`, `plugin_utils.py`, plus `memory/`, `observability/`, `context_engine/`,
`web/`, `security-guidance/`. ~30 files. Complements F10 with the Python-side loader and storage
isolation.

**`F13-reference-agent-loop`** — open-claude-code `archive/open_claude_code/src` (203 files,
6.4%). ~35 files. A decompiled reference implementation of the agent loop, terminal handling and
tool dispatch: ground truth for TERM-1 and the turn machinery, and the only origin in the corpus
that is a faithful reconstruction rather than a reimagining.

**`F14-secrets-at-rest-and-broker`** — `openclaw/src/secrets` remainder (96, 10%) +
`extensions/{vault,onepassword}` remainder + `src/security` remainder. ~30 files. Tier-2 secrets,
scrub-before-model, and the credential-as-reference pattern the `HM03` verifier flagged as missed
("a credential can be a reference resolved at use time, not a value stored in the config").

### P3 — worth doing, not urgent

**`F15-command-surface`** — `openclaw/src/commands` remainder (556, 5.4%). Slash/command registry
depth; CLI-1. `OC03` already showed Halbert has one hardcoded `/model` parser against a
data-driven registry here.

**`F16-hermes-tools-remainder`** — hermes `tools/` remainder (281, 50% read): `computer_use/`,
the `browser_*` family tail, notes/memory tools. ~30 files.

**`F17-desktop-rpc-bridge`** — hermes `tui_gateway/methods_*` remainder (60, 30%) +
`apps/desktop`. ~30 files. The RPC method surface between a desktop shell and an agent daemon —
the pattern Halbert's `hostConversation` bridge is a small instance of.

**`F18-protocol-and-host-sdk-contracts`** — `openclaw/packages/ai` (156, **0%**) +
`packages/memory-host-sdk` (77, 1.3%) + `packages/gateway-protocol` remainder (149, 4.7%).
~35 files. Typed wire contracts; useful mainly as a shape reference for Halbert's own event and
memory boundaries.

**`F19-cross-cutting-primitives`** — `openclaw/src/shared` (123, 4.1%) + `src/utils` (30, **0%**)
+ `src/types` (4, **0%**). ~30 files. Small, and the place where a codebase keeps the invariants
everything else assumes.

**`F20-deterministic-policy-extension`** — `openclaw/extensions/policy` full read (72, 8.3%) +
`extensions/{reef,visitor-access,admin-http-rpc}` remainder. ~30 files. A policy engine shipped
as an extension with doctor/auto-repair and state attestation; relevant to the deterministic-policy
directive, though `OC19`'s verifier already found Halbert's `consent/selfmod.py` ahead of it in
places.

### Explicitly not recommended

`openclaw/apps/{android,ios,mobile,macos-mlx-tts}` (mobile clients); the 94 unassigned
`extensions/` chat-platform and model-vendor adapters (multi-tenant fan-out and baked model
names — both against standing directives); hermes `website/`, `tests/`, `tests-js/`, `locales/`,
`nix/`, `contributors/`; `open-claude-code/rudevolution` (empty).

## 5. Verify-pass anomalies

### HM09 — the reader produced nothing, the verifier did the unit

`HM09-tools-mcp` is the one broken cell in the matrix. The reader's output file
(`.../wf-oss/HM09-tools-mcp.json`) contained **the single token `PLACEHOLDER`**. The verifier
says so plainly: *"there is nothing to verify and verdicts is empty."* It then read the unit
itself — hermes `tools/mcp_*` (schema, registration, discovery, content, handlers, health,
errors, sampling, schema_cache, death_supervisor, config, transport) plus
`hermes_cli/{mcp_security,mcp_catalog}.py` — and grepped Halbert's `mcp/{client,config,bridge,
health,registry}.py`, `dashboard/routes/mcp.py` and the test tree for each analog.

Consequences for anyone consuming this data:

- The **18 candidates** stored under `HM09-tools-mcp.candidates` are the reader's, carry
  `verdict: None` and `status: "no-verdict"`, and are the **only unverified candidates in the
  entire pass** (789 candidates: 589 kept, 182 dropped, 18 no-verdict — all 18 are HM09's).
  Their origin citations and their Halbert-state claims have not been checked by anyone. Do not
  dispatch them as written.
- The **13 items under `missed_by_reader`** are the verifier's own first-hand findings, with
  read citations on both sides. These are the trustworthy HM09 output. Five are high and absent
  in Halbert: whole-environment inheritance by stdio MCP children (`mcp/client.py:239` vs
  `mcp_tool_config.py:56-112`); unscanned server-supplied tool descriptions reaching the prompt
  (`bridge.py:130-158` vs `mcp_tool_schema.py:16-40` + `ansi_strip.py:74-83`); uncapped tool
  results with binary blobs JSON-dumped into context (`bridge.py:161-186` vs
  `mcp_tool_content.py:16-231`); orphaned stdio children killed without their process group
  (`client.py:265-335` vs `mcp_death_supervisor.py:1-135`); and no security screen on either the
  config save path (`dashboard/routes/mcp.py:131-164`) or the spawn path (vs `mcp_security.py:1-135`).
- The two sets **overlap heavily but not exactly** — the verifier's C4/C5/C1 correspond to the
  reader's top three. Where they agree, take the verifier's citation. The verifier also recorded
  one deliberate **non-lift**: Hermes accepts server-initiated sampling behind a gate; Halbert
  refuses server-initiated requests outright, which is stronger, and the task is to pin that
  refusal with a test rather than build the gate.
- Coverage-wise HM09 is not an outlier: 17 of `tools/`' 281 files cited, in line with its
  siblings. It is the *verification* that failed, not the reading.

**Recommended action:** re-run HM09 as a normal unit (reader + verifier) over hermes `tools/mcp_*`
+ `hermes_cli/mcp_*`, and fold `F03-mcp-server-side` into the same dispatch so the client and
server halves land together. Until then, treat only the 13 verifier items as dispatchable.

### Other units whose verify_summary reports a problem

No other unit had a process failure. Scanning all 46 `verify_summary` fields for failure
language turns up only content-level corrections, which is the verifier working as designed:

- **Fabricated or wrong evidence, corrected in place** — `HM01`, `HM05`, `HM06`, `HM13`,
  `OC02`, `OC03`, `OC13`. The sharpest is `OC03`: two candidates (C7, C9) *share a fabricated
  evidence sentence* — `grep fallback model/router.py` returns zero hits, and the real fallback
  path is `model/tier_router.py:480-527` plus `federation/compute_router.py`. Retarget before
  dispatch. `OC05` similarly found the reader described the internals of a file it never opened
  (`replace-file.js` does not exist; `replace-file.ts` is an 8-line re-export).
- **Wrong Halbert-state claims from greps that could not see the analog** — `HM20` (four claims
  wrong), `OC05` (two, both understating what Halbert has), `OC03` (four corrected),
  `OC19` (`C10` unsound as written because Halbert's redaction placeholders are `<secret>` /
  `[redacted]`, strings that occur in legitimate content). This is the most common failure mode
  in the pass and it argues for verifying Halbert state with reads, not greps.
- **Wrong line citations on a correct mechanism** — `OC03` C6 (`command-auth.ts` union is at
  line 41, not 294-330), `HM20` C1. Mechanism kept, citation fixed.
- **Truncation notes** (`HM02`, `HM03`, `HM07`, `HM08`) are the reader admitting a large file was
  read by grep-index plus excerpts — `agent/context_compressor.py` (281KB, ~4,900 lines) and
  `agent/conversation_compression.py` (219KB) are the extreme cases. Both are named in
  unread_areas and neither is a verification failure, but any candidate resting on those two
  files should be re-read at the line level before dispatch.
- **`HM11`, `HM13`, `HM18`** mention "corruption" only as subject matter (store corruption,
  state-DB repair), not as a problem with the unit.

One more structural note: `merged_discoveries.json` holds full text for all 46 discovery units,
but six of the 17 **solidity audits** lost their full text (`A06` scheduler, `A08` store,
`A10` tts, `A11` permission lattice, `A13` skills, `A15` heartbeat/catch-up) and survive only as
`lost_units_digest.md` + `lost_units_verdicts.md`. That is a separate gap from HM09 and is worth
the same treatment: re-run those six audits if their gaps are ever dispatched.



## 6. Appendix — per-unit unread_areas, verbatim

The reader's own `unread_areas` for each unit, unedited, followed by the titles of the
mechanisms the independent verifier added (`missed_by_reader`).

### `HM01-agent-turn-family`

scope `agent/ turn+tool+error family (shared agent/ with HM02-HM04)` — 267 files in scope, 45 cited read (16.9%), self-reported 45, verifier-missed 6.

**unread_areas (reader, verbatim):**

- agent/turn_context.py's full 1060-line body beyond the stdio-guard/idle-compaction sections
- agent/tool_executor.py's remaining ~1150 lines (concurrent-batch/start-order-gate machinery, sequential-dispatch/checkpoint code)
- agent/turn_recovery.py's provider-specific 401/credential-refresh bodies (Nous/Anthropic/Copilot/Codex) and validate_response_shape/describe_invalid_response
- agent/error_classifier.py's ~825-line classify_api_error/route_classified_error pipeline body and remaining provider-specific pattern tables
- agent/turn_finalizer.py's 635-line body (budget summary, trajectory save, memory/skill review) and turn_context_compaction.py's preflight/overflow-warning passes beyond idle-compaction
- agent/inline_tool_executors.py's dispatch table body and agent/tool_dispatch_helpers.py's parallelism/multimodal logic
- the bulk of tests/agent/ beyond test_turn_liveness.py and test_tool_guardrails.py's test-name inventories

**verifier-added mechanisms the reader missed (titles):**

- Untrusted-data delimiters around high-risk tool results — the indirect-prompt-injection boundary
- Typed turn_exit_reason vocabulary with a deterministic 'why there is no reply, and what to do' explanation
- End-of-turn over-claim verifier: state deterministically which claimed effects did NOT land
- Pre-mutation workspace checkpoint, including before a destructive terminal command
- Leak-safe cross-thread coroutine scheduling (close the coroutine when the loop refuses it)
- Iteration accounting that can be refunded, and a per-turn ceiling that is not five

### `HM02-agent-context-prompt-family`

scope `agent/ context+prompt family (shared)` — 267 files in scope, 28 cited read (10.5%), self-reported 27, verifier-missed 6.

**unread_areas (reader, verbatim):**

- agent/prompt_builder.py (99.8KB) — only grepped for _scan_context_content/_read_text_with_timeout/_truncate_content and DEFAULT_AGENT_IDENTITY/help-guidance strings; the bulk (environment-hint building, the full context-file discovery/priority chain, workspace snapshot assembly beyond what coding_context.py covers) is unread
- agent/conversation_compression.py (219KB) — only the CompressionCommitFence class (lines ~366-406) was read; compress_context() itself, run_compress_context_with_progress_timeout, mark_context_compression_timed_out, and the bulk of the two-phase-commit orchestration logic are unread
- agent/context_compressor.py (281KB, ~4900 lines) — read via grep of all top-level def/class names plus 5-6 targeted excerpts (tool-result summarizers, image eviction, resolve_model_threshold signature only); the ContextCompressor class body itself (lines 1641-4704, the bulk of the file: anchor-index building, skill-pruned marker reinjection, salvage_grown_transcript's full logic, the handoff-scan state machine, temporal anchoring, anti-thrash cooldown ladder) is unread
- agent/system_prompt.py — read build_system_prompt_parts/build_system_prompt/invalidate_system_prompt/reconstruct_static_prefix; the ~15 smaller _*_parts() helper functions building each individual prompt section (identity, guidance, memory, timestamp, zone/timezone bits, bot-mode, Alibaba-specific identity block) are unread
- agent/coding_context.py — read the git-status/project-facts block builder; ContextProfile/RuntimeMode class definitions and the mode-detection logic (_detect_profile, resolve_runtime_mode) are unread
- agent/message_sanitization.py — read the surrogate/ASCII sanitization and tool-call-argument JSON repair; the reasoning-echo-family matching (lines 438-509) and tool_call_id dedup/uniquify machinery (lines 309-438) were only listed via grep, not read in detail
- tests/agent/test_context*.py and test_prompt*.py — the task lists ~60 matching test files under tests/agent/, tests/run_agent/, tests/gateway/, tests/hermes_cli/, tests/cli/, tests/tui_gateway/, tests/state/; only test_micro_compaction.py (partial), test_side_question.py (partial), and test_prompt_cache_boundary.py (partial) were actually opened — the rest were enumerated by filename only
- docs/ beyond micro-compaction.md — no other doc files in the unit's docs/ directory were checked for additional claims about this unit's mechanisms
- agent/context_references.py — read in full for the @-reference expansion mechanism but not cross-checked against Halbert's chat-input handling for an equivalent (deferred; no @file:/@folder: candidate was written up despite reading the source, since Halbert's chat input surface for this wasn't located in the time available)
- agent/prompt_cache_scope.py and agent/native_compaction.py — read in full but not converted into standalone candidates (folded into anti-pattern notes / lower-priority mentions) since their applicability to Halbert's local-first, no-session-rotation design is marginal without further confirmation of how Halbert's compression lineage (if any) works

**verifier-added mechanisms the reader missed (titles):**

- Malformed tool-call argument JSON repair ladder (local-model shaped) instead of silently substituting an empty object
- Untrusted-tool-result delimiter wrapping with delimiter neutralization, for external content entering the turn
- Absorption cursor so a per-turn summary is folded incrementally instead of rebuilt from the whole thread
- Timeout-bounded read for any file loaded into a prompt, so a stalled mount cannot wedge a turn
- One scoped threat-pattern library applied at several boundaries, with an invisible-unicode and homograph check
- A deterministic tool-result prune with its own cheap trigger, separate from the compaction decision

### `HM03-agent-providers-credentials-usage`

scope `agent/ provider+credential+usage family (shared)` — 267 files in scope, 37 cited read (13.9%), self-reported 37, verifier-missed 6.

**unread_areas (reader, verbatim):**

- agent/models_dev.py (777 lines) — models.dev catalog cache; skipped as high-confidence anti-pattern territory given the no-model-names directive, but not read in full
- agent/model_metadata.py — read function index + top ~900 lines (connect-timeout/blackhole caching); the full 2203 lines' endpoint-probing and context-length-extraction internals (~lines 600-2203) not read in detail
- agent/rate_limit_credits.py, agent/credits_tracker.py, agent/billing_links.py, agent/billing_usage.py, agent/billing_view.py — not read; likely Hermes-subscription-specific (Nous Portal credits/billing UI), low-relevance given Halbert has no subscription surface, but not opened to confirm
- agent/moa_trace.py, agent/relay_tools.py — not read (moa_trace is MoA-specific, already anti-patterned; relay_tools is NeMo-Relay-specific like relay_llm.py/relay_runtime.py which were only partially read)
- agent/chat_completion_helpers.py — read only the function/class name index (100+ defs) plus 2 function bodies out of 3337 lines; try_activate_fallback (~1824-1937), the full streaming call classes (_BedrockStream/_StreamingCall, ~2274-3337) and iteration-summary logic not read in detail
- agent/chat_completion_nonstream.py, agent/chat_completion_helpers_relay.py, agent/stream_delivery.py — not read at all
- agent/client_lifecycle.py — read only the function-name index and 2 function bodies out of 970 lines; credential-swap and per-provider client-rebuild logic (~538-970) not read
- agent/relay_llm.py, agent/relay_runtime.py, agent/relay_tools.py, agent/lazy_forward.py (relay family) — read only enough to confirm NeMo Relay (managed-compute telemetry integration) is largely not applicable; not read exhaustively
- agent/account_usage.py — read only first ~70 lines (dataclasses); per-provider account-limits httpx-fetching logic not read
- agent/usage_pricing.py — read only first ~140 lines (cost-label formatting + dataclasses); the per-provider pricing table and cost-computation logic (~140-632) not read in detail

**verifier-added mechanisms the reader missed (titles):**

- Give up before the next attempt: a consecutive-stale streak gate (Halbert's circuit breaker is write-only)
- Learn the real context window from the provider's error text, and never confuse 'prompt too long' with 'max_tokens too large'
- Stop actually stops the wire: shutdown() the socket from a foreign thread, never close()
- Halbert defect surfaced by the origin's cooldown sizing: a Retry-After longer than 60s is silently clamped
- A credential can be a reference resolved at use time, not a value stored in the config
- The unhealthy mark is written without its timestamp, so a failing backend returns to rotation early

### `HM04-agent-learning-verification-review`

scope `agent/ learning+verify+curator family (shared)` — 267 files in scope, 25 cited read (9.4%), self-reported 26, verifier-missed 7.

**unread_areas (reader, verbatim):**

- agent/curator.py lines 120-1084 (apply_automatic_transitions state machine, LLM consolidation fork wiring, report generation)
- agent/background_review.py lines 120-1191 (bulk of the file: conversation replay, memory-write metadata, tool whitelist enforcement details)
- agent/insights.py lines 90-578 (bulk of InsightsEngine.generate() and format_terminal)
- agent/trace_upload.py lines 120-246 (the actual upload call, _do_upload, dataset creation)
- agent/verify/runner.py lines 90-255 (phase execution loop, readiness-poll implementation, teardown/signal handling)
- agent/verify/recipes.py lines 60-296 (per-framework detection rules)
- agent/learning_graph_render.py lines 60-430 (bulk of the terminal timeline renderer)
- agent/pet/constants.py, manifest.py, render.py, store.py, generate/ (entire pet pipeline, ~2200 of 2252 lines unread) — deprioritized once identified as an anti-pattern for Halbert's tone
- agent/monitoring/cron_health.py, emitter.py, events.py, gateway_health.py, gateway_health_export.py, otlp_exporter.py (~1500 of 1554 monitoring lines unread) — deprioritized after redaction.py/policy.py suggested fleet-telemetry shape, not verified line-by-line
- Most tests/agent/test_curator*.py, test_learning*.py, test_review*.py, test_verification*.py, test_pet*.py, test_trace_upload.py, test_insights.py, test_reactions.py, test_session_activity.py, plus tests/verify/, tests/hermes_cli/test_curator_*.py, tests/run_agent/test_background_review*.py — grepped for test names only, assertion bodies not read
- agent/curator_backup.py lines 120-358 (manifest reading, list_backups, prune-to-keep-count implementation) — only the docstring, config, and rollback() function were read in full

**verifier-added mechanisms the reader missed (titles):**

- The stop-gate chain itself: an ordered, fail-open set of turn-end gates that preserve and SHOW the model's attempted answer
- Refuse to run a check that would destroy the live state it is checking — fail open on absence, fail CLOSED on uncertainty
- Halbert's run_command leaks orphan processes on timeout: no process group, and only the direct child is killed
- Never punish state you have not observed: three rules that stop an autonomous time-based sweep from mutating on first sight
- Verify an LLM's self-report against the observed diff: the model's summary is a claim, the before/after diff and the tool-call audit are the evidence
- A background fork sharing the live session id writes its own harness turn into the real conversation — which the next live turn re-reads as a standing instruction
- Dry-run as a first-class preview mode whose output IS the deliverable, feeding a human approve step

### `HM05-delegation-subagents-kanban`

scope `agent/ + tools/ delegation & kanban family (shared)` — 1008 files in scope, 23 cited read (2.3%), self-reported 27, verifier-missed 7.

**unread_areas (reader, verbatim):**

- hermes_cli/kanban_db.py, kanban_db_connect.py, kanban_db_dispatch.py, kanban_db_notify.py, kanban_db_workspace.py, kanban_db_repair.py (DB schema/locking layer — only signatures/test filenames read, not full SQL/WAL discipline)
- gateway/kanban_watchers_dispatcher.py and kanban_watchers_common.py (singleton lock acquisition and full dispatcher tick body — signatures only)
- tools/kanban_tools_schemas.py (full JSON tool-schema definitions — only referenced)
- hermes_cli/kanban_pr_acceptance.py and kanban_pr_acceptance_store.py bodies beyond the top docstring
- hermes_cli/kanban_worker* spawn/lifecycle-hook files (inferred from test filenames only)
- plugins/kanban/dashboard/plugin_api.py and compiled dist/index.js
- docs/kanban/multi-gateway.md and docs/hermes-kanban-v1-spec.pdf (not opened)
- tools/delegate_tool_dispatch.py's _run_children_parallel/_dispatch_background full body (async unit partitioning read at signature level only)
- tools/async_delegation.py lines beyond ~520 (executor sizing, session ownership matching, runner injection contract)
- hermes_cli/kanban_swarm.py body beyond the module docstring (actual planning/verifier/synthesizer state machine)

**verifier-added mechanisms the reader missed (titles):**

- Liveness is proven by PROGRESS, not by a stopwatch: a shared-thread staleness monitor replaces a wall-clock child timeout
- Abandonment accounting: an unfinished child gets an explicit terminal entry, a cooperative stop signal and a deferred close — the parent never joins a wedged worker
- Offloading background work to a thread must run in an EMPTY Context — asyncio.to_thread copies the caller's security ContextVars
- A positive denial marker that survives exec — absence of an identity key is never a grant — behind one predicate every gate uses
- A read ledger, so the parent is told when work it delegated wrote files it had already read
- The steer/completion linearization boundary: a steer that loses the race is recorded, never silently swallowed
- The 0-API-call timeout dump: the one blind failure gets a structured artifact, and only that one

### `HM06-tools-approval-guards`

scope `tools/ approval+guard family (shared tools/ with HM07-HM10)` — 281 files in scope, 29 cited read (10.3%), self-reported 30, verifier-missed 5.

**unread_areas (reader, verbatim):**

- approval.py lines ~1-530 and ~850-1168 (session-state accessors, _run_approval_gate/check_all_command_guards/check_execute_code_guard bodies)
- approval_context.py body beyond function signatures
- approval_floors.py beyond the user-deny-glob section
- approval_gateway_wait.py and approval_human_wait.py beyond their first ~50 lines each
- credential_files.py beyond register_credential_file()
- schema_sanitizer.py and arg_coercion.py beyond their first ~90-100 lines
- osv_check.py beyond the caching setup
- write_approval.py beyond config resolution
- clarify_tool.py and clarify_gateway.py beyond their public API surface
- plugin_guard.py beyond ~70 lines
- website_policy.py and tirith_security.py beyond their setup sections
- hook_output_spill.py beyond config resolution
- every tests/tools/test_*.py body for this unit (only names grepped for two files, others only enumerated)
- hermes_cli/approval_mode.py, hermes_cli/write_approval_commands.py, hermes_cli/subcommands/approvals.py, and gateway-side platform approval-button adapters — identified but left unread as CLI/gateway territory outside this unit's tools/ file list
- full audit of Halbert's dashboard staged-command resolution (C17) and persona/permission session-context propagation (C18) — those two candidates rest on a targeted-not-exhaustive check

**verifier-added mechanisms the reader missed (titles):**

- Fail-CLOSED when the command cannot be parsed: a parser-limit / malformed-executable block, plus a saved-payload recovery path
- Unattended-context approval policy: an origin with no human present never parks on a prompt, and 'silence is not consent' is written into the refusal
- A user-authored deny list that outranks every bypass, matched against the same deobfuscated command variants as the detector
- Trust-tier x scan-verdict install policy matrix for skills, with a distinct row for agent-authored skills
- One combined approval request when two independent detectors both fire, so a replayed force cannot bypass the check that was never shown

### `HM07-tools-terminal-files-checkpoints`

scope `tools/ terminal+file+checkpoint family (shared)` — 281 files in scope, 30 cited read (10.7%), self-reported 33, verifier-missed 6.

**unread_areas (reader, verbatim):**

- computer_use/ backend directory (backend.py, cua_backend*.py, doctor.py, permissions.py, schema.py, vision_routing.py) — 12 files, none read; this is mouse/keyboard/screen automation (CUA-style computer use) which did not clearly map to any Halbert founder constraint or existing subsystem, so it was deprioritized in favor of terminal/process/checkpoint/file-edit material more directly named in the FOCUS list
- computer_use_tool.py itself only skimmed (29 lines, not read in full) and its ~15 dedicated test files (tests/tools/test_computer_use*.py) not read
- drive_preview_tool.py, annotate_preview_tool.py, read_preview_tool.py, close_preview_tool.py, apply_layout_tool.py, focus_pane_tool.py, read_window_tool.py — the desktop-GUI preview-pane driving/annotation/window-layout tools were not read beyond open_preview_tool.py and desktop_ui.py's shared plumbing; these assume a code-preview/dev-server IDE-like desktop surface that may or may not map to Halbert's dashboard design intent
- session_search_tool.py (679 lines) was skimmed only for its header (FTS5/BM25 session recall, cron demotion) — deliberately not deep-dived since it substantively overlaps the memory/continuity workstream's existing OSS-review coverage of Hermes's recall design, not this unit's terminal/files/checkpoints FOCUS
- project_tools.py workspace-switching internals beyond the first 60 lines — Hermes's multi-project-workspace concept was judged low-relevance given Halbert's single-host/capability-scoped design and not pursued further
- file_operations_search.py (938 lines, the search_files/grep-equivalent backend) and file_operations_common.py (279 lines) were not read at all
- terminal_tool_backends.py (325 lines, per-backend env builders/requirement checkers) and terminal_tool_lifecycle.py (328 lines, sandbox reaper/teardown) were not read — largely subsumed by the C1 anti-pattern (multi-backend sandbox machinery judged not worth lifting for single-host Halbert)
- terminal_tool_background.py (233 lines, the actual background=true spawn path into ProcessRegistry) was not read directly; its behavior was inferred from process_registry.py and terminal_tool_guards.py's guidance text pointing at it
- hermes_cli/checkpoints.py, hermes_cli/cli_terminal_mixin.py, hermes_cli/terminal_notify.py, hermes_cli/terminal_breadcrumbs.py, agent/terminal_env_registry.py, agent/terminal_env_provider.py, gateway/hosted_room_policy_checkpoint.py — CLI/gateway-side wiring around these tools was not read; this unit focused on the tools/ implementations themselves per the assigned DIRECTORIES list
- the ~40 tests/tools/test_terminal_*.py and test_process_registry*.py files were not individually read beyond checkpoint_manager's test file; their names were scanned for coverage signal (pty fallback, degraded mode, signal exit, cwd echo, self-repo guard, sudo, requirements) but invariants were not verified test-by-test

**verifier-added mechanisms the reader missed (titles):**

- Yield-to-background: a mid-turn user message hands off the live foreground process instead of killing it
- Non-atomic write in the one agent-facing file-write tool, plus no post-write verification
- Recursive search/walk excludes macOS TCC-protected home directories under a broad root
- Command normalization + per-command-start scanning before any safety pattern match
- Unicode-equivalent (NFC/NFD) filename resolution and similar-file suggestion on a failed read
- Self-repo guard: refuse git operations that would rewrite the checkout backing the running process

### `HM08-tools-browser-web-media-voice`

scope `tools/ browser+web+media+voice family (shared)` — 281 files in scope, 20 cited read (7.1%), self-reported 33, verifier-missed 5.

**unread_areas (reader, verbatim):**

- tools/browser_camofox.py, browser_camofox_state.py, browser_cdp_tool.py, browser_extension_router.py, browser_lightpanda.py, browser_tool_install.py, browser_tool_lifecycle.py, browser_tool_session.py, browser_tool_cloud.py, browser_tool_lightpanda_fallback.py, browser_use_cli.py, browser_dialog_tool.py, browser_tool_cdp.py, browser_supervisor_frames.py (only skimmed via imports), browser_tool.py (1365-line main facade, only its plugin-compat tail seen)
- tools/vision_tools.py (Hermes, 1060 lines — only parts referenced from browser_tool_vision.py read) and vision_tools_image_prep.py (249 lines, unread)
- tools/image_generation_catalog.py, image_generation_tool.py, image_source.py, video_generation_tool.py, xai_video_tools.py — skipped as out-of-scope for a single-user host-steward assistant with no image/video-gen plans
- tools/x_search_tool.py — skipped, no social-media integration in Halbert
- tools/transcription_audio.py, transcription_common.py, transcription_tools.py — only read via imports/references
- tools/voice_mode.py (1572 lines) and voice_mode_transcript.py — not read; could not separate already-merged wave-1 mechanisms from genuinely new ones without reading it
- tools/tts_streaming.py, tts_text_normalize.py, tts_tool.py, tts_tool_delivery.py, tts_tool_lifecycle.py, tts_tool_local.py, tts_tool_openai.py, tts_tool_plugins.py, tts_tool_providers.py, tts_tool_speaker.py, tts_command_provider.py — none read
- tools/wakewords/ and tools/neutts_samples/ — binary/asset directories, not inspected
- Most of tests/tools/test_browser_*.py (~45 files) and several test_web_*.py/test_tts_*.py/test_transcription_*.py files beyond the ones read

**verifier-added mechanisms the reader missed (titles):**

- Idle-unload watcher for a resident local model (release hundreds of MB after N idle seconds, reload on next use)
- The read-back leg of truncate-and-spill: Halbert's read_file has no offset/limit and refuses >1MB, so its own spill pointer is a dead instruction
- Coordinate-mapping disclosure when a screenshot is downscaled or cropped before the vision model sees it
- Spoken-text normalization beyond markdown stripping: unterminated <think> blocks, emoji/variation selectors, symbol and temperature expansion
- Cross-process microphone lease: one exclusive owner, typed refusal, surface eligibility separate from ownership

### `HM09-tools-mcp`

scope `tools/ mcp_* family (shared)` — 281 files in scope, 17 cited read (6.0%), self-reported 27, verifier-missed 13.

**unread_areas (reader, verbatim):**

- tools/mcp_oauth.py (1012 lines, the largest file in the unit) — only its two satellite modules (mcp_oauth_manager.py, mcp_oauth_provider.py) were skimmed at the header level; the core legacy OAuth flow (build_oauth_auth, PKCE, dynamic client registration, token storage/HermesTokenStorage) was not read in depth
- hermes_cli/mcp_catalog.py (677 lines) — the 'PR-reviewed manifest catalog (presence = approval)' model referenced in the prior synthesis was not independently re-verified in this pass
- hermes_cli/mcp_picker.py (242 lines) — not opened at all
- hermes_cli/mcp_config.py (903 lines) — only grepped for the whitespace-warning test target; the bulk of config load/merge/validate/save logic (including the dual-gate save-time call into mcp_security.py) was not read
- tools/mcp_tool_transport.py (458 lines) — read only headers and the content-type preflight section (~40 lines); the OAuth/client-cert/identity-header wiring at transport bring-up, and SSE-specific handling, were not read
- tools/mcp_tool_loop.py (301 lines) — read only headers; the cross-process discovery lock's actual file-locking implementation (_try_acquire_mcp_discovery_lock) and the loop-scheduling/exception-handler code were not read
- tools/mcp_tool_lifecycle.py (277 lines) — read only headers; the orphan-pid sweep and graceful-shutdown/drain implementation were not read in depth
- tools/mcp_tool_registration.py (327 lines) — read only via targeted grep for trust/readOnlyHint; the include/exclude filtering, name-collision resolution, and utility-tool-selection logic were not read
- tools/mcp_tool_agent.py (252 lines) — not read beyond the header; live-agent tool-list refresh/prefix-preservation mechanics unexplored
- tools/mcp_tool_server_run.py (419 lines) — not read beyond the header; the full connect→serve→reconnect/park/recycle state machine (the actual run() loop referenced throughout mcp_tool_health.py and mcp_tool_handlers.py) was not read directly
- tools/mcp_tool_common.py (156 lines) — not read beyond the header
- mcp_serve.py root (728 lines) — read ~150 lines (structure + EventBridge); the full _ToolHandlers class (lines 458-692, the actual 9+ tool implementations) and create_mcp_server/run_mcp_server were not read
- tests/tools/test_mcp*.py (~60 files) — only one test file (whitespace warning) was read in full; the other ~59 were only enumerated by filename, not opened, so several named invariants (test_mcp_rapid_drop_budget, test_mcp_reconnect_retry_reset, test_mcp_dynamic_discovery, test_mcp_stability, etc.) were inferred from source comments/docstrings rather than verified against their pinning tests directly
- apps/desktop/src/lib/mcp-*.ts and apps/desktop/src/store/mcp-*.ts (TypeScript desktop-app MCP UI/OAuth/health/cost files) — out of the stated Python-file FOCUS list, not opened
- website/docs/**/mcp*.md and website/docs/reference/mcp-config-reference.md — documentation, not opened; per the assignment's instruction to prefer code over docs, deliberately skipped

**verifier-added mechanisms the reader missed (titles):**

- Every stdio MCP subprocess inherits Halbert's ENTIRE environment; Hermes hands it an 8-key allowlist plus the server's own declared env
- Server-supplied MCP tool descriptions reach Halbert's prompt unscanned and unsanitized — no injection scan, no invisible-Unicode-tag stripping
- No size cap and no binary spill on MCP tool results — Halbert JSON-dumps whatever a server returns straight into agent context
- Orphaned stdio MCP subprocesses survive an ungraceful Halbert death, and the graceful path kills only the direct child, not its process group
- MCP server config entries get no security screening at all — Hermes screens the same shapes at BOTH save time and spawn time
- Halbert spawns every configured stdio MCP server at agent init just to read tools/list; Hermes registers them from a fingerprinted on-disk schema cache and connects lazily on first call
- Halbert truncates a large tool list to an arbitrary first-64; Hermes has a per-server include/exclude filter picked from a live probe at add time
- A remote server's declared readOnlyHint is snapshotted at discovery and gates write-capable calls on untrusted servers — but Hermes lets the server LOWER its own gate; Halbert should invert it
- Halbert's HTTP MCP transport follows redirects, so the operator-configured URL is not the pinned destination for the JSON-RPC body
- Halbert drops every server notification, including notifications/tools/list_changed, so a server's tool set can only refresh when the config file changes
- Idle and max-lifetime recycling of stdio MCP children
- MCP failure text is written FOR the model — a circuit breaker whose message tells it not to retry, and named stdio-death messages that distinguish 'never reached the server' from a timeout
- MCP sampling: Hermes accepts server-initiated LLM calls behind a rate/model/token/tool-round gate; Halbert refuses them outright and should keep it that way

### `HM10-tools-skills-second-pass`

scope `tools/ skills_* family (shared)` — 281 files in scope, 28 cited read (10.0%), self-reported 34, verifier-missed 8.

**unread_areas (reader, verbatim):**

- hermes_cli/skills_hub.py (1496 lines, the CLI entry point for `hermes skills` hub commands) — only referenced indirectly via hermes_cli/skills_config.py; not read at all.
- tools/skills_hub_sources.py — class list only (WellKnownSkillSource, UrlSource, LobeHubSource, BrowseShSource); bodies not read.
- tools/skills_sync_bundled_ops.py, tools/skills_sync_client_org.py, tools/skills_sync_client_wire.py — not read beyond grep/imports; the org-mirror propose/pull flow and the wire protocol details (object format, merge algorithm specifics) are unverified beyond the docstring level.
- tools/skill_manager_tool.py — read the imports, guard wiring, and _security_scan_skill/_run_write_gate sections (~150 of 906 lines); the individual _create_skill/_edit_skill/_patch_skill/_delete_skill/skill_manage bodies were not read in full.
- agent/skill_utils.py — read ~150 of 786 lines (org-mirror helpers, project-trust functions); the frontmatter/config-var extraction and discover_all_skill_config_vars sections (lines ~600-786) were not read.
- tools/skill_linter.py — read only the constants/docstring (~60 of 219 lines); the actual LintFinding-yielding checks were not read line-by-line.
- tools/skills_hub_official.py, tools/skills_hub_skillssh.py — read only the module docstrings and class opening; the HermesIndexSource class body and the skills.sh sitemap-walking logic were not read.
- tools/skills_tool.py — read ~90 of 691 lines (scan signature, path-error helper, security-warning logger); skill_view's full body and _find_all_skills were not read.
- agent/skill_bundles.py, agent/skill_commands.py — read function signatures and a few sections; the message-scaffolding builders (_build_skill_message, _scaffold_header) and bundle invocation-message assembly were not read in full.
- tests/tools/test_skill_*.py and tests/hermes_cli/test_skills_*.py — none of the test files were opened; invariants were inferred from docstrings and inline comments in the source, not confirmed against test assertions.

**verifier-added mechanisms the reader missed (titles):**

- The write-approval gate module itself: file-backed pending store, three-state decision, and stage-never-silently-refuse
- Catalog-time availability gating with fallback_for inverse semantics, and the offer-time-only asymmetry
- Per-hop redirect re-validation on every fetch of untrusted remote content
- Quarantine-then-promote install order with a content-hashed install receipt
- Skill-declared configuration variables with an operator settings surface and defaults resolution
- Skill prerequisites that are secrets are captured out-of-band, and a surface that cannot prompt securely refuses instead of asking in-channel
- Write origin as ambient context: one ContextVar separates autonomous writes from user-directed ones, and every guard reads it
- Directory-signature + TTL scan cache calibrated to what a directory mtime cannot see

### `HM11-gateway-core`

scope `gateway/ core (shared with HM12)` — 145 files in scope, 38 cited read (26.2%), self-reported 39, verifier-missed 6.

**unread_areas (reader, verbatim):**

- run_turn.py, run_turn_runner.py (the two largest files in the unit, 222KB+98KB) -- turn execution core; likely overlaps heavily with the already-lifted interrupt algebra and state-machine work but was not read line-by-line given the file-count budget
- run_inbound.py, run_busy.py -- explicitly out of scope per the assignment (already covered by the interrupt algebra), skipped entirely
- run_startup.py, run_adapters.py, run_notifications.py, run_shutdown.py, run_config_loaders.py, run_watchers.py, run_topics.py, run_goals.py, run_agent_cache.py, run_common.py -- the remaining run_*.py phase files; only run.py's header/imports were skimmed, not these
- session.py, session_context.py, session_db_recovery.py, session_lifecycle.py, session_persistence.py, session_state.py, session_transcript.py -- read only session_stall.py fully and session_recovery.py partially; the rest of the session_*.py mixin family is unread
- slash_commands.py, slash_commands_session.py, slash_commands_model.py, slash_commands_status.py, slash_commands_goals.py, slash_access.py -- the entire slash-command surface was not read at all; likely contains concrete, liftable command-dispatch and access-tier patterns for Halbert's terminal-slash-channel work
- stream_consumer.py, stream_consumer_fallback.py, stream_consumer_fences.py, stream_consumer_think.py, stream_consumer_transport.py, stream_dispatch.py, stream_events.py -- the whole stream_*.py family was not read
- config.py, config_env.py, config_loader.py -- the gateway's raw-YAML config loading was not read
- profile_routing.py, whatsapp_identity.py -- skimmed by name/grep only, not read; both are multiplex/multi-platform specific and judged low-relevance
- authz_mixin.py, pairing.py, control_socket.py, session_recovery.py, media_fetch.py -- read partially, not to their full extent
- turn_lease.py -- explicitly named as partially out of scope (already lifted via the interrupt algebra); not independently re-verified against the current file

**verifier-added mechanisms the reader missed (titles):**

- Bare SQLITE_CORRUPT must NOT authorize the FTS fail-open path — Halbert's classifier diverges from the Hermes one it says it mirrors
- Distinct exit-code vocabulary (restart-me vs stop-restarting-me) plus supervisor detection, without which a hard-exit watchdog is just an outage
- No single-instance lock scoped to the data dir — the Tauri shell deliberately starts a SECOND backend on another port against the same conversation store
- Close orphaned code fences before rendering a truncated or interrupted response
- A store handle that has been replaced or quarantined must stop taking writes and divert its backlog, not retry and not rebuild
- Per-session state grouped by the lifecycle scope at which it is cleared, with clear() derived from the dataclass defaults

### `HM12-gateway-rooms-platforms-hooks`

scope `gateway/ rooms+platforms+hooks (shared with HM11)` — 145 files in scope, 23 cited read (15.9%), self-reported 27, verifier-missed 4.

**unread_areas (reader, verbatim):**

- gateway/relay/adapter.py (2174 lines) — the actual RelayAdapter implementation is unread; only its Protocol contract (transport.py) and sibling small modules were read
- gateway/relay/ws_transport.py (817 lines) — production WebSocket transport unread
- gateway/relay/media.py (159 lines) — unread
- gateway/platforms/api_server.py (3952 lines) — only module docstring and imports read; the /v1/chat/completions, /v1/responses, session, and job handlers are unread
- gateway/platforms/api_server_openai_routes.py (1014 lines) and api_server_runs.py (849 lines) and api_server_room_dispatch.py (104 lines) — unread
- gateway/platforms/signal.py (1000 lines) and signal_format.py (96 lines) — unread beyond signal_rate_limit.py
- gateway/platforms/whatsapp_cloud.py (1012 lines) and whatsapp_common.py (330 lines) — unread beyond the mixin-pattern description in ADDING_A_PLATFORM.md
- gateway/hosted_room_discussion.py (792), hosted_room_driver.py (870), hosted_room_peer.py (544), hosted_room_links.py (151), hosted_rooms.py body beyond header/constants — read only enough to confirm anti-pattern classification, not full internals
- gateway/browser_control_artifacts.py (333 lines) — unread
- gateway/platforms/msgraph_webhook.py — only signatures read, not bodies
- gateway/platforms/qqbot/, weixin.py, yuanbao*.py — outside the assigned unit's file list, not examined
- tests/gateway/relay/*, tests/gateway/test_hosted_room_*.py, tests/gateway/test_bluebubbles.py, tests/gateway/test_signal*.py — no test files opened; invariants inferred from source docstrings only

**verifier-added mechanisms the reader missed (titles):**

- Turn-owned process ownership + baseline-diff reap of processes an abandoned turn left running, epoch-gated
- Byte-size and MIME caps enforced BEFORE any read or write, and server-minted ids instead of client-supplied names
- A single shutdown budget apportioned across teardown steps, with every await individually bounded
- Error text goes through the egress redaction seam too -- and the redaction lives in the envelope builder, not at each call site

### `HM13-state-root-files`

scope `repo-root *.py (hermes_state*, bootstrap, watchdog...)` — 39 files in scope, 20 cited read (51.3%), self-reported 20, verifier-missed 7.

**unread_areas (reader, verbatim):**

- hermes_state_schema.py (1119 lines) — only referenced via import; migration-ladder internals not read in detail (the PRAGMA user_version ladder pattern is already noted lifted elsewhere per the master plan).
- hermes_state_telegram.py (359 lines) — not opened at all; platform-specific, judged low-value for a single-user local assistant.
- hermes_state_gateway.py — only signatures grepped plus a partial read of heartbeats/handoff; bulk of multi-backend routing not read (see anti-pattern note).
- hermes_state_registry.py and hermes_state_holders.py — only signatures grepped; the shared-writer-connection acquire/release/generation-teardown-barrier logic and foreign-holder-process detection deserve a follow-up read given overlap with C6/C7.
- model_tools.py (906 lines) — only signatures grepped; primarily tool-dispatch/execution plumbing that likely belongs to an execute_code/tool-dispatch unit.
- run_agent.py (1544 lines), batch_runner.py (998 lines), cli.py (4663 lines) — skimmed only (wc -l + adjacent test listing) per instruction; batch_runner.py's RL-trajectory purpose is explicitly out of this unit's focus.
- hermes_state_common.py's flock/lock-holder code (~860-1085) — read only at docstring level; likely overlaps the flock pattern already the reference for Haloysius engine stores.
- Individual test bodies under tests/hermes_state/*.py and tests/run_agent/*.py — file names enumerated but very few bodies opened; a follow-up reading test_cross_process_turn_lease.py, test_bounded_recent_sessions.py, test_state_db_corrupt_quarantine.py in full would sharpen C6/C7/C13/C14.

**verifier-added mechanisms the reader missed (titles):**

- PRAGMA journal_mode=WAL RETURNS the resulting mode — a silent refusal leaves the store in rollback-journal mode and nothing notices
- The linked SQLite has the WAL-reset bug — Hermes gates WAL on the runtime version; Halbert enables it unconditionally on a runtime the gate would refuse
- Refcounted shared-store registry with generation-aware retirement — the real lift behind the read-pool candidate
- SQLite error taxonomy: busy-vs-damaged-vs-disk-full, with the ordering trap that 'database disk image is malformed' contains the word 'disk'
- close() cancels every POSIX advisory lock on a file — never open/read/close a live SQLite database, pread from a cached fd instead
- Title sanitisation against invisible/bidi/object-replacement code points and lone surrogates — Halbert fences brackets but not glyphs
- Zeroed-database detection and quarantine under a cross-process lock, before any connection is opened

### `HM14-cli-ops-lifecycle`

scope `hermes_cli/ ops+lifecycle (shared with HM15)` — 460 files in scope, 33 cited read (7.2%), self-reported 33, verifier-missed 5.

**unread_areas (reader, verbatim):**

- update_cmd.py, update_cmd_common.py, update_cmd_config.py, update_cmd_deps.py, update_cmd_fleet.py, update_cmd_git.py, update_cmd_maint.py, update_cmd_stash.py, update_cmd_windows.py, update_cmd_zip.py, update_restart_recovery.py — the ~7500-line core self-update implementation; only the small standalone primitives (update_lock.py, update_receipt.py, update_contract.py, update_abort_recovery.py partial) were read, deliberately deprioritized until Halbert has a self-update path to design against
- worktree_cmd.py, worktree_gc.py, worktree_ops.py (862 lines) — read only module docstrings; not cross-checked against CoDRAG's own worktree usage in the Halbert ecosystem, which the task context flags as relevant
- session_export.py, session_export_md.py, session_export_html.py (804 lines) — read only docstrings
- session_recovery.py (1141 lines) — read only the module docstring; the actual canonical-table-copy/rebuild implementation was not read line-by-line
- foreign_sessions.py, foreign_sessions_browser.py — importing history from Claude Code/Codex CLI sessions; not evaluated for relevance
- doctor_config.py, doctor_connectivity.py, doctor_live.py, doctor_tools.py — read only module docstrings/imports
- uninstall.py, gui_uninstall.py, logs.py, dump.py, debug.py — read only docstrings; not assessed for reusable patterns
- sqlite_safe_read.py — read only the module docstring (lock-safe raw-file-read tracking for live sqlite3 connections); flagged as promising but not verified against any place Halbert reads its own live SQLite files raw
- active_sessions.py beyond its first ~70 lines — the actual lease/liveness-registry file format and staleness logic not read
- backup.py beyond a def-signature grep — the full ~1650-line implementation only sampled
- tests/hermes_cli/test_doctor*.py and test_update*.py — not read at all; invariants pinned by these tests not extracted
- process_identity.py's Windows job-object self-attach (Layer 3) — read the intro but not the Windows-specific implementation, not relevant to Halbert's macOS-first target anyway

**verifier-added mechanisms the reader missed (titles):**

- A bare open() on a live SQLite file cancels that process's advisory locks — and Halbert raw-copies a live chroma.sqlite3 today
- Store-health rows a user can actually see: an FTS write-health probe and a WAL-size warning with a checkpoint fix
- macOS TCC grants are keyed to the interpreter binary too, not only the .app bundle — and Halbert's venv python is a symlink
- Undo that survives the process: a durable checkpoint store with a status/prune/clear operator surface
- A destructive confirmation must bind to the exact set that was previewed, not to a re-scan at execution time

### `HM15-cli-model-config-ux`

scope `hermes_cli/ model+config UX (shared with HM14)` — 460 files in scope, 38 cited read (8.3%), self-reported 34, verifier-missed 8.

**unread_areas (reader, verbatim):**

- config.py (176KB) and config_defaults.py (185KB) — only def/class names grepped plus a few targeted sections; most validator bodies and the ~2000 default-config entries unread.
- models.py (114KB, the module the *_pricing/*_local/*_validate/*_reasoning_caps files were split from) — not read directly.
- model_switch.py (74KB) and model_switch_providers.py (60KB) — the interactive picker flow implementation not read.
- ~10 of 16 cli_*_mixin.py files (cli_model_switch_mixin, cli_session_mixin 66KB, cli_tui_mixin 110KB, cli_commands_mixin 143KB, cli_billing_mixin, cli_chat_turn_mixin, cli_modal_mixin, cli_stream_mixin, cli_terminal_mixin, cli_info_mixin, cli_agent_setup_mixin) — ~600KB combined, not opened.
- main.py and the main_*.py family (desktop/dashboard/provider_setup/tui_launch/web_build/platform_setup/install_repair/agent_cmds) — not opened.
- setup.py and the setup_*.py onboarding-wizard family (quick/terminal/tts/platforms/migration/summary/whatsapp_cloud/hidden_env) — explicitly named in FOCUS but essentially unexplored.
- model_setup_flows.py (53KB) and azure/bedrock/common/custom siblings — per-provider auth setup flows unexplored.
- auth.py and the auth_*.py family (oauth device-code, external, minimax, qwen, xai, zai-kimi, spotify, auth_model_picker.py) — credential-acquisition UX unexplored.
- tools_config.py (63KB), tools_config_cua.py, tools_config_mcp.py, tools_config_post_setup.py, tools_config_providers.py (53KB) — the toolset-configuration UX beyond the small scope/validation files unexplored.
- skin_engine.py (37KB) and skin_cmd.py — CLI theming system unexplored beyond a passing reference from journey.py.
- curses_ui.py (33KB), banner.py (44KB), most of pt_input_extras.py — terminal-rendering internals mostly unexplored.
- pty_bridge.py, pty_session.py, win_pty_bridge.py, windows_ssh_runtime.py — cross-platform PTY bridging unexplored; directly relevant to Halbert's watched-terminal design and worth a follow-up pass.
- dashboard_procs.py (31KB), dashboard_register.py — listed in-scope but not opened.
- web_server.py (92KB) and ~14 web_server_*.py siblings (chat/config/cron/dashboard/files/gateway/idle_exit/lifecycle/mcp/memory/messaging/oauth/profiles/sessions) — marked skim-only in the task but not opened at all; likely the largest source of unexplored dashboard-equivalent UX (esp. web_server_profiles.py, web_server_config.py).
- plugins_cmd.py (93KB) and the plugin_*/plugins_*.py family (capabilities/compat/dev/index/packs/discovery/dispatch/ledger/loader/manifest/state) — not opened; no cross-check against any Halbert plugin-equivalent surface.
- goals.py's full body beyond the def/docstring listing — judge-prompt construction, subgoal rendering, SessionDB persistence details not read line-by-line.
- profile_cmd.py, profile_describer.py — not opened (only profiles.py and profile_distribution.py heads read).

**verifier-added mechanisms the reader missed (titles):**

- Mid-session model-switch warning: the next turn will preflight-compress because the new window is smaller
- Route-keyed, fail-closed invalidation of a cached context-length verdict when the endpoint changes
- Credential headers are stripped when a model-endpoint request redirects cross-origin
- `doctor`: a structured self-diagnostic with opt-in repair, config-drift detection and parallel connectivity probes
- LM Studio loaded-state and real runtime context come from /api/v1/models loaded_instances, not the OpenAI-compat /v1/models list
- Configured provider headers and credentials apply only to the origin they were configured for
- Never materialize a missing mount's target: symlink-aware home initialization that fails loudly instead of creating a stub
- Provider credentials are scrubbed from the environment of any shell command the agent or user runs

### `HM16-cron-second-pass`

scope `cron/` — 22 files in scope, 17 cited read (77.3%), self-reported 35, verifier-missed 9.

**unread_areas (reader, verbatim):**

- cron/scheduler_delivery.py: only ~250 of 1714 lines read; per-platform delivery formatting/routing (Telegram/Discord/email/bot-chat/relay-fronted) not read
- hermes_cli/cron.py: only the ~50-line doctor section of 772 lines read; create/edit/list/status/runs subcommands and the argument parser not read
- tools/cronjob_tools.py: ~150 of 1051 lines read; full cronjob() tool schema, _action_list/_action_remove bodies, check_cronjob_requirements not read
- cron/scheduler_provider.py: only signatures/docstrings read; InProcessCronScheduler's tick-loop body (lines 361-555) not read line-by-line
- cron/scheduler_script.py: script-argv building, Windows bootstrap, claim-heartbeat-thread sections (296-465) only lightly sampled
- tools/cronjob_job_args.py: ~120 of 415 lines read; _format_job, _apply_continuity, and update-path validators not read
- docs/chronos-managed-cron-contract.md: only first ~60 of 222 lines read
- tests/cron/ (66 files) and tests/tools|hermes_cli/test_cron*.py: filenames enumerated only, individual test bodies not read — a follow-up pass on test_cron_incidents.py, test_cron_failure_alert_remediation_hint.py, test_cron_relay_delivery_guards.py, test_cronjob_schema.py, test_cron_run_stale_claim_reap_86721.py, test_cron_provider_pin.py would likely surface more edge-case invariants
- cron/AGENTS.md's Kanban section read but deliberately out of unit scope (separate feature)
- C14's halbert_state was set from the files actually read, not a repo-wide grep of scheduler/engine.py and dashboard/routes/ for an existing pause/disable concept — flagged for a follow-up check before treating it as a confirmed clean gap

**verifier-added mechanisms the reader missed (titles):**

- The fire path re-reads the durable record and refuses to fire a paused/disabled job (Halbert: the dashboard's cancel button does not stop a scheduled job)
- Deterministic natural-language schedule parser (no model needed to turn 'every weekday at 8' into a cron expression)
- Two-signal ticker liveness markers: 'alive but failing' is distinguishable from 'firing'
- A timed-out script must be killed as a process GROUP, or a surviving grandchild holds the pipes open forever
- Reentrant in-process lock + cross-process flock around the whole load->modify->save cycle, degrading to in-process-only rather than dying
- Cron expresses wall-clock intent: a stored next-run under a different UTC offset must be re-read as wall clock, not as an instant
- Job-script confinement: resolve-then-relative_to a single scripts directory, and the shebang is deliberately not honoured
- Owner-only permissions on the job store, and ownership restored after a privileged writer's atomic replace
- The agent-facing scheduling tool is deliberately denied the model/provider/endpoint fields the human surfaces have

### `HM17-plugins-acp-providers`

scope `plugins/ + acp_adapter/` — 253 files in scope, 23 cited read (9.1%), self-reported 29, verifier-missed 3.

**unread_areas (reader, verbatim):**

- acp_adapter/server.py (1011 lines) and acp_adapter/session.py (435 lines) and acp_adapter/tools.py (899 lines) — read only via grep/skim of imports and call sites, not line-by-line; the actual ACP session lifecycle, MCP-server-per-session wiring, and tool-schema translation logic in these three large files is unverified in detail
- plugins/memory/ backends themselves (honcho, mem0, supermemory, byterover, hindsight, holographic, openviking, retaindb) — only the shared __init__.py discovery/precedence logic was read; no individual backend's MemoryProvider implementation was read
- plugins/cron_providers/chronos — not read at all
- plugins/dashboard_auth/basic, drain, nous providers — only self_hosted/__init__.py and the shared _shared.py helpers were read in full
- plugins/hermes-achievements/dashboard/plugin_api.py's second half (scan/aggregation engine) and hermes-achievements/tests/test_achievement_engine.py — only the achievement catalog definitions were read
- plugins/model-providers/ — only README.md and anthropic/__init__.py read; the other 37 provider dirs were not opened (mechanism assumed uniform per the documented contract)
- plugins/platforms/ (23 dirs) — only irc/adapter.py was read as a sample; the other 22 adapters (including the AGENTS.md-cited canonical feishu token-lock rules) were not opened
- providers/base.py and providers/__init__.py (the ProviderProfile ABC itself, distinct from plugins/model-providers/) — not read; likely covered by a different reader's unit per the prior review's Providers/TUI/MCP section
- native/fts5_cjk/fts5_cjk.c and build.sh — only README.md read, not the C source or build script
- plugins/web, plugins/google_meet, plugins/image_gen, plugins/teams_pipeline, plugins/browser, plugins/spotify, plugins/video_gen — not opened at all (listed in scope but out of reach given the 46-way split; lowest-signal for a host-steward given Halbert has no video/meeting/spotify surfaces today)
- hermes_cli/plugin_capabilities.py's actual CALL SITES (where plugin_capability_granted() is invoked at runtime) were not traced — only the module itself was read

**verifier-added mechanisms the reader missed (titles):**

- Tool-surface refresh is gated to a turn boundary (and to pre-first-turn) for prompt-cache and mid-turn-swap safety
- Per-entity cooldown on EVERY watched entity, plus an ignore list and a closed-by-default filter warning, on the Home Assistant event ingress
- Markdown fences sized to the content, so a preview containing backticks cannot break out of its code block on the approval dialog

### `HM18-tui-gateway-ui-desktop-docs`

scope `tui_gateway/ + web/src + ui-tui/src + apps/` — 1672 files in scope, 23 cited read (1.4%), self-reported 33, verifier-missed 8.

**unread_areas (reader, verbatim):**

- tui_gateway/server.py (168KB facade) — not read beyond its AGENTS.md description; likely holds the master method/event table
- tui_gateway/methods_*.py (methods_session.py 115KB, methods_prompt.py 60KB, methods_tools.py 70KB, plus methods_config/methods_config_set/methods_groups/methods_profiles/methods_projects/methods_voice/methods_browser/methods_browser_control/methods_bot_relay/methods_images/methods_complete/methods_complete_helpers/methods_slash/methods_session_control/methods_session_foreign.py) — the actual RPC surface, not read
- tui_gateway/hosted_room_peer_http.py, hosted_room_peer_transport.py, hosted_room_server_rpc.py, hosted_room_service.py — only hosted_room_driver.py's header read; flagged anti-pattern but not verified in depth
- tui_gateway/session_compression.py, session_history.py, session_workdir.py, session_auto_continue.py, model_switch.py, compute_host_bridge.py, entry.py, ws.py, render.py, loop_noise.py, mcp_rpc_helpers.py, _env.py — not read
- ui-tui/src — 298 TypeScript files across app/, components/, config/, content/, domain/, hooks/, lib/, protocol/, sdk/, types/; only directory structure listed, no file read despite FOCUS naming ui-tui components explicitly
- web/src — components/, contexts/, hooks/, i18n/, lib/, pages/, plugins/, themes/; only 2 of ~16 pty-*.ts lib files partially read
- apps/desktop — only 3 of 80+ electron/*.ts files read in any depth; e2e/*.spec.ts, renderer source, DESIGN.md, README.md not touched
- docs/relay-connector-contract.md (786 lines, the largest doc in the unit) — not read
- docs/billing-lifecycle.md, docs/observability/monitoring.md, docs/observability/relay-shared-metrics.md, docs/rfcs/*.md, docs/chronos-managed-cron-contract.md, docs/cron-doctor-spec.md, docs/rca-ssl-cacert-post-git-pull.md, docs/micro-compaction.md, docs/streaming-tts.md, docs/kanban/multi-gateway.md, docs/design/multiplexing-gateway.md, docs/design/kanban-dialogs/index.html, docs/hermes-kanban-v1-spec.pdf — not read

**verifier-added mechanisms the reader missed (titles):**

- The PTY reattach contract is built end-to-end in Halbert and wired nowhere — server keeps the session, buffer replays on attach, client declares it dead
- Stateful PTY frame sanitizer: escape sequences, UTF-8 code points and newline runs all straddle read boundaries and need trailing-state buffering
- Backend announces its ACTUAL bound port on stdout and the parent waits for it, with a floored cold-start deadline — instead of the parent guessing a free port
- A pure, testable WS reconnect POLICY module: exponential backoff with a cap, an attempt ceiling, and close codes classified terminal vs retryable
- Startup sweep of durable session rows orphaned by a dead process, gated so a live-but-idle peer's rows are never reaped
- Crash forensics for the desktop shell: fault handlers that write the stack to a durable log and flush SYNCHRONOUSLY, because a fatal fault outlives no async flush
- asyncio loop-exception handler that collapses benign peer-hangup teardown noise, gated on BOTH exception type and callback, chained to the previous handler
- Renderer-bundle vs runtime skew detection, with the ancestry check that makes the commit-distance measurement meaningful

### `HM19-evals-tests-meta`

scope `evals/ + repo-root meta docs` — 118 files in scope, 32 cited read (27.1%), self-reported 34, verifier-missed 7.

**unread_areas (reader, verbatim):**

- evals/browser_use/tasks/ fixture JSON and orchestrate_cloud.py -- only the README was read
- evals/desktop_bug_campaign/thread-scroll/ and the .mjs/.tsx probe file bodies (async-report-live.mjs, navigation-markdown-*.mjs/.tsx, native_ready_probe.mjs) -- only READMEs and Python producer/probe headers read
- evals/compaction/ and evals/postmortem/forensics|live_ab|review_probes internals -- marked 'cited' in the task and confirmed already-lifted via the packet-09 handoff and consolidation/SCORECARD, so only the postmortem README was read in depth
- evals/desktop_mcp_oauth/ (backend_http_fixture.py, renderer_lifecycle.mjs) -- not opened at all
- tests/ (3,898 files) -- only conftest.py autouse-fixture headers and pyproject.toml's pytest markers sampled; the 'sample 15 test files across areas' instruction was not done systematically given this unit's size relative to the FOCUS areas
- tests-js/ remaining files: allow-scripts-sync.test.ts, bootstrap-installer-stage-timer.test.ts, desktop-mac-entitlements.test.ts, desktop-mac-usage-descriptions.test.ts, package-json-lazy-deps.test.ts, window-open-policy.test.ts -- listed but not opened
- compat_manifest.json internals beyond the summary table
- docker-compose.yml and flake.nix -- not opened (Dockerfile skimmed; Halbert has no Docker/compose/flake so deprioritized once confirmed not applicable)
- AGENTS.md (root) and CONTRIBUTING.md beyond opening sections -- placed in scope but not read exhaustively, since prompt/skills-meta territory likely belongs to another reader's unit
- evals/readtool/ and evals/session_search_schema/ fixtures.py/runner.py/tasks.py internals -- only README read for each; readtool's hostile-file fixture set judged a weak fit (no generic read_file agent tool in Halbert) and not pursued further

**verifier-added mechanisms the reader missed (titles):**

- The ruff gate is five rules, not one: ASYNC210/220/221/251 plus a per-file-ignores ratchet baseline — and Halbert has live blocking calls inside async route handlers
- Per-file process isolation as the test-runner design — the fix for a suite whose failures vanish in isolation
- One hermetic-environment autouse fixture: credential scrub, behavioural-flag scrub, HOME redirect, import-time DB-constant re-pin, TZ/locale/hashseed pin
- A live-system guard in conftest that intercepts the destructive primitive itself, with its own argv-parsing regression suite
- Declarative desktop-security contract tests — a window-open policy and an entitlements/Info.plist alignment test that already covers a Tauri app
- npm install-script allowlist pinned to the lockfile it gates
- AST guard at collection time: no test module may define the same name twice

### `HM20-skill-library`

scope `skills/ + optional-skills/` — 770 files in scope, 22 cited read (2.9%), self-reported 27, verifier-missed 6.

**unread_areas (reader, verbatim):**

- optional-skills/mlops/* (30 skills) — deliberately deprioritized as ML-training/serving infra, not host-steward relevant; one-liners only.
- optional-skills/creative/*, skills/creative/* (~30 skills) — image/video/design generation, out of unit focus, one-liners only.
- optional-skills/finance/*, blockchain/*, payments/*, gaming/* — vertical-specific, one-liners only.
- optional-skills/research/* beyond grounded-citations — one-liners only.
- optional-skills/security/unbroker (data-broker opt-out, ~30 files), sherlock, web-pentest — SKILL.md openings only, not full scripts/references/broker JSON trees.
- optional-skills/devops/{actual-setup,inference-sh-cli}, optional-skills/health/neuroskill-bci — line counts checked, content not read.
- skills/{autonomous-ai-agents,email,media,social-media,web}/*, remaining skills/productivity/* (airtable, box, google-workspace, maps, notion, pdf, powerpoint, product-price-monitor, teams-meeting-pipeline, xlsx), skills/research/{arxiv,competitor-news-monitor,llm-wiki,rss-feeds} — one-liner inventory only.
- optional-skills/{mcp,web-development,communication,data-science,dogfood/DESCRIPTION,yuanbao}/* — one-liner inventory only.
- skills/index-cache — listed but not opened.

**verifier-added mechanisms the reader missed (titles):**

- Repo-wide mechanical authoring-standards test over every SKILL.md, with a shrink-only grandfather dict
- Every skill declares its prerequisites and platform gate in frontmatter — the input SK-4 capability gating has none of
- Two-surface skill library: shipped-but-inactive optional skills, activated on demand, so the default catalog stays lean
- 1-3-1 decision brief: problem in one sentence, exactly three options with trade-offs, one recommendation, plus a definition of done
- Blocked-page recovery ladder with a snapshot-vs-live provenance rule ('a snapshot is context, not an answer')
- Category DESCRIPTION.md files and a cached third-party skill-hub index carrying a trust_level per entry

### `OC01-infra-approvals-devices-backup`

scope `src/infra (shared with OC02)` — 810 files in scope, 38 cited read (4.7%), self-reported 34, verifier-missed 7.

**unread_areas (reader, verbatim):**

- device-pairing.ts (806 lines, main pairing state machine — only structurally skimmed via grep, not read in depth)
- device-pairing-node.ts (739 lines, node lifecycle/facts/state — not read)
- device-pairing-tokens.ts (427 lines, scoped token minting for approved pairings — not read)
- device-pairing-state.ts, device-pairing-migration.ts, device-pairing-churn.test.ts, device-pairing-cloud-worker.ts — not read
- device-identity-store.ts (450 lines), device-identity-legacy.ts, device-identity-coordinator-paths.ts — only device-identity.ts's top-level orchestration was read in depth
- state-migrations.device-auth.ts, state-migrations.device-identity.ts, state-migrations.device-identity-repair.ts, state-migrations.exec-approvals.ts — the whole state-migrations.* cluster was not read; likely rich in Halbert's own 'no migrations, refuse and repair' philosophy
- The full approval-handler-*/approval-gateway-*/approval-view-model.ts/approval-presentation.ts/approval-request-filters.ts/approval-turn-source.ts cluster (~15 files) — only approval-scope.ts and approval-resolution-ref.ts were read in depth
- exec-approvals-*.ts full cluster (~35 files) — largely already covered with file:line citations by the prior OSS-REVIEW-OPENCLAW-2026-09-07.md synthesis, so deliberately not re-read in depth; a follow-up should verify no NEW mechanism beyond what that review cites
- backup-create.ts's middle section (lines 440-719: tar-invocation/streaming loop, manifest building, CLI summary) and backup-create-stream.ts (194 lines) — only snapshot-planning and remapping functions were read
- command-analysis/inline-eval.ts (669 lines) — only referenced via risks.ts's import, not read directly
- command-explainer/extract.ts and tree-sitter-runtime.ts — actual tree-sitter parsing/grammar-loading implementation not read, only output types and consumers
- delivery-queue-sqlite-bound.ts, delivery-queue-sqlite-namespace.ts, delivery-queue-sqlite.types.ts — only top-level delivery-queue-sqlite.ts and claim layer read
- container-environment.ts (as opposed to container-env-file.ts, which was read) — not read
- backup-create-stream.ts's observeBackupTarEntryProgress/writeArchiveStreamToFile — not read
- All *.test.ts files across this unit were skipped entirely; the invariants they pin (device-pairing-churn.test.ts, exec-approvals-parity.test.ts, backup-create.windows.test.ts) were not extracted

**verifier-added mechanisms the reader missed (titles):**

- One approval-presentation builder is the only path to any surface, and every field is sanitized there
- The argv-normalization tables that make command-risk detection actually work (interpreter inline-eval + command carriers)
- Durable publish as a commit boundary: exclusive create, fd-identity verification, and a fail-closed directory fsync
- An automation's identity is declared by its runner, never inferred from a run id or session key
- Display compaction at an approval surface must never hide a segment that changes what is being approved
- Progress-idle watchdog with a diagnostic stall message, instead of a wall-clock timeout
- A backup manifest declares its assets, and the symlink policy is enforced against that declaration on both create and verify

### `OC02-infra-rest`

scope `src/infra (shared with OC01)` — 810 files in scope, 28 cited read (3.5%), self-reported 29, verifier-missed 4.

**unread_areas (reader, verbatim):**

- src/infra/outbound/ (~150 files) — nested subdir not covered by OC01's exclusion grep; likely its own unit
- src/infra/exec-approvals-*.ts and exec-safe-bin-*.ts (~50 files) — only exec-host.ts's HMAC transport was read
- src/infra/state-migrations.*.ts (~140 files) — SQLite schema/migration subsystem, not read
- src/infra/heartbeat-*.ts (~70 files) — already covered by lift packet 03 per prior docs; deliberately deprioritized
- src/infra/push-apns-*.ts, push-web-*.ts (~20 files) — not read
- src/infra/provider-usage.*.ts (~25 files), session-cost-usage-*.ts (~20 files) — not read, out of host-infra focus
- src/infra/update-managed-service-handoff-*.ts, update-repair-*.ts, package-update-*.ts, update-runner*.ts (~80 files) — self-update choreography, gated on FDR-04 pricing; only restart-sentinel.ts header skimmed
- src/infra/sqlite-*.ts (~45 files) — not read
- src/infra/net/proxy/, node-proxy-agent.ts, proxy-fetch.ts, undici-*.ts — filenames skimmed only
- src/infra/tls/gateway.ts — not read
- src/infra/tailscale.ts, tailnet.ts, tailscale-route-owner*.ts, ssh-client.ts, ssh-config.ts, scp-host.ts — not read beyond ssh-tunnel.ts
- src/infra/detect-binary.ts, detect-package-manager.ts, binaries.ts, brew.ts, resolve-system-bin.ts, executable-path.ts — not read
- src/infra/machine-name.ts, machine-model.ts, host-account-name.ts, host-account-avatar.ts, os-summary.ts, system-disks.ts, network-interfaces.ts, network-discovery-display.ts — not read
- src/infra/gateway-lock.ts, gateway-boot-lifecycle.ts, gateway-processes.ts, gateway-supervision.ts, gateway-suspend-coordinator.ts, gateway-active-work.ts — not read directly
- src/infra/dotenv*.ts, path-*.ts variants, remote-env.ts, fs-safe-remove.ts — not read
- src/infra/tmp-openclaw-dir.ts, temp-artifact-cleanup.ts, temp-download.ts, sibling-temp-file.ts — not read beyond owned-temp-file.ts/secure-temp-root.ts
- all windows-*.ts and wsl.ts — deliberately skipped, macOS-only target
- src/infra/ports-*.ts, tcp-port.ts, widearea-dns.ts — not read

**verifier-added mechanisms the reader missed (titles):**

- PATH-hijack-resistant system-binary resolution (strict vs standard trust tiers) — Halbert drives the macOS Keychain through a bare `security` name
- PID liveness must be paired with process start time (and argv identity) — Halbert's boot-time run-receipt recovery uses a bare os.kill(pid, 0), exactly where PID reuse is most likely
- Machine display name from the OS's human-set computer name (not the DNS hostname), and a host account real name that refuses to fall back to the login name
- Port already in use: name the owning process and say 'that is already me' — Halbert instead silently starts a second instance on the next free port

### `OC03-auto-reply`

scope `src/auto-reply` — 477 files in scope, 37 cited read (7.8%), self-reported 33, verifier-missed 5.

**unread_areas (reader, verbatim):**

- src/auto-reply/reply/ subdirectory (~700 of the unit's 825 files): agent-runner-*.ts (~120 files, agent-execution harness), dispatch-from-config.*.ts (~180 files, the core delivery pipeline), commands-*.ts (~90 files, every individual slash command handler), session-*.ts, queue/ and queue.*.ts, typing-*.ts, route-reply.ts/routing-policy.ts, reply-run-registry.*.ts, abort*.ts, history*.ts, model-selection*.ts/directive-handling.*.ts, commands-acp/ and commands-subagents/ subdirectories — deliberately not covered file-by-file since FOCUS names only top-level mechanisms and this subdirectory is almost certainly split across other readers in the 46-way run.
- media-understanding.test-fixtures.ts and stage-sandbox-media.test-harness.ts (test scaffolding only, skipped).
- thinking.ts's provider-thinking-profile resolution past line ~220 (deeply OpenClaw-provider-catalog-specific; only the reusable normalization layer in thinking.shared.ts was read in full).
- commands-registry.shared.ts (620 lines), commands-registry.types.ts, and commands-registry.data.ts were not read in full.

**verifier-added mechanisms the reader missed (titles):**

- Transcript-artifact span removal for no-op autonomous turns
- A turn's cause is orthogonal to its transport (InternalTurnSource)
- A non-command turn cannot carry authorization (unsafe state made unrepresentable)
- Build-time registry assertion instead of a hand-maintained reserved-name mirror
- Durable abort cutoff watermark (a stop that survives the process)

### `OC04-commands`

scope `src/commands` — 556 files in scope, 30 cited read (5.4%), self-reported 30, verifier-missed 7.

**unread_areas (reader, verbatim):**

- agent-via-gateway.ts (1329 lines, largest file in the unit) was not read in depth -- only listed.
- agent-exec.ts / agent-exec-input.ts / agent-exec-result.ts (agent exec CLI proper) were located and sized but not read line-by-line; the FOCUS item 'agent exec/audit' is only partially covered.
- The doctor-session-sqlite* cluster (~20 files: migration run/recover/restore/compact/readers/verification) was only seen in the doctor.ts dispatcher excerpt, not read individually.
- doctor/shared/legacy-config-migrations.*.ts (45 files) and the rest of doctor/shared/ (~60 more files) were enumerated by filename only, flagged wholesale as an anti-pattern rather than mined individually.
- configure.wizard.ts (964 lines) was only grepped for function signatures, not read in depth.
- configure.gateway-auth.ts, configure.gateway.ts, configure.channels.ts, configure.commands.ts, configure.shared.ts were not opened at all.
- channels/ and channel-setup/ subdirectories (~20 files) were listed but not read.
- models/ subdirectory (~35 files) was listed but not read beyond doctor-model-catalog-credentials.ts.
- onboard-*.ts and onboard-non-interactive/ (~40 files) were listed but not read.
- sessions-*.ts, status.*.ts / status-all/ / status.scan.* (large status-command subtree, ~50 files) were listed but not read.
- migrate/*.ts (memory-import, item-selection, providers) was listed but not read.
- backup-git.ts, backup-sqlite.ts, backup-schedule.ts, backup-resource-inventory.ts, backup-restore.ts, backup-shared.ts were located/sized but not read in depth.
- cleanup-utils.ts was read for its safety-guard functions but removeStateAndLinkedPaths/removeWorkspaceDirs/listAgentSessionDirs (lines 373-590) were not read.
- triage.ts / triage-*.ts, tasks.ts / tasks-*.ts, promos/, export-trajectory.ts, reset.ts, uninstall.ts, sandbox*.ts, flows.ts, message.ts were not opened.

**verifier-added mechanisms the reader missed (titles):**

- `sandbox explain`: render the EFFECTIVE policy for one session, naming every failed gate with the exact config key that opens it
- Read-only recovery inventory: every deletion candidate carries a reason code AND a plain-language consequence, and anything with missing, ambiguous or aliased evidence is reclassified protected/blocked
- Exec allowlist self-audit: flag interpreter-shaped entries, risky-semantics entries, and any allowlisted binary that RESOLVES outside a trusted directory
- Offline maintenance boundary: every target path must be owned by the active state directory both lexically AND after symlink resolution, plus hardlink reconciliation before touching it
- Error and diagnostic text is untrusted content: strip control characters and cap length before it reaches a terminal or a log
- Diagnostics export is its own redaction choke point, keyed on FIELD NAME classes rather than value patterns, with depth and size caps
- Destructive reset as a scope ladder that stops the running service first and recommends a backup before it deletes

### `OC05-config`

scope `src/config` — 500 files in scope, 24 cited read (4.8%), self-reported 25, verifier-missed 6.

**unread_areas (reader, verbatim):**

- All channel-specific config (types.slack.ts, types.whatsapp.ts, types.discord.ts, types.telegram.ts, types.imessage.ts, types.msteams.ts, types.signal.ts, types.irc.ts, types.googlechat.ts, and matching zod-schema.*.ts files) — out of FOCUS.
- Model provider/policy config (model-provider-config.ts, model-alias-defaults.ts, model-policy-allowlist-migration.ts, model-policy-ref.ts, model-input*.ts) — filenames skimmed only.
- Plugin config surface (plugin-auto-enable.*.ts ~13 files, plugin-install-config-migration.ts, plugin-install-record-map.ts, plugins-allowlist.ts, plugins-runtime-boundary.ts) — not read.
- Gateway/network config (gateway-control-ui-origins.ts, gateway-dispatch-config.ts, gateway-env-selection.ts, gateway-public-origin.ts, port-defaults.ts, control-ui-link-base.ts, tls) — not read.
- Sandbox/docker config (validation.sandbox-container-env.test.ts, config.sandbox-docker.test.ts, types.sandbox.ts) — not read.
- The schema DSL engine itself (schema.ts, schema.walk.ts, schema.lookup.ts, schema.help.*.ts, schema.hints.ts, schema.tiers.ts, schema-base.ts, schema.field-metadata.ts) — only inferred from references in issue-location.ts.
- Root config type and mutation machinery in full depth (config.ts, materialize.ts, mutate.ts, mutation-conflict.ts, mutation-types.ts, merge-patch.ts, merge-missing.ts, patch-replace-paths.ts) — only inferred from call sites in io.write.ts.
- Runtime snapshot/override layer (runtime-snapshot.ts, runtime-overrides.ts, runtime-schema.ts, runtime-group-policy.ts, runtime-source-projection.ts, runtime-write-application.ts) — not read.
- Full redact-snapshot subsystem beyond redact-snapshot.raw.ts and sensitive-paths.ts (redact-snapshot.schema.test.ts, redact-snapshot.restore.test.ts, redact-snapshot.secret-ref.ts, redact-snapshot.test-helpers.ts) — only the raw fallback was read.
- Agent-roster/agent-dirs config (agent-dirs.ts, agent-limits.ts, agent-list-projection.ts, agent-roster-provenance.ts, agent-workspace-roster-transition.ts) — not read.
- CLI command surface (commands.ts, commands.flags.ts) and talk/tts/desktop config (talk.ts, talk-defaults.ts, types.tts.ts, types.desktop.ts) — not read.
- legacy.roster.ts, legacy.shared.ts, legacy.context-budget.ts, legacy-private-network-migration.ts, legacy-codex-provider.ts implementations (only legacy.ts's re-exports were read).
- doc-baseline mechanics beyond the opening lines (doc-baseline.runtime.ts, doc-baseline.integration.test.ts, docs-config-examples.ts) and markdown-tables.ts.
- nix-mode-write-guard.ts (only its import site in io.write.ts was seen).
- redact-argv.ts (only its call site in io.audit.ts was read).
- normalize-paths.ts, normalize-exec-safe-bin.ts, exec-command-highlighting.ts, silent-reply.ts, implicit-mentions.ts, bindings.ts, thread-bindings-config-keys.ts, state-dir-dotenv.ts, web-search-*.ts, official-external-channel-secret-schema.ts — filenames skimmed, not read.

**verifier-added mechanisms the reader missed (titles):**

- Optimistic snapshot-race guard (config CAS) — models.yml read-modify-write has no lock and no conflict detection
- Config content reaches the model unredacted — write_config returns a raw unified diff of any host config file
- The policy gate is skipped on dry runs, so write_config's preview is an unpoliced read of any file on the host
- HMAC-fingerprinted per-leaf config diff baseline — field-level change attribution with no value ever stored
- Dangerous-env-var denylist before materialising or inheriting an environment
- Config-load happens on a write path: being.yml is rewritten during load, with no snapshot of what was overwritten

### `OC06-plugins-sdk`

scope `src/plugins + plugin-sdk + plugin-state` — 1133 files in scope, 34 cited read (3.0%), self-reported 34, verifier-missed 6.

**unread_areas (reader, verbatim):**

- src/plugins loader cluster (loader.ts, loader-runtime-*.ts, loader-records.ts, loader-cache*.ts, ~30 files) -- module resolution/caching internals, not read
- src/plugins manifest-registry.ts (1230 lines) -- only grepped for imports, not read in depth
- src/plugins management-service.ts and the management-*.ts cluster (install/uninstall/enable lifecycle orchestration, ~15 files) -- not read
- src/plugins discovery.ts / discovery.types.ts and the doctor-contract-registry.* cluster (~10 files) -- plugin discovery algorithm and doctor migrations not read
- src/plugins hooks.ts / hook-runner-global.ts and the whole hook-*.ts / hooks.*.test.ts cluster (~25 files) -- plugin hook lifecycle not read; likely overlaps with 'interrupt algebra' already-lifted work but not verified
- src/plugins qa-channel.ts / qa-lab.ts / qa-runner-runtime.ts (plugin QA test harness) -- not read
- src/plugins memory-core-host-*.ts cluster (~15 files, RAG/memory host-engine adapters) -- directly relevant to Halbert's Haloysius integration but not read due to time
- src/plugins provider-auth-*.ts / provider-oauth-*.ts / provider-catalog-live-*.ts clusters (~40 files, OAuth and live model-catalog acquisition) -- not read
- src/plugins install-npm*.ts / install-managed-npm*.ts / npm-package-*.ts (npm package management internals) -- skimmed filenames only
- src/plugin-sdk: only file-lock.ts and command-auth.ts read in full among ~625 files; the SDK is overwhelmingly thin re-export shims (12-25 lines) pointing back into src/plugins, but channel-*.ts, provider-*.ts, session-*.ts, browser-*.ts clusters in plugin-sdk were not individually opened
- src/plugin-state/plugin-blob-store.ts implementation (only .types.ts read) and runtime-health-store.ts -- not read
- access-groups.ts, plugin-entry.ts, tool-plugin.ts -- deliberately not re-read per task instructions (already cited in prior review)
- packages/plugin-package-contract/src/index.test.ts -- not read

**verifier-added mechanisms the reader missed (titles):**

- Per-process incarnation token: liveness that fails closed instead of trusting a PID probe
- Failure direction and time budget declared per extension point in one table, not decided inside each seam
- Untrusted consumers get an isolated copy, and a value that cannot be isolated is refused
- The same policy key, opposite defaults by origin: first-party defaults open, everything else defaults closed
- A review that cannot be shown in full cannot be approved
- Reopening a store namespace with different quotas is refused, not silently resolved

### `OC07-cli-wizard-tui-entry`

scope `src/cli + wizard + tui + bootstrap + interactive + entry*.ts` — 542 files in scope, 20 cited read (3.7%), self-reported 27, verifier-missed 4.

**unread_areas (reader, verbatim):**

- src/cli/ has ~830 files; only a small, focus-targeted slice was read (respawn-policy, argv, progress, banner, one-shot-exit, lobster-art). Entirely unread: capability-cli/*, channel-auth/channels-cli, cron-cli/*, daemon-cli/* (large lifecycle/restart-health subtree), exec-approvals-cli, fleet-cli, gateway-cli/* (run-loop, task-supervisor, suspend-cli), mcp-cli, models-cli, nodes-cli/* (camera/location/pairing/push — device-node RPC), plugins-cli/* (large install/update/marketplace subtree), program/ (build-program, command-registry, routes, register.* for every subcommand group), skills-cli, update-cli/* (very large: schema-preflight, rollback, service lifecycle, windows-task) — these are plausibly covered by other units (daemon/scheduler, plugins, MCP, channels) given the master unit list, but were not verified against those units' scope here.
- src/wizard/ setup.finalize.ts, setup.gateway-config.ts, setup.default-agent.test.ts, setup.official-plugins.ts, setup.plugin-config.ts, setup.workspace.ts, setup.migration-*.ts (canonical/finalize/promotion/snapshot/stage/transaction — a whole config-migration-import subsystem), clack-prompter.ts (the actual @clack/prompts adapter implementation), i18n/ (three locale files) were not read.
- src/tui/ is ~120 files; read only coalesced-refresh, tui-busy-notice, gateway-chat (partial), tui-launch, tui-last-session. Unread: embedded-backend.ts (1542 lines — the embedded/in-process TUI runtime), tui.ts (main TUI entry, 1010 lines with its own test files), tui-session-run-coordinator, tui-stream-assembler, tui-submit(.ts/-state.ts), tui-task-suggestions, tui-plugin-approvals, tui-overlays, all components/ (chat-log, custom-editor, filterable/searchable-select-list, tool-execution rendering), theme/theme.ts, tui-autocomplete, tui-formatters, osc8-hyperlinks — a large fraction of the actual TUI rendering/interaction layer.
- src/interactive/payload.ts was only grep-scanned (50KB file, portable message-presentation/button/model-picker-action schema) — not read in full; likely more relevant to a channels/messaging unit than this one, but flagged in case no other unit claims it.
- src/bootstrap/node-extra-ca-certs.ts was not read (only its sibling node-startup-env.ts was).
- entry.*.test.ts and setup.*.test.ts files were not read for invariants beyond what the source comments already stated; a follow-up pass reading entry.respawn.test.ts and progress.test.ts would sharpen edge-case details for candidates C2 and C9/C10.
- No time was spent on src/cli/program/ (the actual Commander wiring — build-program.ts, command-registry.ts, routes.ts, register.*.ts for every command group) despite it being arguably the closest analog to 'CLI root options' in the FOCUS list; root-help-metadata.ts / precomputed-help.ts (referenced from entry.ts) were read only by reference, not directly.

**verifier-added mechanisms the reader missed (titles):**

- Sanitize untrusted text at the display boundary, with a display/apply split and RTL isolation rather than deletion
- Onboarding rerun has no server-side already-onboarded precondition and silently re-identifies the machine
- Argv-detected read-only mode so a diagnostic invocation cannot mutate a store as a side effect of loading it
- Invalid-config posture: fail visibly with a named repair-command allowlist, instead of silently serving defaults

### `OC08-daemon-process-worker-hooks-audit`

scope `src/daemon+process+worker+hooks+audit+logging+node-host+status` — 389 files in scope, 38 cited read (9.8%), self-reported 38, verifier-missed 4.

**unread_areas (reader, verbatim):**

- src/daemon/schtasks-*.ts (Windows Task Scheduler, ~20 files) — out of scope for macOS-only Halbert, not read
- src/daemon/systemd-*.ts (~15 files) — filenames skimmed only, not read; plausible future Linux-host relevance
- src/worker/worker-deploy-*.ts, worker-rpc-*.ts, embedded-agent*.ts (~15 files) — remote/cloud worker deployment, filenames skimmed only
- src/node-host/node-worker-container-*.ts, node-worker-transfer-*.ts, node-worker-workspace-*.ts (~25 files) — container/workspace lifecycle for remote node hosting, filenames skimmed only
- src/node-host/computer-command.ts, desktop-stream-command.ts, portal-stream-command.ts, pty-command.ts — the specifically-cited files were NOT read in this pass despite being called out in the task; worth a dedicated follow-up read
- src/status/status-message.ts, status-queue.runtime.ts, status-runtime-lines.ts, summary.ts, summary.runtime.ts — not read
- src/logging/diagnostic-stuck-session-recovery*.ts, diagnostic-run-activity*.ts, diagnostic-session-recovery*.ts (~15 files) — a 'stuck session auto-recovery' subsystem never opened; filenames suggest a genuinely novel automatic-recovery pattern worth a dedicated follow-up pass
- src/audit/execution-decision-facts.ts, execution-identity-*.ts, execution-owner-*.ts, message-delivery-*.ts (~15 files) — not read, likely overlaps with the already-lifted admission-evidence pattern
- src/hooks/gmail-*.ts, import-url.ts, install*.ts, module-loader.ts, plugin-hooks.ts, loader.ts, frontmatter.ts (~20 files) — hook installation/discovery machinery and the Gmail integration not read
- All *.test.ts files across the unit not opened directly; relied on production-code comments/docstrings for invariants rather than test assertions

**verifier-added mechanisms the reader missed (titles):**

- Stuck-session recovery: reclaim a wedged run, gated by a closed enum of typed skip reasons
- The daemon writes no log file, and the log line it does emit is hand-built JSON that breaks on any quote or newline
- Bounded fire-and-forget background work: concurrency cap, queue cap, per-job timeout, control-character-stripped single-line error logs
- Shell-wrapped spawn treats BASH_ENV/ENV/CDPATH/PS4 as code-execution carriers and strips them; children are also handed to the OOM killer instead of the steward

### `OC09-tasks-system-agent-flows-boards-claws`

scope `src/tasks+system-agent+flows+boards+claws+trajectory+snapshot+fleet+session-cards+projects` — 271 files in scope, 39 cited read (14.4%), self-reported 38, verifier-missed 6.

**unread_areas (reader, verbatim):**

- src/system-agent: the ~30-file setup-inference-*.ts provider wizard cluster, chat-engine.ts, chat-turn-router.ts, assistant.ts/audit.ts/config-write-policy.ts, rescue-*.ts, transcript-store.ts, tui-backend.ts, delegation-session.ts, greeting/dialogue/onboarding files, verified-inference.ts, probes.ts, operations-execute.ts (574 lines), system-agent.ts core orchestrator (259 lines) not read line-by-line
- src/tasks: task-executor.ts (630 lines, actual spawn/run logic), task-registry.ts/task-registry-mutation.ts/task-registry-state.ts/task-registry-records.ts/task-registry-query.ts/task-registry.audit.ts storage layer, harness-owned-subagent-task.ts, generated-media-task-activity.ts, cron-history/continuation-cleanup, task-session-identity.ts, task-domain-views.ts, task-retention.ts, task-run-owner.ts, most *.test.ts files
- src/claws: ~50 of ~60 files unread — bootstrap.ts, doctor.ts, cron*.ts, mcp*.ts, package-*.ts family, provenance*.ts family, schema*.ts, update-*.ts family, workspace*.ts, export.ts, add.ts, project.ts, experimental.ts, tool-policy-runtime.ts, openclaw-profile.ts, yaml-document.ts, legacy-resume.ts, reader.ts
- src/boards: board-store.ts read only partially; board-notices.ts, board-report.ts, github-actions-capability.ts, sqlite-board-codec.ts (540 lines), sqlite-board-store.ts (731 lines) persistence layer unread
- src/fleet: backup.runtime.ts, containers.runtime.ts/containers.redaction.ts, doctor.runtime.ts, service*.runtime.ts unread (deliberately deprioritized given the multi-tenant anti-pattern finding)
- src/projects: project-clone.ts/project-clone-runtime.ts/project-git-url.ts unread beyond project-registry.ts's head
- src/trajectory: export.ts/command-export.ts/paths.ts/runtime-file.ts/runtime-store.sqlite.ts unread beyond types/runtime/cleanup/metadata heads
- src/snapshot: local-repository.ts (1610 lines, largest file in the unit) not read at all; git-backup-codec.ts, git-backup-streaming files, openclaw-snapshot-copy.ts, windows variants unread
- src/flows: only 2 of ~95 files read; this directory turned out to be OpenClaw's CLI onboarding/doctor-health-check flow system, not a multi-step task-automation engine — flagged as a naming surprise, not the intended 'flows' concept (that lives in src/tasks/task-flow-registry.ts, covered)

**verifier-added mechanisms the reader missed (titles):**

- Config-key denylist that stands regardless of approval, with a named human escalation per root
- Severity-coded self-audit of the machine's own in-flight background work (stale-queued / stuck-running / lost / undelivered)
- Cancellation of in-flight work is provisional until the producer confirms — and Halbert currently loses that race
- Trusted-private-directory assertion for the state root: uid, mode, identity-stable-during-use, ancestor writability, darwin ACLs
- Strip leaked internal runtime-context markers out of model-authored text before any status or notification surface
- Duplicate-terminal-delivery suppression across separate records that share one run

### `OC10-media-pipelines`

scope `src/media* + canvas + link-understanding + transcripts + realtime-transcription` — 160 files in scope, 41 cited read (25.6%), self-reported 43, verifier-missed 8.

**unread_areas (reader, verbatim):**

- src/media-understanding/runner.ts body beyond line ~120 of 1038 (the core provider/model auto-selection and fallback-chain orchestration)
- src/media-understanding/provider-capability-registry.ts, provider-registry.ts, config-provider-models.ts, provider-registry-metadata.ts (provider metadata/capability plumbing)
- src/media-understanding/openai-audio-api.ts, openai-compatible-audio.ts, openai-compatible-video.ts, local-audio.ts (specific provider integrations)
- src/media/store.ts beyond line ~140 (cleanup/eviction sweep, staged-inputs, remote-runtime, retry logic bodies) and store.cleanup.test.ts / store.retry.test.ts
- src/media/playback-transcode.ts, playback-input.ts (the actual ffmpeg transcode pipeline body, only its cache-budget constants and codec-policy sibling were read)
- src/media/image-ops.ts, photon.runtime.ts, png-encode.ts (image resize/encode internals)
- src/media/pdf-extract.ts, document-extractors.runtime.ts body beyond the head, and the extractor plugin contract
- src/media/anthropic-inline-images.ts, prompt-image-input.ts, prompt-image-order.ts, runtime-prompt-image-provenance.ts (prompt-assembly-specific image ordering/provenance, Anthropic-specific inlining)
- src/media/local-media-access.ts, local-media-path.ts (+ .windows.test.ts), read-capability.ts, temp-files.ts, staged-inputs.ts, outbound-attachment.ts, web-media.ts, parse.ts, file-context.ts, load-options.ts
- src/image-generation/runtime.ts, openai-compatible-image-provider.ts, image-assets.ts bodies
- src/video-generation/capabilities.ts, capability-overlays.ts, runtime.ts, normalization.ts bodies
- src/music-generation/ (all files) bodies — only registry-level facade read
- src/transcripts/ — 8499 total lines, only sqlite-schema.ts (full) and status.ts (partial ~90 lines) read; capture.ts, capture-operations.ts, library.ts, store-sqlite.ts, store-read.ts, store-export-jsonl.ts, store-export-ownership.ts, summary.ts, summary-model.ts, source-locator.ts, config.ts, auto-start.ts, manual-source.ts, read.ts all unread
- src/canvas/widget-tool.ts beyond line ~140 of 626 (grants resolution, presenter dispatch, scheduled-report handling) and its five dedicated test files (grants/presenter/prompt/report/scheduled)
- src/canvas/wrap.ts beyond line ~180 of 278 (remainder of the bridge script, e.g. request/response plumbing tail)
- src/realtime-transcription/websocket-session.ts full connect/reconnect state machine (only ~120 lines + targeted grep read of a 640-line file) and its 1096-line test file
- src/media-generation/geometry-normalization.ts, runtime-shared.ts bodies

**verifier-added mechanisms the reader missed (titles):**

- Helper binaries resolved from trusted system directories, never from PATH (strict/standard trust tiers)
- A file-read route that bypasses the one policy pipeline and the redaction choke point
- One primitive that binds root, byte cap and symlink policy to a single read (and names a path swapped during the read)
- One shared bound on every ffmpeg/ffprobe child process (stdout buffer, wall-clock timeout, max media duration)
- Decompression-bomb pixel cap applied to input AND output, with header-only metadata read before any decode
- Bounded response-body read with a Content-Length pre-check, so an oversized remote reply is refused before it is buffered
- Prompt images carry which source fact they came from, on a side channel that does not change provider-visible bytes
- Export-directory ownership proven by a content-hash manifest, with symlinked or pending artifacts refused

### `OC11-talk-tts-acp-web-routing-context`

scope `src/talk+tts+acp+context-engine+meeting-bot+routing+proxy-capture+web*+chat+memory*` — 250 files in scope, 48 cited read (19.2%), self-reported 33, verifier-missed 6.

**unread_areas (reader, verbatim):**

- src/acp/control-plane/manager.*.ts (40+ files) — read only server.ts/approval-classifier.ts/event-ledger.ts/permission-relay.ts; the manager.* family is unread
- src/acp/translator.*.ts (session-lifecycle, prompt-stream, presentation, cancel-scoping) — unread beyond permission-relay.ts
- src/acp/persistent-bindings.*.ts — unread
- src/meeting-bot/chrome-transport.ts, browser-controller.ts, node-host.ts, realtime-engine.ts, realtime-engine-support.ts, plugin-entry.ts, page-script-source.ts — skimmed filenames only, not read
- src/talk/client-voice-session.ts, client-voice-confirmation.ts, client-voice-mutation-digest-owner.ts — not re-read here (already covered by prior review per OSS-REVIEW-OPENCLAW lines 107-108)
- src/talk/provider-internal.ts, provider-registry.ts, provider-resolver.ts, session-runtime.ts, talk-session-controller.ts, session-log-runtime.ts — unread
- src/tts/openai-compatible-speech-provider.ts, voice-models.ts, tts-runtime-personas/fallbacks/models/routing test files, tts-settings.ts, directive-facts.ts, directive-number.ts — unread
- src/routing/account-lookup.ts, bound-account-read.ts, channel-route-targets.ts, bindings.ts, account-id.ts — skimmed only
- src/context-engine/registry.ts (full body beyond head), host-param-projection.ts, runtime-settings.ts, legacy.ts, init.ts — unread beyond partial reads
- src/memory-host-sdk/event-store.ts, engine-storage.ts, event-types.ts, events.ts, multimodal.ts, query.ts, secret.ts, status.ts — unread
- src/chat/canvas-render.ts, tool-content.ts — unread
- src/web-search/runtime-types.ts, runtime.test.ts (38KB, invariants not extracted)
- src/web-fetch/runtime.test.ts — SSRF/safety logic if any likely lives in agents/tools/web-shared.ts, a different unit's files, not covered here

**verifier-added mechanisms the reader missed (titles):**

- Sequenced, replayable event ledger so a reconnecting client recovers a turn it was disconnected from
- Three-axis store budget with a maintained running footprint, so trimming never scans events
- Output-activity tracker: is speech actually playing, is it interruptible, and a watchdog for playback that outlives its own audio
- Per-operation host-capability requirements, refused at the seam with a message naming what is missing
- Durable subsystem quarantine records whose expiry is owned by process liveness, not a TTL
- Bounded, durable memory event log that records why a recall hit was skipped, not just what was returned

### `OC12-state-sessions-secrets-security-shared`

scope `src/state+sessions+secrets+security+shared+model-catalog+model-picker+llm+pairing+compat+utils+types` — 496 files in scope, 43 cited read (8.7%), self-reported 34, verifier-missed 4.

**unread_areas (reader, verbatim):**

- src/secrets/*.ts — of ~174 top-level files, only the core resolution/sentinel/audit/target-registry/store/egress-proxy mechanism files (~20) were read; the ~140 'runtime-*' files (runtime-config-collectors-*, runtime-*-surfaces, runtime-matrix/telegram/discord/nextcloud/zalo/nostr-specific plumbing) were deliberately skipped as OpenClaw's own many-external-channel integration surface, which has no Halbert analog (single-user, no external chat-platform channels) — flagged here rather than silently dropped in case a future unit needs the provider-secret-ownership-table pattern specifically.
- src/state/*.ts — read ~10 of 183 files (schema-additive, schema-repair, readonly, quarantine-store, lease). Unread: the full migration-required/schema-version/table-retirements/legacy-backfills chain, user-profiles-* (tailscale login/avatar/owner migration — OpenClaw multi-user profile system, likely low relevance to single-user Halbert), backup-run-records, agent-deletion-cleanup/journal, claw-package-adoption/lifecycle-lease, github-publication-lifecycle files.
- src/sessions/*.ts — read ~9 of 77 files. Unread: session-worktree-lifecycle.ts, session-upstream-links/monitor.ts (coding-agent git-worktree and CI-link specific, likely low Halbert relevance), send-policy.ts, user-turn-transcript.* family (7 files), background-session-result.ts, auth-profile-preservation.ts, model-overrides.ts/stored-model-overrides.ts (could bear on Halbert's model picker session state, worth a follow-up pass).
- src/security/*.ts — read 3 of 92 files (secret-equal, secret-mask, safe-regex). Unread: the large audit-channel-*/audit-gateway-*/audit-sandbox-*/audit-plugin-* family (~50 files) — these are OpenClaw's own multi-channel/multi-plugin trust-surface audit checks, a rich source for Halbert's prep_audit / doctor-equivalent design but not covered here; also unread: install-policy.ts, windows-acl.ts, dangerous-tools.ts, exec-filesystem-policy.ts, external-content.ts — all plausible follow-up candidates for a security-focused pass.
- src/shared/*.ts — read 4 of ~195 files. Unread: pending-approval-registry.ts, permit-pool.ts, keyed-fifo-lease.ts, scoped-expiring-id-cache.ts, resume-handoff.ts, global-singleton.ts, session-archive-timeout.ts, websocket-upgrade-reject.ts, thread-binding-lifecycle.ts — all named suggestively close to Halbert's turn/steering/thread machinery and worth a dedicated follow-up pass.
- src/utils/*.ts — listed only, zero files read in depth (safe-json.ts, zod-parse.ts, normalize-secret-input.ts, run-with-concurrency.ts worth a look).
- src/llm/*.ts — read the redaction test and stream.ts header only; oauth.ts, model-registry.ts, model-runtime-binding.ts, ai-transport-host.ts unread — model-runtime-binding.ts in particular could bear on Halbert's model/utility_slot.py.
- src/model-catalog/*.ts — read 4 of 15 files; manifest-planner.ts, remote-overlay.ts, remote-store.ts, remote-config.ts unread (all part of the anti-pattern-flagged remote-catalog mechanism, lower priority given C-list above).
- src/types/*.d.ts — all 4 files are OpenClaw-specific ambient type declarations (microsoft-teams-sdk, qrcode, agent-sessions, node-runtime-globals); skimmed by filename only, judged not substantive enough to warrant full reads.

**verifier-added mechanisms the reader missed (titles):**

- Untrusted text is stripped of LLM chat-template special tokens before it reaches the model — Halbert defangs only its own tags
- Halbert's own cloud API keys are never registered with the redaction registry — the origin registers every credential at the moment it is resolved
- Terminal output is persisted and parsed without stripping control sequences — OSC 133 markers inside a command's own output are read as genuine block boundaries
- Pasted credentials are normalised before they can be pushed into an HTTP header

### `OC13-packages`

scope `packages/*` — 655 files in scope, 47 cited read (7.2%), self-reported 47, verifier-missed 5.

**unread_areas (reader, verbatim):**

- gateway-protocol/src/schema/*.ts — only 5 of ~150 schema files read; approvals.ts, exec-approvals.ts, cron.ts, hooks.ts, plugins.ts, worktrees.ts, channels.ts, board.ts, canvas.ts, portals.ts, secrets.ts, terminal.ts and ~15 protocol-schema-fragment-*.ts composition files unread — a full 'every method/event' wire-protocol inventory was not completed given the package's size
- gateway-client/src/{client.ts,protocol-client.ts,websocket.ts,session-projection*.ts,browser-device-auth.ts,cloudflare-access.ts,scope-upgrade.ts} — only reconnect-policy.ts read; request/response framing, sequencing, and session-projection dedup logic unread
- memory-host-sdk/src/host/* (Haloysius-adjacent, ~90 files) — only directory-listed; batch-runner.ts, embedding-chunk-limits.ts, sqlite-wal.ts, read-retry.ts, session-files.ts and the whole batch-embeddings pipeline unread — any findings there would be engine-side, left for a follow-up pass
- markdown-core/src/ir.ts, render.ts, tables.ts, table-layout.ts, render-attributed.ts — the core Markdown IR/rendering engine unread beyond fences.ts and chunk-text.ts's head
- terminal-core/src/{ansi.ts,ansi-sequences.ts,table.ts,note.ts,prompt-select-styled*.ts,theme.ts,palette.ts} — the ANSI parsing/table-rendering core unread beyond the smaller utility files
- normalization-core — only 3 of ~40 files read in depth; cjk-chars.ts, phone-presentation.ts, utf16-slice.ts, text-decoding.ts, expect.ts, format.ts, json-schema.ts, stable-stringify.ts and most coercion helpers unread
- model-catalog-core/src/{model-catalog-pricing.ts,model-catalog-context-windows.ts,configured-model-refs.ts,remote-catalog-bundle.ts} unread beyond provider-model-id-normalize.ts
- media-core/src/{mime.ts,attachment-classify.ts,content-length.ts,read-byte-stream-with-limit.ts,inline-image-data-url.ts,base64.ts} unread beyond inbound-path-policy.ts
- sdk/src/{client.ts,transport.ts,event-hub.ts,normalize.ts,run-terminal.ts} — the public app-SDK surface entirely unread
- acp-core/src/{session.ts,session-lineage-meta.ts,session-interaction-mode.ts,runtime/types.ts} unread beyond error-format.ts/errors.ts
- llm-core/src/{model-contracts/anthropic.ts,model-data.ts,utils/event-stream.ts,validation.ts} unread beyond usage-cost.ts's head
- workboard-contract/src/index.ts not read at all
- agent-core/src/{agent.ts,agent-loop.ts,agent-stream-response.ts,reasoning.ts,stream-steering.ts,turn-interruption.ts,validation.ts,harness/messages.ts,harness/session/session.ts,harness/compaction/*} — deliberately not re-read since the prior OSS-review doc already covers compaction/steering (OSS-REVIEW-OPENCLAW-2026-09-07.md:55-63)
- gateway-protocol test files (*.test.ts) — invariant-pinning tests largely not read; candidates were verified against source + Halbert grep evidence rather than the origin's own test suite

**verifier-added mechanisms the reader missed (titles):**

- Approval bound to the reviewed state: a sha256 of the file the action will mutate, plus a baseHash optimistic-concurrency guard on security-policy writes
- A hard byte cap enforced while reading an HTTP response body, plus strict Content-Length parsing
- Model-produced tool arguments validated against the tool's declared JSON schema before dispatch, with coercion that may never invent a null to pass
- Closed wire objects: every protocol payload rejects unknown properties instead of ignoring them
- Declared byte bounds on inbound base64 payloads, validated as canonical base64 before decoding

### `OC14-agents-second-pass-A`

scope `src/agents (shared with OC15)` — 1750 files in scope, 29 cited read (1.7%), self-reported 29, verifier-missed 6.

**unread_areas (reader, verbatim):**

- src/agents/agent-command.ts (714 lines) — only exported entry-point signatures skimmed; orchestration body not read line-by-line.
- src/agents/agent-scope.ts (709 lines) — entirely unread.
- src/agents/agent-scope-config.ts — only exported function signatures skimmed; resolveAgentWorkspaceProvisioning and isImplicitAcpWorkspaceCandidate bodies not read in detail.
- src/agents/agent-bundle-lsp-runtime.ts (635 lines) and agent-bundle-lsp-process.ts — LSP server process management entirely unread; deprioritized as likely out-of-scope for Halbert.
- src/agents/agent-auth-credentials.ts and agent-auth-discovery.ts/agent-auth-discovery-core.ts — only signatures and env-lookup helper read; secret-handling details not verified in depth, deprioritized given 'no model menus' constraint.
- src/agents/agent-command-execution-identity.ts (236 lines) — only first ~120 lines read.
- src/agents/agent-command-recovery-owner.ts (264 lines) — only first ~100 lines read.
- src/agents/agent-tools.before-tool-call.diagnostics.ts — middle section (~160-365: resolveToolErrorDiagnostic, resolveToolResultTerminalDiagnostic, resolveToolDiagnosticIdentity) not read.
- src/agents/agent-command-local.ts (88 lines) — only header/signature read.
- src/agents/agent-run-terminal-outcome.ts — read roughly first 300 lines of what may be a longer file; did not confirm full extent.
- src/agents/agent-runtime-config.ts, agent-runtime-id.ts, agent-runtime-metadata.ts, agent-settings.ts, agent-dir-registry.ts, agent-create.ts, agent-compaction-constants.ts — not opened at all.
- src/agents/agent-hooks/ (compaction-instructions.ts, compaction-safeguard*.ts, session-manager-runtime-registry.ts) — in scope per instructions but not opened; FOCUS list did not name compaction explicitly.
- All *.test.ts files across this unit — none read; invariants inferred from source comments/types, not confirmed against test expectations.

**verifier-added mechanisms the reader missed (titles):**

- Run-scoped tool handles that die with the run (revoking discovery is not enough)
- Approvals fail closed on timeout, and a caller-supplied 'allow on timeout' is ignored
- Cross-tool guidance gated on the tool actually being in this turn's set
- A denial handed back to the model states its own finality
- Channel/transport-scoped tool denial as declared data
- Shape-only parameter error hints plus deterministic repair of known model-mangled args

### `OC15-agents-second-pass-B`

scope `src/agents (shared with OC14)` — 1750 files in scope, 23 cited read (1.3%), self-reported 27, verifier-missed 5.

**unread_areas (reader, verbatim):**

- src/agents/subagents/announce/ (~30 files) and subagents/completion/ (~8 files) — wake/delivery/retry mechanics, only skimmed via ls
- src/agents/subagents/registry/ beyond subagent-run-timeout.ts and subagent-depth.ts (~90 more files: restart-recovery, orphan/parent recovery, sweeper, persistence) — high value given Halbert has zero subagent restart-recovery today
- src/agents/subagents/swarm/ (7 files) — not read
- streaming internals: stream-compat.ts, stream-message-shared.ts, provider-stream.ts, anthropic-vertex-stream.ts, openai-transport-stream.ts, cli-output-stream*.ts — sizes checked, content not read
- the ~150 mcp-*.ts files (client lifecycle, OAuth, stdio/http transport, tool filtering/quarantine) — out of time budget
- the ~150 model-*/prepared-model-*.ts files (catalog, auth, routing, discovery) beyond model-fallback-cooldown.ts and context-window-guard.ts
- code-mode-*.ts (~30 files, in-process script execution runtime) — likely overlaps with Halbert's already-lifted execute_code, not diffed this pass
- transcript-redact*.ts, transcript-policy.ts, transcript-credential-safety.ts, session-transcript-repair.ts (beyond one grep) — transcript redaction specifics not read in depth
- github-*.ts (~7 files) and cli-*.ts (~15 files) — not read
- auth-profiles/, cli-runner/, harness/, runtime-plan/, sessions/, session-maintenance/, worktrees/, schema/, command/, modes/, utils/ subdirectories listed but not opened

**verifier-added mechanisms the reader missed (titles):**

- One shared prompt-literal sanitizer plus a labelled <untrusted-text> wrapper that tells the model the block is data
- Replay-safety as a fail-closed allowlist of tools a retry may repeat, with name shadowing failing closed
- Approval wait pauses the clock and never extends authority
- Per-invocation tool-call budget charged at the last synchronous boundary, and an authority guard captured at tool construction
- One canonical tool policy projected onto raw MCP identities, with callable names reserving policy identity ahead of hidden inventory

### `OC16-gateway-second-pass-A`

scope `src/gateway (shared with OC17)` — 1311 files in scope, 47 cited read (3.6%), self-reported 42, verifier-missed 5.

**unread_areas (reader, verbatim):**

- Most of control-ui-* (~50 of ~75 files): github-api/preview.ts, session-pr-*.ts, plugin-assets*/frame-contract/tabs.ts, public-session-read/render/http.ts, http-utils.ts, identity.ts, links.ts, resource-routes.ts, response-metadata.ts, root-assets.ts, user-avatar-route.ts, shared.ts, assistant-media-policy tests -- only grepped for structure.
- config-reload.ts body (1341 lines): only the import header was read; watch loop, debounce/coalescing, and apply-plan execution not read.
- config-get-response.ts, config-reload-settings.ts, config-reload-status.types.ts -- not read.
- chat-abort.ts: only ~250 of 803 lines read; abort-request handling, restart-recovery candidate logic, and broadcast wiring in the remaining ~550 lines not read.
- chat-display-projection.core.ts/.history.ts/.message-tool.ts/.helpers.ts/.canvas.ts (2000+ combined lines) and all chat-display-projection.*.test.ts golden tests -- not read beyond .sanitize.ts excerpts.
- chat-attachments.ts, chat-auth-readiness.integration.test.ts, chat-abort.authority.test.ts -- not read.
- cli-session-history.claude.ts (656 lines), .claude-activity.ts, .claude-snapshot.ts -- not read beyond the orchestrator and merge.ts's comparison-key logic.
- board-host-tools.ts (320 lines), board-http.ts, board-view-ticket.ts, board-widget-approval.ts, board-widget-view.ts -- not read.
- channel-avatar-http.ts, channel-status-patches.ts, channel-health-policy.ts -- not read (channel-health-monitor.ts correctly skipped per instructions).
- call.ts, call.runtime.ts -- not opened; assumed already-cited voice-call plumbing per instructions but not actually confirmed by reading them.
- assistant-avatar.ts, assistant-avatar-cache.ts, assistant-avatar-thumbnail.runtime.ts, assistant-media-policy.ts -- not read.
- approval-web-push.ts (only first ~70 of 406 lines) and approval-session-audience.ts (only first ~110 of 223 lines) -- partial only.
- Almost all *.test.ts files in the unit (dozens) -- invariants inferred from source comments/types rather than confirmed against assertions.
- auth-config-utils.ts: only first ~90 of 234 lines read.
- client-bootstrap.ts: only first ~60 of 328 lines read; client-bootstrap.auth.test.ts, client-bootstrap.test.ts, client-callsites.guard.test.ts not read.

**verifier-added mechanisms the reader missed (titles):**

- A high-risk confirmation is not re-bound to the action it approved at execution time
- The host config watcher has no debounce, no re-entrancy guard, and no recovery when the observer dies
- Env-vs-file token precedence can silently break ticket minting, with no diagnostic
- The session cookie name is not instance-scoped, so two local Halberts evict each other's sessions
- A confirmation carries no speaker claim — approval authority is the door, not the asker

### `OC17-gateway-second-pass-B`

scope `src/gateway (shared with OC16)` — 1311 files in scope, 29 cited read (2.2%), self-reported 27, verifier-missed 5.

**unread_areas (reader, verbatim):**

- src/gateway/server-methods/ -- read only ~10 of ~640 files; exec-approvals.ts, board.ts, chat-send-*, cron.ts, skills.ts, usage.ts, github-publication-*, mcp-app.ts, portals.ts, talk*.ts, worktrees.ts, and the ~100-file agent/agents/agent-run-* cluster were only filename-scanned
- src/gateway/worker-environments/ (~340 files: placement-dispatch-*, provider-*, workspace-*, tunnel*, credential-broker.ts) -- filenames scanned only, likely has its own rich candidate set for remote device placement not covered here
- src/gateway/node-registry.ts (1591 lines) and node-registry-private.ts (729 lines) -- only the ~90-line header read; invoke-stream, system.run approval wiring, reconnect/reconcile logic body not read
- src/gateway/desktop/ (RFB/VNC observe-bridge, rfb-preauth/probe/view-only-filter) -- filenames scanned only, relevant to 'remote access' focus but not opened
- src/gateway/terminal/ (session-manager, output-flow-control, node-relay) -- filenames scanned only
- src/gateway/health/context-engine.ts and account-context.ts -- not opened
- src/gateway/server/ws-connection.ts (705 lines) and ~300 flat server-*.ts restart/reload/hot-reload/shutdown/sidecar files -- not opened beyond the specific small files cited in candidates
- src/gateway/talk-realtime-relay-*.ts (~10 files, voice relay tool-call ledger/forced consults) -- filenames scanned only
- src/gateway/methods/ (registry.ts, core-descriptors.ts, descriptor.ts) -- the descriptor system method-scopes.ts builds on was not read directly
- server-methods/nodes*.ts, node-command-policy*.ts, node-wake-state*.ts -- node command allowlisting/wake-sleep state, directly relevant to focus, not opened
- Test files throughout were not read for invariants -- candidates derived from implementation only, not cross-checked against test suites' documented edge cases

**verifier-added mechanisms the reader missed (titles):**

- Authorization is a field on the method descriptor, and a missing or duplicate one is a startup error, not a runtime default
- A dangerous capability stays declarable at pairing but never enters the runtime allowlist on the strength of the pairing approval alone
- The approved command's script bytes and resolved real path are re-verified after the human answers, immediately before exec
- View-only observation enforced on the wire by an allowlist re-framer, with the observer forced to shared so it can never evict the human
- PTY output flow control coupled to the viewer socket's send pressure, with a reassert failsafe and an interactive flush window

### `OC18-channels-cron-second-pass`

scope `src/channels + src/cron` — 463 files in scope, 56 cited read (12.1%), self-reported 55, verifier-missed 7.

**unread_areas (reader, verbatim):**

- src/cron/normalize.ts (655 lines, largest unread cron file — job creation/validation normalization)
- src/cron/store/run-receipt-store.ts (763 lines, largest cron file overall — not read)
- src/cron/store.ts, src/cron/store/schema.ts, row-codec.ts, trigger-codec.ts, delivery-codec.ts (persistence layer largely unread)
- src/cron/service/timer-scheduler.ts (585 lines) and service/timer-job-runner.ts, timer-outcome-finalization.ts, wake.ts (the actual timer/wake execution core — only skimmed via grep, not read line-by-line)
- src/cron/service/agent-watchdog.ts (247 lines) — explicitly relevant to FOCUS ('isolation') and not read
- src/cron/isolated-agent.ts + the entire src/cron/isolated-agent/ subdirectory (~80 files: model-preflight, subagent-followup, delivery-dispatch policy, session-key isolation) — only channel-output-policy.ts was read; this is the largest unread portion of the cron half of the unit
- src/cron/active-jobs.ts (435 lines), schedule-identity.ts, run-diagnostics.ts, public-job.ts, job-read-view.ts, trigger-script.ts
- src/channels/plugins/ subdirectory (~150 files: setup wizards, per-channel adapters, threading-helpers, bootstrap-registry) — only registry-lookup context was read via imports; not surveyed directly
- src/channels/message/ subdirectory beyond outbound-echo.ts and ingress-retry-policy.ts: ingress-queue.ts, ingress-drain-*.ts, ingress-claim-*.ts, receive.ts, send.ts, reply-pipeline.ts, reply-transform.ts, live.ts, adapter.ts, capabilities.ts, contracts.ts, durable-receive.ts, ingress-monitor.ts, ingress-unavailable.ts
- src/channels/status/ (account-state.ts, read-model.ts) and src/channels/transport/stall-watchdog.ts
- src/channels/turn/execution.ts (393 lines), lifecycle.ts (710 lines), run-channel-turn.ts (341 lines), types.ts (518 lines), delivery-result.ts, durable-delivery.ts — the core turn-execution/delivery pipeline itself, only its smaller satellite files were read
- src/channels/allowlists/resolve-utils.ts, direct-dm*.ts, allow-from.ts, allowlist-match.ts — access-control-adjacent files not read (message-access/ proper was explicitly out of scope)
- src/channels/conversation-resolution.ts read only ~half (220/429 lines)

**verifier-added mechanisms the reader missed (titles):**

- Phase-aware cron watchdog: separate setup / pre-execution / execution budgets, with queue wait excluded from the setup clock
- Idle-stall watchdog for a stream (armable, fires once, handler failures contained) — and Halbert's streaming client uses a TOTAL timeout instead
- Preflight the local model endpoint before ADMITTING a scheduled run, and skip rather than fail when it is unreachable
- PID-recycling-proof ownership identity (pid:starttime:uuid) with a lease cap — Halbert's boot recovery uses a bare os.kill(pid, 0)
- Marker-forgery defense that folds lookalike Unicode before scanning — Halbert's untrusted-text neutralizer only matches ASCII
- Refuse a scheduled job's delivery target when it was only inherited from a shared last-recipient bucket — and route the refusal through the one result every consumer already checks
- Every abandonment path must terminalize the run receipt, or the job self-fences forever

### `OC19-extensions-identity-security-ops`

scope `extensions/{a2a,acpx,admin-http-rpc,bonjour,clawrouter,device-pair,diagnostics-*,file-transfer,oc-path,onepassword,openshell,policy,raft,reef,tokenjuice,vault,visitor-access,webhooks}` — 336 files in scope, 30 cited read (8.9%), self-reported 34, verifier-missed 6.

**unread_areas (reader, verbatim):**

- policy/src/doctor/scopes/*.ts (9 files) and cli*.ts/register.*.test-utils.ts — full per-domain finding catalog unread beyond types.ts/automatic-repairs.ts/attestation.
- openshell/src/backend.ts (1444 lines) and fs-bridge.ts (681 lines) — SSH-remote execution engine unread beyond mirror.ts.
- crabbox beyond doctor.ts/plugin.json — deliberately deprioritized (cloud-VM provider, no Halbert analog).
- reef beyond guard.ts/friendcode.ts: pipeline.ts, envelope.ts, identity.ts, replay.ts, trust-store.ts, legacy-key-guard.ts, transport.ts, flow.ts, outbound.ts.
- raft beyond inbound.ts: channel.ts, gateway.ts, accounts.ts, setup.ts.
- diagnostics-otel beyond service-genai-content.ts: service-exporter.ts, service-metrics.ts, service-traces.ts, 5x service-recorders-*.ts, service-propagation.ts, service.ts.
- diagnostics-prometheus beyond a grep of service.ts's auth check.
- file-transfer's node-host/* implementation files and tools/*-tool.ts descriptors beyond shared/policy.ts, path-binding.ts, audit.ts.
- oc-path's parse/edit/emit engines for markdown/jsonc/jsonl/yaml (10+ files) beyond sentinel.ts.
- clawrouter's provider-catalog.ts (434 lines) and tool-schemas.ts/stream.ts beyond usage.ts.
- acpx's codex-adapter.ts, pi-session-catalog*.ts, runtime.ts, service.ts beyond process-lease.ts/process-reaper.ts.
- a2a's protocol.ts, channel.ts, gateway.ts, outbound.ts, inbound.ts, http.ts — only task-store.ts skimmed; deprioritized as lower fit for single-user Halbert.
- webhooks/src/config.ts and http-request-schema.ts beyond http.ts's security primitives.
- vault/src/cli.ts, onepassword's cli.ts/tool.ts/config.ts/pending-authorization.ts/secret-ref-cli.ts, and onepassword-secret-ref-resolver.js — beyond broker.ts, op-client.ts, onepassword-op-path.js.

**verifier-added mechanisms the reader missed (titles):**

- SSRF check is bypassed by one HTTP redirect: Halbert validates the URL once, then follows redirects (OpenClaw pins redirect:'manual' and re-asserts the origin per request)
- A method allowlist separate from the handler table decides what crosses the remote surface — and the discovery listing is generated from that same allowlist
- A concrete seed catalog of config-posture checks — the doctor's check-id table the reader left unread, several ids naming Halbert's own open rows
- One composable inbound-HTTP guard pipeline (method, content-type, memory-bounded rate limiter, per-key in-flight cap, bounded+timed body read, schema) shared by every listener
- A registered tool-result middleware seam — and the head-vs-tail truncation asymmetry it would let Halbert fix in one place
- Stateless, self-verifying, expiry-bound pairing code (HMAC over expiry||nonce, Crockford base32) instead of server-held pending state

### `OC20-extensions-memory-knowledge-automation`

scope `extensions/{memory-*,active-memory,logbook,team-reports,workboard,migrate-*,llm-task,lobster,qa-*}` — 786 files in scope, 32 cited read (4.1%), self-reported 44, verifier-missed 4.

**unread_areas (reader, verbatim):**

- extensions/memory-core/src/memory/ and migration/ subdirectories (not listed or read)
- extensions/memory-core/src/dreaming-*.ts beyond dreaming-consolidation.ts (7 files not read)
- extensions/memory-core/src/session-backfill-*.ts (6 files) and session-search-visibility*.ts
- extensions/memory-core/src/memory-forget-curated-writes.ts, memory-forget-report.ts and related participant tests
- extensions/memory-core/src/workspace-path-classifier.ts, tools.citations.ts, public-artifacts.ts, rem-evidence.ts, rem-harness.ts
- extensions/memory-lancedb/doctor-contract-api.ts and its large test files, embeddings.lifecycle.test.ts, concurrent/live tests
- extensions/active-memory/transcript.ts, transcript-watch.ts, query.ts, prompt.ts, recall-state.ts, recall-run.ts, types.ts, session.ts
- extensions/memory-wiki/src/compile.ts, vault.ts, source-sync.ts, obsidian.ts, chatgpt-import.ts, wiki-overview.ts, presentation.ts, person-page.ts, query.ts, gateway.ts, status.ts and ~30 more files — the single most under-read directory relative to its size (~40 files, 5 read)
- extensions/memory-wiki/skills/ subdirectory
- extensions/logbook/src/analyze.ts, node-host.ts
- extensions/team-reports/src/render/, sources/, http.ts, scheduler.ts, summaries.ts, config.ts, gateway-methods.ts
- extensions/migrate-claude/apply.ts, config.ts, helpers.ts, plan.ts, provider.ts, skills.ts, source.ts
- extensions/migrate-hermes/apply.ts, auth.ts, auth-config.ts, config*.ts, items.ts, model.ts, plan.ts, provider*.ts, skills*.ts, source.ts (large, security-relevant, deserves a dedicated follow-up pass)
- extensions/llm-task/src/llm-task-tool.ts body beyond ~140 lines, doctor-contract-api.ts
- extensions/workboard/src/dispatcher*.ts, lifecycle-sync*.ts, sqlite-store*.ts, most store-*.ts files, tools*.ts, gateway*.ts, workspace-access.ts, session-link.ts, change-events.ts, card-lookup.ts, command.ts, cli.ts — the largest directory in the unit (~24k lines) and most under-read relative to size
- extensions/workboard/browser/ subdirectory (19 files)
- extensions/lobster/src/lobster-runner.ts, lobster-taskflow.ts in full
- extensions/buzz/src/ (69 files) — not opened beyond README/index.ts
- extensions/clickclack/src/ (55 files) — not opened beyond README.md
- extensions/qa-channel/src/ (28 files) — only top-level index.ts read
- extensions/qa-lab/src/ (340 files!) and web/ subdirectory — largest directory in the unit by file count, essentially unexplored
- extensions/qa-lab/confidence-profiles/, shared/ subdirectories
- extensions/test-support/debug-proxy-env-test-helpers.ts, generation-live-test-helpers.ts, provider-model-test-helpers.ts

**verifier-added mechanisms the reader missed (titles):**

- Cross-pipeline redaction product-boundary test: a secret in a transcript must not survive into the dreaming corpus or a promoted memory entry
- Read-side recall visibility filter: ownership, deleted-archive, and post-reset cutoff enforced on search hits, not only on writers
- Memory-subsystem self-audit and archive-never-delete repair, including a self-ingestion detector
- Budgeted eviction from a file a human may also edit: drop only blocks the machine can structurally prove it generated

### `OC21-extensions-device-media-desktop`

scope `extensions/{cua-computer,imessage,browser,geolocation,document-extract,diffs*,tts-local-cli,linux-node,talk-voice,voice-call,web-readability,image-generation-core,canvas,speech/tts vendors}` — 631 files in scope, 32 cited read (5.1%), self-reported 34, verifier-missed 6.

**unread_areas (reader, verbatim):**

- extensions/browser: read only ~8 of ~200 non-test src/ files; the chrome-extension/ native-messaging bootstrap+relay-auth-v2 crypto layer, the CDP transport layer, screencast subsystem, session-tab-registry sqlite store, and all of src/cli/ and src/browser/routes/ (agent action routes) were not read — a follow-up pass is justified only if Halbert commits to a scoped browser-automation capability
- extensions/canvas: file listing only (46 files); the a2ui widget-rendering protocol was not read, likely low relevance given Halbert's own bespoke dashboard
- extensions/voice-call: read only webhook-security.ts partially out of ~45 non-test src/ files; the actual live-call agent pipeline (realtime-agent-context.ts, realtime-call-control.ts, media-stream.ts, response-generator.ts) was not read
- extensions/imessage: read 5 of ~70 non-test src/ files; send.ts (1237 lines, 'how they send safely'), the real monitor/ subdirectory implementation, install-imsg.ts, remote-host.ts (SSH-to-a-real-Mac pattern), and approval-native.ts/approval-polls.ts were not read
- extensions/matrix: 393 files total, read only auth-presence.ts; doctor-contract-api's capacity/archive-scan/account-state/credentials/import test files suggest richer doctor-check patterns not investigated
- extensions/signal, extensions/mxc, extensions/nextcloud-talk, extensions/sms: file-listing survey only
- extensions/diffs and diffs-language-pack: read prompt-guidance.ts and part of store.ts only out of ~8700 lines; render.ts, tool.ts, viewer-client.ts/viewer-payload.ts not read
- extensions/geolocation: config.ts and lookup-route.ts not read
- extensions/cua-computer: commands.ts (598 lines, per-action dispatch), window-actions.ts, driver-client.ts, browser-actions.ts, recording-actions.ts, execution-resources.ts not read in detail

**verifier-added mechanisms the reader missed (titles):**

- An authorized write executes through a re-verified open handle bound to (device, inode), not a re-open by path
- Per-execution scratch root: symlink/hardlink-rejecting root, opaque handles instead of paths, re-stat on every use, bounded tree walk, whole-tree dispose
- Scope escalation is an explicit typed action, and granting it invalidates every reference minted under the narrower scope
- Deny-by-default path policy where deny always wins, and a saved 'allow always' grant is keyed to the node-authoritative canonical path, not the requested one
- One-time capability ticket bound to the requester's liveness, not just to a TTL
- Bound a frame producer by delaying the acknowledgement instead of maintaining a frame queue

### `OC22-extensions-local-providers-apps`

scope `extensions/{ollama,llama-cpp,vllm,sglang,lmstudio,litellm,copilot-proxy} + apps/{macos,linux,swabble}` — 699 files in scope, 23 cited read (3.3%), self-reported 34, verifier-missed 6.

**unread_areas (reader, verbatim):**

- extensions/openai and extensions/anthropic (explicitly reference-only per task scope — skimmed listings only, not read in depth)
- extensions/ollama/src/sanitizers/, config-compat.ts, wsl2-crash-loop-check.ts, discovery-shared.ts internals, node-inference-registration.ts, node-inference.abort.test.ts/.deadline.test.ts (test invariants) — listed but not read line-by-line
- extensions/llama-cpp/src/llama-server-install.ts, llama-server-extract.ts, llama-server-preset.ts, model-catalog.ts, external-server/ (binary download/verification and preset selection logic) — only hardware.ts and managed-server.ts headers read
- extensions/lmstudio/src/stream.ts, model-reasoning.ts, runtime.ts, provider-auth.ts, embedding-provider*.ts — only models.fetch.ts read
- extensions/vllm/api.ts, defaults.ts, provider-policy-api.ts — only thinking-policy.ts and stream.ts head read
- extensions/sglang beyond api.ts/defaults.ts (provider-discovery.contract.test.ts, index.ts) — very thin plugin, likely low-yield but not confirmed
- extensions/litellm/onboard.ts, image-generation-provider.ts
- apps/macos: ~290 of 309 top-level Swift files not read at all (only ~15 read in depth) — MenuBar.swift, StatusMenuController.swift, ComputerActionService/ComputerScreenActionExecutor/ComputerWindowActionExecutor.swift (computer-use), CameraCaptureService.swift, CameraPTZService/CameraPTZNativeController.swift, ScreenRecordService.swift, ScreenSnapshotService.swift, MicLevelMonitor.swift, AudioInputDeviceObserver.swift, AppleEventPermission.swift (only grepped for), ExecApprovalsSocketServer/Client/PathGuard.swift (unix-socket exec-approval IPC), HostEnvSanitizer.swift/HostEnvSecurityPolicy.generated.swift, DevicePairingApprovalPrompter.swift, all Voice/Talk-mode files (TalkModeRuntime, VoiceWake*, MLXSpeechSynthesizer), Onboarding*.swift, Dashboard*.swift, Gateway*.swift (connection lifecycle beyond sleep controller), CronJobsStore/CronModels.swift, CookieSyncManager/BrowserProfileImport*.swift, PeekabooBridgeHostCoordinator/CuaDriver*.swift
- apps/macos/Sources/OpenClawIPC, OpenClawDiscovery, OpenClawCameraPTZNative, OpenClawMacCLI (separate SwiftPM targets) — not opened
- apps/macos/Tests/ (OpenClawIPCTests, Fixtures/TalkOverlay) — not read, so no invariants pinned from tests
- apps/macos/Packaging, AppIconDesigns, Icon.icon — packaging/asset dirs, skipped as non-substantive
- apps/linux/src-tauri, apps/linux/ui, apps/linux/scripts — only README read, no source
- apps/swabble/Sources, Tests — only README read; wake-word daemon internals (SwabbleKit gating logic) unexamined
- apps/shared/OpenClawMLXTTSProtocol, OpenClawWatchRTC, mermaid — not opened (OpenClawKit confirmed near-empty)
- apps/mobile — confirmed to contain only version.json, nothing to read
- apps/android, apps/ios — not opened at all (task said skim only; even a skim of file listings was skipped given time budget)
- apps/macos-mlx-tts — explicitly out of scope per task instructions, correctly skipped

**verifier-added mechanisms the reader missed (titles):**

- Staged commands are written into a live shell with no gate and no control-character escaping - an embedded newline executes
- Every agent-spawned shell inherits Halbert's full environment, including provider API keys
- The Tauri shell disables CSP entirely and grants the whole default core permission set
- The command danger gate matches raw strings - no shell-wrapper or env-prefix unwrapping
- A remembered approval has no way to be bound to the exact argv and cwd it was granted for
- Download-integrity discipline: refuse an artifact with no server digest, and bind the hash to an open fd

### `OC23-control-ui`

scope `ui/src` — 1445 files in scope, 30 cited read (2.1%), self-reported 30, verifier-missed 7.

**unread_areas (reader, verbatim):**

- Most of components/ (only ~15 of 248 top-level files read; app-sidebar-*, session-menu-*, sidebar-attention-*, lobster-pet-* mascot system, markdown-* rendering beyond a cursory pass, config-form.node.*.ts internals, mcp-app-view.ts/theme.ts/unmount.ts full bodies, web-awesome-* wrappers)
- Most of lib/ subdirectories not opened: agents/, board/, channels/, secrets-store/, skill-workshop/, skills/, tasks/, worktrees/; also session-progress-cards.ts, session-organizer-*.ts, model-catalog-store.ts, provider-quota-summary.ts
- pages/apps, pages/channels, pages/tasks, pages/workboard, pages/skill-workshop, pages/skills, pages/secrets, pages/usage, pages/model-providers, pages/model-setup, pages/portals, pages/labs, pages/custodian, pages/meetings, pages/plugin(s), pages/worktrees, pages/lobsterdex, pages/dashboards, pages/connection, pages/new-session — none opened
- pages/config/ page-level wiring (save/diff-preview flow, validation-error surfacing) — only the generic config-form library was read
- pages/chat/ page itself and components/markdown-streaming.ts's actual streaming-chunk algorithm (size checked only)
- components/board/, components/browser/, components/desktop/, components/terminal/ subdirectories — not explored
- i18n/locales/* (30+ files) and i18n/lib/registry.ts, lit-controller.ts — only translate.ts partially read; RTL/pluralization unverified
- styles/ directory — not opened
- app-navigation.ts / app-routes.ts full route table — only inferred from listings
- pages/sessions/view.ts (1882 lines) and pages/cron/view.ts (2069 lines) — grep-surveyed for exports only, not read in full
- e2e/ and test-helpers/ — skipped per prioritization of substantive files

**verifier-added mechanisms the reader missed (titles):**

- Approval surface forces LTR so a command cannot visually reorder itself (bidi/trojan-source defence)
- Write-only secret store: the secret variant structurally has no value field, plus per-secret allowed-hosts egress binding
- Attention dismissals keyed to a content signature, pruned on recurrence, with non-dismissible severities
- Typed refresh policy: visibility, TTL, interruption and coalescing decide fetch vs defer vs skip
- Config diff preview: sensitive paths redacted by ancestor-prefix inheritance, behind an explicit reveal, with bounded diff computation
- Per-request expiry timers and per-source failure isolation in the approval refresh
- Client-minted idempotency key plus expected-leaf token on the chat send RPC

### `OC24-docs-qa-security-skills`

scope `docs/ + qa/ + security/ + custodian-skills/` — 1436 files in scope, 32 cited read (2.2%), self-reported 47, verifier-missed 5.

**unread_areas (reader, verbatim):**

- docs/gateway/ — only 4 of ~59 files read (gateway-lock, permission-modes, sandbox-vs-tool-policy-vs-elevated, secrets-plan-contract); doctor.md, health.md, restart-recovery.md, operator-scopes.md, secrets.md, telemetry.md, heartbeat.md, sandboxing.md, and ~40 more not read.
- docs/concepts/ — only standing-intents.md read of ~52 files; compaction.md, queue-steering.md, memory-provenance.md, session-pruning.md, usage-tracking.md, retry.md, model-failover.md not checked against Halbert.
- docs/nodes/ — index.md (1084 lines), audio.md, computer-use.md, media-understanding.md, talk.md, troubleshooting.md, location-command.md not read; camera.md only head read.
- docs/automation/ — hooks.md (795 lines), tasks.md (449 lines), imap.md, index.md, taskflow.md, and the entire docs/automation/cron-jobs/ subdirectory not read.
- qa/convex-credential-broker/ and qa/scenarios/<theme>/*.yaml (per-scenario files across 14 theme directories) not opened.
- skills/skill-creator/scripts/*.py (package_skill.py, quick_validate.py) not read beyond the SKILL.md head.
- docs/security/formal-verification.md not read; docs/specs/codex-supervision.md only partially read (deprioritized, Codex-specific).
- The bulk of security/opengrep/precise.yml's 145 rule bodies (pattern-regex internals) — only ids/messages and ~10 full rule bodies inspected.

**verifier-added mechanisms the reader missed (titles):**

- Auth-failure rate limiter that charges wrong credentials and never charges absent ones
- LLM special-token stripping on untrusted text before it reaches a chat-templated local model
- Metadata-only audit ledger with a closed schema — the record states what changed, never what it was
- Read-only `--lint --json` mode over one health-check registry, with detect()/repair() separated and threshold exit codes
- QA scenario pack: every behavioural claim bound to a taxonomy coverage ID, its docs, its code, and an executable path

### `OCC01-v2-second-look`

scope `v2/src` — 69 files in scope, 34 cited read (49.3%), self-reported 33, verifier-missed 4.

**unread_areas (reader, verbatim):**

- v2/src/mcp/transport-shttp.mjs, transport-sse.mjs, transport-ws.mjs — not read in detail, only client.mjs's dispatch to them; Halbert's own MCP client already covers stdio+Streamable HTTP and a prior wave hardened it, so deprioritized rather than overlooked.
- v2/src/tools/notebook-edit.mjs and v2/src/tools/lsp.mjs body past line 60 — skimmed as IDE/Jupyter-specific and out of Halbert's host-steward domain, not read in full.
- v2/src/ui/app.mjs, ink-app.mjs, components.mjs, markdown.mjs, repl.mjs — not read at all; CLI/Ink terminal-rendering concerns that map weakly to Halbert's browser dashboard, flagged for a follow-up if terminal-UI patterns are wanted against Halbert's own terminal-as-a-talk-channel work.
- v2/src/ui/commands.mjs lines ~135-533 — only the command index and /cost, /doctor, /fast handlers read; ~35 other slash commands (/compact, /review, /memory, /forget, /effort, /think, /plan, /agents, /skills, etc.) not read.
- docs/adr/ADR-001-v2-architecture.md and ADR-002-path-to-100-percent.md — section headers only, content not read (FOCUS called out ADR-003 specifically).
- v2/src/config/cli-args.mjs and env.mjs — not read; only settings.mjs (the merge chain) was read.
- v2/test/test.mjs — only grepped/sampled around this unit's modules, not read end-to-end (2091 lines total).

**verifier-added mechanisms the reader missed (titles):**

- One shell=True survives, on a caller-supplied string, behind a route named dry-run
- One declared table of every environment variable, and the security switches that table declares but nothing reads
- Windowed file reads with a total-lines footer, plus binary and directory detection, instead of a hard size refusal
- The ADRs overstate the code -- ADR-001's five-layer settings chain with an enterprise remote-fetch layer does not exist

### `OCC02-archive-bundle-and-tracking-pipeline`

scope `archive/open_claude_code + scripts/` — 210 files in scope, 20 cited read (9.5%), self-reported 27, verifier-missed 4.

**unread_areas (reader, verbatim):**

- cli.mjs is a 7.6MB bundle (191k lines); this pass sampled it via targeted grep -ob / byte-offset slicing on ~20 search terms (system/agent prompt, Bash tool description + banned commands, Edit tool description, command-prefix policy_spec, doctor/init command definitions, permission-confirmation UI, retry/backoff client, bash-output file-path extraction). Not read: full tool descriptions for Glob/Grep/LS/WebFetch/NotebookEdit/dispatch_agent's own instructions, the complete 'Tool usage policy' and 'Committing changes with git' sections beyond what was excerpted, the full auth/OAuth device-code flow, statsig/feature-gate flag names and their effects (29 hits on 'statsig', none inspected), the complete retry/error-taxonomy code beyond shouldRetry/calculateDefaultRetryTimeoutMillis, and any MCP-related strings (not searched).
- archive/open_claude_code/src/wasm/*.mjs (7 files, ~1700 lines: conversation-ui.mjs, demo.mjs, index.mjs, layout-engine.mjs, terminal-renderer.mjs, test.mjs, ui-components.mjs, yoga-loader.mjs) — skimmed via `wc -l` only, not read; likely a clean-room Yoga/Ink-style sketch of low novelty given the same pattern seen in src/cli/* and src/api/client.mjs (placeholder/mock implementations), but not confirmed.
- archive/open_claude_code/docs/components/terminal.md read only through line 140 of 266; archive/open_claude_code/docs/wasm/{overview,integration,ui}.md (175+306+409 lines) not read at all — architecture/overview.md and the read portion of terminal.md both read as generic/synthetic clean-room documentation rather than real product internals, which is why the wasm docs were deprioritized in favor of mining the real cli.mjs bundle per the FOCUS instruction, but they were not actually opened to confirm the same is true of them.
- archive/open_claude_code/CLAUDE.md (22 lines) and README.md (86 lines) not read.
- The `rudevolution` git submodule referenced by decompile-and-diff.mjs and analyze-discoveries.sh (MinCut graph partitioning, witness chains, pattern corpus, 21 research docs) is an unfetched empty submodule directory in this checkout — its internal decompiler code and claimed research documents could not be read or verified; C4's task_proposal deliberately does not depend on rudevolution's internals for that reason.

**verifier-added mechanisms the reader missed (titles):**

- run_command has two execution paths with different redaction, output bounding and audit — and which runs depends on whether a dashboard client is subscribed
- Tool descriptions generated from the capability-filtered live tool registry, so what the model is told it can do cannot drift from what the gate allows
- Hard steer away from the shell toward the narrow, gated tools — stated as a MUST with the alternatives named
- A tracking script that silently rewrites its own dependency's source on disk before importing it

