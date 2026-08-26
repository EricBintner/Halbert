# @halbert/model-picker

A headless React package for choosing where inference happens: discovering local
engines, holding bring-your-own-key endpoints, assigning a model to each of the
host's slots, and pinning a choice for a single turn. It ships behaviour and
accessibility only — no styling, no markup opinions, and no I/O of its own.

## The two rules

**No role names.** Every host names its slots differently. The package renders
whatever `AppRole[]` it is handed and never mentions a slot by name, so the same
components serve a host with one slot and a host with six.

**No I/O.** The package makes no network call. Every read and write goes through
the injected `ModelPickerTransport`, which is what lets the same code run against
an HTTP API, a desktop command bridge, or a plain object in a test — and what
makes extracting this directory into its own repository a move rather than a
rewrite.

A third rule governs anything rendered: name providers, never models. Provider
names are vendors (Ollama, LM Studio, OpenAI, Anthropic, Google). Model names
belong to the user's configuration and only ever reach the screen as data.

## Implementing a transport

The transport is the only seam. A host with an HTTP API implements it in about
thirty lines:

```ts
import type { ModelPickerTransport } from '@halbert/model-picker'

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return (await res.json()) as T
}

const send = (path: string, body: unknown, method = 'POST') =>
  fetch(path, {
    method,
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })

export const httpTransport: ModelPickerTransport = {
  loadConfig: () => fetch('/api/llm/config').then(json),

  // Must merge server-side and return what was actually stored: the hook
  // adopts the response, so a rejected field is visible immediately.
  saveConfig: (patch) => send('/api/llm/config', patch, 'PUT').then(json),

  listModels: (endpoint) =>
    fetch(`/api/llm/endpoints/${encodeURIComponent(endpoint.id)}/models`).then(json),

  testEndpoint: (endpoint) => send('/api/llm/test-endpoint', endpoint).then(json),

  // Optional. Omit it and the picker falls back to testing the endpoint.
  testModel: (endpoint, model) =>
    send('/api/llm/test-model', { endpoint, model }).then(json),

  // Optional. Omit it on a host with no loopback access and the picker
  // degrades to manual endpoint entry.
  discoverLocal: () => fetch('/api/llm/discover').then(json),
}
```

Errors are surfaced, not thrown: a rejected promise from any method becomes an
`error` string and an `onError` call, and one unreachable endpoint never empties
the others.

## Consuming it from a host

There is no npm workspace in this repository, so hosts point at the source
directory directly.

```ts
// vite.config.ts
resolve: {
  alias: {
    '@halbert/model-picker': path.resolve(__dirname, '../../packages/model-picker/src'),
  },
}
```

```jsonc
// tsconfig.json
"paths": {
  "@halbert/model-picker": ["../../packages/model-picker/src"]
}
```

Then declare the slots in the host's own vocabulary and render:

```tsx
import { useModelPicker } from '@halbert/model-picker'
import type { AppRole } from '@halbert/model-picker'

const ROLES: AppRole[] = [
  { id: 'conversation', label: 'Conversation', description: 'Answers ordinary turns.' },
  { id: 'analysis', label: 'Analysis', description: 'Longer reasoning.', requiresTools: true },
  { id: 'images', label: 'Images', description: 'Reads screenshots.', requiresVision: true },
]

function Settings() {
  const picker = useModelPicker({ transport: httpTransport, roles: ROLES })
  return <RoleAssignmentList picker={picker} className="your-own-class" />
}
```

Every component takes the whole hook result as a `picker` prop and reads what it
needs, and every element accepts `className` and `style`. The host owns
appearance entirely.

## The extraction contract

The package must stay liftable into a repository that shares none of this one's
tooling. `npm run check:boundary` enforces the mechanical half of that:

- [ ] Imports are relative, or exactly `react` / `react-dom` / a `react/` subpath.
      Test files may also reach for `vitest` and `@testing-library/*`.
- [ ] No `fetch`, `XMLHttpRequest`, `WebSocket`, or HTTP client anywhere outside tests.
- [ ] No stylesheet imports, no `styled.` usage, no hard-coded class lists in
      `className` — hosts supply classes through props.
- [ ] No `Math.random()` or `Date.now()` in render paths, so output is deterministic.
- [ ] No slot named in package copy, and no model named anywhere in the source.
- [ ] Keyboard and ARIA behaviour lives in the package, not in the host.

```sh
npm run check:boundary   # extraction contract
npm run typecheck        # strict, with unused locals and parameters on
npm test                 # hook and component behaviour
```

Licensed GPL-3.0-or-later.
