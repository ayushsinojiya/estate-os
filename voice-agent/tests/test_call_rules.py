"""The must-follow rules: no repeats, a visit asked about once, visits only for the caller's project,
and a far-off budget confirmed before searching."""

import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace

from app.config import Settings
from app.domain.base import CallInfo
from app.domain.real_estate.plugin import RealEstatePlugin
from app.domain.real_estate.tools import SearchArgs, SlotArgs
from app.outbound.registry import CallRegistry


def _conversation():
    settings = Settings(crm_mode="mock")
    services = SimpleNamespace(settings=settings, outbox=SimpleNamespace(register=lambda *a: None),
                               dialer=SimpleNamespace(), registry=CallRegistry(Path(tempfile.mkdtemp()) / "c.sqlite"))
    plugin = RealEstatePlugin(services)
    asyncio.run(plugin.refresh_catalog())
    return plugin.conversation(CallInfo("t", "outbound", "+919800000001", "hi"))


def test_a_sentence_already_said_is_not_said_again():
    c = _conversation()
    c.screen_caller("मुझे 2 BHK चाहिए", "hi")
    assert c.screen_reply("आप किस area में देख रहे हैं?", "hi")
    assert c.screen_reply("आप किस area में देख रहे हैं?", "hi") == ""
    c.screen_caller("दोबारा बताइए", "hi")  # asked to repeat: allowed
    assert c.screen_reply("आप किस area में देख रहे हैं?", "hi")


def test_the_visit_is_asked_about_once():
    c = _conversation()
    c.screen_caller("Baner में क्या है?", "hi")
    first = "क्या आप Sahyadri Grove की site visit करना चाहेंगे?"
    assert c.screen_reply(first, "hi")
    c.on_agent_reply(first)
    c.screen_caller("details बताइए", "hi")
    assert c.screen_reply("तो क्या आप visit करना चाहेंगे?", "hi") == ""
    c.screen_caller("ठीक है site visit book कर दो", "hi")  # the caller raises it: allowed
    assert c.screen_reply("कौन सा visit time ठीक रहेगा?", "hi")


def test_visit_slots_only_for_the_project_the_caller_is_talking_about():
    c = _conversation()
    c.screen_caller("Baner वाला project बताइए, visit करना है", "hi")
    other = asyncio.run(c.toolbox.get_visit_slots(SlotArgs(project="Mula Vista"))).content
    assert other["error"] == "not_the_callers_project" and other["callerIsAskingAbout"] == "Sahyadri Grove"
    same = asyncio.run(c.toolbox.get_visit_slots(SlotArgs(project="Sahyadri Grove"))).content
    assert "error" not in same


def test_a_far_off_budget_is_confirmed_before_searching():
    c = _conversation()
    c.screen_caller("मेरा budget 780 लाख है", "hi")
    assert c.state.budget_to_confirm == 78_000_000
    held = asyncio.run(c.toolbox.search_properties(SearchArgs(budget_max_inr=78_000_000, bhk=[2]))).content
    assert held["options"] == [] and "confirm the budget" in held["instruction"]
    c.screen_caller("नहीं नहीं, 70 से 80 लाख", "hi")  # the caller corrects it
    assert c.state.budget_to_confirm is None


def test_a_confirmed_unusual_budget_is_accepted():
    c = _conversation()
    c.screen_caller("budget 780 लाख", "hi")
    c.screen_caller("हाँ, 780 लाख ही है", "hi")
    assert c.state.budget_to_confirm is None


def test_a_reply_that_is_only_a_repeat_is_said_rather_than_silence():
    c = _conversation()
    c.screen_caller("Baner में क्या है?", "hi")
    assert c.screen_reply("Sahyadri Grove में 2 BHK available है।", "hi")
    c.screen_caller("हम्म", "hi")
    assert c.screen_reply("Sahyadri Grove में 2 BHK available है।", "hi") == ""
    assert c.take_dropped() == "Sahyadri Grove में 2 BHK available है।"
    assert c.take_dropped() == ""
