---
description: Get structural codebase context from SourcePrep
tools:
  - mcp__prep__prep
  - mcp__prep__prep_search
  - mcp__prep__prep_impact
---

Call `prep` to get the structural overview of this codebase -- modules,
hub files, and knowledge base content. Use the structural context to
inform your approach before reading or editing files.

If the user asked a specific question, also call `prep_search` with
their question to find relevant code with structural trace expansion.

Before making changes, call `prep_impact` on the target file to
understand what depends on it.
