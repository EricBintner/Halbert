# Phase 21: Agentic ReAct Architecture

**Status**: Planning  
**Priority**: High - Core functionality improvement  
**Objective**: Implement industry-standard agentic reasoning loop (ReAct pattern) like Cursor, Windsurf Cascade, and Copilot

---

## Research Summary

### Industry Leaders Architecture

Based on research of Cursor, Windsurf Cascade, GitHub Copilot, and academic papers:

| System | Architecture | Key Feature |
|--------|-------------|-------------|
| **Windsurf Cascade** | ReAct agent with AI Flows | Chains up to 20 tool calls without user intervention |
| **Cursor** | Embed-Think-Do loop | Mixture-of-experts: GPT-4/Claude for reasoning, specialized models for edits |
| **Copilot** | Multi-model routing | Task-specific model selection |

### The ReAct Pattern (Yao et al., 2022)

From the seminal paper "ReAct: Synergizing Reasoning and Acting in Language Models":

```
Loop until solved:
  1. THOUGHT  → AI reasons about the current state and what to do next
  2. ACTION   → AI executes a tool (run command, search, read file)
  3. OBSERVATION → AI observes the result
  4. REFLECT  → AI decides: continue loop or provide final answer
```

**Key insight**: The AI should execute tools under the hood and show its reasoning, NOT inject fake user messages asking itself questions.

### How Cascade Does It (from DiamantAI research)

1. **AI Flows**: Multi-step execution without user intervention
2. **Tool chaining**: Up to 20 sequential tool calls
3. **Live adaptation**: If user changes code, AI adapts automatically
4. **Thinking UI**: Shows "Thought for 8s" with collapsible reasoning steps
5. **Protected sandbox**: Experimental code runs in isolation

---

## The Problem (Current State)

Currently, Halbert's chat:
1. **Fake user messages** - Injects "Please analyze this output" as user message (awkward)
2. **No thinking UI** - No visibility into AI reasoning process
3. **Single-shot** - One request → one response, no tool loop
4. **Wrong model** - Uses 8b guide for complex reasoning that needs 70b specialist

---

## Industry-Standard Architecture

### Research Findings
Modern AI coding assistants share common architectural patterns:

1. **Chat Message Arrays** - Structured conversation with distinct roles
2. **Tool Calling** - AI invokes tools for file operations, search, commands
3. **Codebase Embeddings** - Vector search for relevant context retrieval
4. **Context Window Management** - Track usage, summarize when needed
5. **Streaming Responses** - Token-by-token output for responsive UX
6. **Context Blocks** - Attach terminal output/errors as structured context

### The Standard Pattern: Chat API Format
```json
{
  "model": "llama3.3:70b",
  "messages": [
    {"role": "system", "content": "You are Linus, a Linux admin assistant..."},
    {"role": "user", "content": "Why did this service fail?"},
    {"role": "assistant", "content": "Let's check the status..."},
    {"role": "user", "content": "Command output:\n```\nError: Syntax error...\n```"},
    {"role": "user", "content": "looks like the command is malformed"}
  ],
  "stream": true
}
```

**Key insight**: The LLM sees the actual conversation structure, not a concatenated mess.

---

## Phase 21 Implementation Plan

### Milestone 1: ReAct Agent Loop (Core)
**Goal**: Implement the Thought → Action → Observation loop

**New file**: `halbert_core/agents/react_agent.py`

```python
class ReActAgent:
    """
    ReAct agent implementing Thought-Action-Observation loop.
    Based on Yao et al. 2022 and Cascade/Cursor architectures.
    """
    
    MAX_ITERATIONS = 10  # Prevent infinite loops (Cursor uses 3-5)
    
    async def run(self, query: str, context: ConversationContext) -> AgentResponse:
        """
        Execute ReAct loop until solution or max iterations.
        
        Returns AgentResponse with:
          - thinking_steps: List of thoughts for UI
          - tool_calls: List of actions taken
          - final_response: The synthesized answer
        """
        steps = []
        
        for i in range(self.MAX_ITERATIONS):
            # 1. THOUGHT - AI reasons about current state
            thought = await self._generate_thought(query, context, steps)
            steps.append(ThinkingStep(type="thought", content=thought))
            
            # 2. Decide: ACTION or FINAL ANSWER?
            decision = await self._decide_next(thought)
            
            if decision.type == "final_answer":
                return AgentResponse(
                    thinking_steps=steps,
                    final_response=decision.content
                )
            
            # 3. ACTION - Execute tool
            action = decision.action
            steps.append(ThinkingStep(type="action", content=f"Running: {action}"))
            
            # 4. OBSERVATION - Get result
            observation = await self._execute_tool(action)
            steps.append(ThinkingStep(type="observation", content=observation))
            
            # Add to context for next iteration
            context.add_tool_result(action, observation)
        
        # Max iterations reached
        return self._synthesize_response(steps)
```

**Key differences from current approach**:
- Loop runs under the hood, not fake user messages
- Thinking steps are tracked separately for UI
- Tools executed automatically without user intervention
- Final response synthesizes all observations

### Milestone 2: Thinking UI Component
**Goal**: Show reasoning steps like Cascade's "Thought for 8s >"

**Frontend component**: `ThinkingSteps.tsx`

```tsx
interface ThinkingStep {
  type: 'thought' | 'action' | 'observation'
  content: string
  duration_ms?: number
}

function ThinkingSteps({ steps, isExpanded }: { steps: ThinkingStep[], isExpanded: boolean }) {
  const totalTime = steps.reduce((acc, s) => acc + (s.duration_ms || 0), 0)
  
  return (
    <div className="thinking-container">
      <button onClick={toggle} className="thinking-header">
        <span>Thought for {(totalTime/1000).toFixed(0)}s</span>
        <ChevronDown className={isExpanded ? 'rotate-180' : ''} />
      </button>
      
      {isExpanded && (
        <div className="thinking-steps">
          {steps.map((step, i) => (
            <div key={i} className={`step step-${step.type}`}>
              {step.type === 'action' && <Terminal className="icon" />}
              {step.type === 'thought' && <Brain className="icon" />}
              {step.type === 'observation' && <Eye className="icon" />}
              <span>{step.content}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

**UI Flow**:
```
User: "Why did mount-bcachefs fail?"

[AI Response]
┌─ Thought for 12s ────────────────────────────┐
│ ▶ Thought: Need to check service status      │
│ ▶ Action: journalctl -u mount-bcachefs -n 20 │
│ ▶ Observation: [log output...]               │
│ ▶ Thought: I see bcachefs-tools not found    │
│ ▶ Action: which bcachefs                     │
│ ▶ Observation: bcachefs not found            │
│ ▶ Thought: The tool is missing, that's cause │
└──────────────────────────────────────────────┘

The mount-bcachefs service failed because the bcachefs 
userspace tools are not installed. The service tries to 
run `bcachefs mount` but the command doesn't exist.

**To fix:**
```bash
sudo apt install bcachefs-tools  # or build from source
```
```

### Milestone 3: Tool Execution Engine
**Goal**: Execute tools under the hood safely

**Existing tools to wire up** (from `tools/system_tools.py`):
- `get_service_status(service_name)` - Service status + logs
- `check_disk_space(path)` - Disk usage
- `run_command(cmd)` - Execute shell command (with safety checks)
- `read_file(path)` - Read config files
- `list_running_services()` - All services

**Safety model** (like Cursor):
```python
class ToolSafety(Enum):
    READ_ONLY = "read_only"      # Auto-execute: journalctl, cat, ls
    WRITE = "write"              # Require approval: rm, edit, restart
    DANGEROUS = "dangerous"      # Block or double-confirm: rm -rf, format

TOOL_SAFETY = {
    "journalctl": ToolSafety.READ_ONLY,
    "systemctl status": ToolSafety.READ_ONLY,
    "cat": ToolSafety.READ_ONLY,
    "ls": ToolSafety.READ_ONLY,
    "systemctl restart": ToolSafety.WRITE,
    "rm": ToolSafety.DANGEROUS,
}
```

### Milestone 4: Smart Model Routing (Fix Current Bug)
**Goal**: Actually use specialist model for reasoning

**Current bug**: Tool-calling path bypasses complexity routing.

**Fix**: Unified routing at agent level:
```python
class ReActAgent:
    async def run(self, query: str, context: ConversationContext):
        # Route at the start based on query complexity
        complexity = score_query_complexity(query)
        
        if complexity >= 0.5:
            self.model = self.specialist_model  # llama3.3:70b
            logger.info(f"Using specialist for complex query (score: {complexity})")
        else:
            self.model = self.guide_model  # llama3.1:8b
        
        # All reasoning in the loop uses this model
        ...
```

### Milestone 5: Streaming + Real-time Updates
**Goal**: Show thinking steps as they happen

**WebSocket protocol**:
```json
// Server → Client messages
{"type": "thinking_start", "step_id": 1}
{"type": "thought", "step_id": 1, "content": "Need to check service logs"}
{"type": "action_start", "step_id": 2, "command": "journalctl -u mount-bcachefs"}
{"type": "action_complete", "step_id": 2, "output": "...", "duration_ms": 342}
{"type": "observation", "step_id": 3, "content": "Service failed due to..."}
{"type": "final_response_start"}
{"type": "token", "content": "The"}
{"type": "token", "content": " mount"}
{"type": "final_response_end"}
```

---

## Existing Infrastructure Inventory

### Already Implemented (Use These!)

| Component | Location | Purpose |
|-----------|----------|---------|
| `Message`, `MessageRole` | `model/context_handoff.py` | Structured message format with roles |
| `ConversationContext` | `model/context_handoff.py` | Conversation history container |
| `ContextHandoffEngine` | `model/context_handoff.py` | Context window management, summarization |
| `HandoffStrategy` | `model/context_handoff.py` | FULL, SUMMARIZED, MINIMAL, RAG_ENHANCED |
| `ModelRouter` | `model/router.py` | Task-based model routing |
| `TaskType` | `model/router.py` | CHAT, CODE_GENERATION, REASONING, etc. |
| `SYSTEM_TOOLS` | `tools/system_tools.py` | Function definitions for tool calling |
| `OllamaProvider` | `model/providers/ollama.py` | Ollama API client (needs `chat()` method) |
| `RAG pipeline` | `rag/pipeline.py` | Context retrieval from knowledge base |
| Conversation storage | `dashboard/routes/conversations.py` | Persist conversations to DB |

### Not Using (Problem!)

| Component | Current State | Should Be |
|-----------|---------------|-----------|
| `chat.py` send_message | Builds concatenated string prompt | Use `ConversationContext` + message arrays |
| Command outputs | Added to prompt string | Proper `Message` with `TOOL` or `USER` role |
| History handling | Manual string concatenation | Use `ContextHandoffEngine.prepare_handoff()` |
| Token tracking | Not implemented | Use `ConversationContext.get_token_estimate()` |

---

## Technical Details

### Ollama Chat API
```python
def chat(self, messages: List[dict], model: str, **kwargs) -> str:
    response = requests.post(
        f"{self.base_url}/api/chat",
        json={
            "model": model,
            "messages": messages,
            "stream": False,  # or True for streaming
            "options": {"temperature": 0.7, "num_predict": 2048}
        },
        timeout=180
    )
    return response.json()["message"]["content"]
```

### Message Array Construction
```python
def build_messages(conversation: ConversationManager, system_prompt: str) -> List[dict]:
    messages = [{"role": "system", "content": system_prompt}]
    
    for msg in conversation.get_relevant_history():
        messages.append({
            "role": msg.role,
            "content": msg.content
        })
    
    return messages
```

### Command Output as Message
```python
# When command is executed inline
command_output_msg = ChatMessage(
    role="user",  # User provided this context
    content=f"I ran the command. Here's the output:\n```\n{output}\n```",
    metadata={"type": "command_output", "command": cmd, "exit_code": code}
)
conversation.add_message(command_output_msg)
```

---

## Success Criteria

1. **Context Understanding**: AI analyzes visible command outputs without asking for clarification
2. **Natural Follow-ups**: "Why did that fail?" works without re-explaining
3. **Long Conversations**: Works well even after 20+ messages
4. **Streaming**: Responses appear token-by-token
5. **Tool Integration**: AI can proactively gather information

---

## References

### Academic Papers
- **ReAct (Yao et al., 2022)** - [arXiv:2210.03629](https://arxiv.org/abs/2210.03629) - The foundational paper on Reasoning+Acting in LLMs
- **Chain-of-Thought (Wei et al., 2022)** - [arXiv:2201.11903](https://arxiv.org/abs/2201.11903) - CoT prompting for reasoning

### Industry Research
- **[The Hidden Algorithms Powering Your Coding Assistant](https://diamantai.substack.com/p/the-hidden-algorithms-powering-your)** - Deep dive into Cursor/Windsurf architecture
- **[IBM: What is a ReAct Agent?](https://www.ibm.com/think/topics/react-agent)** - ReAct loop explanation
- **[Prompt Engineering Guide: ReAct](https://www.promptingguide.ai/techniques/react)** - ReAct prompting techniques

### Ollama/LLM APIs
- [Ollama Chat API](https://github.com/ollama/ollama/blob/main/docs/api.md#generate-a-chat-completion)
- [Ollama Tool Calling](https://github.com/ollama/ollama/blob/main/docs/api.md#chat-request-with-tools)

---

## Timeline Estimate

| Milestone | Effort | Dependencies |
|-----------|--------|--------------|
| M1: ReAct Agent Loop | 3-4 days | None |
| M2: Thinking UI | 2-3 days | M1 |
| M3: Tool Execution Engine | 2-3 days | M1 |
| M4: Smart Model Routing | 1 day | M1 |
| M5: Streaming + WebSocket | 3-4 days | M1, M2 |

**Total**: ~2-3 weeks for full implementation

---

## Quick Win: Immediate Fix

Before full ReAct implementation, we can fix the current awkward behavior:

### Current (Bad)
```
User: clicks Run on command
→ UI injects: "I ran command X and got output Y. Please analyze..."
→ This appears as a user message (awkward)
→ AI responds
```

### Quick Fix (Better)
```
User: clicks Run on command  
→ Command executes under the hood
→ Output is added to context (not as visible message)
→ AI automatically continues with analysis
→ Single AI response with embedded output + analysis
```

**Implementation**: Modify `onAutoAnalyze` to NOT create a visible user message, but instead trigger a background continuation that only shows the AI response.
