# Deep Scrutiny & Reverse-Engineering Audit: LLM Picker Redesign & Agent Parity

**Document Version:** 1.0.0  
**Date:** 2026-08-26  
**Status:** Architectural Review & Risk Audit — For Technical Review  
**Audience:** Technical Lead, Systems Architects, Engineering Reviewers  
**Subject:** Reverse-engineering Halbert's agent execution loop, discovering hidden failure modes in BYOK/Ollama routing, and verifying the technical viability of the redesigned model picker.

---

## 1. Executive Summary of Scrutiny

We subjected the approved UI/UX design ([`UI-SPEC-REUSABLE-MODEL-PICKER-2026-08-26.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/UI-SPEC-REUSABLE-MODEL-PICKER-2026-08-26.md)) and the handoff plan to an adversarial reverse-engineering audit. We traced the entire stack—from the user clicking the in-chat pill in the browser down through the React state, SSE streaming hooks, FastAPI request schemas, agent state machine transitions, and actual HTTP socket calls to Ollama and cloud providers.

This scrutiny uncovered **four critical hidden landmines** in the existing codebase that would have caused the redesigned UI to fail silently upon release:

1. **The BYOK Authentication Blindspot (Severity: CRITICAL / BLOCKING)**:
   * `model/client.py`'s `_resolve_endpoint()` completely drops `api_key`.
   * `_do_llm_call()` does not send an `Authorization: Bearer` header for OpenAI, and has **no Anthropic branch at all** (Anthropic requests are sent to `api.anthropic.com/api/chat`, which returns an immediate 404).
   * Any BYOK key configured in the UI would have failed with 401 Unauthorized or 404 Not Found in chat.
2. **The In-Chat Runtime Disconnect (Severity: HIGH / BLOCKING)**:
   * `useAgentStream.ts` and `routes/agent.py`'s `SendMessageRequest` only send `{ message, session_id, max_tokens, temperature }`.
   * There was no `model` or `tier` parameter in the API payload. The in-chat picker pill had no way to tell the backend to use the selected model.
3. **The Multi-Turn Memory Illusion (Severity: HIGH / ARCHITECTURAL)**:
   * In `routes/agent.py:686`, `agent.process()` is called without passing `conversation_history`.
   * In `state_machine.py:660,1277`, the LLM is called with `messages=[{"role": "user", "content": prompt}]`.
   * Halbert is currently completely stateless between turns. Multi-turn Claude Code behavior is impossible without fixing this foundation.
4. **The Auto-Routing vs. User Override Ambiguity (Severity: MEDIUM / UX PREDICTABILITY)**:
   * Halbert's `ComplexityRouter` automatically redirects queries with complexity >= 0.5 to the Specialist model.
   * If a user explicitly selects a model in the in-chat pill (e.g. `qwen2.5:7b`), the router would have overridden their choice behind their back unless an explicit "Locked Mode" vs "Auto Mode" is introduced.

Below is the exhaustive reverse-engineering breakdown of each failure mode, along with the precise architectural fixes.

---

## 2. Reverse-Engineering the Stack: Trace & Vulnerability Map

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          THE COMPLETE CALL TRACE                            │
└─────────────────────────────────────────────────────────────────────────────┘
  [Frontend UI]
    │ User selects "claude-3-7-sonnet" in <ModelSelectorPill />
    ▼
  [AgentChat.tsx] ──> sendMessage(input)
    │
    ▼
  [useAgentStream.ts:583]
    │ fetch('/api/agent/message', { body: { message, session_id, max_tokens, temperature } })
    │ ⚠️ VULNERABILITY #1: 'model' is not in the request body!
    ▼
  [routes/agent.py:644] send_message(request: SendMessageRequest)
    │ SendMessageRequest has no 'model' or 'tier' field!
    │ ⚠️ VULNERABILITY #2: Ignores request.conversation_id, never loads history!
    ▼
  [agents/state_machine.py:190] agent.process(query, session_id, images)
    │ self.ctx.conversation_history = conversation_history or []  # Always []!
    │ ⚠️ VULNERABILITY #3: conversation_history is empty on every turn!
    ▼
  [agents/state_machine.py:660] LLMClientAdapter.chat(messages=[{"role": "user", "content": prompt}])
    │ Routes based on score_query_complexity(prompt)
    │ ⚠️ VULNERABILITY #4: Complexity router overrides user's manual in-chat model pick!
    ▼
  [model/client.py:270] get_specialist_model()
    │ url, provider = _resolve_endpoint(llm_config, endpoint_id)
    │ ⚠️ VULNERABILITY #5: api_key is discarded! Never returned to caller!
    ▼
  [model/client.py:444] _do_llm_call(endpoint, model, messages, provider, ...)
    │ if provider == "openai":
    │     requests.post(url, json=payload)  # NO AUTHORIZATION HEADER! -> 401 Unauthorized
    │ else:
    │     requests.post(f"{endpoint}/api/chat", json=payload) # Anthropic -> 404 Not Found!
    │ ⚠️ VULNERABILITY #6: Cloud BYOK endpoints fail 100% of the time!
```

---

## 3. Vulnerability Analysis & Technical Fixes

### 3.1 Vulnerability 1 & 6: The BYOK Authentication Blindspot

#### The Reverse-Engineered Code:
Look at `model/client.py:169-184`:
```python
def _resolve_endpoint(llm_config: Dict[str, Any], endpoint_id: Optional[str]) -> Tuple[str, str]:
    if not endpoint_id:
        return ("http://localhost:11434", "ollama")
    endpoints = llm_config.get("saved_endpoints") or []
    for ep in endpoints:
        if ep.get("id") == endpoint_id:
            # BUG: Only returns url and provider! api_key is completely discarded!
            return (ep.get("url", "http://localhost:11434"), ep.get("provider", "ollama"))
    return ("http://localhost:11434", "ollama")
```

And look at `model/client.py:455-481` (`_do_llm_call`):
```python
    if provider == "openai":
        url = f"{endpoint}/v1/chat/completions"
        # BUG: requests.post is executed without headers={"Authorization": f"Bearer {api_key}"}!
        response = requests.post(url, json=payload, timeout=timeout)
    else:
        # BUG: Anthropic falls into this branch and calls https://api.anthropic.com/api/chat!
        url = f"{endpoint}/api/chat"
        response = requests.post(url, json=payload, timeout=timeout)
```

#### Why This Existed:
Halbert originated as a local-only Ollama tool. When `saved_endpoints` was introduced to store BYOK keys, the keys were saved to disk and tested in the test route (`POST /api/llm/proxy/test`), but the actual chat execution path (`call_llm_chat`) was never updated to accept `api_key` or inject HTTP headers!

#### The Required Fix:
1. Update `_resolve_endpoint()` to return `Tuple[str, str, Optional[str]]` (`url`, `provider`, `api_key`).
2. Update `call_llm_chat()` and `_do_llm_call()` to accept `api_key: Optional[str] = None`.
3. In `_do_llm_call()`:
   * For `provider in ("openai", "openai-compatible")`:
     ```python
     headers = {"Content-Type": "application/json"}
     if api_key:
         headers["Authorization"] = f"Bearer {api_key}"
     response = requests.post(url, json=payload, headers=headers, timeout=timeout)
     ```
   * For `provider == "anthropic"`:
     Route to `agents/llm_client.py:AnthropicClient` (which already has complete Anthropic Messages formatting and header generation) instead of the raw requests call.

---

### 3.2 Vulnerability 2: The In-Chat Runtime Disconnect

#### The Reverse-Engineered Code:
In `dashboard/frontend/src/hooks/useAgentStream.ts:583-591`:
```typescript
fetch(apiUrl('/api/agent/message'), {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    message: message,
    session_id: sid,
    max_tokens: maxTokens,
    temperature: temperature,
    // BUG: No model, no tier, no endpointId!
  }),
  signal: controller.signal
})
```

And in `dashboard/routes/agent.py:37-48`:
```python
class SendMessageRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    images: Optional[List[str]] = None
    max_tokens: Optional[int] = 8192
    temperature: Optional[float] = 0.7
    # BUG: No model or tier fields exist on the Pydantic schema!
```

#### The Required Fix:
1. Extend `SendMessageRequest`:
   ```python
   class SendMessageRequest(BaseModel):
       # ... existing fields ...
       model: Optional[str] = Field(None, description="Explicit model override for this turn")
       tier: Optional[str] = Field(None, description="'guide' | 'specialist' | 'auto'")
   ```
2. Update `routes/agent.py:LLMClientAdapter.chat()`:
   * Accept `model_override: Optional[str] = None` and `tier_override: Optional[str] = None`.
   * If `model_override` is provided, bypass the complexity router entirely and call that model.
3. Update `useAgentStream.ts`:
   * Forward the currently selected model and tier from `<ModelSelectorPill />` in the `POST /api/agent/message` body.

---

### 3.3 Vulnerability 3: The Multi-Turn Memory Illusion

#### The Reverse-Engineered Code:
In `routes/agent.py:686-690`:
```python
async for event in agent.process(
    query=request.message,
    session_id=session_id,
    images=request.images,
    # BUG: conversation_history is omitted completely!
):
```

In `agents/state_machine.py:221`:
```python
self.ctx = StateContext(
    session_id=session_id,
    request_id=request_id,
    user_query=query,
    user_id=user_id,
    conversation_history=conversation_history or [], # Always evaluates to []!
    max_loops=self.max_loops,
    images=images,
)
```

In `agents/state_machine.py:660,1277`:
```python
response = await self.llm.chat(
    messages=[{"role": "user", "content": prompt}], # Only 1 message sent to LLM!
    tools=tool_schemas,
    intake_result=self.ctx.intake if self.ctx else None,
)
```

#### Why Claude Code Feels Intelligent:
Claude Code maintains a continuous conversation thread. If you say:
> 1. *"Check if nginx is running"* → (runs `systemctl status nginx`, reports stopped)
> 2. *"Start it and check the error log"* → (starts nginx, reads `/var/log/nginx/error.log`)

Claude Code remembers the context of the first turn. In Halbert today, Turn #2 has **zero memory** of Turn #1! Turn #2 has to guess what service "it" refers to because `conversation_history` is empty.

#### The Required Fix:
1. **Load Conversation History**: In `routes/agent.py:send_message()`, if `request.conversation_id` is passed (or derived from `session_id`), fetch recent turns from `conversation_store.get(conv_id)`.
2. **Pass History to Agent**: Call `agent.process(query=..., conversation_history=history)`.
3. **Structured Messages List**: In `state_machine.py`, construct `messages` by taking previous turn history, appending the current turn's planning prompt and tool results, and passing the full multi-turn array to `self.llm.chat()`.

---

### 3.4 Vulnerability 4: The Auto-Routing vs. User Override Ambiguity

#### The Problem:
Halbert features a `score_query_complexity()` router.
* If complexity < 0.5 → calls Guide (`chat_model`).
* If complexity >= 0.5 → calls Specialist (`specialist_model`).

If the user picks `qwen2.5:7b` in the in-chat pill because they want quick, local responses, and then asks:
> *"Why did my btrbk snapshot cron job fail at midnight?"*

The complexity score is evaluated at ~0.75. The router silently switches the request to `specialist_model` (e.g. `claude-3-7-sonnet`). The user is left confused: *"I selected Qwen 7B, why is Claude answering and consuming cloud credits?"*

#### The Required Fix (State Machine for the Selector Pill):
The in-chat UI must support **two explicit modes**:

1. **`Auto Mode` (Default)**:
   * The pill displays `[ 🟢 Ollama · qwen2.5-coder:14b ▾ ] [ ⚡ Auto: Guide ]`.
   * Normal queries use Guide; complex queries escalate to Specialist.
   * When escalation occurs, the inline Handoff Banner notifies the user.
2. **`Locked Mode` (User Pin)**:
   * The user clicks the tier dropdown and selects `[ 🔒 Lock to this model ]`.
   * The pill displays `[ 🔒 Pin: qwen2.5-coder:14b ]`.
   * Complexity routing is **completely bypassed**; the pinned model handles all queries regardless of complexity.

---

## 4. Reverse-Engineering Local Auto-Discovery (CORS & SSRF Constraints)

### 4.1 Browser vs. Desktop Webview Execution
The design specification proposes auto-probing `localhost:11434` (Ollama) and `localhost:1234` (LM Studio). We scrutinized whether this works across Halbert’s two distribution modes:

1. **Tauri Desktop Mode (`make dev` / production build)**:
   * In Tauri, webview HTTP calls can use `@tauri-apps/api/http` or standard `fetch` with relaxed CORS for localhost. Probing works directly from the frontend.
2. **Browser Dashboard Mode (`make dev-web` @ `http://localhost:8000`)**:
   * If a user opens `http://localhost:8000` in Google Chrome, standard cross-origin security rules apply.
   * Ollama (`localhost:11434`) allows CORS by default in recent versions, but if `OLLAMA_ORIGINS` is restricted, direct browser `fetch('http://localhost:11434/api/version')` may throw a CORS network error.

### 4.2 The Solution: The Server-Side Discovery Proxy
To guarantee 100% reliability regardless of browser headers or CORS policies, Halbert’s FastAPI backend (`routes/llm.py`) must provide an asynchronous discovery route:

```python
@router.get("/api/llm/discover")
async def discover_local_engines() -> Dict[str, Any]:
    """Asynchronously probe standard localhost ports with 500ms timeout."""
    results = {
        "ollama": {"running": False, "version": None, "models": []},
        "lm_studio": {"running": False, "models": []}
    }
    # Fast loopback probe using asyncio with strict timeout
    # ...
    return results
```
* The frontend calls `GET /api/llm/discover` on mount.
* Probing runs on the server loopback interface (bypassing all browser CORS restrictions).
* Results arrive in <100ms.

---

## 5. Cross-App Schema Generalization: Reconciling the Four Repositories

We reverse-engineered the model configurations across all four sister codebases:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       CROSS-APP SCHEMA COMPARISON                           │
├─────────────────┬─────────────────────────┬─────────────────────────────────┤
│ Repository      │ Internal Config Keys    │ Use Case                        │
├─────────────────┼─────────────────────────┼─────────────────────────────────┤
│ Halbert         │ chat_model,             │ Conversational sysadmin agent,  │
│                 │ specialist_model,       │ diagnosis, terminal execution.  │
│                 │ vision_model            │                                 │
├─────────────────┼─────────────────────────┼─────────────────────────────────┤
│ SourcePrep      │ small_model,            │ Batch codebase intelligence,    │
│                 │ large_model,            │ AST edge extraction, concepts,  │
│                 │ code_model, embedding   │ vector embeddings.              │
├─────────────────┼─────────────────────────┼─────────────────────────────────┤
│ LinuxBrain      │ orchestrator,           │ Linux system cognition, image   │
│                 │ specialist, vision,     │ generation model selection,     │
│                 │ parser, image_models    │ state parsing.                  │
├─────────────────┼─────────────────────────┼─────────────────────────────────┤
│ BrightestMinds  │ (Forked from LinuxBrain │ Research cognition and          │
│                 │ with custom pipelines)  │ multi-agent debates.            │
└─────────────────┴─────────────────────────┴─────────────────────────────────┘
```

### The Architectural Verdict:
**Zero hardcoded role names in the UI package.**
The component in `packages/design-system` MUST accept an array of role definitions:
```typescript
interface AppRoleDefinition {
  id: string;              // e.g. "chat_model" or "parser"
  label: string;           // e.g. "Chat (Guide)" or "AST Parser"
  description: string;     // Helper text explaining what this slot does
  requiresTools?: boolean; // Filters for models supporting tool-use
  requiresVision?: boolean;// Filters for multimodal models
}
```
Each application supplies its own array. The reusable component handles 100% of the UI rendering, port probing, API key masking, and model dropdown building without knowing or caring what the host application's backend calls the role.

---

## 6. Implementation Verification Matrix

Before any code is committed for this feature, the technical review team should verify against this pass/fail matrix:

| Test ID | Scenario | Expected Behavior | Failure Indicator |
| :--- | :--- | :--- | :--- |
| **V-01** | Fresh install with Ollama running | App boots. Header pill reads `[🟢 Ollama · <first-model>]`. No settings configuration needed. | Empty dropdown, "Not configured" error, or prompt to add endpoint. |
| **V-02** | BYOK Anthropic key entered | User enters Anthropic key in Tab 2, clicks "Test Key". Receives green checkmark. Assigns to Specialist. | 401 Unauthorized, 404 Not Found, or dropped `api_key`. |
| **V-03** | In-chat model switch | User types `/model deepseek-r1`. System message announces switch. Next message is processed by DeepSeek. | Switch ignored; backend continues using previous model. |
| **V-04** | User Pin Override | User pins Guide model (`[🔒 Pin: Guide]`). Asks complex query (>0.5 score). | Specialist is invoked anyway; complexity router ignores pin. |
| **V-05** | Multi-turn reference | User: "Check nginx". Agent: "Nginx is stopped". User: "Start it". | Agent asks "What should I start?" (indicates empty history). |
| **V-06** | Chat model has native vision | User assigns `llama3.2-vision` to Chat. Vision slot says "Inherited from Chat". | Vision card forces user to configure a redundant second endpoint. |
| **V-07** | SourcePrep isolation | SourcePrep daemon is killed (`kill -9 $(pgrep -f "prep serve")`). Halbert chat continues working normally. | Halbert picker hides or throws connection refused to `:8400`. |

---

## 7. Next Actions for Technical Implementation

1. **Step 1 (Backend Plumbing)**:
   * Fix `model/client.py`: Update `_resolve_endpoint` to preserve `api_key`. Add Bearer headers to `_do_llm_call`.
   * Fix `routes/agent.py`: Add `model` and `tier` fields to `SendMessageRequest`. Pass `conversation_history` into `agent.process()`.
2. **Step 2 (Shared Package in `packages/design-system`)**:
   * Implement `packages/design-system/src/components/model-picker/` with the schema-agnostic dual-surface architecture.
3. **Step 3 (Halbert Frontend Wiring)**:
   * Delete `AIModelsSettings.tsx` and replace with `<ModelSettingsDrawer />`.
   * Mount `<ModelSelectorPill />` and `/model` parser into [`AgentChat.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.tsx).
4. **Step 4 (Verification Sweep)**:
   * Execute test suite `V-01` through `V-07`.
