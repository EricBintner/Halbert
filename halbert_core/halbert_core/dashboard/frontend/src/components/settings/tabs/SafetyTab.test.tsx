// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * SafetyTab tests. Unlike the other settings tabs, SafetyTab is a fully
 * controlled presentational component -- its custom-AI-rules state and its
 * add-rule form both come in as props and are driven entirely through the
 * setter callbacks the parent passes down. The one exception is the tool
 * policy section, which owns its own fetch calls to
 * /api/settings/policy[/tool[/:name]] and only reports the result back up
 * through `setPolicy`.
 */
import type { ComponentProps } from 'react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SafetyTab, type AIRule, type ToolPolicy } from './SafetyTab'

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

const RULE: AIRule = {
  id: 'r1',
  rule: 'NAS mounts may be offline',
  category: 'storage',
  priority: 'high',
  enabled: true,
}

function renderTab(overrides: Partial<ComponentProps<typeof SafetyTab>> = {}) {
  const calls: Array<{ url: string; init?: RequestInit }> = []
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    return jsonResponse({ status: 'ok' })
  })
  vi.stubGlobal('fetch', fetchMock)

  const setNewRule = vi.fn()
  const onAddRule = vi.fn()
  const onDeleteRule = vi.fn()
  const onToggleRule = vi.fn()
  const setPolicy = vi.fn()
  const setSavingPolicy = vi.fn()

  const props: ComponentProps<typeof SafetyTab> = {
    aiRules: [],
    aiRulesExamples: [],
    newRule: { rule: '', category: 'general', priority: 'high' },
    setNewRule,
    addingRule: false,
    onAddRule,
    onDeleteRule,
    onToggleRule,
    policy: { default_allow: true, tools: {} },
    setPolicy,
    savingPolicy: false,
    setSavingPolicy,
    policyPath: 'config/policy.yml',
    ...overrides,
  }

  const { rerender } = render(<SafetyTab {...props} />)
  return { calls, props, rerender, setNewRule, onAddRule, onDeleteRule, onToggleRule, setPolicy, setSavingPolicy }
}

afterEach(() => vi.unstubAllGlobals())

describe('SafetyTab', () => {
  it('shows the empty state with example rules when there are no custom rules', () => {
    renderTab({ aiRulesExamples: ['Ignore offline NAS shares'] })
    expect(screen.getByText('No custom rules yet')).toBeTruthy()
    expect(screen.getByText('Ignore offline NAS shares')).toBeTruthy()
  })

  it('renders existing rules with their badges', () => {
    renderTab({ aiRules: [RULE] })
    expect(screen.getByText('NAS mounts may be offline')).toBeTruthy()
    expect(screen.getByText('high')).toBeTruthy()
    expect(screen.getByText('storage')).toBeTruthy()
    expect(screen.getByText('1 rule active. The AI will always consider these when providing advice.')).toBeTruthy()
  })

  it('toggling a rule calls onToggleRule with the rule object', async () => {
    const user = userEvent.setup()
    const { onToggleRule } = renderTab({ aiRules: [RULE] })
    await user.click(screen.getByTitle('Disable rule'))
    expect(onToggleRule).toHaveBeenCalledWith(RULE)
  })

  it('deleting a rule calls onDeleteRule with its id', async () => {
    const user = userEvent.setup()
    const { onDeleteRule } = renderTab({ aiRules: [RULE] })
    const deleteButtons = screen.getAllByRole('button').filter((b) => b.querySelector('svg.lucide-trash2'))
    await user.click(deleteButtons[0])
    expect(onDeleteRule).toHaveBeenCalledWith('r1')
  })

  it('typing a new rule calls setNewRule, and Add Rule is disabled until non-blank', async () => {
    const user = userEvent.setup()
    const { setNewRule } = renderTab()
    expect(screen.getByRole('button', { name: /add rule/i })).toBeDisabled()

    await user.type(screen.getByLabelText('Add a New Rule'), 'x')
    expect(setNewRule).toHaveBeenCalled()
  })

  it('Add Rule is enabled once newRule.rule is non-blank, and calls onAddRule', async () => {
    const user = userEvent.setup()
    const { onAddRule } = renderTab({ newRule: { rule: 'Some rule', category: 'general', priority: 'high' } })
    const addButton = screen.getByRole('button', { name: /add rule/i })
    expect(addButton).toBeEnabled()
    await user.click(addButton)
    expect(onAddRule).toHaveBeenCalled()
  })

  it('toggling Default Allow POSTs to /api/settings/policy and updates policy', async () => {
    const user = userEvent.setup()
    const { calls, setPolicy } = renderTab({ policy: { default_allow: true, tools: {} } })

    await user.click(screen.getByRole('button', { name: /enabled/i }))

    await waitFor(() => {
      const post = calls.find((c) => c.url === '/api/settings/policy' && c.init?.method === 'POST')
      expect(post).toBeTruthy()
      const body = JSON.parse(post!.init!.body as string)
      expect(body.policy.default_allow).toBe(false)
    })
    expect(setPolicy).toHaveBeenCalledWith({ default_allow: false, tools: {} })
  })

  it('renders tool overrides and toggling one POSTs to /api/settings/policy/tool', async () => {
    const user = userEvent.setup()
    const policy: ToolPolicy = { default_allow: true, tools: { run_command: { allow: true } } }
    const { calls, setPolicy } = renderTab({ policy })

    expect(screen.getByText('run_command')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Allowed' }))

    await waitFor(() => {
      const post = calls.find((c) => c.url === '/api/settings/policy/tool' && c.init?.method === 'POST')
      expect(post).toBeTruthy()
      expect(JSON.parse(post!.init!.body as string)).toEqual({ tool: 'run_command', allow: false })
    })
    // setPolicy is called with a functional updater here, not a plain object.
    expect(setPolicy).toHaveBeenCalledTimes(1)
    const updater = setPolicy.mock.calls[0][0] as (prev: ToolPolicy) => ToolPolicy
    expect(updater(policy)).toEqual({
      ...policy,
      tools: { run_command: { allow: false } },
    })
  })

  it('removing a tool override DELETEs /api/settings/policy/tool/:name', async () => {
    const user = userEvent.setup()
    const policy: ToolPolicy = { default_allow: true, tools: { run_command: { allow: true } } }
    const { calls, setPolicy } = renderTab({ policy })

    const trashButtons = screen.getAllByRole('button').filter((b) => b.querySelector('svg.lucide-trash2'))
    await user.click(trashButtons[0])

    await waitFor(() => {
      const del = calls.find((c) => c.url === '/api/settings/policy/tool/run_command' && c.init?.method === 'DELETE')
      expect(del).toBeTruthy()
    })
    expect(setPolicy).toHaveBeenCalledTimes(1)
    const updater = setPolicy.mock.calls[0][0] as (prev: ToolPolicy) => ToolPolicy
    expect(updater(policy)).toEqual({ ...policy, tools: {} })
  })

  it('shows the configured policy file path', () => {
    renderTab({ policyPath: 'custom/policy.yml' })
    expect(screen.getByText('custom/policy.yml')).toBeTruthy()
  })
})
