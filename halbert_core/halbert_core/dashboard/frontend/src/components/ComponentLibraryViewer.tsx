/**
 * Component Library Viewer - Interactive component documentation
 * 
 * A full-screen overlay that showcases all UI components with live previews,
 * props documentation, and copy-paste code snippets.
 * 
 * Access: Settings → About → "View Component Library"
 */

import { useState } from 'react'
import { createPortal } from 'react-dom'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { 
  X, 
  Search, 
  ChevronDown, 
  ChevronRight, 
  Copy, 
  Check,
  Palette,
  Box,
  Sparkles,
  Ruler,
  Sun,
  Moon,
  Monitor,
} from 'lucide-react'
import { cn } from '@/lib/utils'

// Domain components
import { SystemItemActions, StatusBadge, UsageBar, EmptyState, CodeBlock, MarkdownRenderer, PageHeader } from '@/components/domain'
import { WhyBrain } from '@/components/ui/why-brain'

interface ComponentLibraryViewerProps {
  onClose: () => void
}

interface PropDef {
  name: string
  type: string
  default?: string
  description?: string
}

interface ComponentExample {
  id: string
  name: string
  description: string
  status: 'stable' | 'beta' | 'deprecated'
  preview: React.ReactNode
  props: PropDef[]
  code: string
}

interface ComponentCategory {
  id: string
  name: string
  icon: React.ReactNode
  components: ComponentExample[]
}

// ═══════════════════════════════════════════════════════════════════════════
// DESIGN SYSTEM STANDARDS - These values are the source of truth
// ═══════════════════════════════════════════════════════════════════════════
const DESIGN_SYSTEM = {
  iconButton: {
    sm: { button: 'h-7 w-7', icon: 'h-4 w-4' },
    default: { button: 'h-8 w-8', icon: 'h-4 w-4' },
  },
  // @ symbol must be larger than icons because text is optically smaller
  atSymbol: {
    sm: 'text-base font-bold',
    default: 'text-lg font-bold',
  },
  // Inactive state for all action icons
  inactiveColor: 'text-muted-foreground/60',
  // Hover colors by action type
  hoverColors: {
    mention: 'hover:text-blue-500 hover:bg-blue-500/10',
    chat: 'hover:text-primary hover:bg-primary/10',
    research: 'hover:text-purple-500 hover:bg-purple-500/10',
    whyDefined: 'text-pink-500 hover:text-pink-400',
    whyUndefined: 'text-muted-foreground/60 hover:text-muted-foreground',
  },
}

// Component definitions
const COMPONENT_LIBRARY: ComponentCategory[] = [
  {
    id: 'design-system',
    name: 'Design System',
    icon: <Ruler className="h-4 w-4" />,
    components: [
      {
        id: 'typography',
        name: 'Typography',
        description: 'Montserrat font family with consistent type scale',
        status: 'stable',
        preview: (
          <div className="space-y-6 w-full">
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground uppercase tracking-wide">Font Family</p>
              <p className="text-2xl">Montserrat</p>
            </div>
            <div className="space-y-4">
              <div className="flex items-baseline gap-4">
                <span className="text-3xl font-bold">H1</span>
                <span className="text-xs text-muted-foreground">30px / Bold / tracking-tight</span>
              </div>
              <div className="flex items-baseline gap-4">
                <span className="text-2xl font-semibold">H2</span>
                <span className="text-xs text-muted-foreground">24px / SemiBold / tracking-tight</span>
              </div>
              <div className="flex items-baseline gap-4">
                <span className="text-lg font-semibold">H3</span>
                <span className="text-xs text-muted-foreground">18px / SemiBold</span>
              </div>
              <div className="flex items-baseline gap-4">
                <span className="text-base font-semibold">H4</span>
                <span className="text-xs text-muted-foreground">16px / SemiBold</span>
              </div>
              <div className="flex items-baseline gap-4">
                <span className="text-sm">Body</span>
                <span className="text-xs text-muted-foreground">14px / Regular</span>
              </div>
              <div className="flex items-baseline gap-4">
                <span className="text-xs">Small</span>
                <span className="text-xs text-muted-foreground">12px / Regular</span>
              </div>
            </div>
            <div className="pt-4 border-t space-y-2">
              <p className="text-xs text-muted-foreground uppercase tracking-wide">Font Weights</p>
              <div className="flex gap-6">
                <span className="font-normal">400</span>
                <span className="font-medium">500</span>
                <span className="font-semibold">600</span>
                <span className="font-bold">700</span>
              </div>
            </div>
          </div>
        ),
        props: [],
        code: `/* Brand Typography - Montserrat */

/* Headings (auto-applied via index.css) */
h1 { @apply text-3xl font-bold tracking-tight; }
h2 { @apply text-2xl font-semibold tracking-tight; }
h3 { @apply text-lg font-semibold; }
h4 { @apply text-base font-semibold; }

/* Manual usage */
<h1 className="text-3xl font-bold">Page Title</h1>
<p className="text-sm">Body text</p>
<span className="text-xs text-muted-foreground">Caption</span>`,
      },
      {
        id: 'colors',
        name: 'Colors',
        description: 'Semantic color tokens for light and dark themes',
        status: 'stable',
        preview: (
          <div className="space-y-6 w-full">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Core</p>
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded bg-primary" />
                  <span className="text-xs">primary</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded bg-secondary border" />
                  <span className="text-xs">secondary</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded bg-muted border" />
                  <span className="text-xs">muted</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded bg-destructive" />
                  <span className="text-xs">destructive</span>
                </div>
              </div>
              <div className="space-y-2">
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Brand Accents</p>
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded bg-pink-500" />
                  <span className="text-xs">Brain Pink</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded bg-purple-500" />
                  <span className="text-xs">Research</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded bg-blue-500" />
                  <span className="text-xs">Mention</span>
                </div>
              </div>
            </div>
            <div className="pt-4 border-t space-y-2">
              <p className="text-xs text-muted-foreground uppercase tracking-wide">Status</p>
              <div className="flex gap-4">
                <span className="text-green-500">Success</span>
                <span className="text-yellow-500">Warning</span>
                <span className="text-red-500">Error</span>
                <span className="text-blue-500">Info</span>
              </div>
            </div>
          </div>
        ),
        props: [],
        code: `/* Semantic Color Tokens */
bg-background / text-foreground   /* Main surfaces */
bg-primary / text-primary         /* Brand actions */
bg-secondary / text-secondary     /* Alternative */
bg-muted / text-muted-foreground  /* Subdued */
bg-destructive                    /* Danger */

/* Brand Accents */
text-pink-500    /* WhyBrain, AI */
text-purple-500  /* Research */
text-blue-500    /* Mentions */

/* Status Colors */
text-green-500   /* Success */
text-yellow-500  /* Warning */
text-red-500     /* Error */`,
      },
      {
        id: 'icon-button-sizing',
        name: 'Icon Button Sizing',
        description: 'Standard sizes for all icon buttons - THIS IS THE SOURCE OF TRUTH',
        status: 'stable',
        preview: (
          <div className="space-y-6">
            <div>
              <h4 className="text-sm font-medium mb-3">Size: sm (used in row actions)</h4>
              <div className="flex items-center gap-4 p-3 bg-muted/30 rounded-lg">
                <div className="flex items-center gap-0">
                  <WhyBrain itemId="sizing-demo" itemName="Demo" itemType="service" size="sm" />
                  <SystemItemActions item={{ name: 'Demo', type: 'service', id: 'demo' }} size="sm" />
                </div>
                <code className="text-xs bg-muted text-foreground px-2 py-1 rounded border">
                  button: {DESIGN_SYSTEM.iconButton.sm.button} | icon: {DESIGN_SYSTEM.iconButton.sm.icon}
                </code>
              </div>
            </div>
            <div>
              <h4 className="text-sm font-medium mb-3">Size: default</h4>
              <div className="flex items-center gap-4 p-3 bg-muted/30 rounded-lg">
                <div className="flex items-center gap-0">
                  <WhyBrain itemId="sizing-demo-2" itemName="Demo" itemType="service" size="md" />
                  <SystemItemActions item={{ name: 'Demo', type: 'service', id: 'demo' }} />
                </div>
                <code className="text-xs bg-muted text-foreground px-2 py-1 rounded border">
                  button: {DESIGN_SYSTEM.iconButton.default.button} | icon: {DESIGN_SYSTEM.iconButton.default.icon}
                </code>
              </div>
            </div>
            <div>
              <h4 className="text-sm font-medium mb-3">@ Symbol (larger for optical balance)</h4>
              <div className="flex items-center gap-4 p-3 bg-muted/30 rounded-lg">
                <code className="text-xs bg-muted text-foreground px-2 py-1 rounded border">
                  sm: {DESIGN_SYSTEM.atSymbol.sm} | default: {DESIGN_SYSTEM.atSymbol.default}
                </code>
              </div>
            </div>
          </div>
        ),
        props: [],
        code: `// DESIGN SYSTEM STANDARDS
const DESIGN_SYSTEM = {
  iconButton: {
    sm: { button: 'h-7 w-7', icon: 'h-4 w-4' },
    default: { button: 'h-8 w-8', icon: 'h-4 w-4' },
  },
  atSymbol: {
    sm: 'text-base font-bold',
    default: 'text-lg font-bold',
  },
  inactiveColor: 'text-muted-foreground/60',
}`,
      },
      {
        id: 'color-system',
        name: 'Action Colors',
        description: 'Standard hover colors for action buttons',
        status: 'stable',
        preview: (
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <div className={cn("w-8 h-8 rounded flex items-center justify-center", DESIGN_SYSTEM.hoverColors.mention.replace('hover:', ''))}>
                <span className="text-base font-bold">@</span>
              </div>
              <span className="text-sm">Mention: <code className="text-xs bg-muted text-foreground px-1 rounded border">blue-500</code></span>
            </div>
            <div className="flex items-center gap-3">
              <div className={cn("w-8 h-8 rounded flex items-center justify-center text-primary bg-primary/10")}>
                <span className="text-sm">★</span>
              </div>
              <span className="text-sm">Chat: <code className="text-xs bg-muted text-foreground px-1 rounded border">primary</code></span>
            </div>
            <div className="flex items-center gap-3">
              <div className={cn("w-8 h-8 rounded flex items-center justify-center text-purple-500 bg-purple-500/10")}>
                <span className="text-sm">✨</span>
              </div>
              <span className="text-sm">Research: <code className="text-xs bg-muted text-foreground px-1 rounded border">purple-500</code></span>
            </div>
            <div className="flex items-center gap-3">
              <div className={cn("w-8 h-8 rounded flex items-center justify-center text-pink-500")}>
                <span className="text-sm">🧠</span>
              </div>
              <span className="text-sm">Why (defined): <code className="text-xs bg-muted text-foreground px-1 rounded border">pink-500</code></span>
            </div>
            <div className="flex items-center gap-3">
              <div className={cn("w-8 h-8 rounded flex items-center justify-center text-muted-foreground/60")}>
                <span className="text-sm">🧠</span>
              </div>
              <span className="text-sm">Inactive: <code className="text-xs bg-muted text-foreground px-1 rounded border">muted-foreground/60</code></span>
            </div>
          </div>
        ),
        props: [],
        code: `// Hover colors by action type
hoverColors: {
  mention: 'hover:text-blue-500 hover:bg-blue-500/10',
  chat: 'hover:text-primary hover:bg-primary/10',
  research: 'hover:text-purple-500 hover:bg-purple-500/10',
  whyDefined: 'text-pink-500 hover:text-pink-400',
  whyUndefined: 'text-muted-foreground/60 hover:text-muted-foreground',
}`,
      },
    ],
  },
  {
    id: 'domain',
    name: 'Domain Components',
    icon: <Sparkles className="h-4 w-4" />,
    components: [
      {
        id: 'system-item-actions',
        name: 'SystemItemActions',
        description: 'Universal action buttons for system items (@ mention, chat, research)',
        status: 'stable',
        preview: (
          <div className="space-y-4">
            <div className="flex items-center gap-4">
              <span className="text-sm text-muted-foreground w-20">icon:</span>
              <SystemItemActions 
                item={{ name: 'Example Item', type: 'storage', id: 'example', context: 'Example context' }}
              />
            </div>
            <div className="flex items-center gap-4">
              <span className="text-sm text-muted-foreground w-20">compact:</span>
              <SystemItemActions 
                item={{ name: 'Example Item', type: 'storage', id: 'example' }}
                variant="compact"
              />
            </div>
            <div className="flex items-center gap-4">
              <span className="text-sm text-muted-foreground w-20">full:</span>
              <SystemItemActions 
                item={{ name: 'Example Item', type: 'storage', id: 'example' }}
                variant="full"
              />
            </div>
            <div className="flex items-center gap-4">
              <span className="text-sm text-muted-foreground w-20">+ research:</span>
              <SystemItemActions 
                item={{ name: 'Example Item', type: 'storage', id: 'example' }}
                showResearch
              />
            </div>
          </div>
        ),
        props: [
          { name: 'item', type: 'SystemItem', description: 'The system item (name, type, id, context)' },
          { name: 'showMention', type: 'boolean', default: 'true', description: 'Show @ button' },
          { name: 'showChat', type: 'boolean', default: 'true', description: 'Show chat button' },
          { name: 'showResearch', type: 'boolean', default: 'false', description: 'Show research button' },
          { name: 'variant', type: "'icon' | 'compact' | 'full'", default: "'icon'", description: 'Button style' },
          { name: 'size', type: "'sm' | 'default'", default: "'default'", description: 'Button size' },
        ],
        code: `import { SystemItemActions } from '@/components/domain'

<SystemItemActions
  item={{
    name: 'Main Storage',
    type: 'storage',
    id: 'main-storage',
    context: 'Storage device info...',
  }}
  showResearch
  variant="icon"
  size="sm"
/>`,
      },
      {
        id: 'why-brain',
        name: 'WhyBrain',
        description: 'Brain icon for "why" explanations - shows if item has explanation',
        status: 'stable',
        preview: (
          <div className="space-y-4">
            <div className="flex items-center gap-4">
              <span className="text-sm text-muted-foreground w-32">undefined (sm):</span>
              <WhyBrain itemId="demo-undefined" itemName="Demo" itemType="service" size="sm" />
            </div>
            <div className="flex items-center gap-4">
              <span className="text-sm text-muted-foreground w-32">with SystemItemActions:</span>
              <div className="flex items-center gap-0">
                <WhyBrain itemId="demo-combo" itemName="Demo" itemType="service" size="sm" />
                <SystemItemActions 
                  item={{ name: 'Demo', type: 'service', id: 'demo' }}
                  size="sm"
                />
              </div>
            </div>
          </div>
        ),
        props: [
          { name: 'itemId', type: 'string', description: 'Unique identifier for the item' },
          { name: 'itemName', type: 'string', description: 'Display name of the item' },
          { name: 'itemType', type: 'string', description: 'Type of item (service, storage, etc)' },
          { name: 'size', type: "'sm' | 'md' | 'lg'", default: "'md'", description: 'Button size' },
        ],
        code: `import { WhyBrain } from '@/components/ui/why-brain'

{/* Always pair with SystemItemActions for consistent spacing */}
<div className="flex items-center gap-0">
  <WhyBrain
    itemId={\`service:\${name}\`}
    itemName={name}
    itemType="service"
    size="sm"
  />
  <SystemItemActions
    item={{ name, type: 'service', id }}
    size="sm"
  />
</div>`,
      },
      {
        id: 'status-badge',
        name: 'StatusBadge',
        description: 'Severity-colored status badge with automatic styling',
        status: 'stable',
        preview: (
          <div className="flex flex-wrap gap-3">
            <StatusBadge status="Running" severity="success" />
            <StatusBadge status="Warning" severity="warning" />
            <StatusBadge status="Failed" severity="critical" />
            <StatusBadge status="Pending" severity="info" />
            <StatusBadge status="Unknown" severity="unknown" />
            <StatusBadge status="With Icon" severity="success" showIcon />
          </div>
        ),
        props: [
          { name: 'status', type: 'string', description: 'Display text' },
          { name: 'severity', type: "'success' | 'warning' | 'critical' | 'info' | 'unknown'", description: 'Color scheme' },
          { name: 'showIcon', type: 'boolean', default: 'false', description: 'Show status icon' },
          { name: 'size', type: "'sm' | 'default'", default: "'default'", description: 'Badge size' },
        ],
        code: `import { StatusBadge } from '@/components/domain'

<StatusBadge status="Running" severity="success" />
<StatusBadge status="Failed" severity="critical" showIcon />`,
      },
      {
        id: 'usage-bar',
        name: 'UsageBar',
        description: 'Percentage progress bar with automatic color coding based on thresholds',
        status: 'stable',
        preview: (
          <div className="space-y-3 w-full max-w-md">
            <UsageBar percent={45} />
            <UsageBar percent={78} />
            <UsageBar percent={95} />
            <UsageBar percent={60} used="60GB" total="100GB" />
            <UsageBar percent={85} showPercent={false} height="sm" />
          </div>
        ),
        props: [
          { name: 'percent', type: 'number', description: 'Usage percentage (0-100)' },
          { name: 'used', type: 'string', description: 'Used amount label' },
          { name: 'total', type: 'string', description: 'Total amount label' },
          { name: 'showPercent', type: 'boolean', default: 'true', description: 'Show percentage' },
          { name: 'warningThreshold', type: 'number', default: '75', description: 'Yellow threshold' },
          { name: 'criticalThreshold', type: 'number', default: '90', description: 'Red threshold' },
          { name: 'height', type: "'sm' | 'default'", default: "'default'", description: 'Bar height' },
        ],
        code: `import { UsageBar } from '@/components/domain'

<UsageBar percent={75} />
<UsageBar percent={92} used="92GB" total="100GB" />
<UsageBar percent={45} showPercent={false} height="sm" />`,
      },
      {
        id: 'empty-state',
        name: 'EmptyState',
        description: 'Consistent placeholder for empty lists or no results',
        status: 'stable',
        preview: (
          <EmptyState
            title="No Items Found"
            description="Try adjusting your search or add new items."
            action={<Button size="sm">Add Item</Button>}
          />
        ),
        props: [
          { name: 'icon', type: 'React.ReactNode', description: 'Custom icon' },
          { name: 'title', type: 'string', description: 'Title text' },
          { name: 'description', type: 'string', description: 'Description text' },
          { name: 'action', type: 'React.ReactNode', description: 'Action button' },
        ],
        code: `import { EmptyState } from '@/components/domain'
import { Archive } from 'lucide-react'

<EmptyState
  icon={<Archive className="h-12 w-12" />}
  title="No Backups Found"
  description="Click Scan to discover backup configurations."
  action={<Button onClick={handleScan}>Scan Now</Button>}
/>`,
      },
      {
        id: 'code-block',
        name: 'CodeBlock',
        description: 'Executable code block with copy and run buttons for shell commands',
        status: 'stable',
        preview: (
          <div className="space-y-4 w-full max-w-lg">
            <CodeBlock 
              code="sudo systemctl status nginx" 
              lang="bash"
            />
            <CodeBlock 
              code={`# This is output (non-runnable)
Active: active (running) since Mon 2025-12-16
Main PID: 1234 (nginx)`}
              lang="output"
            />
          </div>
        ),
        props: [
          { name: 'code', type: 'string', description: 'Code content to display' },
          { name: 'lang', type: 'string', default: "'bash'", description: 'Language for syntax hint' },
          { name: 'onRun', type: '(cmd: string) => Promise<Result>', description: 'Run callback' },
          { name: 'showRunButton', type: 'boolean', default: 'true', description: 'Show run button for shell' },
          { name: 'compact', type: 'boolean', default: 'false', description: 'Compact padding mode' },
        ],
        code: `import { CodeBlock } from '@/components/domain'

{/* Runnable shell command */}
<CodeBlock 
  code="sudo systemctl restart nginx" 
  lang="bash"
/>

{/* Display-only output */}
<CodeBlock 
  code="Active: running since..." 
  lang="output"
  showRunButton={false}
/>`,
      },
      {
        id: 'markdown-renderer',
        name: 'MarkdownRenderer',
        description: 'Renders LLM markdown output with headers, bullets, bold, links, and code blocks',
        status: 'stable',
        preview: (
          <div className="p-4 bg-muted/30 rounded-lg max-w-lg">
            <MarkdownRenderer text={`## Overview

This component handles **markdown** from AI responses.

- Supports headers (# and ##)
- **Bold text** and [links](https://example.com)
- Bullet lists like this one
- Embedded code blocks with run buttons`} />
          </div>
        ),
        props: [
          { name: 'text', type: 'string', description: 'Markdown text to render' },
          { name: 'onRunCommand', type: '(cmd: string) => Promise<Result>', description: 'Callback for code block execution' },
          { name: 'compact', type: 'boolean', default: 'false', description: 'Tighter spacing mode' },
        ],
        code: `import { MarkdownRenderer } from '@/components/domain'

<MarkdownRenderer 
  text={llmResponse}
  onRunCommand={async (cmd) => {
    const result = await executeCommand(cmd)
    return result
  }}
/>`,
      },
      {
        id: 'page-header',
        name: 'PageHeader',
        description: 'Consistent page header with title, icon, description, and scan button',
        status: 'stable',
        preview: (
          <div className="w-full max-w-2xl border rounded-lg p-4 bg-background">
            <PageHeader
              icon={<Box className="h-8 w-8" />}
              title="Example Page"
              description="A description of what this page shows"
              scanning={false}
              onScan={() => {}}
            />
          </div>
        ),
        props: [
          { name: 'icon', type: 'React.ReactNode', description: 'Icon next to title' },
          { name: 'title', type: 'string', description: 'Page title' },
          { name: 'description', type: 'string', description: 'Subtitle text' },
          { name: 'scanning', type: 'boolean', default: 'false', description: 'Show loading state' },
          { name: 'onScan', type: '() => void', description: 'Scan button callback' },
          { name: 'scanText', type: 'string', default: "'Scan'", description: 'Custom button text' },
          { name: 'actions', type: 'React.ReactNode', description: 'Additional action buttons' },
          { name: 'hideScanButton', type: 'boolean', default: 'false', description: 'Hide scan button' },
        ],
        code: `import { PageHeader } from '@/components/domain'
import { Archive } from 'lucide-react'

<PageHeader
  icon={<Archive className="h-8 w-8" />}
  title="Backups"
  description="Discovered backup configurations on your system"
  scanning={scanning}
  onScan={handleScan}
/>`,
      },
    ],
  },
  {
    id: 'primitives',
    name: 'UI Primitives',
    icon: <Box className="h-4 w-4" />,
    components: [
      {
        id: 'button',
        name: 'Button',
        description: 'Primary interactive element with multiple variants and sizes',
        status: 'stable',
        preview: (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Button>Default</Button>
              <Button variant="secondary">Secondary</Button>
              <Button variant="outline">Outline</Button>
              <Button variant="ghost">Ghost</Button>
              <Button variant="destructive">Destructive</Button>
              <Button variant="link">Link</Button>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm">Small</Button>
              <Button size="default">Default</Button>
              <Button size="lg">Large</Button>
              <Button size="icon"><Search className="h-4 w-4" /></Button>
            </div>
          </div>
        ),
        props: [
          { name: 'variant', type: "'default' | 'secondary' | 'outline' | 'ghost' | 'destructive' | 'link'", default: "'default'" },
          { name: 'size', type: "'sm' | 'default' | 'lg' | 'icon'", default: "'default'" },
          { name: 'asChild', type: 'boolean', default: 'false' },
          { name: 'disabled', type: 'boolean', default: 'false' },
        ],
        code: `import { Button } from '@/components/ui/button'

<Button variant="outline" size="sm">
  Click me
</Button>`,
      },
      {
        id: 'badge',
        name: 'Badge',
        description: 'Small status indicator or label',
        status: 'stable',
        preview: (
          <div className="flex flex-wrap gap-2">
            <Badge>Default</Badge>
            <Badge variant="secondary">Secondary</Badge>
            <Badge variant="outline">Outline</Badge>
            <Badge variant="destructive">Destructive</Badge>
          </div>
        ),
        props: [
          { name: 'variant', type: "'default' | 'secondary' | 'outline' | 'destructive'", default: "'default'" },
        ],
        code: `import { Badge } from '@/components/ui/badge'

<Badge variant="outline">Status</Badge>`,
      },
      {
        id: 'card',
        name: 'Card',
        description: 'Container for related content with header, content, and footer',
        status: 'stable',
        preview: (
          <Card className="w-full max-w-sm">
            <CardHeader>
              <CardTitle>Card Title</CardTitle>
              <CardDescription>Card description goes here</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm">Card content with any elements.</p>
            </CardContent>
          </Card>
        ),
        props: [
          { name: 'className', type: 'string', description: 'Additional CSS classes' },
        ],
        code: `import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'

<Card>
  <CardHeader>
    <CardTitle>Title</CardTitle>
    <CardDescription>Description</CardDescription>
  </CardHeader>
  <CardContent>
    Content here
  </CardContent>
</Card>`,
      },
      {
        id: 'input',
        name: 'Input',
        description: 'Text input field',
        status: 'stable',
        preview: (
          <div className="space-y-2 w-full max-w-sm">
            <Input placeholder="Default input" />
            <Input placeholder="Disabled" disabled />
          </div>
        ),
        props: [
          { name: 'type', type: 'string', default: "'text'" },
          { name: 'placeholder', type: 'string' },
          { name: 'disabled', type: 'boolean', default: 'false' },
        ],
        code: `import { Input } from '@/components/ui/input'

<Input placeholder="Enter text..." />`,
      },
    ],
  },
  {
    id: 'hooks',
    name: 'Hooks',
    icon: <Sparkles className="h-4 w-4" />,
    components: [
      {
        id: 'use-scan-page',
        name: 'useScanPage',
        description: 'Hook for managing page scan state and triggering discovery scans',
        status: 'stable',
        preview: (
          <div className="w-full max-w-md space-y-4 p-4 border rounded-lg bg-background">
            <div className="text-sm font-mono bg-muted p-3 rounded">
              <div className="text-muted-foreground">// Usage in a page component</div>
              <div className="mt-2">
                <span className="text-blue-500">const</span> {'{'} scanning, handleScan {'}'} = <span className="text-purple-500">useScanPage</span>({'{'}
              </div>
              <div className="pl-4">scanType: <span className="text-green-500">'backup'</span>,</div>
              <div className="pl-4">onScanComplete: loadBackups,</div>
              <div>{'}'})</div>
            </div>
            <div className="text-xs text-muted-foreground">
              Returns <code className="bg-muted px-1 rounded">scanning</code> (boolean) and <code className="bg-muted px-1 rounded">handleScan</code> (async function)
            </div>
          </div>
        ),
        props: [
          { name: 'scanType', type: "'backup' | 'service' | 'storage' | 'network' | 'security' | 'sharing' | 'all'", description: 'Scanner to run' },
          { name: 'onScanComplete', type: '() => Promise<void>', description: 'Callback after scan finishes' },
          { name: 'onError', type: '(error: unknown) => void', description: 'Optional error handler' },
        ],
        code: `import { useScanPage } from '@/hooks'
import { PageHeader } from '@/components/domain'

function BackupsPage() {
  const [backups, setBackups] = useState([])
  
  const loadBackups = async () => {
    const data = await api.getDiscoveries('backup')
    setBackups(data.discoveries || [])
  }

  const { scanning, handleScan } = useScanPage({
    scanType: 'backup',
    onScanComplete: loadBackups,
  })

  return (
    <PageHeader
      title="Backups"
      scanning={scanning}
      onScan={handleScan}
    />
  )
}`,
      },
      {
        id: 'use-copy-to-clipboard',
        name: 'useCopyToClipboard',
        description: 'Hook for clipboard operations with visual feedback',
        status: 'stable',
        preview: (
          <div className="w-full max-w-md space-y-4 p-4 border rounded-lg bg-background">
            <div className="text-sm font-mono bg-muted p-3 rounded">
              <div className="text-muted-foreground">// Copy with feedback</div>
              <div className="mt-2">
                <span className="text-blue-500">const</span> {'{'} copy, isCopied {'}'} = <span className="text-purple-500">useCopyToClipboard</span>()
              </div>
              <div className="mt-2 text-muted-foreground">// In JSX:</div>
              <div>{'<button onClick={() => copy(text, id)>'}</div>
              <div className="pl-4">{'{isCopied(id) ? <Check /> : <Copy />}'}</div>
              <div>{'</button>'}</div>
            </div>
            <div className="text-xs text-muted-foreground">
              Auto-clears after 2 seconds (configurable via <code className="bg-muted px-1 rounded">timeout</code> option)
            </div>
          </div>
        ),
        props: [
          { name: 'timeout', type: 'number', default: '2000', description: 'Ms before clearing copied state' },
        ],
        code: `import { useCopyToClipboard } from '@/hooks'
import { Copy, Check } from 'lucide-react'

function CopyButton({ text, id }: { text: string; id: string }) {
  const { copy, isCopied } = useCopyToClipboard()

  return (
    <button onClick={() => copy(text, id)}>
      {isCopied(id) ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
    </button>
  )
}`,
      },
    ],
  },
]

export function ComponentLibraryViewer({ onClose }: ComponentLibraryViewerProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedCategories, setExpandedCategories] = useState<string[]>(['design-system', 'domain', 'primitives', 'hooks'])
  const [selectedComponent, setSelectedComponent] = useState<ComponentExample | null>(
    COMPONENT_LIBRARY[0].components[0]
  )
  const [copiedCode, setCopiedCode] = useState(false)
  const [previewTheme, setPreviewTheme] = useState<'system' | 'light' | 'dark'>('system')

  const toggleCategory = (categoryId: string) => {
    setExpandedCategories(prev =>
      prev.includes(categoryId)
        ? prev.filter(id => id !== categoryId)
        : [...prev, categoryId]
    )
  }

  const copyCode = () => {
    if (selectedComponent) {
      navigator.clipboard.writeText(selectedComponent.code)
      setCopiedCode(true)
      setTimeout(() => setCopiedCode(false), 2000)
    }
  }

  // Filter components by search
  const filteredLibrary = COMPONENT_LIBRARY.map(category => ({
    ...category,
    components: category.components.filter(comp =>
      comp.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      comp.description.toLowerCase().includes(searchQuery.toLowerCase())
    ),
  })).filter(category => category.components.length > 0)

  const statusColors = {
    stable: 'bg-green-500/10 text-green-600 border-green-500/30',
    beta: 'bg-yellow-500/10 text-yellow-600 border-yellow-500/30',
    deprecated: 'bg-red-500/10 text-red-600 border-red-500/30',
  }

  // Use portal to render at document body level, escaping all parent layout constraints
  return createPortal(
    <div className="fixed inset-0 z-[9999] bg-background flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b">
        <div className="flex items-center gap-3">
          <Palette className="h-6 w-6 text-primary" />
          <h1 className="text-xl font-semibold">Component Library</h1>
          <Badge variant="outline" className="text-xs">Phase 20</Badge>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose}>
          <X className="h-5 w-5" />
        </Button>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <div className="w-64 border-r flex flex-col">
          {/* Search */}
          <div className="p-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search components..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
              />
            </div>
          </div>

          {/* Component list */}
          <div className="flex-1 overflow-y-auto">
            <div className="px-2 pb-4">
              {filteredLibrary.map((category) => (
                <div key={category.id} className="mb-2">
                  <button
                    className="flex items-center gap-2 w-full px-2 py-1.5 text-sm font-medium hover:bg-muted rounded-md"
                    onClick={() => toggleCategory(category.id)}
                  >
                    {expandedCategories.includes(category.id) ? (
                      <ChevronDown className="h-4 w-4" />
                    ) : (
                      <ChevronRight className="h-4 w-4" />
                    )}
                    {category.icon}
                    {category.name}
                  </button>
                  {expandedCategories.includes(category.id) && (
                    <div className="ml-6 mt-1 space-y-0.5">
                      {category.components.map((comp) => (
                        <button
                          key={comp.id}
                          className={cn(
                            "w-full text-left px-2 py-1.5 text-sm rounded-md transition-colors",
                            selectedComponent?.id === comp.id
                              ? "bg-primary text-primary-foreground"
                              : "hover:bg-muted text-muted-foreground hover:text-foreground"
                          )}
                          onClick={() => setSelectedComponent(comp)}
                        >
                          {comp.name}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Main content */}
        <div className="flex-1 overflow-y-auto">
            {selectedComponent ? (
              <div className="p-6 max-w-4xl">
                {/* Component header */}
                <div className="flex items-start justify-between mb-6">
                  <div>
                    <h2 className="text-2xl font-bold">{selectedComponent.name}</h2>
                    <p className="text-muted-foreground mt-1">{selectedComponent.description}</p>
                  </div>
                  <Badge variant="outline" className={statusColors[selectedComponent.status]}>
                    {selectedComponent.status}
                  </Badge>
                </div>

                {/* Live preview */}
                <Card className="mb-6">
                  <CardHeader className="flex flex-row items-center justify-between">
                    <CardTitle className="text-base">Preview</CardTitle>
                    <div className="flex items-center gap-1 bg-muted rounded-lg p-1">
                      <button
                        onClick={() => setPreviewTheme('light')}
                        className={cn(
                          "p-1.5 rounded transition-colors",
                          previewTheme === 'light' ? "bg-background shadow-sm" : "hover:bg-background/50"
                        )}
                        title="Light mode"
                      >
                        <Sun className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setPreviewTheme('system')}
                        className={cn(
                          "p-1.5 rounded transition-colors",
                          previewTheme === 'system' ? "bg-background shadow-sm" : "hover:bg-background/50"
                        )}
                        title="System theme"
                      >
                        <Monitor className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setPreviewTheme('dark')}
                        className={cn(
                          "p-1.5 rounded transition-colors",
                          previewTheme === 'dark' ? "bg-background shadow-sm" : "hover:bg-background/50"
                        )}
                        title="Dark mode"
                      >
                        <Moon className="h-4 w-4" />
                      </button>
                    </div>
                  </CardHeader>
                  <CardContent className={cn(
                    "rounded-b-lg p-6 transition-colors",
                    previewTheme === 'light' && "bg-white",
                    previewTheme === 'dark' && "bg-zinc-950",
                    previewTheme === 'system' && "bg-muted/30"
                  )}>
                    <div className={cn(
                      previewTheme === 'light' && "light [&_*]:text-zinc-900 [&_.text-muted-foreground]:text-zinc-500 [&_.bg-card]:bg-white [&_.text-card-foreground]:text-zinc-900 [&_.bg-muted]:bg-zinc-100 [&_.border]:border-zinc-200",
                      previewTheme === 'dark' && "dark [&_*]:text-zinc-100 [&_.text-muted-foreground]:text-zinc-400 [&_.bg-card]:bg-zinc-900 [&_.text-card-foreground]:text-zinc-100 [&_.bg-muted]:bg-zinc-800 [&_.border]:border-zinc-700"
                    )}>
                      {selectedComponent.preview}
                    </div>
                  </CardContent>
                </Card>

                {/* Props table */}
                {selectedComponent.props.length > 0 && (
                  <Card className="mb-6">
                    <CardHeader>
                      <CardTitle className="text-base">Props</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b">
                              <th className="text-left py-2 pr-4 font-medium">Prop</th>
                              <th className="text-left py-2 pr-4 font-medium">Type</th>
                              <th className="text-left py-2 pr-4 font-medium">Default</th>
                              <th className="text-left py-2 font-medium">Description</th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedComponent.props.map((prop) => (
                              <tr key={prop.name} className="border-b last:border-0">
                                <td className="py-2 pr-4 font-mono text-primary">{prop.name}</td>
                                <td className="py-2 pr-4 font-mono text-xs text-muted-foreground">{prop.type}</td>
                                <td className="py-2 pr-4 font-mono text-xs">{prop.default || '-'}</td>
                                <td className="py-2 text-muted-foreground">{prop.description || '-'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Code snippet */}
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between">
                    <CardTitle className="text-base">Usage</CardTitle>
                    <Button variant="ghost" size="sm" onClick={copyCode}>
                      {copiedCode ? (
                        <>
                          <Check className="h-4 w-4 mr-1 text-green-500" />
                          Copied
                        </>
                      ) : (
                        <>
                          <Copy className="h-4 w-4 mr-1" />
                          Copy
                        </>
                      )}
                    </Button>
                  </CardHeader>
                  <CardContent>
                    <pre className="bg-muted text-foreground p-4 rounded-lg overflow-x-auto text-sm border">
                      <code>{selectedComponent.code}</code>
                    </pre>
                  </CardContent>
                </Card>
              </div>
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground">
                Select a component to view its documentation
              </div>
            )}
        </div>
      </div>
    </div>,
    document.body
  )
}

export default ComponentLibraryViewer
