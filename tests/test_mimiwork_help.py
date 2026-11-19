"""Mimi's knowledge of MimiWork itself.

The owner, 2026-11-19: "mimiwork should know very well about mimiwork first.. we need to
build a knowledge base for it". In his two conversations that day Mimi sent him to a
"Manage → Settings" menu that does not exist, built Claude Code and Codex as ordinary Mimi
agents, put a coding agent's name where a model goes, and ran `pwd` eight times to learn
which folder she was in. The answers live in a help file that ships with the app, searched
offline like the research knowledge base, plus a short map in her instructions.
"""

from __future__ import annotations

from coworker import kb
from coworker.tools.kb import kb_tools


def _help():
    return {t.__name__: t for t in kb_tools()}["mimiwork_help"]


def _titles(question):
    return [r["title"] for r in _help()(question)["results"]]


def test_the_help_ships_with_the_app_and_stays_out_of_research_searches():
    assert len(kb.help_sections()) >= 25
    found = {t.__name__: t for t in kb_tools()}["kb_search"]("thematic analysis coding")["results"]
    assert found and all(r["collection"] != "mimiwork_help" for r in found)


def test_every_help_section_is_short_enough_to_read_whole():
    for section in kb.help_sections():
        assert section["title"] and 80 < len(section["content"]) < 2600, section["title"]


def test_the_questions_from_the_owners_conversations_find_their_answers():
    assert any("key" in t.lower() for t in _titles("where do I add my OpenAI API key"))
    assert any("coding agent" in t.lower() for t in _titles("make Claude Code Codex and Gemini argue as coding agents"))
    assert any("folder" in t.lower() for t in _titles("which folders can you read in this conversation"))
    assert any("agents" in t.lower() for t in _titles("how do I run an agent system with my own question"))


def test_a_question_with_no_answer_says_so_instead_of_inviting_a_guess():
    out = _help()("zzqx flarnbat")
    assert out["count"] == 0 and "not sure" in out["note"]


def test_mimi_is_told_to_look_mimiwork_up_and_given_the_map():
    from coworker.agents.cowork import COWORK_INSTRUCTIONS

    assert "mimiwork_help" in COWORK_INSTRUCTIONS
    for place in ("Settings > Models", "Connectors", "Agents"):
        assert place in COWORK_INSTRUCTIONS
    assert "Manage →" not in COWORK_INSTRUCTIONS and "Manage >" not in COWORK_INSTRUCTIONS
