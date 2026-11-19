"""Read side: the questions a coding agent asks before it edits a file.

Every method is a few Cypher statements against the store built by whygraph.build,
plus a small amount of ranking in Python. All results are plain dicts, so the CLI
and the eval harness use the same code path.
"""
from __future__ import annotations

import math
import re

import relate

HALF_LIFE_DAYS = 14.0  # ownership decays fast: the graph spans weeks, not years
FT_STRIP = re.compile(r"[^0-9A-Za-z_ ]+")
RRF_K = 60
BASIS = ("cited in the file", "cited by a commit that touched the file", "cited by a file that changes with it")


def path_tokens(path: str) -> set:
    return {t for t in re.split(r"[^A-Za-z0-9]+", path.lower()) if len(t) > 2}


class NotFound(Exception):
    """Raised with a message that tells the caller how to fix the request."""


def _rows(cur):
    return [dict(r) for r in cur]


class WhyGraph:
    def __init__(self, store: str = None, db=None):
        self.db = db if db is not None else relate.connect(store)
        self._cite_counts = None

    def close(self):
        self.db.close()

    # ---- helpers -------------------------------------------------------------------
    def q(self, cypher: str, params: dict = None):
        return _rows(self.db.execute(cypher, params or {}))

    def meta(self) -> dict:
        if getattr(self, "_meta", None) is not None:
            return self._meta
        rows = self.q("MATCH (m:Meta) RETURN m.repo_rev AS rev, m.built_with AS built_with, m.adr_dir AS adr_dir")
        stats = self.q("MATCH (c:Commit) WITH count(c) AS commits, max(c.ts) AS latest "
                       "MATCH (d:Decision) RETURN commits, latest, count(d) AS decisions")
        self._meta = {**(rows[0] if rows else {}), **(stats[0] if stats else {})}
        return self._meta

    def resolve_file(self, path: str) -> str:
        """Exact path, else a unique suffix match; otherwise raise NotFound listing candidates."""
        if self.q("MATCH (f:File {path: $p}) RETURN f.path AS p", {"p": path}):
            return path
        cand = [r["p"] for r in self.q(
            "MATCH (f:File) WHERE f.path ENDS WITH $p RETURN f.path AS p ORDER BY size(f.path) LIMIT 6", {"p": path})]
        if len(cand) == 1:
            return cand[0]
        if cand:
            raise NotFound(f"'{path}' matches {len(cand)}+ files; pass a longer path. Candidates: {cand}")
        raise NotFound(f"no file named '{path}' in the graph; the store only knows paths touched by "
                       f"indexed commits or cited in source. Try: whygraph find <fragment>")

    def find(self, fragment: str, limit: int = 10) -> list:
        return self.q("MATCH (f:File) WHERE toLower(f.path) CONTAINS toLower($s) "
                      "OPTIONAL MATCH (f)<-[:TOUCHES]-(c:Commit) "
                      "RETURN f.path AS path, count(c) AS commits ORDER BY commits DESC, path LIMIT $n",
                      {"s": fragment, "n": limit})

    def cite_counts(self) -> dict:
        if self._cite_counts is None:
            self._cite_counts = {r["id"]: r["n"] for r in self.q(
                "MATCH (d:Decision) OPTIONAL MATCH (d)<-[:CITES]-(x) RETURN d.id AS id, count(x) AS n")}
        return self._cite_counts

    # ---- coupling ------------------------------------------------------------------
    def cochange(self, path: str, limit: int = 10) -> list:
        """Files changed in the same commits as `path`, best first.

        Score is sum(1 / files-in-commit): a two-file commit is strong evidence of
        coupling, a thirty-file commit almost none.
        """
        return self.q(
            "MATCH (a:File {path: $p})<-[:TOUCHES]-(c:Commit)-[:TOUCHES]->(b:File) WHERE b <> a "
            "RETURN b.path AS path, count(c) AS commits, sum(1.0 / c.nfiles) AS score "
            "ORDER BY score DESC, commits DESC, path LIMIT $n", {"p": path, "n": limit})

    def _file_index(self):
        """touch counts, folder -> files and path tokens, loaded once per connection."""
        if getattr(self, "_fi", None) is None:
            touches = {r["p"]: r["n"] for r in self.q(
                "MATCH (f:File) OPTIONAL MATCH (f)<-[:TOUCHES]-(c:Commit) RETURN f.path AS p, count(c) AS n")}
            dirs: dict = {}
            for p in touches:
                dirs.setdefault(p.rsplit("/", 1)[0] if "/" in p else "", []).append(p)
            self._fi = (touches, dirs, {p: path_tokens(p) for p in touches})
        return self._fi

    def related_by_location(self, path: str, limit: int = 50):
        """Same-folder files (busiest first) and files with similar path words: the signals
        that still work for a file the history has not seen change with anything."""
        touches, dirs, tok = self._file_index()
        same = sorted((p for p in dirs.get(path.rsplit("/", 1)[0] if "/" in path else "", []) if p != path),
                      key=lambda p: (-touches[p], p))[:limit]
        ta = tok.get(path) or path_tokens(path)
        similar = sorted((p for p in tok if p != path),
                         key=lambda p: (-len(ta & tok[p]) / (len(ta | tok[p]) or 1), p))[:limit]
        return same, similar

    def changes_with(self, path: str, limit: int = 10) -> list:
        """Reciprocal-rank fusion of three signals: co-change history, same folder, similar name.

        Each result says which signals supported it, so an agent can weigh the evidence."""
        hist = self.cochange(path, limit)
        same, similar = self.related_by_location(path)
        score: dict = {}
        src: dict = {}
        for name, lst in (("co-changed", [h["path"] for h in hist]), ("same folder", same), ("similar name", similar)):
            for i, p in enumerate(lst, 1):
                score[p] = score.get(p, 0.0) + 1.0 / (RRF_K + i)
                src.setdefault(p, []).append(name)
        commits = {h["path"]: h["commits"] for h in hist}
        top = sorted(score, key=lambda p: (-score[p], p))[:limit]
        return [{"path": p, "commits": commits.get(p, 0), "signals": src[p]} for p in top]

    # ---- people --------------------------------------------------------------------
    def owners(self, path: str, limit: int = 5) -> list:
        """People ranked by recency-weighted commits touching the file (module fallback)."""
        now = self.meta().get("latest") or 0
        rows = self.q("MATCH (p:Person)-[:AUTHORED]->(c:Commit)-[:TOUCHES]->(:File {path: $p}) "
                      "RETURN p.name AS person, collect(c.ts) AS tss", {"p": path})
        scope = "file"
        if not rows:
            folder = path.rsplit("/", 1)[0] if "/" in path else ""
            rows = self.q("MATCH (p:Person)-[:AUTHORED]->(c:Commit)-[:TOUCHES]->(f:File) "
                          "WHERE f.path STARTS WITH $d RETURN p.name AS person, collect(c.ts) AS tss",
                          {"d": folder + "/"})
            scope = "folder"
        out = []
        for r in rows:
            w = sum(0.5 ** ((now - t) / 86400.0 / HALF_LIFE_DAYS) for t in r["tss"])
            out.append({"person": r["person"], "commits": len(r["tss"]), "weight": round(w, 3),
                        "last_ts": max(r["tss"]), "scope": scope})
        out.sort(key=lambda o: (-o["weight"], o["person"]))
        return out[:limit]

    def recent_authors(self, path: str, limit: int = 3) -> list:
        """The most recent distinct authors of the file (of its folder if the file is new)."""
        rows = self.q("MATCH (p:Person)-[:AUTHORED]->(c:Commit)-[:TOUCHES]->(:File {path: $p}) "
                      "RETURN p.name AS person, max(c.ts) AS last_ts ORDER BY last_ts DESC, person LIMIT $n",
                      {"p": path, "n": limit})
        if not rows:
            rows = self.q("MATCH (p:Person)-[:AUTHORED]->(c:Commit)-[:TOUCHES]->(f:File) WHERE f.path STARTS WITH $d "
                          "RETURN p.name AS person, max(c.ts) AS last_ts ORDER BY last_ts DESC, person LIMIT $n",
                          {"d": (path.rsplit("/", 1)[0] if "/" in path else "") + "/", "n": limit})
        return rows

    # ---- decisions -----------------------------------------------------------------
    def decisions_for_files(self, paths: list, limit: int = 8) -> list:
        """Rank the decisions that govern a set of files, with the evidence for each.

        Evidence, strongest first: the file's own text cites the ADR; a commit that
        touched the file cited it; a file that changes together with it cites it.
        Each contribution is divided by ln(2 + how many things cite that ADR), so a
        decision cited by 150 files does not drown a specific one. Each row's `basis`
        names the strongest kind of evidence it has; the order is by score alone.
        """
        cites = self.cite_counts()
        score: dict = {}
        why: dict = {}
        best: dict = {}

        def add(did, kind, pts, reason):
            idf = 1.0 / math.log(2 + cites.get(did, 0))
            score[did] = score.get(did, 0.0) + pts * idf
            best[did] = min(best.get(did, kind), kind)
            why.setdefault(did, []).append(reason)

        for p in paths:
            for r in self.q("MATCH (:File {path: $p})-[:CITES]->(d:Decision) RETURN d.id AS id", {"p": p}):
                add(r["id"], 0, 3.0, f"cited in {p}")
            for r in self.q("MATCH (:File {path: $p})<-[:TOUCHES]-(c:Commit)-[:CITES]->(d:Decision) "
                            "RETURN d.id AS id, count(DISTINCT c) AS n", {"p": p}):
                add(r["id"], 1, 2.0 + min(r["n"], 3), f"{r['n']} commit(s) touching {p} cite it")
            for r in self.q("MATCH (a:File {path: $p})<-[:TOUCHES]-(c:Commit)-[:TOUCHES]->(b:File)-[:CITES]->(d:Decision) "
                            "WHERE b <> a RETURN d.id AS id, count(DISTINCT b) AS n", {"p": p}):
                add(r["id"], 2, min(r["n"], 3) * 0.5, f"{r['n']} file(s) that change with {p} cite it")
        ranked = sorted(score, key=lambda d: -score[d])[:limit]
        out = self._decorate(ranked, score, why)
        for row in out:
            row["basis"] = BASIS[best[row["id"]]]
        return out

    def _decorate(self, ids: list, score: dict = None, why: dict = None) -> list:
        if not ids:
            return []
        info = {r["id"]: r for r in self.q(
            "MATCH (d:Decision) WHERE d.id IN $ids RETURN d.id AS id, d.title AS title, d.status AS status, "
            "d.date AS date, d.summary AS summary", {"ids": ids})}
        newer = {}
        for r in self.q("MATCH (n:Decision)-[r:SUPERSEDES|AMENDS]->(d:Decision) WHERE d.id IN $ids "
                        "RETURN d.id AS id, n.id AS by, type(r) AS kind", {"ids": ids}):
            newer.setdefault(r["id"], []).append(f"{'superseded' if r['kind'] == 'SUPERSEDES' else 'amended'} by {r['by']}")
        out = []
        for did in ids:
            if did not in info:
                continue
            row = dict(info[did])
            row["summary"] = (row["summary"] or "")[:240]
            row["updated_by"] = newer.get(did, [])
            if score is not None:
                row["score"] = round(score[did], 3)
                row["evidence"] = why[did][:4]
            out.append(row)
        return out

    def decision(self, did: str) -> dict:
        did = did.upper()
        if not did.startswith("ADR-"):
            did = f"ADR-{int(did):04d}" if did.isdigit() else did
        elif re.fullmatch(r"ADR-\d+", did):
            did = f"ADR-{int(did[4:]):04d}"
        base = self._decorate([did])
        if not base:
            raise NotFound(f"{did} is not in the graph. Search by words instead: whygraph search \"<topic>\"")
        d = base[0]
        d["amends"] = [r["id"] for r in self.q("MATCH (:Decision {id: $i})-[:AMENDS|SUPERSEDES]->(o:Decision) "
                                               "RETURN o.id AS id ORDER BY id", {"i": did})]
        d["referenced_by"] = [r["id"] for r in self.q("MATCH (o:Decision)-[:REFERENCES]->(:Decision {id: $i}) "
                                                       "RETURN o.id AS id ORDER BY id LIMIT 10", {"i": did})]
        d["references"] = [r["id"] for r in self.q("MATCH (:Decision {id: $i})-[:REFERENCES]->(o:Decision) "
                                                    "RETURN o.id AS id ORDER BY id LIMIT 10", {"i": did})]
        d["modules"] = self.q("MATCH (f:File)-[:CITES]->(:Decision {id: $i}) "
                              "RETURN f.module AS module, count(f) AS files ORDER BY files DESC LIMIT 6", {"i": did})
        d["recent_commits"] = self.q("MATCH (p:Person)-[:AUTHORED]->(c:Commit)-[:CITES]->(:Decision {id: $i}) "
                                     "RETURN c.sha AS sha, c.subject AS subject, p.name AS author, c.ts AS ts "
                                     "ORDER BY ts DESC LIMIT 5", {"i": did})
        d["people"] = self.q("MATCH (p:Person)-[:AUTHORED]->(:Commit)-[:CITES]->(:Decision {id: $i}) "
                             "RETURN p.name AS person, count(*) AS commits ORDER BY commits DESC, person LIMIT 5",
                             {"i": did})
        return d

    def search(self, text: str, limit: int = 8) -> list:
        """Full-text search over decision titles and summaries (BM25-style score)."""
        words = [w for w in FT_STRIP.sub(" ", text).split() if len(w) > 1]
        if not words:
            raise NotFound("empty search; pass a few words, e.g. whygraph search \"plan cache invalidation\"")
        rows = self.q("MATCH (d:Decision) SEARCH d IN (FULLTEXT INDEX decision_text FOR $q LIMIT $n) "
                      "SCORE AS score RETURN d.id AS id, score ORDER BY score DESC, id",
                      {"q": " ".join(words), "n": limit})
        scores = {r["id"]: r["score"] for r in rows}
        out = self._decorate([r["id"] for r in rows])
        for o in out:
            o["score"] = round(scores[o["id"]], 3)
        return out

    # ---- the one call an agent makes before editing -------------------------------
    def why(self, path: str, limit: int = 6) -> dict:
        path = self.resolve_file(path)
        recent = self.q("MATCH (p:Person)-[:AUTHORED]->(c:Commit)-[:TOUCHES]->(:File {path: $p}) "
                        "RETURN c.sha AS sha, c.subject AS subject, p.name AS author, c.ts AS ts "
                        "ORDER BY ts DESC LIMIT $n", {"p": path, "n": limit})
        return {
            "path": path,
            "decisions": self.decisions_for_files([path], limit),
            "owners": self.owners(path, 3),
            "recent_authors": self.recent_authors(path, 3),
            "changes_with": self.changes_with(path, limit),
            "recent_commits": recent,
            "graph": self.meta(),
        }
