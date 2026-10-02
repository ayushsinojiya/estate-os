"""The engine's tool-calling loop: call, filler, result back to the model, then the answer."""

import asyncio
import json

from app.domain.base import CallerTurnAction, Tool, ToolOutcome
from app.llm.base import ToolSpec
from app.llm.fake import ScriptedLLM, call, say

from tests.helpers import PHRASES, StubConversation, session


def _tool(run, filler="filler_lookup", timeout_s=1.0):
    return Tool(ToolSpec("lookup", "look something up",
                         {"type": "object", "properties": {"q": {"type": "string"}},
                          "required": ["q"], "additionalProperties": False}),
                run, timeout_s=timeout_s, filler=filler)


def test_a_tool_result_is_handed_back_before_the_answer():
    seen = []

    async def run(args):
        seen.append(args)
        return ToolOutcome({"price": "85 lakh"})

    llm = ScriptedLLM([call("lookup", q="2 bhk"), say("The two bedroom is 85 lakh.")])
    s, speech = session(llm, StubConversation(tool_list=[_tool(run)]))
    asyncio.run(s._respond("price of 2 bhk", "en"))
    assert seen == [{"q": "2 bhk"}]
    # The filler covers the lookup; then the answer.
    assert speech.started == [PHRASES["filler_lookup"], "The two bedroom is 85 lakh."]
    tool_msg = [m for m in llm.calls[1] if m.role == "tool"][0]
    assert json.loads(tool_msg.content) == {"price": "85 lakh"}


def test_a_slow_tool_times_out_and_the_model_is_told_not_to_guess():
    async def run(args):
        await asyncio.sleep(1)
        return ToolOutcome({"price": "late"})

    llm = ScriptedLLM([call("lookup", q="x"), say("I will have that confirmed.")])
    s, speech = session(llm, StubConversation(tool_list=[_tool(run, timeout_s=0.05)]))
    asyncio.run(s._respond("price", "en"))
    tool_msg = [m for m in llm.calls[1] if m.role == "tool"][0]
    assert json.loads(tool_msg.content)["error"] == "timeout"
    assert s.metrics.tool_errors == 1


def test_bad_arguments_and_unknown_tools_do_not_crash_the_call():
    async def run(args):
        return ToolOutcome({"ok": True})

    llm = ScriptedLLM([call("nope", q="x"), say("Sorry about that.")])
    s, speech = session(llm, StubConversation(tool_list=[_tool(run)]))
    asyncio.run(s._respond("hello", "en"))
    assert speech.started[-1] == "Sorry about that."
    assert s.metrics.tool_errors == 1


def test_tool_hops_are_bounded():
    async def run(args):
        return ToolOutcome({"again": True})

    loops = [call("lookup", q=str(i)) for i in range(10)]
    llm = ScriptedLLM(loops + [say("done")])
    s, _ = session(llm, StubConversation(tool_list=[_tool(run, filler=None)]), max_tool_hops=2)
    asyncio.run(s._respond("hello", "en"))
    # Two tool hops, then a final call offered no tools.
    assert len(llm.calls) == 3


def test_a_screened_turn_never_reaches_the_model():
    llm = ScriptedLLM()
    convo = StubConversation(screen=lambda text: CallerTurnAction(say="Understood.", end_call=True,
                                                                  end_reason="dnc"))
    s, speech = session(llm, convo)

    async def scenario():
        await s.turns.turns.put(type("T", (), {"text": "don't call me", "language": None})())
        await asyncio.wait_for(s._turn_loop(), 1)

    asyncio.run(scenario())
    assert llm.calls == []
    assert speech.started == ["Understood."]
    assert s.metrics.end_reason == "dnc"


def test_an_end_call_tool_hangs_up_after_the_reply():
    async def end(args):
        return ToolOutcome({"ok": True}, end_call=True, end_reason="agent_closed", skip_closing=True)

    tool = Tool(ToolSpec("end_call", "end", {"type": "object", "properties": {}}), end, filler=None)
    llm = ScriptedLLM([call("end_call"), say("Thank you, goodbye.")])
    hung_up = []
    s, speech = session(llm, StubConversation(tool_list=[tool]))
    s.hangup = lambda: hung_up.append(True)

    async def scenario():
        await s.turns.turns.put(type("T", (), {"text": "that's all for now", "language": None,
                                               "committed_at": 0, "speech_ended_at": 0})())
        await asyncio.wait_for(s._turn_loop(), 1)

    asyncio.run(scenario())
    assert speech.started == ["Thank you, goodbye."]
    assert hung_up and s.metrics.end_reason == "agent_closed"
