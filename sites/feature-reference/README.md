# Halbert Feature Reference & Architecture Inventory

A local and public-ready browsable, searchable dictionary of every feature in Halbert — the authoritative source of truth for *"what features exist, how they work, which files implement them, and what safety boundaries protect them."*

## Architecture

* **Framework**: React 19 + Vite 6
* **Styling**: Tailwind CSS v4 using the **Olivetti Vermilion & Bone** universal design tokens (`../../shared-tokens/tailwind-v4.css` & `tokens.css`)
* **Design Pillars**:
  1. *Daylight & Paper*: Warm unbleached linen canvas (`--color-canvas`), clean card surfaces, and dark mode ("Olivetti After Hours").
  2. *The Letterpress Stroke*: Mechanical Vermilion accent budget (`--color-accent`).
  3. *Editorial & Computational Type*: Fraunces (humanist display serif), Space Grotesk (modernist sans), JetBrains Mono (code and paths).
  4. *Diagnostic Tones*: Botanical (shipped), Ochre (unbuilt), Blueprint (backend-only), Terracotta (deferred).

## Run Locally

```bash
cd web/feature-reference
npm install
npm run dev
```

The dev server will start at `http://localhost:5188`.

## Catalog Schema (`src/catalog.json`)

Each entry in `catalog.json` defines a feature:

* `id`: Unique kebab-case slug (e.g. `tier-model-routing`).
* `name`: Plain-language human-facing name.
* `category`: One of the 10 core domain categories.
* `oneLine`: Single concise sentence stating purpose.
* `status`: `shipped` | `hidden` (backend-only / unwired) | `unbuilt` | `deferred`.
* `visibility`: `public-ready` | `internal`.
* `decisionRefs`: Array of design decisions or RFC IDs (e.g. `["FDR-04", "ROADMAP-08-23"]`).
* `gating`: Optional prerequisite (hardware, OS, or configured endpoint).
* `whatItIs`: Plain-language explanation for end users and engineers.
* `howItWorks`: Deep technical explanation of mechanism, lifecycle, and data flow.
* `toolingAndBackend`: Exact file paths, scanners, modules, and tests.
* `limitsAndInvariants`: Hard architectural non-goals, fail-closed safety constraints, and security bounds.
* `subFeatures`: Array of child sub-features sharing the same schema.

## Release Checklist

When adding or refactoring a capability in Halbert:
1. Update `src/catalog.json`.
2. Verify that `status` reflects reality in the tree (`shipped` vs `hidden` / backend-only vs `unbuilt`).
3. Ensure `limitsAndInvariants` lists all fail-closed behavior.
