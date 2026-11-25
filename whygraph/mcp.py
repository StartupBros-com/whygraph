"""A minimal Model Context Protocol server (stdio, newline-delimited JSON-RPC 2.0).

Dependency-free on purpose: the only runtime dependency of whygraph is relate-db.
Any MCP client (Claude Code, Cursor, Codex) can launch it with
    whygraph --store whygraph.rl mcp
and call the tools below. Tool results are the same JSON the CLI prints.
"""
from __future__ import annotations

import json
import sys

from . import __version__
from .query import NotFound, WhyGraph

PROTOCOL = "2024-11-05"

_SEARCH_DECISIONS_LIMIT = 6
_CHANGES_WITH_LIMIT = 10
_FIND_FILE_LIMIT = 10

TOOLS = [
    {"name": "why_file",
     "description": "Call BEFORE editing a file. Returns the architecture decisions (ADRs) that govern it with the "
                    "evidence for each, who to ask, the files that usually change with it, and its recent commits.",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string", "description": "repo-relative path or unique suffix"}}, "required": ["path"]}},
    {"name": "get_decision",
     "description": "One ADR: status, summary, what amends or supersedes it, what references it, where it is cited in code.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string", "description": "ADR-0118 or 118"}}, "required": ["id"]}},
    {"name": "search_decisions",
     "description": "Full-text search over ADR titles and summaries. Use when you know the topic but not the ADR number.",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}, "limit": {"type": "integer", "default": _SEARCH_DECISIONS_LIMIT}}, "required": ["text"]}},
    {"name": "who_owns",
     "description": "People ranked by recency-weighted commits touching a file (folder level if the file is new).",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "changes_with",
     "description": "Files that usually change together with this one, each with the signals that support it.",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer", "default": _CHANGES_WITH_LIMIT}}, "required": ["path"]}},
    {"name": "find_file",
     "description": "Find files in the graph by path fragment, busiest first.",
     "inputSchema": {"type": "object", "properties": {"fragment": {"type": "string"}, "limit": {"type": "integer", "default": _FIND_FILE_LIMIT}}, "required": ["fragment"]}},
]


def call_tool(w: WhyGraph, name: str, args: dict):
    if name == "why_file":
        return w.why(args["path"])
    if name == "get_decision":
        return w.decision(str(args["id"]))
    if name == "search_decisions":
        return w.search(args["text"], int(args.get("limit", _SEARCH_DECISIONS_LIMIT)))
    if name == "who_owns":
        return w.owners(w.resolve_file(args["path"]), 5)
    if name == "changes_with":
        return w.changes_with(w.resolve_file(args["path"]), int(args.get("limit", _CHANGES_WITH_LIMIT)))
    if name == "find_file":
        return w.find(args["fragment"], int(args.get("limit", _FIND_FILE_LIMIT)))
    raise KeyError(name)


def handle(w: WhyGraph, msg: dict):
    """Return a response dict for a request, or None for a notification."""
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:  # notification such as notifications/initialized
        return None

    def ok(result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def err(code, text):
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": text}}

    if method == "initialize":
        return ok({"protocolVersion": PROTOCOL, "capabilities": {"tools": {}},
                   "serverInfo": {"name": "whygraph", "version": __version__}})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        params = msg.get("params") or {}
        try:
            data = call_tool(w, params.get("name", ""), params.get("arguments") or {})
            return ok({"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]})
        except KeyError as e:
            return err(-32602, f"unknown tool or missing argument {e}; call tools/list")
        except NotFound as e:  # tool-level error the model can read and act on
            return ok({"content": [{"type": "text", "text": str(e)}], "isError": True})
    return err(-32601, f"method not found: {method}")


def serve(store: str, stdin=None, stdout=None):
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    w = WhyGraph(store)
    try:
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                resp = handle(w, json.loads(line))
            except json.JSONDecodeError:
                resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
            if resp is not None:
                stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                stdout.flush()
    finally:
        w.close()
