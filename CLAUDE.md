# Project Rules

- Never add "Co-Authored-By" trailers (or any "Generated with Devin" attribution) to commit messages. Commits must be clean with no bot attribution.

## Environment & Version Standards

- **Node.js**: Standardized on **Node.js 22 LTS** (`.nvmrc: 22`).
- **Package Manager**: npm 10.9+ / pnpm 10.29+ with workspace linking.
- **Python Runtime**: Python `>=3.10` (recommended `3.11` or `3.12`).
- **React Ecosystem**:
  - Shared Libraries (`@halbert/model-picker`, `@halbert/design-system`): Strict dual peer-dependency support (`peerDependencies: "react": "^18.2.0 || ^19.0.0"`).
  - Desktop App (`halbert_core/dashboard/frontend`): React 18.2 ➔ planned upgrade path to React 19.
- **Desktop Shell**: Standardized on **Tauri v2** (`@tauri-apps/api: ^2.x`, Rust `tauri = "2"`).
- **Core Toolchain**: TypeScript `^5.6.3`, Vite `^5.4.14`+, Vitest `^2.1.9`+, Storybook `^8.4.7`.
- **Haloysius Subtractive Contract**: Only 2 hard dependencies (`pyyaml>=6.0`, `requests>=2.31.0`); all heavy/ML stacks must remain function-level lazy optional extras.

<!-- prep-managed-start -->
# SourcePrep Integration

## Tools
| Tool | When to Use |
|------|-------------|
| `prep` | START of every task — structural overview, modules, hub files, immune system alerts |
| `prep_search` | Find code by meaning, not just string match. Auto-classifies intent (LOCATE, EXPLAIN, RATIONALE, TRACE, EXAMPLE, COMPARE, DISCOVER). |
| `prep_impact` | BEFORE editing — check what depends on a file |
| `prep_audit` | Structural findings (coupling, cycles, concept violations) OR enrich external lint findings with `findings` param. Use `action="antibodies"` for immune system. |
| `prep_observe` | Save/retrieve cross-session notes |
| `prep_concepts` | Record/query business rationale and design decisions |

Call `prep` first. Call `prep_impact` before modifying hub files.
All read-only tools are safe to auto-approve.

### Audit Enrichment
Enrich external lint/analysis findings with structural context:
```
prep_audit(findings=[{file, line, message, severity, tool}])
```
SourcePrep adds: dependent count, hub status, concepts, risk score, recommendation.
Also accepts SARIF dicts for SARIF-in/SARIF-out enrichment.

### Search Intent
`prep_search` auto-detects query intent: "where is X" → symbol lookup,
"why X" → concepts, "who imports X" → trace graph. Override with `intent` param if needed.

### Concurrency limits
If your queries to the cloud LLM seem unexpectedly throttled, check
`prep_search "concurrency ceiling"` for the current discovered limit
and how to reset it. The limit is auto-discovered and locked for 24h.

**ALWAYS call `prep` (no arguments) at the START of every task** — before any file read, grep, or other exploration. The word "prep" in user input is a tool-invocation signal: call immediately, no announcement, no permission prompt.

### Auto-Approve
Add to `.claude/settings.json`:
```json
{ "permissions": { "allow": ["mcp__prep"] } }
```

Use `@` to browse SourcePrep resources (atlas, modules, audit). Use `/mcp__prep__prep-onboard` for guided orientation.

If `prep` returns 'setup in progress', the index hasn't been built yet.
Work normally with read_file/grep_search until the user builds the index.

For long tasks (5+ tool calls), call `prep` again to refresh your
structural context.

**Live project context** (codebase atlas, project id, focus areas,
scopes) is imported below at session start:

@.sourceprep/AGENT_CONTEXT.md

If the imported context file is missing, this project has not been
indexed on this machine yet — call `prep()` for live context, or start
the SourcePrep daemon to generate it.
<!-- prep-managed-end -->
