"""Dependency-free stdio MCP server subset for local agent integrations."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

from mga.memory import MemoryRetrieval
from mga.memory.state import StateManager

JSONRPC_VERSION = "2.0"
PROTOCOL_VERSION = "2024-11-05"


class MangaTranslatorMCPServer:
    """Handle a small MCP-compatible JSON-RPC tool surface."""

    def __init__(self, project_root: Path | str = ".") -> None:
        self.project_root = Path(project_root).resolve()

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Handle one JSON-RPC message."""
        method = str(message.get("method") or "")
        request_id = message.get("id")
        if not request_id and method.startswith("notifications/"):
            return None
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "serverInfo": {
                        "name": "manga-translator-agent",
                        "version": "0.1.0",
                    },
                    "capabilities": {"tools": {}},
                }
            elif method == "tools/list":
                result = {"tools": self.tool_definitions()}
            elif method == "tools/call":
                params = message.get("params") or {}
                if not isinstance(params, dict):
                    raise ValueError("tools/call params must be an object")
                result = self.call_tool(
                    str(params.get("name") or ""),
                    params.get("arguments") or {},
                )
            else:
                return self._error(request_id, -32601, f"Unknown method: {method}")
        except Exception as exc:  # noqa: BLE001 - JSON-RPC should return structured errors.
            return self._error(request_id, -32000, str(exc), type(exc).__name__)

        return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}

    def tool_definitions(self) -> list[dict[str, Any]]:
        """Return MCP tool definitions."""
        project_dir_property = {
            "type": "string",
            "description": "Project directory relative to the MCP project root.",
            "default": ".",
        }
        return [
            {
                "name": "project_summary",
                "description": "Summarize local project memory counts.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"project_dir": project_dir_property},
                },
            },
            {
                "name": "memory_search",
                "description": "Search character, scene, term, and decision memory.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_dir": project_dir_property,
                        "query": {"type": "string"},
                        "entity_types": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "translation_memory_search",
                "description": "Search saved translation history for reusable examples.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_dir": project_dir_property,
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "translation_report_read",
                "description": "Read a project-local translation report JSON file.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_dir": project_dir_property,
                        "report_path": {"type": "string"},
                    },
                    "required": ["report_path"],
                },
            },
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call one exposed tool and return an MCP tool result."""
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be an object")
        if name == "project_summary":
            project_dir = self._resolve_project_dir(arguments.get("project_dir"))
            payload = {
                "project_dir": str(project_dir),
                "characters": len(StateManager.list_characters(project_dir)),
                "scenes": len(StateManager.list_scenes(project_dir)),
                "terms": len(StateManager.list_terms(project_dir)),
                "decisions": len(StateManager.list_decisions(project_dir)),
            }
            return _tool_result(payload)
        if name == "memory_search":
            project_dir = self._resolve_project_dir(arguments.get("project_dir"))
            query = _required_string(arguments, "query")
            entity_types = arguments.get("entity_types")
            if entity_types is not None and not isinstance(entity_types, list):
                raise ValueError("entity_types must be a list when provided")
            results = MemoryRetrieval.search(project_dir, query, entity_types=entity_types)
            return _tool_result({
                "query": query,
                "results": [_serialize_memory_result(item) for item in results],
            })
        if name == "translation_memory_search":
            project_dir = self._resolve_project_dir(arguments.get("project_dir"))
            query = _required_string(arguments, "query")
            limit = int(arguments.get("limit") or 5)
            return _tool_result({
                "query": query,
                "results": MemoryRetrieval.search_translation_memory(
                    project_dir,
                    query,
                    limit=limit,
                ),
            })
        if name == "translation_report_read":
            project_dir = self._resolve_project_dir(arguments.get("project_dir"))
            report_path = _required_string(arguments, "report_path")
            path = self._resolve_child_path(project_dir, report_path)
            return _tool_result(json.loads(path.read_text(encoding="utf-8")))
        raise ValueError(f"Unknown tool: {name}")

    def _resolve_project_dir(self, value: Any = None) -> Path:
        raw = Path(str(value or "."))
        path = raw if raw.is_absolute() else self.project_root / raw
        path = path.resolve()
        self._ensure_under_root(path)
        return path

    def _resolve_child_path(self, base: Path, child: str) -> Path:
        path = (base / child).resolve()
        self._ensure_under_root(path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Report not found: {child}")
        return path

    def _ensure_under_root(self, path: Path) -> None:
        try:
            path.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError(f"Path escapes MCP project root: {path}") from exc

    @staticmethod
    def _error(
        request_id: Any,
        code: int,
        message: str,
        error_type: str | None = None,
    ) -> dict[str, Any]:
        error: dict[str, Any] = {"code": code, "message": message}
        if error_type:
            error["data"] = {"type": error_type}
        return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error}


def run_stdio(
    server: MangaTranslatorMCPServer | None = None,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> None:
    """Run the MCP server over newline-delimited stdio JSON-RPC."""
    server = server or MangaTranslatorMCPServer()
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    for line in input_stream:
        line = line.strip()
        if not line:
            continue
        try:
            response = server.handle(json.loads(line))
        except Exception as exc:  # noqa: BLE001 - malformed JSON still gets a JSON-RPC error.
            response = MangaTranslatorMCPServer._error(None, -32700, str(exc), type(exc).__name__)
        if response is None:
            continue
        output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
        output_stream.flush()


def _required_string(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Missing required string argument: {key}")
    return value


def _serialize_memory_result(item: dict[str, Any]) -> dict[str, Any]:
    entity = item.get("entity")
    if hasattr(entity, "model_dump"):
        entity_payload = entity.model_dump()
    else:
        entity_payload = entity
    return {
        "type": item.get("type"),
        "entity": entity_payload,
    }


def _tool_result(payload: Any) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, indent=2),
            }
        ],
        "isError": False,
    }
