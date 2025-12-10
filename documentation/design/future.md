# Future Directions

This document outlines potential future enhancements for Halbert. These are ideas, not commitments.

---

## Disclaimer

**These are not planned features.** They represent directions the project could take if there's community interest and resources. Contributors are welcome to explore any of these.

---

## Potential Enhancements

### Enhanced Tool Library

The current tool set covers basic system operations. Potential expansions:

| Category | Potential Tools |
|----------|-----------------|
| **Networking** | Firewall management, DNS diagnostics, VPN configuration |
| **Containers** | Docker cleanup, image management, compose integration |
| **Performance** | Profiling, bottleneck detection, resource optimization |
| **Security** | SSH hardening, update management, audit scanning |
| **Storage** | SMART monitoring, RAID management, quota enforcement |

### Predictive Capabilities

The current system is reactive. Future versions could:

- **Trend Analysis** — Detect patterns (disk filling, memory leaks)
- **Predictive Alerts** — "Disk will be full in 12 days"
- **Anomaly Detection** — "Unusual CPU pattern detected"
- **Capacity Planning** — "At current growth, you'll need more storage"

This would require historical data retention and ML models.

### Plugin System

Allow third-party extensions:

- **Tool Plugins** — Add new capabilities without core changes
- **Ingestion Plugins** — New data sources (application metrics, custom logs)
- **Dashboard Widgets** — Custom visualizations

### Multi-Host Support

Currently Halbert monitors a single machine. Extensions could include:

- **Fleet Management** — Monitor multiple hosts from one dashboard
- **Aggregated Views** — Cross-host metrics and alerts
- **Centralized Memory** — Shared knowledge across hosts

### Advanced RAG

The current RAG system is basic. Improvements could include:

- **Hybrid Search** — Combine vector and keyword search
- **Reranking** — ML-based relevance scoring
- **Query Expansion** — Automatic query enhancement
- **Citation** — Source attribution in responses

### Voice Interface

Natural language through voice:

- **Speech-to-Text** — Speak queries
- **Text-to-Speech** — Hear responses
- **Wake Word** — "Hey Halbert, how's the disk?"

---

## Architectural Considerations

### Distributed Architecture

The current monolithic design could evolve:

```
┌─────────────────┐     ┌─────────────────┐
│   Agent Host    │────▶│  Central Brain  │
│  (collector)    │     │  (LLM + RAG)    │
└─────────────────┘     └─────────────────┘
        │
        ▼
┌─────────────────┐
│   Dashboard     │
│   (web UI)      │
└─────────────────┘
```

This would allow:
- Lightweight agents on resource-constrained hosts
- Centralized intelligence on a more capable machine
- Reduced LLM requirements per host

### Custom Model Training

Fine-tuned models for system administration:

- **Domain-Specific Training** — Linux admin knowledge
- **Your System's Patterns** — Learn from your specific environment
- **Efficient Inference** — Smaller, specialized models

---

## Community Contributions Welcome

If you're interested in any of these directions:

1. Open a GitHub issue to discuss
2. Check if someone else is already working on it
3. Submit a PR with your implementation

No area is "owned" — contributions in any direction are welcome.

---

## Not Planned

To set expectations, some things are explicitly **not** on the roadmap:

- **Cloud-hosted version** — Halbert is local-first by design
- **Paid features** — The project is fully open source
- **Windows support** — Focus is on Linux
- **Mobile apps** — Desktop/server focus only

---

## Contributing to Future Development

See [contributing/CONTRIBUTING.md](../contributing/CONTRIBUTING.md) for how to contribute.

The best way to influence future direction is to:
1. Use Halbert and report issues
2. Propose features with clear use cases
3. Submit PRs that implement features cleanly
4. Help with documentation and testing
