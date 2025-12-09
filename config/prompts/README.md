# Cerebric Prompt Configuration

## Base Safety Prompt

`base-safety.txt` contains the immutable safety rules. This prompt is **read-only** and should not be modified unless you fully understand the security implications.

The base safety prompt ensures:
- All dangerous operations require user approval
- Policy engine is always consulted
- Audit logging is mandatory
- Structured outputs when needed
- Confidence estimation for decisions

## Mode-Specific Layers (Phase 3)

Cerebric supports two operational modes:

### Interactive Mode (default)
User-driven conversation. Cerebric responds to questions, provides recommendations, and requires confirmation for all changes.

### Autonomous Mode
Scheduled maintenance routines. Cerebric executes tasks within guardrails (confidence thresholds, resource budgets, policy constraints).

## Persona Layers (Phase 4)

Phase 4 will add user-swappable personas:
- **IT Admin**: Professional technical assistant (default)
- **Friend**: Casual conversational companion
- **Custom**: User-defined personality

Persona layers will be stored as:
- `it_admin.txt`
- `friend.txt`
- `custom.txt`

## Important

**The base safety prompt is ALWAYS included.** 

Persona layers are **ADDITIVE** (not replacements). You can customize tone and style, but you cannot remove safety rules or policy enforcement.

## Customization (Advanced)

To customize prompts:

1. **DO NOT** modify `base-safety.txt` (security risk)
2. **DO** create custom persona files in this directory (Phase 4)
3. **DO** test changes with dry-run mode first
4. **DO** validate that safety rules are still enforced

Example persona customization (Phase 4):
```
# friend.txt
You're in friend mode. Be warm and conversational.
- Use appropriate emoji to convey emotion
- Discuss music, hobbies, creative projects
- Keep system monitoring in the background

All safety rules still apply. Friend mode changes tone, not capabilities.
```

---

**Security Note**: Cerebric safety comes from the **policy engine** (independent of LLM), not just prompts. Even if prompts are modified, the policy engine enforces tool restrictions at execution time.
