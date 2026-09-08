# SEC-15: `:cloud` model suffix bypasses the secure-model gate

**Date:** 2026-09-07
**Severity:** Critical (security — secrets egress to cloud vendor)
**Status:** Open, unverified in production
**Discovered by:** Devin session 2026-09-07, investigating "apple-foundation-3b was unavailable. deepseek-v4-flash:cloud answered instead."

> **Canonical id: SEC-21.** This issue was filed as SEC-15, but SEC-15 is already
> *Prompt-injection containment* in `SECURITY-IMPLEMENTATION-PLAN-2026-09-06.md`
> (highest assigned was SEC-20). Code, tests, commits and `DECISIONS.md` use
> **SEC-21**; the filename is kept because `ROADMAP.md` already references it.
>
> **Status 2026-09-08: FIXED** on `fix/sec-15-cloud-suffix`. Two corrections to
> the text below, both measured on this machine (Ollama 0.32.15): `/api/show`
> exposes **no `remote_host` field** in this version, so it cannot be the
> authoritative check; and the fix landed as a single `llm_config.is_local_model()`
> implementing all three clauses of the `being_config.py` rule, used at **five**
> sites, not two — the turn gate, the fallback, the dedicated secure-slot branch
> (which returned *before* `gate()` and so was checked nowhere), `normalise` at
> config-write time, and both capability probes.

## Summary

The secure-model locality gate (`_endpoint_is_local`) checks only the endpoint URL and provider name. It does not inspect the model name. Ollama models tagged with a `:cloud` suffix (e.g. `deepseek-v4-flash:cloud`) are proxied to `https://ollama.com` at inference time — they are cloud models served through a localhost relay. The gate sees `localhost:11434`, declares the endpoint "local", and lets a secure turn (one carrying secrets, credentials, or persona memory) flow to a cloud vendor.

This is the exact failure mode the project's own `being_config.py` warns about:

> If a local model is ever reintroduced for open-ended questions about secrets, it must carry a fail-closed assertion: **reject any tag ending in `:cloud`**, reject any provider outside `LOCAL_GPU_PROVIDERS`, **never infer locality from the endpoint URL.**

All three rules are violated by the current code.

## Affected code

**Primary:** `halbert_core/halbert_core/dashboard/routes/agent.py` lines 471-482

```python
def _endpoint_is_local(provider: str, endpoint: str) -> bool:
    from ...model.llm_config import _is_local_url
    if (provider or "") in ("mlx", "apple-foundation"):
        return True
    return _is_local_url(endpoint or "")
```

The function takes `provider` and `endpoint` but **not the model name**. Callers in `_resolve_turn_model` (line 595) and `_fallback_to_guide` (line 739) pass only those two fields.

**Secondary:** `halbert_core/halbert_core/model/llm_config.py` `_is_local_url` (lines 143-157) — the URL-only check that `_endpoint_is_local` delegates to.

## Attack path

1. User configures `secure_model` = `apple-foundation-3b` @ `http://127.0.0.1:11435` (the Apple Foundation bridge)
2. The bridge is not running (see APPLE-1) — connection refused
3. `_fallback_to_guide` is called with `secure=True`
4. Guide model is `deepseek-v4-flash:cloud` @ `http://localhost:11434`, provider `ollama`
5. `_endpoint_is_local("ollama", "http://localhost:11434")` → `True` (URL is loopback)
6. Secure gate passes — the turn's secrets are sent to Ollama, which proxies to `https://ollama.com`

Verified on this machine: `curl http://localhost:11434/api/show -d '{"name":"deepseek-v4-flash:cloud"}'` returns `remote_host: "https://ollama.com"`.

## Also affected: the primary secure gate

The same bug exists in the non-fallback path. `_resolve_turn_model`'s `gate()` function (line 593-606) calls `_endpoint_is_local` to decide whether the normally-resolved model can answer a secure turn. If the chat/specialist model is a `:cloud` Ollama model, it passes the gate the same way.

## Fix

`_endpoint_is_local` must accept the model name and reject `:cloud`-suffixed models:

```python
def _endpoint_is_local(provider: str, endpoint: str, model: str = "") -> bool:
    from ...model.llm_config import _is_local_url
    if (provider or "") in ("mlx", "apple-foundation"):
        return True
    # Ollama :cloud models are proxied to https://ollama.com — localhost
    # URL is not proof of locality (being_config.py fail-closed rule).
    if (model or "").rstrip().endswith(":cloud"):
        return False
    return _is_local_url(endpoint or "")
```

All call sites must pass `turn.model` (or the relevant model string) as the third argument. There are two call sites in `agent.py` (lines 595, 739) and potentially others in `tier_router.py` and `llm_config.py` that should be audited.

## Tests to add

1. `_endpoint_is_local("ollama", "http://localhost:11434", "deepseek-v4-flash:cloud")` returns `False`
2. `_endpoint_is_local("ollama", "http://localhost:11434", "llama3.2:3b")` returns `True`
3. `_endpoint_is_local("apple-foundation", "http://127.0.0.1:11435", "apple-foundation-3b")` returns `True`
4. Secure turn with `:cloud` guide model fails closed (not falls back to cloud)
5. The existing `test_fallback_to_guide_refuses_cloud_guide_on_secure_turn` test should be extended to cover `:cloud` suffix on a localhost endpoint

## Related

- **APPLE-1** — the trigger condition (bridge down) that exposes this bug
- `being_config.py` lines 53-60 — the design rule this violates
- `config/queries.py` — `key_is_cloud_ok` / `secret_tier == "cloud_ok_acknowledged"` shows the project already understands the `:cloud` distinction elsewhere
