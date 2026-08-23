"""
Audit script: inventory chat.py's unique features vs agent.py.

Scans chat.py for functions and endpoints that don't exist in agent.py,
categorizing each as "port", "already replaced", or "cut".

Usage:
    python -m halbert_core.tools.chat_audit
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple


def extract_functions(filepath: Path) -> List[Tuple[str, int, str]]:
    """Extract function name, line number, and docstring first line."""
    content = filepath.read_text()
    functions = []
    for match in re.finditer(
        r'^(?:    )?(?:async )?def (\w+)\(', content, re.MULTILINE
    ):
        name = match.group(1)
        line = content[:match.start()].count('\n') + 1
        # Try to get docstring
        rest = content[match.start():]
        doc_match = re.search(r'"""(.*?)"""', rest, re.DOTALL)
        doc = doc_match.group(1).strip().split('\n')[0] if doc_match else ""
        functions.append((name, line, doc))
    return functions


def extract_endpoints(filepath: Path) -> List[Tuple[str, str, int]]:
    """Extract endpoint method, path, and line number."""
    content = filepath.read_text()
    endpoints = []
    for match in re.finditer(
        r'@router\.(get|post|put|delete|patch)\("([^"]+)"\)', content
    ):
        method = match.group(1).upper()
        path = match.group(2)
        line = content[:match.start()].count('\n') + 1
        endpoints.append((method, path, line))
    return endpoints


def main():
    base = Path(__file__).resolve().parent.parent / "dashboard" / "routes"
    chat_py = base / "chat.py"
    agent_py = base / "agent.py"

    chat_fns = extract_functions(chat_py)
    agent_fns = extract_functions(agent_py)
    agent_fn_names = {name for name, _, _ in agent_fns}

    chat_endpoints = extract_endpoints(chat_py)
    agent_endpoints = extract_endpoints(agent_py)

    print("=" * 80)
    print("CHAT.PY FEATURE AUDIT")
    print("=" * 80)

    print(f"\nchat.py: {chat_py.stat().st_size} bytes, {len(chat_fns)} functions, {len(chat_endpoints)} endpoints")
    print(f"agent.py: {agent_py.stat().st_size} bytes, {len(agent_fns)} functions, {len(agent_endpoints)} endpoints")

    # ── Endpoints ──────────────────────────────────────────────
    print("\n## ENDPOINTS\n")
    print(f"| Method | Path | Line | Status |")
    print(f"|--------|------|------|--------|")

    # Categorize endpoints
    endpoint_categories = {
        "send": "Port → agent.py /message (Phase 3)",
        "send/stream": "Port → agent.py /message (already delegated via HALBERT_USE_AGENT_PATH)",
        "explain": "Cut — trivial stub, not worth porting",
        "models": "Keep on chat.py — model management, not conversation",
        "models/select": "Keep on chat.py — model management",
        "models/status": "Keep on chat.py — model management",
        "models/loaded": "Keep on chat.py — model management",
        "models/check": "Keep on chat.py — model management",
        "config": "Port → agent.py with write_config tool",
        "memory/stats": "Keep on chat.py — memory management UI",
        "memory/query": "Keep on chat.py — memory management UI",
        "memory/collections": "Keep on chat.py — memory management UI",
        "memory/entries": "Keep on chat.py — memory management UI",
        "memory/entry": "Keep on chat.py — memory management UI",
        "memory/delete": "Keep on chat.py — memory management UI",
        "memory/clear": "Keep on chat.py — memory management UI",
    }

    for method, path, line in chat_endpoints:
        # Find matching category
        status = "Review"
        for key, val in endpoint_categories.items():
            if path.startswith(key):
                status = val
                break
        print(f"| {method} | {path} | {line} | {status} |")

    # ── Unique functions ───────────────────────────────────────
    print("\n## UNIQUE FUNCTIONS (in chat.py, not in agent.py)\n")
    print(f"| Function | Line | Description | Status |")
    print(f"|----------|------|-------------|--------|")

    # Categorize functions
    fn_categories = {
        "get_prompt_builder": "Already replaced — agent.py has AgentPromptBuilder",
        "reload_prompts": "Already replaced — agent.py manages its own prompts",
        "get_context_injector": "Already replaced — agent.py has ContextInjector",
        "build_system_prompt_v2": "Already replaced — agent.py uses AgentPromptBuilder",
        "get_approval_engine": "Already replaced — agent.py has ToolSafetyFramework",
        "create_tool_approval_request": "Already replaced — agent.py has ToolExecutor",
        "get_guardrails": "Already replaced — agent.py has safety checks",
        "get_policy": "Already replaced — agent.py has policy engine",
        "check_tool_authorization": "Already replaced — agent.py has ToolExecutor",
        "get_memory_context": "Already replaced — Phase 2 memory adapter",
        "store_conversation_memory": "Already replaced — agent.py stores in memory",
        "get_telemetry_context": "PORT — telemetry injection (journald/hwmon search)",
        "get_docs_context": "Already replaced — Phase 2 SourcePrep retrieval",
        "get_discovery_context": "Already replaced — Phase 2 discovery adapter",
        "get_self_knowledge_context": "Already replaced — Phase 2 migration to SourcePrep",
        "get_loaded_models": "Keep — model management",
        "is_model_loaded": "Keep — model management",
        "get_model_status": "Keep — model management",
        "call_ollama_with_tools": "Already replaced — agent.py uses call_llm_chat",
        "should_use_tools": "Already replaced — Phase 1 intake signals",
        "call_ollama_with_images": "PORT — vision/image handling",
        "should_use_web_search": "Already replaced — Phase 1 intake signals",
        "get_web_search_context": "Already replaced — agent.py has web_search tool",
        "detect_query_topics": "Already replaced — Phase 1 intake signals",
        "get_topic_context": "Already replaced — Phase 1 intake domains",
        "get_system_identity": "Already replaced — agent.py SystemIdentityAdapter",
        "get_custom_ai_rules": "Already replaced — agent.py prompt builder",
        "get_model_router": "Already replaced — Phase 3 intake routing",
        "generate_guide_response": "Cut — MVP stub, not used",
        "generate_coder_response": "Cut — MVP stub, not used",
        "apply_edit_blocks": "PORT — config-edit diff application",
        "find_best_match": "PORT — fuzzy matching for edit blocks",
        "_delegate_to_agent_stream": "Already replaced — this IS the delegation",
        "send_message": "Port → agent.py /message",
        "send_message_stream": "Port → agent.py /message (delegation exists)",
        "explain_context": "Cut — trivial stub",
        "config_chat": "Port → agent.py with write_config tool",
    }

    for name, line, doc in chat_fns:
        if name in agent_fn_names:
            continue
        status = fn_categories.get(name, "Review")
        doc_short = doc[:60] + "..." if len(doc) > 60 else doc
        print(f"| {name} | {line} | {doc_short} | {status} |")

    # ── Summary ────────────────────────────────────────────────
    port_count = sum(1 for v in fn_categories.values() if v.startswith("PORT"))
    replaced_count = sum(1 for v in fn_categories.values() if v.startswith("Already"))
    cut_count = sum(1 for v in fn_categories.values() if v.startswith("Cut"))
    keep_count = sum(1 for v in fn_categories.values() if v.startswith("Keep"))

    print(f"\n## SUMMARY\n")
    print(f"- PORT to agent.py: {port_count}")
    print(f"- Already replaced: {replaced_count}")
    print(f"- Cut (not needed): {cut_count}")
    print(f"- Keep on chat.py (model/memory management): {keep_count}")
    print(f"\nPort items: telemetry injection, vision/image handling, config-edit blocks")
    print(f"These are the only features that need porting before chat.py can be retired.")


if __name__ == "__main__":
    main()
