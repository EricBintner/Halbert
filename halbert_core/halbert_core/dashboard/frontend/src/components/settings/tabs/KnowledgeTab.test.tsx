// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * FE-15: KnowledgeTab.tsx had zero test coverage despite being the biggest
 * settings tab (self-knowledge, RAG sources, doc suggestions, trending
 * topics, and the add-custom-source form). It is a purely presentational
 * component — Settings.tsx owns every fetch and every piece of state, this
 * component only renders props and calls the callbacks it's given — so
 * these tests drive it entirely through props, no network mocking needed
 * for the tab itself.
 *
 * DataVersionCard (rendered unconditionally at the top) fetches its own
 * data on mount; it's stubbed out here since its own behavior isn't this
 * file's concern.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { KnowledgeTab } from './KnowledgeTab'
import type {
  AddSourceResult,
  CoreSource,
  CustomDoc,
  DocFreshness,
  DocSuggestion,
  IndexProgress,
  NewKnowledge,
  RagIndex,
  RagStats,
  SelfKnowledgeEntry,
  TrendingSuggestion,
  UserStack,
} from './KnowledgeTab'

vi.mock('@/components/domain', () => ({
  DataVersionCard: () => <div data-testid="data-version-card" />,
}))

const emptyIndexProgress: IndexProgress = { percent: 0, currentSource: null, completed: 0, total: 0 }

function baseProps() {
  return {
    selfKnowledge: [] as SelfKnowledgeEntry[],
    loadingSelfKnowledge: false,
    onLoadSelfKnowledge: vi.fn(),
    showAddKnowledge: false,
    setShowAddKnowledge: vi.fn(),
    newKnowledge: { subject: '', content: '', rationale: '' } as NewKnowledge,
    setNewKnowledge: vi.fn(),
    addingKnowledge: false,
    onAddSelfKnowledge: vi.fn(),
    onDeleteKnowledge: vi.fn(),
    ragStats: null as RagStats | null,
    ragIndexes: [] as RagIndex[],
    docFreshness: null as DocFreshness | null,
    indexing: false,
    indexProgress: emptyIndexProgress,
    onReindex: vi.fn(),
    showDocList: false,
    loadingDocs: false,
    customDocs: [] as CustomDoc[],
    coreSources: [] as CoreSource[],
    onToggleDocList: vi.fn(),
    docSuggestions: [] as DocSuggestion[],
    loadingSuggestions: false,
    addingSuggestion: null as string | null,
    onAddSuggestion: vi.fn(),
    onDismissSuggestion: vi.fn(),
    trendingSuggestions: [] as TrendingSuggestion[],
    loadingTrending: false,
    userStack: null as UserStack | null,
    showTrending: true,
    setShowTrending: vi.fn(),
    trendingEnabled: true,
    setTrendingEnabled: vi.fn(),
    onLoadTrendingSuggestions: vi.fn(),
    setTrendingSuggestions: vi.fn(),
    showAddKnowledgeSource: false,
    setShowAddKnowledgeSource: vi.fn(),
    newSourceUrl: '',
    setNewSourceUrl: vi.fn(),
    newSourceName: '',
    setNewSourceName: vi.fn(),
    addingSource: false,
    addSourceResult: null as AddSourceResult | null,
    onAddKnowledgeSource: vi.fn(),
  }
}

function selfKnowledgeEntry(overrides: Partial<SelfKnowledgeEntry> = {}): SelfKnowledgeEntry {
  return {
    id: 'k1',
    type: 'system_fact',
    subject: 'Main pool',
    content: 'A bcachefs pool spanning 3 drives.',
    source: 'user',
    ...overrides,
  }
}

describe('KnowledgeTab', () => {
  it('renders the data version card', () => {
    render(<KnowledgeTab {...baseProps()} />)
    expect(screen.getByTestId('data-version-card')).toBeInTheDocument()
  })

  describe('self-knowledge', () => {
    it('shows the empty state when there is no self-knowledge', () => {
      render(<KnowledgeTab {...baseProps()} />)
      expect(screen.getByText(/No self-knowledge yet/i)).toBeInTheDocument()
    })

    it('lists entries and shows delete only for user-sourced ones', () => {
      render(
        <KnowledgeTab
          {...baseProps()}
          selfKnowledge={[
            selfKnowledgeEntry({ id: 'u1', subject: 'User fact', source: 'user' }),
            selfKnowledgeEntry({ id: 's1', subject: 'System fact', source: 'system' }),
          ]}
        />,
      )
      expect(screen.getByText('User fact')).toBeInTheDocument()
      expect(screen.getByText('System fact')).toBeInTheDocument()
      // Only one delete (trash) button — the user-sourced entry.
      const deleteButtons = screen.getAllByRole('button').filter((b) => b.querySelector('svg.lucide-trash2'))
      expect(deleteButtons).toHaveLength(1)
    })

    it('deleting an entry calls onDeleteKnowledge with its id', async () => {
      const user = userEvent.setup()
      const onDeleteKnowledge = vi.fn()
      render(
        <KnowledgeTab
          {...baseProps()}
          onDeleteKnowledge={onDeleteKnowledge}
          selfKnowledge={[selfKnowledgeEntry({ id: 'u1', source: 'user' })]}
        />,
      )
      const deleteButton = screen.getAllByRole('button').find((b) => b.querySelector('svg.lucide-trash2'))!
      await user.click(deleteButton)
      expect(onDeleteKnowledge).toHaveBeenCalledWith('u1')
    })

    it('shows the loading state instead of the list or empty state', () => {
      render(<KnowledgeTab {...baseProps()} loadingSelfKnowledge selfKnowledge={[selfKnowledgeEntry()]} />)
      expect(screen.getByText(/^Loading\.\.\.$/)).toBeInTheDocument()
      expect(screen.queryByText('Main pool')).not.toBeInTheDocument()
    })

    it('the Teach Something New form toggles and Save is disabled until subject and content are filled', async () => {
      const user = userEvent.setup()
      const setShowAddKnowledge = vi.fn()
      const { rerender } = render(
        <KnowledgeTab {...baseProps()} setShowAddKnowledge={setShowAddKnowledge} />,
      )
      expect(screen.queryByText('Save Knowledge')).not.toBeInTheDocument()

      await user.click(screen.getByText('Teach Something New'))
      expect(setShowAddKnowledge).toHaveBeenCalledWith(true)

      rerender(<KnowledgeTab {...baseProps()} showAddKnowledge />)
      expect(screen.getByRole('button', { name: /Save Knowledge/i })).toBeDisabled()

      rerender(
        <KnowledgeTab
          {...baseProps()}
          showAddKnowledge
          newKnowledge={{ subject: 'X', content: 'Y', rationale: '' }}
        />,
      )
      expect(screen.getByRole('button', { name: /Save Knowledge/i })).not.toBeDisabled()
    })

    it('saving calls onAddSelfKnowledge', async () => {
      const user = userEvent.setup()
      const onAddSelfKnowledge = vi.fn()
      render(
        <KnowledgeTab
          {...baseProps()}
          showAddKnowledge
          newKnowledge={{ subject: 'X', content: 'Y', rationale: '' }}
          onAddSelfKnowledge={onAddSelfKnowledge}
        />,
      )
      await user.click(screen.getByRole('button', { name: /Save Knowledge/i }))
      expect(onAddSelfKnowledge).toHaveBeenCalled()
    })
  })

  describe('RAG sources', () => {
    it('shows the total/custom doc counts and last-indexed date', () => {
      render(
        <KnowledgeTab
          {...baseProps()}
          ragStats={{ total_docs: 1234, user_docs: 5, sources: {} }}
          docFreshness={{ last_indexed_at: '2026-08-01T00:00:00Z', docs_at_last_index: 1234, info: '' }}
        />,
      )
      expect(screen.getByText('1,234 docs')).toBeInTheDocument()
      expect(screen.getByText('5 docs')).toBeInTheDocument()
    })

    it('shows "Never" when there is no last-indexed date', () => {
      render(<KnowledgeTab {...baseProps()} />)
      expect(screen.getByText('Never')).toBeInTheDocument()
    })

    it('Re-index calls onReindex and disables while indexing, showing progress', () => {
      const onReindex = vi.fn()
      const { rerender } = render(<KnowledgeTab {...baseProps()} onReindex={onReindex} />)
      expect(screen.getByRole('button', { name: /Re-index/i })).not.toBeDisabled()

      rerender(
        <KnowledgeTab
          {...baseProps()}
          onReindex={onReindex}
          indexing
          indexProgress={{ percent: 42, currentSource: 'arch-wiki', completed: 3, total: 7 }}
        />,
      )
      expect(screen.getByRole('button', { name: /Indexing/i })).toBeDisabled()
      expect(screen.getByText(/Processing: arch-wiki/)).toBeInTheDocument()
      expect(screen.getByText('42% (3/7 sources)')).toBeInTheDocument()
    })

    it('View All toggles the doc list and calls onToggleDocList', async () => {
      const user = userEvent.setup()
      const onToggleDocList = vi.fn()
      render(<KnowledgeTab {...baseProps()} onToggleDocList={onToggleDocList} />)
      await user.click(screen.getByRole('button', { name: /View All/i }))
      expect(onToggleDocList).toHaveBeenCalled()
    })

    it('renders core and custom sources in the doc list table when shown', () => {
      render(
        <KnowledgeTab
          {...baseProps()}
          showDocList
          coreSources={[{ name: 'Arch Wiki', count: 500 }]}
          customDocs={[{ name: 'My Docs', source: 'custom', url: 'https://example.com', trust_tier: 1, is_custom: true }]}
        />,
      )
      expect(screen.getByText('Arch Wiki')).toBeInTheDocument()
      expect(screen.getByText('My Docs')).toBeInTheDocument()
      expect(screen.getByText('Custom Added (1)')).toBeInTheDocument()
    })

    it('renders RAG search indexes when present', () => {
      render(
        <KnowledgeTab
          {...baseProps()}
          ragIndexes={[
            {
              name: 'arch_wiki',
              doc_count: 500,
              indexed_at: '2026-08-01',
              source_file: 'x.jsonl',
              embedding_model: 'bge-small',
              build_time_seconds: 12.3,
            },
          ]}
        />,
      )
      expect(screen.getByText('Arch Wiki')).toBeInTheDocument()
      expect(screen.getByText('500 docs')).toBeInTheDocument()
      expect(screen.getByText('12.3s')).toBeInTheDocument()
    })
  })

  describe('suggested documentation', () => {
    function suggestion(overrides: Partial<DocSuggestion> = {}): DocSuggestion {
      return {
        doc_key: 'nginx',
        doc_name: 'Nginx',
        doc_url: 'https://nginx.org/docs',
        doc_description: '',
        doc_category: 'webserver',
        discovery_id: 'd1',
        discovery_name: 'nginx',
        confidence: 0.9,
        reason: 'nginx is running',
        priority: 1,
        ...overrides,
      }
    }

    it('adding a suggestion calls onAddSuggestion with its doc_key', async () => {
      const user = userEvent.setup()
      const onAddSuggestion = vi.fn()
      render(
        <KnowledgeTab {...baseProps()} docSuggestions={[suggestion()]} onAddSuggestion={onAddSuggestion} />,
      )
      await user.click(screen.getByRole('button', { name: /^Add$/i }))
      expect(onAddSuggestion).toHaveBeenCalledWith('nginx')
    })

    it('dismissing a suggestion calls onDismissSuggestion with its doc_key', async () => {
      const user = userEvent.setup()
      const onDismissSuggestion = vi.fn()
      render(
        <KnowledgeTab
          {...baseProps()}
          docSuggestions={[suggestion()]}
          onDismissSuggestion={onDismissSuggestion}
        />,
      )
      // The dismiss button is the icon-only ghost button (X icon) beside Add.
      const buttons = screen.getAllByRole('button')
      const dismiss = buttons.find((b) => b.querySelector('svg.lucide-x') && !b.textContent?.includes('Add'))!
      await user.click(dismiss)
      expect(onDismissSuggestion).toHaveBeenCalledWith('nginx')
    })
  })

  describe('trending topics', () => {
    it('toggling the section calls setShowTrending', async () => {
      const user = userEvent.setup()
      const setShowTrending = vi.fn()
      render(<KnowledgeTab {...baseProps()} setShowTrending={setShowTrending} />)
      await user.click(screen.getByText('Trending on GitHub'))
      expect(setShowTrending).toHaveBeenCalledWith(false)
    })

    it('shows the empty message when there are no trending repos', () => {
      render(<KnowledgeTab {...baseProps()} showTrending />)
      expect(screen.getByText(/No trending repos found/i)).toBeInTheDocument()
    })

    it('renders trending repos with stack matches', () => {
      render(
        <KnowledgeTab
          {...baseProps()}
          showTrending
          trendingSuggestions={[
            {
              name: 'cool-tool',
              full_name: 'org/cool-tool',
              description: 'A cool tool',
              url: 'https://github.com/org/cool-tool',
              doc_url: '',
              stars: 1500,
              language: 'Rust',
              relevance_score: 0.8,
              reason: 'matches your stack',
              stack_match: ['rust'],
              has_docs: false,
            },
          ]}
        />,
      )
      expect(screen.getByText('cool-tool')).toBeInTheDocument()
      expect(screen.getByText(/1,500/)).toBeInTheDocument()
    })

    it('the auto-discover checkbox reflects and updates trendingEnabled', async () => {
      const user = userEvent.setup()
      const setTrendingEnabled = vi.fn()
      render(
        <KnowledgeTab
          {...baseProps()}
          showTrending
          trendingEnabled={false}
          setTrendingEnabled={setTrendingEnabled}
        />,
      )
      const checkbox = screen.getByRole('checkbox', { name: /Auto-discover/i })
      expect(checkbox).not.toBeChecked()
      await user.click(checkbox)
      expect(setTrendingEnabled).toHaveBeenCalledWith(true)
    })
  })

  describe('add custom documentation source', () => {
    it('toggling the section calls setShowAddKnowledgeSource', async () => {
      const user = userEvent.setup()
      const setShowAddKnowledgeSource = vi.fn()
      render(<KnowledgeTab {...baseProps()} setShowAddKnowledgeSource={setShowAddKnowledgeSource} />)
      await user.click(screen.getByText('Add Custom Documentation'))
      expect(setShowAddKnowledgeSource).toHaveBeenCalledWith(true)
    })

    it('Add Source is disabled until a URL is entered', () => {
      const { rerender } = render(<KnowledgeTab {...baseProps()} showAddKnowledgeSource />)
      expect(screen.getByRole('button', { name: /Add Source/i })).toBeDisabled()

      rerender(<KnowledgeTab {...baseProps()} showAddKnowledgeSource newSourceUrl="https://docs.example.com" />)
      expect(screen.getByRole('button', { name: /Add Source/i })).not.toBeDisabled()
    })

    it('submitting calls onAddKnowledgeSource', async () => {
      const user = userEvent.setup()
      const onAddKnowledgeSource = vi.fn()
      render(
        <KnowledgeTab
          {...baseProps()}
          showAddKnowledgeSource
          newSourceUrl="https://docs.example.com"
          onAddKnowledgeSource={onAddKnowledgeSource}
        />,
      )
      await user.click(screen.getByRole('button', { name: /Add Source/i }))
      expect(onAddKnowledgeSource).toHaveBeenCalled()
    })

    it('shows the success result with the discovered title', () => {
      render(
        <KnowledgeTab
          {...baseProps()}
          showAddKnowledgeSource
          addSourceResult={{ success: true, message: 'Added successfully!', title: 'Example Docs' }}
        />,
      )
      expect(screen.getByText(/Added successfully!: Example Docs/)).toBeInTheDocument()
    })

    it('shows the failure result', () => {
      render(
        <KnowledgeTab
          {...baseProps()}
          showAddKnowledgeSource
          addSourceResult={{ success: false, message: 'Failed to add source' }}
        />,
      )
      expect(screen.getByText('Failed to add source')).toBeInTheDocument()
    })
  })
})
