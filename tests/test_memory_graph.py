"""The memory graph: wiki-links, tags, workspace hubs — and what must NOT link."""

from coworker.memory.base import MemoryItem, Scope
from coworker.memory.graph import build_graph


def _mem(i, content, key=None, workspace=None, summary=None, scope=Scope.WORKSPACE):
    return MemoryItem(i, scope, content, key=key, summary=summary, workspace=workspace)


def _ids(graph):
    return sorted(n["id"] for n in graph["nodes"])


def _edges(graph):
    return {(e["source"], e["target"], e["kind"]) for e in graph["edges"]}


def test_wiki_link_by_key_connects_two_memories():
    g = build_graph([
        _mem(1, "see [[pricing]] for details"),
        _mem(2, "credits cost table", key="pricing"),
    ])
    assert ("m:1", "m:2", "link") in _edges(g)


def test_wiki_link_by_numeric_id_connects():
    g = build_graph([_mem(1, "follow-up to [[2]]"), _mem(2, "the original note")])
    assert ("m:1", "m:2", "link") in _edges(g)


def test_dangling_wiki_link_is_dropped_not_an_error():
    g = build_graph([_mem(1, "see [[nothing-here]]")])
    assert _ids(g) == ["m:1"]
    assert g["edges"] == []


def test_obsidian_alias_syntax_resolves_the_target():
    g = build_graph([
        _mem(1, "check [[pricing|the price list]]"),
        _mem(2, "table", key="pricing"),
    ])
    assert ("m:1", "m:2", "link") in _edges(g)


def test_key_matching_is_case_insensitive():
    g = build_graph([_mem(1, "see [[Pricing]]"), _mem(2, "x", key="pricing")])
    assert ("m:1", "m:2", "link") in _edges(g)


def test_tags_become_shared_hub_nodes():
    g = build_graph([_mem(1, "likes teal #branding"), _mem(2, "logo work #branding")])
    assert "t:branding" in _ids(g)
    assert ("m:1", "t:branding", "tag") in _edges(g)
    assert ("m:2", "t:branding", "tag") in _edges(g)


def test_a_bare_number_is_not_a_tag():
    """'#3' is an issue reference, not a topic."""
    g = build_graph([_mem(1, "fixed in #3 last week")])
    assert not any(n["kind"] == "tag" for n in g["nodes"])


def test_markdown_headings_are_not_tags():
    g = build_graph([_mem(1, "# Heading\nbody text")])
    assert not any(n["kind"] == "tag" for n in g["nodes"])


def test_workspace_hub_clusters_its_memories():
    g = build_graph([
        _mem(1, "a", workspace="/u/proj"),
        _mem(2, "b", workspace="/u/proj"),
        _mem(3, "c"),
    ])
    assert "w:/u/proj" in _ids(g)
    ws = next(n for n in g["nodes"] if n["id"] == "w:/u/proj")
    assert ws["label"] == "proj"  # basename, not the whole path
    assert ("m:1", "w:/u/proj", "workspace") in _edges(g)
    assert not any(s == "m:3" or t == "m:3" for s, t, _ in _edges(g))


def test_self_link_is_ignored():
    g = build_graph([_mem(1, "recursive [[me]]", key="me")])
    assert g["edges"] == []


def test_duplicate_links_dedupe_to_one_edge():
    g = build_graph([_mem(1, "[[x]] and again [[x]]"), _mem(2, "y", key="x")])
    assert len([e for e in g["edges"] if e["kind"] == "link"]) == 1


def test_degree_counts_every_connection():
    g = build_graph([
        _mem(1, "#a #b links [[k2]]"),
        _mem(2, "plain", key="k2"),
    ])
    node = next(n for n in g["nodes"] if n["id"] == "m:1")
    assert node["degree"] == 3


def test_label_prefers_summary_then_key_then_first_line():
    g = build_graph([
        _mem(1, "long content here", summary="The Summary"),
        _mem(2, "content", key="the-key"),
        _mem(3, "First line of content\nsecond line"),
    ])
    labels = {n["id"]: n["label"] for n in g["nodes"]}
    assert labels["m:1"] == "The Summary"
    assert labels["m:2"] == "the-key"
    assert labels["m:3"] == "First line of content"


def test_scope_rides_along_for_coloring():
    g = build_graph([_mem(1, "x", scope=Scope.GLOBAL)])
    assert g["nodes"][0]["scope"] == "global"
