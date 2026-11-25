"""whygraph command line. Output is JSON when piped (or with --json), a readable
digest on a terminal. Errors say how to fix the request and exit non-zero."""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

from . import __version__
from .build import build
from .query import NotFound, WhyGraph

DEFAULT_STORE = "whygraph.rl"


def _day(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d")


def _emit(obj, as_json, render):
    if as_json:
        print(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
    else:
        print(render(obj))


def _dec_line(d):
    flag = f"  [{'; '.join(d['updated_by'])}]" if d.get("updated_by") else ""
    score = f" ({d['score']})" if "score" in d else ""
    status = f" [{d['status']}]" if d.get("status") else ""
    return f"{d['id']}{status} {d['title']}{score}{flag}"


def render_why(r):
    out = [f"{r['path']}", ""]
    out.append("Decisions that govern it (highest evidence score first):")
    for d in r["decisions"] or []:
        out.append("  " + _dec_line(d))
        for e in d["evidence"][:2]:
            out.append(f"      because: {e}")
    if not r["decisions"]:
        out.append("  none found: no ADR cites this file, its commits, or its neighbours")
    out.append("\nWho to ask (recency-weighted):")
    for o in r["owners"]:
        out.append(f"  {o['person']}: {o['commits']} commits, last {_day(o['last_ts'])} ({o['scope']} level)")
    out.append("\nChanges together with:")
    for c in r["changes_with"]:
        parts = [f"{c['commits']} shared commit{'s' if c['commits'] != 1 else ''}"] if c["commits"] else []
        parts += [s for s in c.get("signals", []) if s != "co-changed"]
        out.append(f"  {c['path']}  ({'; '.join(parts)})")
    out.append("\nRecent commits:")
    for c in r["recent_commits"]:
        out.append(f"  {c['sha'][:8]} {_day(c['ts'])} {c['author']}: {c['subject'][:90]}")
    return "\n".join(out)


def render_decision(d):
    out = [_dec_line(d), "", d["summary"] or "(no summary)"]
    if d["amends"]:
        out.append(f"\nAmends or supersedes: {', '.join(d['amends'])}")
    if d["updated_by"]:
        out.append(f"Later changed by: {', '.join(d['updated_by'])}")
    out.append(f"Referenced by: {', '.join(d['referenced_by']) or 'nothing yet'}")
    out.append("Cited in code under: " + (", ".join(f"{m['module']} ({m['files']})" for m in d["modules"]) or "nowhere"))
    for c in d["recent_commits"]:
        out.append(f"  commit {c['sha'][:8]} {_day(c['ts'])} {c['author']}: {c['subject'][:80]}")
    return "\n".join(out)


def render_list(rows):
    if rows and "id" in rows[0]:
        return "\n".join(_dec_line(d) for d in rows) or "no matches"
    if rows and "person" in rows[0]:
        return "\n".join(f"{o['person']}: {o['commits']} commits (weight {o['weight']})" for o in rows)
    return "\n".join(f"{r['path']}  ({r.get('commits', 0)} commits)" for r in rows) or "no matches"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="whygraph", description="A decision graph for coding agents, stored in a Relate graph.")
    ap.add_argument("--version", action="version", version=f"whygraph {__version__}")
    common = argparse.ArgumentParser(add_help=False)

    def add_common(flag, *, default, help_text, **kwargs):
        ap.add_argument(flag, default=default, help=help_text, **kwargs)
        # Omitted subcommand options must not overwrite values set before it.
        common.add_argument(flag, default=argparse.SUPPRESS, help=argparse.SUPPRESS, **kwargs)

    add_common("--store", default=os.environ.get("WHYGRAPH_STORE", DEFAULT_STORE),
               help_text="path to the .rl store (env WHYGRAPH_STORE; default ./whygraph.rl)")
    add_common("--json", action="store_true", default=False,
               help_text="always print JSON (default when stdout is not a terminal)")
    add_common("--text", action="store_true", default=False,
               help_text="always print the readable digest, even when piped")
    add_common("--limit", type=int, default=6, help_text="rows per list (default 6)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("index", parents=[common], help="build a store from a git repository")
    p.add_argument("--repo", required=True)
    p.add_argument("--rev", default="HEAD")
    p.add_argument("--adr-dir", default="docs/adr")
    p.add_argument("--anonymize", action="store_true", help="replace author names with stable pseudonyms")
    for name, h in (("why", "everything to know before editing a file"), ("who", "likely owners of a file"),
                    ("coupled", "files that change together with a file"), ("find", "find a file by path fragment")):
        s = sub.add_parser(name, parents=[common], help=h)
        s.add_argument("target")
    s = sub.add_parser("decision", parents=[common], help="one ADR with its supersession chain and where it is used")
    s.add_argument("id", help="ADR-0118 or 118")
    s = sub.add_parser("search", parents=[common], help="full-text search of decisions")
    s.add_argument("text")
    sub.add_parser("mcp", parents=[common], help="serve the graph to coding agents over MCP (stdio)")
    a = ap.parse_args(argv)
    as_json = a.json or (not a.text and not sys.stdout.isatty())

    if a.cmd == "index":
        if os.path.exists(a.store):
            print(f"error: {a.store} already exists. Delete it or pass --store NEW.rl; an index is rebuilt, never merged.",
                  file=sys.stderr)
            return 2
        stats = build(a.repo, a.rev, a.store, a.adr_dir, anonymize=a.anonymize)
        _emit(stats, as_json, lambda s: "indexed " + ", ".join(f"{k}={v}" for k, v in s.items()))
        return 0
    if not os.path.exists(a.store):
        print(f"error: no store at {a.store}. Run: whygraph index --repo <git repo> --store {a.store}", file=sys.stderr)
        return 2
    if a.cmd == "mcp":
        from .mcp import serve
        serve(a.store)
        return 0
    w = WhyGraph(a.store)
    try:
        if a.cmd == "why":
            _emit(w.why(a.target, a.limit), as_json, render_why)
        elif a.cmd == "who":
            _emit(w.owners(w.resolve_file(a.target), a.limit), as_json, render_list)
        elif a.cmd == "coupled":
            _emit(w.cochange(w.resolve_file(a.target), a.limit), as_json, render_list)
        elif a.cmd == "find":
            _emit(w.find(a.target, a.limit), as_json, render_list)
        elif a.cmd == "decision":
            _emit(w.decision(a.id), as_json, render_decision)
        elif a.cmd == "search":
            _emit(w.search(a.text, a.limit), as_json, render_list)
    except NotFound as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    finally:
        w.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
