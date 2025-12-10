# Runtime Engine

The runtime engine orchestrates Halbert's behavior using LangGraph for state machine management.

---

## Overview

The engine processes user requests through a graph of nodes, where each node represents a step in the reasoning and action pipeline.

**Code**: `halbert_core/halbert_core/runtime/langgraph_engine.py`

---

## Architecture

```
User Input
    │
    ▼
┌─────────────┐
│   Parse     │  Extract intent, entities, context
└─────────────┘
    │
    ▼
┌─────────────┐
│  Retrieve   │  Query memory, RAG, system state
└─────────────┘
    │
    ▼
┌─────────────┐
│   Reason    │  LLM decides actions
└─────────────┘
    │
    ▼
┌─────────────┐
│   Plan      │  Generate action sequence
└─────────────┘
    │
    ▼
┌─────────────┐
│  Validate   │  Policy check, confidence gate
└─────────────┘
    │
    ▼
┌─────────────┐
│  Execute    │  Run tools (dry-run or live)
└─────────────┘
    │
    ▼
┌─────────────┐
│   Store     │  Write outcomes to memory
└─────────────┘
    │
    ▼
Response
```

---

## State Management

The engine maintains state between nodes:

```python
class EngineState(TypedDict):
    # Input
    user_input: str
    context: dict
    
    # Retrieval
    retrieved_docs: list[Document]
    system_state: dict
    
    # Reasoning
    intent: str
    entities: list[str]
    confidence: float
    
    # Planning
    actions: list[Action]
    
    # Execution
    results: list[ToolResult]
    
    # Output
    response: str
```

---

## Node Implementations

### Parse Node

Extracts intent and entities from user input.

```python
def parse_node(state: EngineState) -> EngineState:
    """Extract intent and entities."""
    user_input = state["user_input"]
    
    # Use LLM to parse
    parsed = llm.parse_intent(user_input)
    
    return {
        **state,
        "intent": parsed.intent,
        "entities": parsed.entities,
    }
```

### Retrieve Node

Gathers relevant context from memory and system.

```python
def retrieve_node(state: EngineState) -> EngineState:
    """Retrieve relevant context."""
    # Query RAG
    docs = rag.retrieve(state["user_input"])
    
    # Get system state
    system = get_system_state()
    
    return {
        **state,
        "retrieved_docs": docs,
        "system_state": system,
    }
```

### Reason Node

LLM determines what actions to take.

```python
def reason_node(state: EngineState) -> EngineState:
    """LLM reasoning step."""
    prompt = build_prompt(
        user_input=state["user_input"],
        context=state["retrieved_docs"],
        system=state["system_state"],
    )
    
    response = llm.generate(prompt)
    actions = parse_actions(response)
    confidence = estimate_confidence(response)
    
    return {
        **state,
        "actions": actions,
        "confidence": confidence,
    }
```

### Validate Node

Policy enforcement and confidence gating.

```python
def validate_node(state: EngineState) -> EngineState:
    """Check policy and confidence."""
    policy = load_policy()
    
    for action in state["actions"]:
        decision = policy.evaluate(action)
        
        if not decision.allow:
            action.blocked = True
            action.reason = decision.reason
        elif decision.require_approval:
            action.needs_approval = True
    
    return state
```

### Execute Node

Runs approved actions.

```python
def execute_node(state: EngineState) -> EngineState:
    """Execute validated actions."""
    results = []
    
    for action in state["actions"]:
        if action.blocked:
            results.append(ToolResult(blocked=True))
            continue
            
        if action.needs_approval:
            approved = request_approval(action)
            if not approved:
                results.append(ToolResult(rejected=True))
                continue
        
        # Run with dry-run first
        dry_result = action.tool.execute(dry_run=True)
        
        if state.get("auto_execute") and state["confidence"] > 0.9:
            live_result = action.tool.execute(dry_run=False)
            results.append(live_result)
        else:
            results.append(dry_result)
    
    return {**state, "results": results}
```

---

## Graph Definition

```python
from langgraph.graph import StateGraph

def build_graph():
    graph = StateGraph(EngineState)
    
    # Add nodes
    graph.add_node("parse", parse_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("reason", reason_node)
    graph.add_node("validate", validate_node)
    graph.add_node("execute", execute_node)
    graph.add_node("store", store_node)
    
    # Define edges
    graph.add_edge("parse", "retrieve")
    graph.add_edge("retrieve", "reason")
    graph.add_edge("reason", "validate")
    graph.add_edge("validate", "execute")
    graph.add_edge("execute", "store")
    
    # Entry and exit
    graph.set_entry_point("parse")
    graph.set_finish_point("store")
    
    return graph.compile()
```

---

## Fallback Engine

If LangGraph is unavailable, a simpler sequential engine runs:

**Code**: `halbert_core/halbert_core/runtime/engine.py`

```python
class Engine:
    def tick(self, state: dict) -> dict:
        """Single iteration of the runtime."""
        # Sequential execution
        state = self.parse(state)
        state = self.retrieve(state)
        state = self.reason(state)
        state = self.validate(state)
        state = self.execute(state)
        return state
```

---

## CLI Integration

```bash
# Run one tick
python Halbert/main.py runtime-tick

# Run autonomous task
python Halbert/main.py autonomous-run --task-type health_check
```

---

## Extension Points

### Custom Nodes

Add new nodes by:

1. Implementing a function with signature `(EngineState) -> EngineState`
2. Adding the node to the graph
3. Defining edges to/from the node

### Custom Tools

Register tools in `halbert_core/halbert_core/tools/`:

```python
from .base import BaseTool, tool_registry

@tool_registry.register
class MyTool(BaseTool):
    name = "my_tool"
    # ...
```

---

## Related

- [ARCHITECTURE.md](../ARCHITECTURE.md) - System overview
- [design/philosophy.md](../design/philosophy.md) - Design principles
- [reference/code-map.md](../reference/code-map.md) - File locations
