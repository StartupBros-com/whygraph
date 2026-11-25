"""Compare advertised defaults with the JSON-RPC entry point using a fake graph."""

import io
import json
import unittest
from unittest.mock import patch

from whygraph import mcp


CASES = (
    ("search_decisions", {"text": "wal"}, "search", "wal", 6),
    ("changes_with", {"path": "src/wal.rs"}, "changes_with", "resolved/src/wal.rs", 10),
    ("find_file", {"fragment": "cache"}, "find", "cache", 10),
)


class Graph:
    def __init__(self):
        self.calls = []
        self.closed = False

    def resolve_file(self, path):
        return f"resolved/{path}"

    def search(self, text, limit):
        self.calls.append(("search", text, limit))
        return {"limit": limit}

    def changes_with(self, path, limit):
        self.calls.append(("changes_with", path, limit))
        return {"limit": limit}

    def find(self, fragment, limit):
        self.calls.append(("find", fragment, limit))
        return {"limit": limit}

    def close(self):
        self.closed = True


def request(mid, method, params=None):
    req = {"jsonrpc": "2.0", "id": mid, "method": method}
    if params is not None:
        req["params"] = params
    return req


class McpDefaultsTests(unittest.TestCase):
    def test_stdio_metadata_defaults_match_omitted_arguments(self):
        graph = Graph()
        requests = [request(1, "tools/list")]
        expected_calls = []
        for name, arguments, method, value, default in CASES:
            for supplied, expected in (({}, default), ({"limit": 0}, 0), ({"limit": 9}, 9)):
                requests.append(request(len(requests) + 1, "tools/call", {
                    "name": name, "arguments": {**arguments, **supplied},
                }))
                expected_calls.append((method, value, expected))
        stdin = io.StringIO("".join(json.dumps(req) + "\n" for req in requests))
        stdout = io.StringIO()
        with patch.object(mcp, "WhyGraph", return_value=graph):
            mcp.serve("unused.rl", stdin=stdin, stdout=stdout)

        responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([res["id"] for res in responses], [req["id"] for req in requests])
        tools = {tool["name"]: tool for tool in responses[0]["result"]["tools"]}
        for name, _, _, _, default in CASES:
            limit = tools[name]["inputSchema"]["properties"]["limit"]
            self.assertEqual(limit, {"type": "integer", "default": default})
        self.assertEqual(graph.calls, expected_calls)
        for response, (_, _, limit) in zip(responses[1:], expected_calls):
            payload = response["result"]["content"][0]
            self.assertEqual(payload["type"], "text")
            self.assertEqual(json.loads(payload["text"]), {"limit": limit})
        self.assertTrue(graph.closed)

    def test_dispatch_still_coerces_numeric_strings(self):
        for name, arguments, method, value, _ in CASES:
            with self.subTest(name=name):
                graph = Graph()
                self.assertEqual(mcp.call_tool(graph, name, {**arguments, "limit": "08"}), {"limit": 8})
                self.assertEqual(graph.calls, [(method, value, 8)])
