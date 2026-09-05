// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Folding a run of inspection calls into one row.
 *
 * Five reads and a grep before one command produced six stacked bordered rows
 * in the feed, each a heading over an empty body. The reads are how Halbert
 * got to the answer, not the answer.
 *
 * What may never be folded is the point of the rule:
 *
 *  - anything that FAILED — a 40ms read that failed is more interesting than
 *    a 4s one that did not;
 *  - anything PROMOTED — a command that ran long enough to earn a task card
 *    does not then disappear into a summary of things that did not matter;
 *  - anything that WROTE — an action is not an inspection, whatever it cost;
 *  - anything still RUNNING — a group summarises what happened, and burying a
 *    call in flight hides the only thing moving;
 *  - anything REDACTED — handled by the render site, which answers
 *    `isRedactedBlock` before this function ever sees a block.
 *
 * The tool names below are checked against the real registry by a test. The
 * handoff this came from listed `grep_search`, `list_dir`, `check_drift` and
 * `systemctl_action`, which exist in neither Halbert nor the OSS repo it
 * cited: half the map would never have matched anything.
 */

import type { ToolExecution } from '../../hooks/useAgentStream';

/** Read-only calls: they look at the host, they do not change it. */
export const INSPECTION_TOOLS: ReadonlySet<string> = new Set([
  'read_file',
  'list_directory',
  'read_log_tail',
  'recall_memory',
  'recall_thread',
  'get_service_status',
  'list_running_services',
  'check_process',
  'check_disk_space',
  'get_system_load',
  'get_network_info',
  'get_cpu_info',
  'get_memory_info',
  'get_disk_usage',
  'get_process_list',
  'terminal_blocks',
  'self_knowledge_all',
  'self_conversations',
]);

/** Matches PROMOTE_AFTER_SECONDS in streaming/agent_pool.py. */
export const QUIET_SECONDS = 2;

export type GroupedRow =
  | { kind: 'single'; item: ToolExecution }
  | { kind: 'group'; items: ToolExecution[] };

/** True when this call is background noise rather than part of the answer. */
export function isQuietInspection(exec: ToolExecution): boolean {
  if (exec.status !== 'success') return false;

  if (exec.tool === 'run_command') {
    // What the command DID, first. The rule above says an action is not an
    // inspection whatever it cost, and then this function folded on cost
    // alone: `rm -rf /tmp/x`, `git push --force`, `systemctl stop nginx` and
    // `mkfs.ext4 /dev/sda1` all return in well under two seconds with exit 0,
    // and all of them were collapsing into a row headed "Looked at".
    //
    // The host answers this — the same safety classification that gates
    // approval — so the feed does not have to parse shell. Undefined means
    // nobody said, which is not the same as "no": an older row, or a fallback
    // to the subprocess path, must not fold.
    if (exec.blockReadOnly !== true) return false;

    // A command is only quiet once something has SAID it was quick. With no
    // block it may still be running, or the pool may have fallen back to the
    // subprocess path; assuming brevity would hide a command still going.
    if (exec.blockDuration === undefined || exec.blockDuration >= QUIET_SECONDS) return false;
    return exec.blockExitCode === 0;
  }

  return INSPECTION_TOOLS.has(exec.tool);
}

/**
 * Consecutive quiet inspections collapse; everything else stands alone.
 *
 * A run of one is left as a single card: one row is not a wall, and folding
 * it would hide a step while saving nothing.
 */
export function groupInspections(executions: ToolExecution[]): GroupedRow[] {
  const rows: GroupedRow[] = [];
  let run: ToolExecution[] = [];

  const flush = () => {
    if (run.length > 1) rows.push({ kind: 'group', items: run });
    else if (run.length === 1) rows.push({ kind: 'single', item: run[0] });
    run = [];
  };

  for (const exec of executions) {
    if (isQuietInspection(exec)) {
      run.push(exec);
      continue;
    }
    flush();
    rows.push({ kind: 'single', item: exec });
  }
  flush();
  return rows;
}

export default groupInspections;
