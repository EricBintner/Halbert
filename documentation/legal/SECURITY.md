# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| main branch | Yes |
| Older releases | Best effort |

## Reporting a Vulnerability

**Do not report security vulnerabilities through public GitHub issues.**

Instead, please report security issues by emailing the maintainers directly.

Include:

1. Description of the vulnerability
2. Steps to reproduce
3. Potential impact
4. Any suggested fixes (optional)

You can expect:

- Acknowledgment within 48 hours
- Status update within 7 days
- Credit in the security advisory (if desired)

## Security Model

### Design Principles

Halbert follows a **safety-first autonomy** model:

1. **Dry-run by default** - Destructive operations preview before execution
2. **Human approval** - High-risk actions require explicit confirmation
3. **Operation budgets** - Rate limits on autonomous actions
4. **Audit logging** - All operations are logged with context
5. **Rollback capability** - State changes can be reverted

### Trust Boundaries

| Component | Trust Level | Access |
|-----------|-------------|--------|
| CLI | User session | User's permissions |
| Dashboard | Localhost only | Bound to 127.0.0.1 |
| LLM (Ollama) | Local process | No network by default |
| ChromaDB | Local storage | User's data directory |

### Data Handling

- **All data stays local** - No external API calls
- **No telemetry** - Usage data is not collected
- **Config isolation** - XDG paths separate user data
- **Secrets** - API keys stored in user config, not code

### Policy Engine

The policy engine at `halbert_core/halbert_core/policy/` controls:

- Which tools can run automatically
- Which require approval
- Which are blocked entirely

Default policy requires approval for:

- Service restarts
- Configuration file modifications
- Scheduled task creation
- File deletions

## Known Considerations

### LLM Output

- LLM responses are not trusted for direct execution
- All actions go through the approval/dry-run system
- Confidence thresholds gate autonomous execution

### journald Access

- Requires user membership in `systemd-journal` group
- Limited to log reading (no write access)

### File System Access

- Respects user permissions
- No root escalation without explicit sudo
- Paths constrained to configured directories

## Hardening Recommendations

### Production Deployment

1. Run as non-root user
2. Use systemd service with `ProtectSystem=strict`
3. Bind dashboard to localhost only
4. Review policy.yml for your environment
5. Enable audit logging

### Network Isolation

```yaml
# config/policy.yml
network:
  allow_external: false
  allowed_hosts: []
```

### Restricting Tools

```yaml
# config/policy.yml
rules:
  - tool: "*"
    action: block
    
  - tool: read_logs
    action: allow
    
  - tool: query_memory
    action: allow
```
