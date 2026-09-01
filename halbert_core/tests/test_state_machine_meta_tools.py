# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A9b: new_thread / recall_thread / resume_thread are handled
inline in PLANNING: no tool card, no loop increment, PLANNING re-runs once."""

from types import SimpleNamespace

import pytest

from halbert_core.agents.states import AgentState, CRAGAction, StateContext
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.llm_client import LLMResponse, ToolCall, FunctionCall
from halbert_core.prompts import AgentPromptBuilder
from halbert_core.prompts.agent_prompts import RECALLED_SECTION_HEADER
from halbert_core.tools import ToolExecutor, ToolSafetyFramework


class _FakeStore:
    """Only list_messages: what _last_turn_id needs from the store."""

    def __init__(self, rows_by_thread):
        self.rows = rows_by_thread

    def list_messages(self, thread_id, *, limit=None):
        return list(self.rows.get(thread_id, []))


class _FakeThreadManager:
    def __init__(self, recall_results=None, resume_ok=True, store=None):
        self.calls, self.recall_results, self.resume_ok = [], recall_results or [], resume_ok
        self.store = store

    def new_thread(self, title, reason, *, from_thread_id):
        self.calls.append(("new_thread", title, reason, from_thread_id))
        return "t-new"

    def recall(self, query=None, thread_id=None, *, exclude_thread_id=None, domains=None):
        self.calls.append(("recall", query, thread_id, exclude_thread_id, domains))
        return list(self.recall_results)

    def resume_thread(self, thread_id, *, from_thread_id):
        self.calls.append(("resume_thread", thread_id, from_thread_id))
        return self.resume_ok


class _ScriptedLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        #: The arrays themselves, and deliberately NOT their join. Since the
        #: merge the instructions (context, receipts) are ``messages[0]`` and
        #: the question — with the continuity hint glued to its front — is the
        #: last message, so an assertion that means "in the instructions" has
        #: to be able to say so: over a flattened join it also matches the
        #: question, and an ordering assertion across the join compares two
        #: positions that may be in different messages. A ``prompts`` attribute
        #: holding that join is what let those assertions pass while the
        #: instructions had moved; it is gone rather than left unread, so no
        #: later assertion can reach for it.
        self.arrays = []

    def instructions(self, index=0):
        """``messages[0]`` of the ``index``-th chat call."""
        return self.arrays[index][0]["content"]

    async def chat(self, messages, tools=None, **kwargs):
        self.arrays.append([dict(m) for m in messages])
        return self.responses.pop(0) if self.responses else LLMResponse(content="answer", tool_calls=[], plan=[])

    async def stream(self, messages, **kwargs):
        yield "answer"


def _call(name, **args):
    return LLMResponse(content="", tool_calls=[ToolCall(id="c1", function=FunctionCall(name=name, arguments=args))])


def _agent(llm):
    return AgentStateMachine(llm_client=llm, tool_executor=ToolExecutor(safety=ToolSafetyFramework()), max_loops=5)


def _planning(llm, tm, thread_id="t-open", **kw):
    agent = _agent(llm)
    agent.ctx = StateContext(session_id="s", request_id="r", user_query="now scanner share", thread_id=thread_id, **kw)
    agent.ctx.thread_manager = tm
    agent.current_state = AgentState.PLANNING
    return agent


RECALLED = {"thread_id": "t-9", "title": "Samba media share", "date": "2026-07-14",
            "receipt": "Title: Samba media share\nCommands: testparm (exit 0)",
            "matching_messages": ["added [media]"], "match_terms": ["samba", "share"]}


@pytest.mark.asyncio
async def test_new_thread_emits_thread_started_and_reenters_planning_without_loop_increment():
    tm = _FakeThreadManager()
    agent = _planning(_ScriptedLLM([_call("new_thread", title="Scanner share", reason="topic changed")]), tm,
                      thread_id="t-old", conversation_history=[{"role": "user", "content": "old"}])
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["thread_started", "state_change"]
    assert events[0].data == {"thread_id": "t-new", "title": "Scanner share", "reason": "topic changed", "previous_thread_id": "t-old"}
    assert events[1].data["state"] == "planning" and events[1].data["previous_state"] == "planning"
    assert agent.ctx.loop_count == 0
    assert agent.ctx.thread_id == "t-new" and agent.ctx.thread_switched is True
    assert agent.ctx.conversation_history == [] and "Scanner share" in agent.ctx.continuity_hint
    assert tm.calls == [("new_thread", "Scanner share", "topic changed", "t-old")]


@pytest.mark.asyncio
async def test_second_new_thread_in_a_turn_is_a_noop_that_reflects():
    tm = _FakeThreadManager()
    agent = _planning(_ScriptedLLM([_call("new_thread", title="Again", reason="r")]), tm, thread_id="t-new")
    agent.ctx.thread_switched = True
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["state_change"] and events[0].data["state"] == "reflecting"
    assert tm.calls == [] and agent.ctx.loop_count == 0


@pytest.mark.asyncio
async def test_full_turn_reenters_planning_exactly_once():
    tm = _FakeThreadManager()
    llm = _ScriptedLLM([_call("new_thread", title="Scanner share", reason="r")])
    agent = _agent(llm)
    events = [e async for e in agent.process("now scanner share", session_id="s-full", thread_id="t-old", thread_manager=tm)]
    types = [e.type for e in events]
    reentries = [e for e in events if e.type == "state_change" and e.data["state"] == "planning" and e.data["previous_state"] == "planning"]
    assert len(reentries) == 1 and types.count("thread_started") == 1
    assert "response_complete" in types and "session_ended" in types and "tool_start" not in types
    assert agent.ctx.loop_count <= 1
    # The second PLANNING pass saw the new hint — in the instructions, which
    # is where the simple planning prompt puts it, not merely somewhere in
    # the array.
    assert any("Scanner share" in llm.instructions(i)
               for i in range(1, len(llm.arrays)))


@pytest.mark.asyncio
async def test_store_failure_emits_thread_store_error_and_still_switches():
    tm = _FakeThreadManager()

    def boom(title, reason, *, from_thread_id):
        raise RuntimeError("db locked")

    tm.new_thread = boom
    agent = _planning(_ScriptedLLM([_call("new_thread", title="T", reason="r")]), tm, thread_id="t-old")
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["thread_store_error", "thread_started", "state_change"]
    assert "db locked" in events[0].data["message"]
    assert agent.ctx.thread_switched is True and agent.ctx.thread_id != "t-old"
    # No manager at all still switches in memory.
    agent2 = _planning(_ScriptedLLM([_call("new_thread", title="T", reason="r")]), None, thread_id="t-old")
    assert [e.type async for e in agent2._handle_planning()] == ["thread_started", "state_change"]


@pytest.mark.asyncio
async def test_recall_injects_receipt_emits_thread_recalled_and_repeat_reflects():
    tm = _FakeThreadManager(
        recall_results=[RECALLED],
        store=_FakeStore({"t-9": [{"turn_id": "turn-a"}, {"turn_id": "turn-b"}, {"turn_id": None}]}),
    )
    agent = _planning(_ScriptedLLM([_call("recall_thread", query="samba share"), _call("recall_thread", query="samba share")]), tm)
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["thread_recalled", "state_change"]
    assert events[0].data["thread_id"] == "t-9" and events[0].data["mode"] == "tool"
    assert events[0].data["match_terms"] == ["samba", "share"]
    assert events[0].data["last_turn_id"] == "turn-b"   # newest row with a turn_id
    assert tm.calls == [("recall", "samba share", None, "t-open", None)]
    assert agent.ctx.retrieved_context[0]["source"] == "thread" and "testparm" in agent.ctx.retrieved_context[0]["content"]
    assert agent.ctx.recalled_threads[0]["thread_id"] == "t-9"
    assert agent.ctx.loop_count == 0 and agent.ctx.thread_switched is False
    second = [e async for e in agent._handle_planning()]
    assert second[-1].data["state"] == "reflecting" and len(tm.calls) == 1


@pytest.mark.asyncio
async def test_recall_without_a_store_has_no_last_turn_id():
    tm = _FakeThreadManager(recall_results=[RECALLED])          # no .store
    agent = _planning(_ScriptedLLM([_call("recall_thread", query="samba share")]), tm)
    events = [e async for e in agent._handle_planning()]
    assert events[0].type == "thread_recalled" and events[0].data["last_turn_id"] is None
    # a recall result that already names its last turn wins over the store
    tm2 = _FakeThreadManager(recall_results=[dict(RECALLED, last_turn_id="turn-given")],
                             store=_FakeStore({"t-9": [{"turn_id": "turn-store"}]}))
    agent2 = _planning(_ScriptedLLM([_call("recall_thread", query="samba share")]), tm2)
    events2 = [e async for e in agent2._handle_planning()]
    assert events2[0].data["last_turn_id"] == "turn-given"


@pytest.mark.asyncio
async def test_recall_with_no_match_is_a_normal_observation():
    agent = _planning(_ScriptedLLM([_call("recall_thread", query="nothing")]), _FakeThreadManager(recall_results=[]))
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["state_change"] and events[0].data["state"] == "planning"
    assert any("No earlier thread matched" in o for o in agent.ctx.observations)


@pytest.mark.asyncio
async def test_resume_switches_thread_and_injects_receipt():
    tm = _FakeThreadManager(recall_results=[{"thread_id": "t-paused", "title": "NAS setup", "date": "2026-06-30",
                                             "receipt": "Title: NAS setup", "matching_messages": [], "match_terms": []}])
    agent = _planning(_ScriptedLLM([_call("resume_thread", thread_id="t-paused")]), tm)
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["thread_started", "state_change"]
    assert events[0].data == {"thread_id": "t-paused", "title": "NAS setup", "reason": "resumed", "previous_thread_id": "t-open"}
    assert ("resume_thread", "t-paused", "t-open") in tm.calls
    assert agent.ctx.thread_id == "t-paused" and agent.ctx.thread_switched is True
    assert agent.ctx.conversation_history[0]["role"] == "system" and "NAS setup" in agent.ctx.conversation_history[0]["content"]


@pytest.mark.asyncio
async def test_resume_failure_keeps_the_open_thread():
    agent = _planning(_ScriptedLLM([_call("resume_thread", thread_id="t-none")]), _FakeThreadManager(resume_ok=False))
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["state_change"]
    assert agent.ctx.thread_id == "t-open" and agent.ctx.thread_switched is False
    assert any("Could not resume" in o for o in agent.ctx.observations)


# -----------------------------------------------------------------------------
# Review round: the no-op signal, the re-entry bound, and CRAG's input
# -----------------------------------------------------------------------------


class _CragStub:
    """Records every document list it is asked to score, and how.

    ``**kwargs`` was widened for the per-turn overrides the merge added to
    both call sites (P3: a pin must not be silently escaped by CRAG, which
    shares the adapter). Widening a stub costs coverage unless what arrives
    through it is also recorded — with the kwargs discarded, deleting both
    arguments from the production call sites left the whole suite green.
    """

    def __init__(self, action="CORRECT", confidence=0.95):
        self.calls, self._action, self._confidence = [], action, confidence
        self.kwargs = []

    async def evaluate(self, query, documents, observations, **kwargs):
        self.calls.append(list(documents))
        self.kwargs.append(dict(kwargs))
        return SimpleNamespace(
            confidence=self._confidence, action=SimpleNamespace(value=self._action)
        )


def _crag_planning(llm, crag, tm=None, **kw):
    agent = AgentStateMachine(
        llm_client=llm, tool_executor=ToolExecutor(safety=ToolSafetyFramework()),
        crag_evaluator=crag, max_loops=5,
    )
    agent.ctx = StateContext(session_id="s", request_id="r",
                             user_query="now scanner share", thread_id="t-open", **kw)
    agent.ctx.thread_manager = tm
    agent.current_state = AgentState.PLANNING
    return agent


@pytest.mark.asyncio
async def test_a_genuine_second_new_thread_reflects_instead_of_replanning():
    """The no-op signal must not be "tool_calls[-1].name == tool_name".

    A second new_thread records nothing, so the record left at index -1 is the
    *first* new_thread's — a name check reads that as a success and re-enters
    PLANNING on a context nothing changed in. Production can only reach the
    no-op this way (whatever set thread_switched also recorded a call), so
    this is the test that actually exercises the branch.
    """
    tm = _FakeThreadManager()
    agent = _planning(
        _ScriptedLLM([_call("new_thread", title="One", reason="a"),
                      _call("new_thread", title="Two", reason="b")]),
        tm, thread_id="t-old",
    )
    first = [e async for e in agent._handle_planning()]
    assert [e.type for e in first] == ["thread_started", "state_change"]
    assert first[-1].data["state"] == "planning"

    second = [e async for e in agent._handle_planning()]
    assert [e.type for e in second] == ["state_change"]
    assert second[0].data["state"] == "reflecting"
    assert tm.calls == [("new_thread", "One", "a", "t-old")]
    assert [tc.name for tc in agent.ctx.tool_calls] == ["new_thread"]
    assert agent.ctx.meta_tool_reentries == 1
    assert agent.ctx.loop_count == 0


@pytest.mark.asyncio
async def test_meta_tool_reentries_are_bounded_and_never_hit_the_oscillation_guard():
    """Inline meta-tools skip loop_count, so max_loops cannot end a
    PLANNING→PLANNING chain of *differing* calls. Without its own bound the
    only backstop is _detect_oscillation, which ends the turn with a
    user-visible "State oscillation detected" error."""
    tm = _FakeThreadManager(recall_results=[RECALLED])
    llm = _ScriptedLLM([_call("recall_thread", query=f"q{i}") for i in range(3)])
    agent = _agent(llm)
    events = [e async for e in agent.process(
        "what came of the share", session_id="s-bound", thread_id="t-old", thread_manager=tm)]
    types = [e.type for e in events]
    reentries = [e for e in events
                 if e.type == "state_change"
                 and e.data["state"] == "planning" and e.data["previous_state"] == "planning"]
    assert len(reentries) == AgentStateMachine.MAX_META_TOOL_REENTRIES == 2
    assert not any(e.type == "error" and "oscillation" in str(e.data.get("message", "")).lower()
                   for e in events)
    assert types.count("thread_recalled") == 3      # the third call still took effect
    assert agent.ctx.meta_tool_reentries == 3
    assert "response_complete" in types and "session_ended" in types


@pytest.mark.asyncio
async def test_recall_receipts_do_not_switch_crag_on_so_the_turn_still_searches():
    """A recalled receipt is continuity, not retrieval. Scoring it turned CRAG
    on for a turn that had retrieved nothing, and a CORRECT verdict routed
    PLANNING straight to REFLECTING — answering off the receipt and never
    querying host knowledge for the actual question."""
    crag = _CragStub(action="CORRECT", confidence=0.95)
    tm = _FakeThreadManager(recall_results=[RECALLED])
    llm = _ScriptedLLM([_call("recall_thread", query="samba share"),
                        LLMResponse(content="", tool_calls=[], plan=[])])
    agent = _crag_planning(llm, crag, tm)

    first = [e async for e in agent._handle_planning()]
    assert [e.type for e in first] == ["thread_recalled", "state_change"]
    assert first[-1].data["state"] == "planning"

    second = [e async for e in agent._handle_planning()]
    assert crag.calls == []
    assert "confidence_update" not in [e.type for e in second]
    assert agent.ctx.crag_action == CRAGAction.PENDING
    assert second[-1].data["state"] == "searching"


@pytest.mark.asyncio
async def test_crag_scores_real_retrieval_and_skips_the_thread_entries():
    crag = _CragStub(action="CORRECT", confidence=0.95)
    agent = _crag_planning(_ScriptedLLM([LLMResponse(content="", tool_calls=[], plan=[])]), crag)
    agent.ctx.add_context(source="thread", content="Title: Samba media share", metadata={})
    agent.ctx.add_context(source="rag", content="smb.conf lives in /etc/samba", metadata={})
    events = [e async for e in agent._handle_planning()]
    assert len(crag.calls) == 1 and [d["source"] for d in crag.calls[0]] == ["rag"]
    assert agent.ctx.crag_action == CRAGAction.CORRECT
    assert events[-1].data["state"] == "reflecting"


@pytest.mark.asyncio
async def test_a_turn_with_no_pin_still_names_both_overrides_to_crag():
    """An unpinned turn passes None for both rather than passing nothing:
    a stub or evaluator that reads them by keyword must not have to guess
    whether "absent" meant "unpinned" or "never wired"."""
    crag = _CragStub(action="CORRECT", confidence=0.95)
    agent = _crag_planning(_ScriptedLLM([LLMResponse(content="", tool_calls=[], plan=[])]), crag)
    agent.ctx.add_context(source="rag", content="smb.conf lives in /etc/samba", metadata={})

    [e async for e in agent._handle_planning()]

    # ``secure`` rides the same contract: the evaluator resolves a secure
    # turn to a local model only, so it must be named on every call, not
    # left for the stub to infer from its absence.
    assert crag.kwargs == [
        {"model_override": None, "tier_override": None, "secure": False}
    ]


@pytest.mark.asyncio
async def test_observing_does_not_treat_a_thread_receipt_as_retrieval():
    crag = _CragStub()
    agent = _crag_planning(_ScriptedLLM([]), crag)
    agent.ctx.add_context(source="thread", content="Title: Samba media share", metadata={})
    agent.current_state = AgentState.OBSERVING
    events = [e async for e in agent._handle_observing()]
    assert crag.calls == []
    assert agent.ctx.crag_action == CRAGAction.INCORRECT and agent.ctx.confidence == 0.3
    assert events[-1].data["state"] == "planning"


# -----------------------------------------------------------------------------
# Review round 2: a receipt is continuity, not retrieval — it must not spend
# the answer prompt's retrieval slots; the last-turn lookup must not
# materialise the recalled thread; and the PLANNING pass the re-entry pays
# for must really contain what the recall observation says it contains.
# -----------------------------------------------------------------------------


class _FakeAssembler:
    """Only assemble(): what _handle_planning needs from a context assembler."""

    def __init__(self, content="ASSEMBLED-CONTEXT"):
        self.content, self.calls = content, []

    async def assemble(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=self.content, sources=[], total_tokens=7)


def _with_context(agent, receipts=0, docs=0, source="rag"):
    for i in range(receipts):
        agent.ctx.add_context(
            source="thread", content=f"Title: earlier {i}\nCommands: testparm (exit 0)",
            metadata={"thread_id": f"t-{i}", "title": f"Earlier {i}", "date": "2026-07-14"},
        )
    for i in range(docs):
        agent.ctx.add_context(
            source=source, content=f"RAGDOC-{i} body", metadata={"id": f"doc-{i}"},
        )
    return agent


@pytest.mark.asyncio
async def test_recalled_receipts_reach_the_planning_pass_the_reentry_pays_for():
    """recall_thread tells the model "their receipts are in the available
    context", but the receipts only ever reached RESPONDING: PLANNING's
    context comes from the assembler, which has no parameter carrying
    retrieved_context, so the re-entry bought a round trip that saw the thread
    names next to a false claim about where their content was."""
    tm = _FakeThreadManager(recall_results=[RECALLED])
    llm = _ScriptedLLM([_call("recall_thread", query="samba share"),
                        LLMResponse(content="", tool_calls=[], plan=[])])
    agent = _planning(llm, tm)
    first = [e async for e in agent._handle_planning()]
    assert first[-1].data["state"] == "planning"
    [e async for e in agent._handle_planning()]

    replan = llm.instructions(1)
    assert "testparm" in replan          # the receipt itself, not only its title
    block = RECALLED_SECTION_HEADER.lstrip("# ")
    assert block in replan
    said = [o for o in agent.ctx.observations if "Recalled earlier subjects" in o]
    # The observation names the block the receipts are actually rendered in.
    assert said and "in the available context" in said[0] and block in said[0]


@pytest.mark.asyncio
async def test_recalled_receipts_reach_the_assembled_planning_prompt_too():
    """The same, on the path that actually runs in production: a wired
    assembler and the real prompt builder. The receipts follow the assembled
    context rather than replacing it."""
    tm = _FakeThreadManager(recall_results=[RECALLED])
    llm = _ScriptedLLM([_call("recall_thread", query="samba share"),
                        LLMResponse(content="", tool_calls=[], plan=[])])
    assembler = _FakeAssembler()
    agent = AgentStateMachine(
        llm_client=llm, tool_executor=ToolExecutor(safety=ToolSafetyFramework()),
        context_assembler=assembler, prompt_builder=AgentPromptBuilder(), max_loops=5,
    )
    agent.ctx = StateContext(session_id="s", request_id="r",
                             user_query="now scanner share", thread_id="t-open")
    agent.ctx.thread_manager = tm
    agent.current_state = AgentState.PLANNING

    [e async for e in agent._handle_planning()]
    [e async for e in agent._handle_planning()]

    # One message, so the ordering below compares two positions in one
    # string rather than across a join of the whole array.
    replan = llm.instructions(1)
    assert "ASSEMBLED-CONTEXT" in replan and "testparm" in replan
    assert replan.index("ASSEMBLED-CONTEXT") < replan.index("testparm")


def test_the_simple_answer_prompt_keeps_all_five_retrieved_documents():
    """Receipts are prepended to retrieved_context during PLANNING, before
    SEARCHING appends anything, so a [:5] slice over the whole list handed
    three of the five answer slots to continuity and dropped real hits."""
    agent = _with_context(_planning(_ScriptedLLM([]), None), receipts=3, docs=5)
    prompt = agent._build_simple_response_prompt()
    assert all(f"RAGDOC-{i}" in prompt for i in range(5))
    assert "testparm" in prompt          # the receipts are still there, elsewhere


def test_receipts_do_not_crowd_provenance_out_of_the_retrieved_context():
    """_extract_provenance walks the same first five entries: three receipts
    (which can never produce a ref) thinned the citations too."""
    agent = _with_context(_planning(_ScriptedLLM([]), None), receipts=3)
    for i in range(3):
        agent.ctx.add_context(source="memory", content=f"mem {i}", metadata={"id": f"mem-{i}"})
    refs = agent._extract_provenance("an answer with no paths in it")
    assert [r["ref"] for r in refs] == ["mem-0", "mem-1", "mem-2"]


@pytest.mark.asyncio
async def test_the_last_turn_lookup_asks_the_store_for_one_id():
    """list_messages(thread_id) materialises every row of the recalled thread
    and JSON-decodes four columns of each (~30 ms on a 4k-row thread, under
    the store lock) to read one column of one row — up to three times per
    recall_thread, and once per turn under A9c's auto-recall."""

    class _IndexedStore:
        def __init__(self):
            self.asked = []

        def last_turn_id(self, thread_id):
            self.asked.append(thread_id)
            return "turn-indexed"

        def list_messages(self, thread_id, *, limit=None):
            raise AssertionError("the whole thread must not be read for one turn id")

    store = _IndexedStore()
    tm = _FakeThreadManager(recall_results=[RECALLED], store=store)
    agent = _planning(_ScriptedLLM([_call("recall_thread", query="samba share")]), tm)
    events = [e async for e in agent._handle_planning()]
    assert events[0].type == "thread_recalled"
    assert events[0].data["last_turn_id"] == "turn-indexed"
    assert store.asked == ["t-9"]


@pytest.mark.asyncio
async def test_resume_keeps_the_resumed_receipt_in_one_place():
    """The resumed subject's receipt IS the current subject's history: it
    belongs in the conversation's receipt slot, which the assembler budgets.
    The second copy on retrieved_context made it look like retrieval and got
    it rendered twice in the answer prompt."""
    tm = _FakeThreadManager(recall_results=[{"thread_id": "t-paused", "title": "NAS setup",
                                             "date": "2026-06-30", "receipt": "Title: NAS setup",
                                             "matching_messages": [], "match_terms": []}])
    agent = _planning(_ScriptedLLM([_call("resume_thread", thread_id="t-paused")]), tm)
    [e async for e in agent._handle_planning()]
    assert "NAS setup" in agent.ctx.conversation_history[0]["content"]
    assert agent.ctx.retrieved_context == []


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["planning", "observing"])
async def test_the_turns_pin_rides_along_to_crag(state):
    """CRAG shares the adapter, so a pin it does not carry is a pin escaped.

    ``inspect.signature(CRAGEvaluator.evaluate)`` pins that the parameters
    exist; nothing pinned that the state machine passes them. It does, from
    both evaluation sites — PLANNING's and OBSERVING's.

    What that costs when it is wrong: the evaluator's confidence verdict
    decides whether the turn searches at all, so a turn pinned to one model
    can have that decision made by whatever the adapter's own configuration
    routes to. The overrides ride on the ``StateContext`` (E-2); an override
    that is not passed through here is silently escaped rather than refused.

    This is the only pin on that seam, and it needs to be: the ``_CragStub``
    accepted ``**kwargs`` and recorded them, but nothing read what it
    recorded, so deleting both arguments from both call sites left the entire
    backend suite green.
    """
    crag = _CragStub(action="CORRECT", confidence=0.95)
    agent = _crag_planning(
        _ScriptedLLM([LLMResponse(content="", tool_calls=[], plan=[])]), crag,
        model_override="pinned:3b", tier_override="specialist",
    )
    agent.ctx.add_context(source="rag", content="smb.conf lives in /etc/samba", metadata={})
    if state == "observing":
        agent.current_state = AgentState.OBSERVING
        events = [e async for e in agent._handle_observing()]
    else:
        events = [e async for e in agent._handle_planning()]

    assert len(crag.kwargs) == 1
    assert crag.kwargs[0] == {
        "model_override": "pinned:3b", "tier_override": "specialist",
        "secure": False,
    }
    assert agent.ctx.crag_action == CRAGAction.CORRECT
    assert events
