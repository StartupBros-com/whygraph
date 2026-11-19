import io
import json

import pytest
import relate

from whygraph import mcp
from whygraph.build import build, parse_adr
from whygraph.query import NotFound, WhyGraph


@pytest.fixture()
def wg(repo):
    db = relate.connect(":memory:")
    stats = build(repo, "HEAD", ":memory:", db=db)
    w = WhyGraph(db=db)
    w.stats = stats
    yield w
    w.close()


def test_build_counts(wg):
    s = wg.stats
    assert (s["commits"], s["people"], s["decisions"]) == (6, 2, 3)
    assert s["files"] == 8  # 5 src files + 3 ADR files; the lockfile is noise


def test_lockfile_is_noise(wg):
    assert wg.q("MATCH (f:File) WHERE f.path ENDS WITH 'package-lock.json' RETURN f") == []


def test_adr_parsing_and_amends(wg):
    d = wg.decision("3")
    assert d["title"] == "Group commit" and d["amends"] == ["ADR-0001"]
    old = wg.decision("ADR-0001")
    assert "amended by ADR-0003" in old["updated_by"]


def test_parse_adr_rejects_unnumbered():
    assert parse_adr("docs/adr/README.md", "# index") is None


def test_why_ranks_cited_adr_first(wg):
    r = wg.why("wal.rs")  # unique suffix
    assert r["path"] == "src/wal.rs"
    assert r["decisions"][0]["id"] == "ADR-0001"
    assert any("cited in src/wal.rs" in e for e in r["decisions"][0]["evidence"])
    assert "amended by ADR-0003" in r["decisions"][0]["updated_by"]


def test_coupling_and_owner(wg):
    co = wg.cochange("src/wal.rs")
    assert co[0]["path"] == "src/wal_tests.rs" and co[0]["commits"] == 2
    owners = wg.owners("src/cache.rs")
    assert owners[0]["person"] == "Bob"


def test_new_file_falls_back_to_folder_owner(wg):
    wg.q("CREATE (:File {path: 'src/new.rs', module: 'src/new.rs'})")
    o = wg.owners("src/new.rs")
    assert o and o[0]["scope"] == "folder"


def test_errors_teach(wg):
    with pytest.raises(NotFound, match="whygraph find"):
        wg.resolve_file("nope.rs")
    with pytest.raises(NotFound, match="search"):
        wg.decision("999")
    with pytest.raises(NotFound, match="empty search"):
        wg.search("!!")


def test_fulltext_search(wg):
    assert wg.search("write-ahead log")[0]["id"] == "ADR-0001"


def test_mcp_roundtrip(wg):
    def rpc(method, params=None, mid=1):
        return mcp.handle(wg, {"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})

    assert rpc("initialize")["result"]["serverInfo"]["name"] == "whygraph"
    assert mcp.handle(wg, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    names = {t["name"] for t in rpc("tools/list")["result"]["tools"]}
    assert {"why_file", "get_decision", "search_decisions"} <= names
    res = rpc("tools/call", {"name": "why_file", "arguments": {"path": "src/wal.rs"}})["result"]
    assert json.loads(res["content"][0]["text"])["decisions"][0]["id"] == "ADR-0001"
    bad = rpc("tools/call", {"name": "get_decision", "arguments": {"id": "999"}})["result"]
    assert bad["isError"] is True
    assert rpc("nope")["error"]["code"] == -32601
    assert rpc("tools/call", {"name": "bogus", "arguments": {}})["error"]["code"] == -32602


def test_mcp_stdio(repo, tmp_path):
    store = str(tmp_path / "s.rl")
    build(repo, "HEAD", store)
    out = io.StringIO()
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": "find_file", "arguments": {"fragment": "src/cache"}}})
    mcp.serve(store, stdin=io.StringIO(req + "\nnot json\n"), stdout=out)
    lines = [json.loads(x) for x in out.getvalue().splitlines()]
    assert json.loads(lines[0]["result"]["content"][0]["text"])[0]["path"] == "src/cache.rs"
    assert lines[1]["error"]["code"] == -32700


def test_decision_basis_names_strongest_evidence(wg):
    wal = wg.why("src/wal.rs")["decisions"]
    assert wal[0]["id"] == "ADR-0001" and wal[0]["basis"] == "cited in the file"
    cache = {d["id"]: d for d in wg.why("src/cache.rs")["decisions"]}
    assert cache["ADR-0002"]["basis"] == "cited by a commit that touched the file"


def test_store_is_never_merged(repo, tmp_path):
    store = str(tmp_path / "s.rl")
    build(repo, "HEAD", store)
    with pytest.raises(FileExistsError):
        build(repo, "HEAD", store)


def test_anonymize_hides_names(repo, tmp_path):
    store = str(tmp_path / "a.rl")
    build(repo, "HEAD", store, anonymize=True)
    w = WhyGraph(store)
    names = {r["n"] for r in w.q("MATCH (p:Person) RETURN p.name AS n")}
    w.close()
    assert names and all(n.startswith("person-") for n in names) and "Ada" not in names
