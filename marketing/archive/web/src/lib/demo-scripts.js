/**
 * Halbert Interactive CLI & Desktop Demonstration Scripts
 * Formatted for the AnimatedCLI engine.
 */

export const howAreYou = {
  title: 'halbert — ubuntu-server-01',
  loop: true,
  loopDelayMs: 6000,
  events: [
    { type: 'user_input', text: 'how are you doing?', typingDelayMs: 35 },
    { type: 'agent_thinking', durationMs: 700 },
    { type: 'tool_call', tool: 'read_sensors', args: '', durationMs: 800, statusText: 'Checking vitals…' },
    { type: 'tool_result', text: 'CPU 45°C · load 0.15 · disk /dev/nvme0n1 healthy', status: 'success' },
    { type: 'pause', durationMs: 400 },
    { type: 'tool_call', tool: 'query_memory', args: '"recent incidents"', durationMs: 700, statusText: 'Recalling incidents…' },
    { type: 'tool_result', text: '3 read errors on /dev/sda1 at 08:00 today', status: 'warning' },
    { type: 'pause', durationMs: 500 },
    {
      type: 'agent_output',
      text: "I'm ubuntu-server-01. I've been up 42 days. CPU is cool at 45°C, load is light.\n\nOne thing though — I logged three read errors on /dev/sda1 this morning. I'd keep an eye on that drive. Want me to schedule a SMART test?",
      typewriterDelayMs: 14,
    },
  ],
};

export const enableCompression = {
  title: 'halbert — ubuntu-server-01',
  loop: true,
  loopDelayMs: 5000,
  events: [
    { type: 'user_input', text: 'can we enable compression on the data volume?', typingDelayMs: 30 },
    { type: 'agent_thinking', durationMs: 600 },
    { type: 'tool_call', tool: 'read_config', args: '/etc/fstab', durationMs: 700, statusText: 'Reading configuration…' },
    { type: 'tool_result', text: '/dev/nvme0n1 · bcachefs · compression=none', status: 'success' },
    { type: 'pause', durationMs: 400 },
    {
      type: 'agent_output',
      text: "I checked my fstab — I'm currently mounted with compression off. Enabling lz4 is safe for our workload and I can do it live without unmounting.\n\nShall I run a benchmark first, or go ahead and enable it?",
      typewriterDelayMs: 14,
    },
  ],
};

export const whatChanged = {
  title: 'halbert — ubuntu-server-01',
  loop: true,
  loopDelayMs: 5000,
  events: [
    { type: 'user_input', text: 'why is ssh on port 2222?', typingDelayMs: 30 },
    { type: 'agent_thinking', durationMs: 600 },
    { type: 'tool_call', tool: 'query_memory', args: '"ssh port change rationale"', durationMs: 800, statusText: 'Recalling history…' },
    { type: 'tool_result', text: 'Changed 2026-07-14 · reason: "avoid scan noise on default port"', status: 'success' },
    { type: 'pause', durationMs: 400 },
    {
      type: 'agent_output',
      text: "I moved SSH to port 2222 on July 14th. You told me to — the auth log was filling up with scan attempts on port 22. It's been quiet since.\n\nThe change is in /etc/ssh/sshd_config. Want to see the diff?",
      typewriterDelayMs: 14,
    },
  ],
};

export const proactiveAlert = {
  title: 'halbert — ubuntu-server-01',
  loop: true,
  loopDelayMs: 6000,
  events: [
    { type: 'user_input', text: 'good morning. anything I should know?', typingDelayMs: 28 },
    { type: 'agent_thinking', durationMs: 700 },
    { type: 'tool_call', tool: 'triage_overnight', args: '', durationMs: 900, statusText: 'Reviewing overnight logs…' },
    { type: 'tool_result', text: '1 urgent · 2 attention · 14 nominal', status: 'warning' },
    { type: 'pause', durationMs: 400 },
    {
      type: 'agent_output',
      text: "Morning. One thing needs your attention: my backup job failed at 3am — the destination volume was full. I've queued a retry after you clear some space.\n\nTwo smaller things: a new kernel update is available, and I noticed sshd_config drifted from what you set last month. Want me to walk through both?",
      typewriterDelayMs: 14,
    },
  ],
};
