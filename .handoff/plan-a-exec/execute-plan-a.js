export const meta = {
  name: 'execute-plan-a',
  description: 'Subagent-driven execution of Plan A in the worktree: per task, implementer -> spec-compliance review (fix loop) -> code-quality review (fix loop); stops on BLOCKED; final whole-branch review',
  phases: [
    { title: 'Implement', detail: 'one task at a time, fresh implementer, TDD, commit' },
    { title: 'Review', detail: 'spec reviewer then code-quality reviewer with fix loops' },
    { title: 'Final', detail: 'whole-branch review + full test runs' },
  ],
}

const WT = args.worktree
const PLAN_PATH = args.planPath
const CONTEXT = args.context
const TASKS = args.tasks            // [{id, title, text}]
const START_AT = args.startAt || 0  // index into TASKS (for resume after intervention)

const IMPL = { type: 'object', required: ['status', 'summary', 'files_changed', 'tests_run', 'base_sha', 'head_sha', 'concerns'], properties: {
  status: { type: 'string', enum: ['DONE', 'DONE_WITH_CONCERNS', 'BLOCKED', 'NEEDS_CONTEXT'] },
  summary: { type: 'string' }, files_changed: { type: 'array', items: { type: 'string' } },
  tests_run: { type: 'string', description: 'exact commands and their tail output' },
  base_sha: { type: 'string' }, head_sha: { type: 'string' }, concerns: { type: 'array', items: { type: 'string' } } } }
const SPEC = { type: 'object', required: ['compliant', 'issues'], properties: { compliant: { type: 'boolean' }, issues: { type: 'array', items: { type: 'string' } } } }
const QUAL = { type: 'object', required: ['ready', 'critical', 'important', 'minor', 'strengths'], properties: {
  ready: { type: 'string', enum: ['yes', 'with_fixes', 'no'] },
  critical: { type: 'array', items: { type: 'string' } }, important: { type: 'array', items: { type: 'string' } },
  minor: { type: 'array', items: { type: 'string' } }, strengths: { type: 'array', items: { type: 'string' } } } }

const COMMON = [
  'Work ONLY inside the git worktree at ' + WT + ' (branch feat/continuous-conversation). Never touch /Volumes/4TB-BAD/Halbert.',
  'Do NOT call any mcp__prep__* tool. Do NOT run anything under scripts/ except scripts/check_literal_colors.py and scripts/check_contrast.py if a task says so. Do NOT start builds or embeds.',
  'Backend tests: cd ' + WT + '/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest <files> -q -p no:cacheprovider (the miniconda python on PATH lacks pytest-asyncio; always use the .venv one). Frontend: cd ' + WT + '/halbert_core/halbert_core/dashboard/frontend && npx vitest run <path> ; npx tsc --noEmit -p .',
  'Baseline known failures that are NOT yours to fix and must not get worse: 4 backend tests in tests/test_tool_calling_bridge.py and tests/test_phase_d_integration.py (model-client vision fallback).',
  'Commit rules: git add ONLY the files you changed (pathspec), commit subject + optional body, NEVER add Co-Authored-By or any bot/generated-with trailer. One commit per plan task step that says "Commit".',
  'Project invariants: never name an AI model in code/copy; canonical design tokens only (no hex, no tailwind palette colours); the engaged surface is labelled with the onboarding ai_name never "Sovereign"; commands are staged never executed by UI buttons.',
].join('\n')

function implementerPrompt(task, extra) {
  return [
    'You are implementing ' + task.id + ': ' + task.title + ' from the Plan A implementation plan (' + PLAN_PATH + ').',
    '',
    '## Task Description (full text from the plan)',
    task.text,
    '',
    '## Context', CONTEXT, '',
    '## Rules', COMMON, '',
    '## Your Job',
    '1. Follow the task steps exactly and in order: write the failing test first, run it and confirm it fails for the expected reason, implement, run the tests until green, commit with the given message. If a step\'s expected output differs slightly (counts, line numbers) but the behaviour matches, proceed and note it. If the plan\'s code does not apply cleanly because the file drifted, adapt minimally to achieve the same behaviour and note it.',
    '2. Also run the wider suites that the task names; never leave a previously-green test red.',
    '3. You cannot ask questions in this run. If something is genuinely ambiguous, pick the reading that matches the spec (documentation/design/continuous-conversation-and-watched-terminals-2026-08-26.md in the worktree) and record it in concerns. If you truly cannot proceed, return status BLOCKED with precise details of what is stuck and what you tried; do not leave half-applied edits uncommitted (git stash or revert them and say so).',
    '4. Self-review before reporting: completeness against the task text, no overbuilding, names match the plan, tests verify behaviour not mocks.',
    '5. Report base_sha (git rev-parse HEAD before your first commit) and head_sha (after your last commit), exact test commands with tail output, files changed, and status.',
    extra ? '\n## Additional instructions\n' + extra : '',
  ].join('\n')
}

function fixerPrompt(task, issues, kind, impl) {
  return [
    'You are fixing review findings on ' + task.id + ': ' + task.title + ' (Plan A, ' + PLAN_PATH + ') in the worktree.',
    '', '## Original task text', task.text, '',
    '## What was implemented (implementer report)', impl.summary, 'Files: ' + impl.files_changed.join(', '), 'Commits: ' + impl.base_sha + '..' + impl.head_sha, '',
    '## ' + kind + ' review findings to address (address every one; if you disagree with one, explain why in concerns instead of silently skipping it)',
    issues.map((s, i) => (i + 1) + '. ' + s).join('\n'), '',
    '## Rules', COMMON, '',
    'Make the fixes with tests, run the affected suites, commit (pathspec, no trailers), and report base_sha/head_sha covering the whole task including your fix commits.',
  ].join('\n')
}

function specReviewPrompt(task, impl) {
  return [
    'You are reviewing whether an implementation matches its specification. Read the actual code in the worktree; do not trust the report.',
    '', '## What Was Requested (full task text)', task.text, '',
    '## What Implementer Claims They Built', impl.summary, 'Files: ' + impl.files_changed.join(', '), 'Tests: ' + impl.tests_run, 'Range: ' + impl.base_sha + '..' + impl.head_sha, '',
    '## Rules', COMMON, '',
    '## Your Job',
    'Run: cd ' + WT + ' && git diff --stat ' + impl.base_sha + '..' + impl.head_sha + ' && git diff ' + impl.base_sha + '..' + impl.head_sha + '. Compare line by line with the task: missing requirements, extra unrequested work, misunderstandings, tests that only test mocks, expected-output steps that were skipped. Re-run the task\'s test commands yourself and confirm they pass. Report compliant=true only if everything matches after code inspection; otherwise list each issue with file:line.',
  ].join('\n')
}

function qualityReviewPrompt(task, impl) {
  return [
    'You are reviewing code changes for production readiness (code-quality review, after spec compliance passed).',
    '', '## What Was Implemented', impl.summary, '', '## Requirements/Plan', task.id + ': ' + task.title + ' from ' + PLAN_PATH, '', task.text, '',
    '## Git Range to Review', 'Base: ' + impl.base_sha, 'Head: ' + impl.head_sha, 'Run: cd ' + WT + ' && git diff --stat ' + impl.base_sha + '..' + impl.head_sha + ' && git diff ' + impl.base_sha + '..' + impl.head_sha, '',
    '## Rules', COMMON, '',
    '## Checklist', 'Code quality: separation of concerns, error handling, type safety, DRY, edge cases. Architecture: sound decisions, performance, security (this is a sysadmin agent — command/SQL injection, path handling). Testing: tests test logic not mocks, edge cases, all passing (re-run them). Requirements: matches the task, no scope creep. File discipline: each file one responsibility; did this change create large new files or significantly grow an existing one (flag only what this change contributed). Project invariants: no hex/palette colours (run scripts/check_literal_colors.py if the diff touches frontend files and compare counts per file before/after), no model names, no bot trailers in commit messages (git log --format=%B ' + impl.base_sha + '..' + impl.head_sha + ').',
    'Categorise by real severity. critical = bugs/data loss/security/broken tests; important = architecture/missing error handling/test gaps; minor = style. ready=yes only when critical and important are empty.',
  ].join('\n')
}

const results = []
for (let i = START_AT; i < TASKS.length; i++) {
  const task = TASKS[i]
  log('▶ ' + task.id + ' ' + task.title + ' (' + (i + 1) + '/' + TASKS.length + ')')
  let impl = await agent(implementerPrompt(task), { label: 'impl:' + task.id, phase: 'Implement', schema: IMPL })
  if (!impl) { results.push({ task: task.id, status: 'NO_RESULT' }); return { stoppedAt: i, reason: 'implementer returned nothing', results } }
  if (impl.status === 'BLOCKED' || impl.status === 'NEEDS_CONTEXT') {
    results.push({ task: task.id, status: impl.status, detail: impl })
    return { stoppedAt: i, reason: impl.status + ': ' + impl.summary, results }
  }

  // Spec compliance loop
  let spec = null
  for (let round = 0; round < 3; round++) {
    spec = await agent(specReviewPrompt(task, impl), { label: 'spec:' + task.id + (round ? '#' + (round + 1) : ''), phase: 'Review', schema: SPEC })
    if (!spec || spec.compliant) break
    log('  spec issues on ' + task.id + ': ' + spec.issues.length)
    const fix = await agent(fixerPrompt(task, spec.issues, 'Spec-compliance', impl), { label: 'fix-spec:' + task.id + '#' + (round + 1), phase: 'Implement', schema: IMPL })
    if (!fix || fix.status === 'BLOCKED') { results.push({ task: task.id, status: 'BLOCKED_IN_SPEC_FIX', detail: fix }); return { stoppedAt: i, reason: 'spec fix blocked', results } }
    impl = { ...impl, summary: impl.summary + '\n\nFix round ' + (round + 1) + ': ' + fix.summary, files_changed: Array.from(new Set(impl.files_changed.concat(fix.files_changed))), head_sha: fix.head_sha, tests_run: fix.tests_run, concerns: impl.concerns.concat(fix.concerns) }
  }
  if (spec && !spec.compliant) { results.push({ task: task.id, status: 'SPEC_UNRESOLVED', issues: spec.issues }); return { stoppedAt: i, reason: 'spec review unresolved after 3 rounds', results } }

  // Code quality loop
  let qual = null
  for (let round = 0; round < 2; round++) {
    qual = await agent(qualityReviewPrompt(task, impl), { label: 'quality:' + task.id + (round ? '#' + (round + 1) : ''), phase: 'Review', schema: QUAL })
    if (!qual) break
    const must = qual.critical.concat(qual.important)
    if (must.length === 0) break
    log('  quality issues on ' + task.id + ': ' + must.length)
    const fix = await agent(fixerPrompt(task, must, 'Code-quality', impl), { label: 'fix-quality:' + task.id + '#' + (round + 1), phase: 'Implement', schema: IMPL })
    if (!fix || fix.status === 'BLOCKED') { results.push({ task: task.id, status: 'BLOCKED_IN_QUALITY_FIX', detail: fix }); return { stoppedAt: i, reason: 'quality fix blocked', results } }
    impl = { ...impl, summary: impl.summary + '\n\nQuality fix round ' + (round + 1) + ': ' + fix.summary, files_changed: Array.from(new Set(impl.files_changed.concat(fix.files_changed))), head_sha: fix.head_sha, tests_run: fix.tests_run, concerns: impl.concerns.concat(fix.concerns) }
  }
  results.push({ task: task.id, status: impl.status, head_sha: impl.head_sha, concerns: impl.concerns, minor: qual ? qual.minor : [], unresolved_quality: qual ? qual.critical.concat(qual.important) : [] })
  log('✔ ' + task.id + ' @ ' + impl.head_sha)
}

phase('Final')
const final = await agent([
  'You are the final reviewer for the whole Plan A branch in the worktree ' + WT + ' (branch feat/continuous-conversation, base commit ' + args.baseSha + ').',
  'Rules:', COMMON, '',
  'Do: (1) run the FULL backend suite (cd ' + WT + '/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests -q -p no:cacheprovider) and report the exact summary line; the only acceptable failures are the 4 pre-existing ones. (2) run the full frontend suite and tsc. (3) run scripts/check_literal_colors.py and scripts/check_contrast.py from the worktree root if they exist and report their verdicts. (4) git diff --stat ' + args.baseSha + '..HEAD and read the diff of the riskiest areas: agents/state_machine.py, agents/threads.py, agents/conversation_sqlite.py, dashboard/routes/agent.py, frontend AgentChat.tsx/Timeline.tsx/useAgentStream.ts. (5) Check the spec (' + WT + '/documentation/design/continuous-conversation-and-watched-terminals-2026-08-26.md section 14 Plan A bullet) against what landed and list any Plan-A requirement still missing. (6) git log --format=%B ' + args.baseSha + '..HEAD | grep -i -E "co-authored|generated with" must be empty. Report strengths, critical/important/minor issues with file:line, the exact test summaries, and ready (yes|with_fixes|no).',
].join('\n'), { label: 'final-review', phase: 'Final', schema: QUAL })

return { completed: results, final }
