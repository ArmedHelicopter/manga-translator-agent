from __future__ import annotations

import json
from io import StringIO

from mga.mcp_server import MangaTranslatorMCPServer, run_stdio
from mga.memory.entities import TermState
from mga.memory.state import StateManager


def _tool_json(response):
    text = response["result"]["content"][0]["text"]
    return json.loads(text)


def test_mcp_initialize_and_tools_list(tmp_path):
    server = MangaTranslatorMCPServer(project_root=tmp_path)

    initialized = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    listed = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

    assert initialized["result"]["serverInfo"]["name"] == "manga-translator-agent"
    tool_names = {tool["name"] for tool in listed["result"]["tools"]}
    assert {
        "project_summary",
        "memory_search",
        "translation_memory_search",
        "translation_report_read",
    }.issubset(tool_names)


def test_mcp_memory_search_tool_returns_serialized_results(tmp_path):
    StateManager.upsert_term(
        tmp_path,
        TermState(term_id="glass-blade", source="glass blade", translation="Glass Blade"),
    )
    server = MangaTranslatorMCPServer(project_root=tmp_path)

    response = server.handle({
        "jsonrpc": "2.0",
        "id": "search",
        "method": "tools/call",
        "params": {
            "name": "memory_search",
            "arguments": {"query": "glass"},
        },
    })

    payload = _tool_json(response)
    assert payload["query"] == "glass"
    assert payload["results"][0]["type"] == "term"
    assert payload["results"][0]["entity"]["term_id"] == "glass-blade"


def test_mcp_translation_memory_search_tool_reads_history(tmp_path):
    translations_dir = tmp_path / "translations"
    translations_dir.mkdir()
    (translations_dir / "p001.json").write_text(
        json.dumps(
            {
                "page_id": "p001",
                "bubbles": [
                    {
                        "bubble_id": "b1",
                        "source_text": "Where is the glass blade?",
                        "speaker_id": "akari",
                    }
                ],
                "translations": [{"bubble_id": "b1", "text": "glass blade target"}],
            }
        ),
        encoding="utf-8",
    )
    server = MangaTranslatorMCPServer(project_root=tmp_path)

    response = server.handle({
        "jsonrpc": "2.0",
        "id": "tm",
        "method": "tools/call",
        "params": {
            "name": "translation_memory_search",
            "arguments": {"query": "glass blade", "limit": 1},
        },
    })

    payload = _tool_json(response)
    assert payload["results"][0]["page_id"] == "p001"
    assert payload["results"][0]["translated_text"] == "glass blade target"


def test_mcp_translation_report_read_rejects_path_escape(tmp_path):
    outside = tmp_path.parent / "outside-report.json"
    outside.write_text("{}", encoding="utf-8")
    server = MangaTranslatorMCPServer(project_root=tmp_path)

    response = server.handle({
        "jsonrpc": "2.0",
        "id": "escape",
        "method": "tools/call",
        "params": {
            "name": "translation_report_read",
            "arguments": {"report_path": "../outside-report.json"},
        },
    })

    assert response["error"]["code"] == -32000
    assert "escapes MCP project root" in response["error"]["message"]


def test_mcp_unknown_method_and_tool_return_structured_errors(tmp_path):
    server = MangaTranslatorMCPServer(project_root=tmp_path)

    unknown_method = server.handle({"jsonrpc": "2.0", "id": 1, "method": "bad/method"})
    unknown_tool = server.handle({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "bad_tool", "arguments": {}},
    })

    assert unknown_method["error"]["code"] == -32601
    assert unknown_tool["error"]["code"] == -32000
    assert "Unknown tool" in unknown_tool["error"]["message"]


def test_run_stdio_handles_newline_delimited_json(tmp_path):
    input_stream = StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
    )
    output_stream = StringIO()

    run_stdio(
        MangaTranslatorMCPServer(project_root=tmp_path),
        input_stream=input_stream,
        output_stream=output_stream,
    )

    response = json.loads(output_stream.getvalue())
    assert response["id"] == 1
    assert response["result"]["tools"]
