# Halbert Prompt Testing Framework

**Phase 46: Prompt Testing Framework**

This directory contains the testing infrastructure for Halbert's prompt system.

## Quick Start

```bash
# Install promptfoo
npm install -g promptfoo

# Run all tests
npx promptfoo eval --config tests/prompts/promptfoo.yaml

# View results
npx promptfoo view
```

## Directory Structure

```
tests/prompts/
├── promptfoo.yaml       # Main configuration
├── test-cases/
│   ├── safety.yaml      # Safety layer tests
│   ├── tools.yaml       # Tool selection tests
│   └── ...
├── datasets/
│   ├── common-queries.json
│   └── edge-cases.json
└── reports/
    └── latest.json      # Test results
```

## Test Categories

### Safety Tests
- Dangerous command refusal (rm -rf, fork bomb, dd)
- Credential protection (no API keys, passwords in output)
- Prompt injection resistance
- Security operation warnings

### Tool Selection Tests
- Correct tool for query type
- Parameter accuracy
- Coverage for all 7 tools

### Conciseness Tests
- Response length for simple queries
- No unnecessary preamble
- No excessive caveats

### Accuracy Tests
- Correct command syntax
- Factual correctness

## Quality Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Safety | 100% | Dangerous requests refused |
| Tool Accuracy | ≥95% | Correct tool selected |
| Conciseness | <100 tokens | Simple query responses |
| No Preamble | 100% | No "I'd be happy to help" |

## Running Specific Tests

```bash
# Safety tests only
npx promptfoo eval --config tests/prompts/test-cases/safety.yaml

# Tools tests only
npx promptfoo eval --config tests/prompts/test-cases/tools.yaml
```

## CI Integration

Add to `.github/workflows/prompt-tests.yml`:

```yaml
on: [push, pull_request]
jobs:
  prompt-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install promptfoo
        run: npm install -g promptfoo
      - name: Run tests
        run: npx promptfoo eval --config tests/prompts/promptfoo.yaml
```

## See Also

- [Phase 46 Documentation](../../docs/Phase46_Prompt-Testing-Framework/README.md)
- [promptfoo docs](https://www.promptfoo.dev/)
