import React from 'react';

const STATUS_MAP = {
  shipped: {
    label: 'Shipped',
    color: 'var(--color-status-nominal)',
  },
  hidden: {
    label: 'Backend-Only',
    color: 'var(--color-status-telemetry)',
  },
  unbuilt: {
    label: 'Unbuilt',
    color: 'var(--color-status-warning)',
  },
  deferred: {
    label: 'Deferred',
    color: 'var(--color-ink-tertiary)',
  },
};

export function StatusIndicator({ status, showDot = true }) {
  const item = STATUS_MAP[status] || STATUS_MAP.deferred;

  return (
    <span
      className="inline-flex items-center gap-1.5 font-mono text-xs uppercase tracking-wider font-semibold"
      style={{ color: item.color }}
    >
      {showDot && (
        <span
          className="w-1.5 h-1.5 rounded-none shrink-0"
          style={{ backgroundColor: item.color }}
        />
      )}
      <span>{item.label}</span>
    </span>
  );
}
