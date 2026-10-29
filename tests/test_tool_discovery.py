from coworker.tools.registry import ToolRegistry


def test_large_catalog_keeps_all_tools_discoverable_within_provider_limit():
    registry = ToolRegistry()
    for index in range(159):
        def invoke():
            return "ok"
        invoke.__name__ = f"tool_{index}"
        registry.register(invoke, schema={"type": "function", "function": {
            "name": invoke.__name__, "description": "Read a test record",
            "parameters": {"type": "object", "properties": {}},
        }})
    schemas, catalog = registry.model_tools()
    assert len(schemas) == 128
    assert "tool_158" in catalog
    registry.execute("discover_available_tools", {"names": ["tool_158"]})
    schemas, _ = registry.model_tools()
    assert len(schemas) == 128
    assert schemas[1]["function"]["name"] == "tool_158"
    assert registry.execute("tool_158") == "ok"
    assert "error" in registry.execute("discover_available_tools", {"names": ["missing"]})
    registry.unregister("tool_158")
    schemas, _ = registry.model_tools()
    assert all(s["function"]["name"] != "tool_158" for s in schemas)
