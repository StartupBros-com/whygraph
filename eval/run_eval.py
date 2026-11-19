"""Temporal-holdout evaluation of whygraph against simple baselines.

Protocol (fixed before any number was looked at; see eval/README.md):

  1. Order the repository's non-merge commits oldest to newest.
  2. Index the first SPLIT of them (graph, ADRs and source citations all as of that
     commit), the "past". The rest are the "future" the graph has never seen.
  3. Replay each future commit as a task an agent could be given, using only what the
     past graph knows, and score the answer against what actually happened.

Tasks
  coupling   "I am editing file A. Which other files will this change also touch?"
             truth = the other files in the same future commit (that exist in the past graph)
  owner      "Who should I ask about / have review file A?"
             truth = the author of the future commit
  decision   "I am about to change these files. Which ADR governs them?"
             truth = the ADRs the future commit message cites (that exist in the past graph)

Everything is deterministic: no LLM, no sampling except the seeded bootstrap.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys

import relate

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from whygraph.build import ADR_RE, MAX_FILES_PER_COMMIT, adr_id, build, git, is_noise, read_commits  # noqa: E402
from whygraph.query import WhyGraph  # noqa: E402

K_FILES = 10
K_ADR = 5
MAX_QUERY_FILES = 15


def ci(vals, seed=7, n=2000):
    """95% bootstrap interval of the mean."""
    if not vals:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(vals) for _ in vals) / len(vals) for _ in range(n))
    return (means[int(0.025 * n)], means[int(0.975 * n)])


def summarize(name, per_query):
    out = {"method": name, "n": len(per_query)}
    for key in per_query[0] if per_query else []:
        vals = [q[key] for q in per_query]
        lo, hi = ci(vals)
        out[key] = round(sum(vals) / len(vals), 3)
        out[key + "_ci"] = [round(lo, 3), round(hi, 3)]
    return out


def rr(ranked, truth):
    for i, x in enumerate(ranked, 1):
        if x in truth:
            return 1.0 / i
    return 0.0


def tokens(path):
    return {t for t in re.split(r"[^A-Za-z0-9]+", path.lower()) if len(t) > 2}


def run(repo, rev, split, adr_dir="docs/adr"):
    head = git(repo, "rev-parse", rev).strip()
    commits = read_commits(repo, head)
    cut = int(len(commits) * split)
    past, future = commits[:cut], commits[cut:]
    cutoff_sha = past[-1].sha
    db = relate.connect(":memory:")
    stats = build(repo, cutoff_sha, ":memory:", adr_dir, db=db)
    w = WhyGraph(db=db)

    known_files = {r["p"] for r in w.q("MATCH (f:File) RETURN f.path AS p")}
    touches = {r["p"]: r["n"] for r in w.q(
        "MATCH (f:File) OPTIONAL MATCH (f)<-[:TOUCHES]-(c:Commit) RETURN f.path AS p, count(c) AS n")}
    tok = {p: tokens(p) for p in known_files}
    popular = sorted(touches, key=lambda p: (-touches[p], p))
    people = [r["p"] for r in w.q("MATCH (p:Person)-[:AUTHORED]->(c) RETURN p.name AS p, count(c) AS n ORDER BY n DESC, p")]
    last_author_by_file = {}
    for c in past:
        for f in c.files:
            last_author_by_file[f] = c.author
    dirs = {}
    for p in known_files:
        dirs.setdefault(p.rsplit("/", 1)[0] if "/" in p else "", []).append(p)
    adr_text = {}
    for r in w.q("MATCH (d:Decision) RETURN d.id AS id, d.path AS path"):
        adr_text[r["id"]] = git(repo, "show", f"{cutoff_sha}:{r['path']}").lower()
    cite_counts = w.cite_counts()
    global_adrs = sorted(cite_counts, key=lambda d: (-cite_counts[d], d))
    dec_ids = set(cite_counts)

    # ---- future commits as tasks --------------------------------------------------
    tasks = []
    for c in future:
        files = [f for f in c.files if not is_noise(f)]
        if len(files) > MAX_FILES_PER_COMMIT:
            continue
        known = [f for f in files if f in known_files]
        adrs = sorted({adr_id(n) for n in ADR_RE.findall(c.subject + "\n" + c.body)} & dec_ids)
        tasks.append(dict(c=c, files=known, adrs=adrs))

    # ---- coupling ------------------------------------------------------------------
    coup = {m: [] for m in ("graph", "graph_count_only", "graph_then_samedir", "graph+name+samedir_rrf", "same_dir", "name_overlap", "popular")}
    cov = 0
    n_q = 0
    for t in tasks:
        fs = t["files"]
        if not (2 <= len(fs) <= MAX_QUERY_FILES):
            continue
        for a in fs:
            truth = set(fs) - {a}
            n_q += 1
            g = w.cochange(a, K_FILES)
            glist = [r["path"] for r in g]
            gcount = [r["path"] for r in sorted(g, key=lambda r: (-r["commits"], r["path"]))]
            cov += bool(glist)
            same = [p for p in sorted(dirs.get(a.rsplit("/", 1)[0] if "/" in a else "", []), key=lambda p: (-touches[p], p)) if p != a]
            ta = tok[a]
            overlap = sorted((p for p in known_files if p != a),
                             key=lambda p: (-len(ta & tok[p]) / (len(ta | tok[p]) or 1), p))
            pop = [p for p in popular if p != a]
            filled = (glist + [p for p in same if p not in glist])[:K_FILES]
            fused = [r["path"] for r in w.changes_with(a, K_FILES)]  # the shipped fusion
            for name, ranked in (("graph", glist), ("graph_count_only", gcount[:K_FILES]),
                                 ("graph_then_samedir", filled), ("graph+name+samedir_rrf", fused),
                                 ("same_dir", same[:K_FILES]),
                                 ("name_overlap", overlap[:K_FILES]), ("popular", pop[:K_FILES])):
                hit = [p for p in ranked if p in truth]
                coup[name].append({"hit@10": 1.0 if hit else 0.0,
                                   "recall@10": len(hit) / len(truth),
                                   "mrr": rr(ranked, truth)})

    # ---- owner ---------------------------------------------------------------------
    owner = {m: [] for m in ("graph", "last_author", "last3_distinct_authors", "graph_recent3", "top_committer_overall")}
    top_overall = people[0] if people else ""
    for t in tasks:
        fs = t["files"]
        if not fs:
            continue
        for a in fs[:MAX_QUERY_FILES]:
            truth = {t["c"].author}
            g = [o["person"] for o in w.owners(a, 3)]
            last = last_author_by_file.get(a)
            if last is None:
                folder = a.rsplit("/", 1)[0] if "/" in a else ""
                for c in reversed(past):
                    if any(f.startswith(folder + "/") for f in c.files):
                        last = c.author
                        break
            folder = a.rsplit("/", 1)[0] if "/" in a else ""
            recent3 = []
            for c in reversed(past):
                if (a in c.files or (a not in last_author_by_file and any(f.startswith(folder + "/") for f in c.files))) \
                        and c.author not in recent3:
                    recent3.append(c.author)
                if len(recent3) == 3:
                    break
            ranked = {"graph": g, "last_author": [last] if last else [], "last3_distinct_authors": recent3,
                      "graph_recent3": [o["person"] for o in w.recent_authors(a, 3)],
                      "top_committer_overall": [top_overall]}
            for name, r in ranked.items():
                owner[name].append({"top1": 1.0 if r[:1] and r[0] in truth else 0.0,
                                    "top3": 1.0 if any(x in truth for x in r[:3]) else 0.0,
                                    "_author": t["c"].author})
    owner_nontop = {m: [{k: v for k, v in q.items() if k != "_author"} for q in qs if q["_author"] != top_overall]
                    for m, qs in owner.items()}
    owner = {m: [{k: v for k, v in q.items() if k != "_author"} for q in qs] for m, qs in owner.items()}

    # ---- decisions -----------------------------------------------------------------
    dec = {m: [] for m in ("graph", "fulltext_on_subject", "graph+fulltext_rrf", "grep_adr_text", "most_cited_overall")}
    for t in tasks:
        fs = t["files"][:MAX_QUERY_FILES]
        truth = set(t["adrs"])
        if not truth or not fs:
            continue
        g = [d["id"] for d in w.decisions_for_files(fs, K_ADR)]
        subj = ADR_RE.sub(" ", t["c"].subject)
        try:
            ft = [d["id"] for d in w.search(subj, K_ADR)]
        except Exception:
            ft = []
        rrf = {}
        for lst in (g, ft):
            for i, d in enumerate(lst, 1):
                rrf[d] = rrf.get(d, 0.0) + 1.0 / (60 + i)
        fused = sorted(rrf, key=lambda d: (-rrf[d], d))[:K_ADR]
        names = {os.path.basename(f).lower() for f in fs if len(os.path.basename(f)) > 6}
        grep_score = {d: sum(1 for n in names if n in txt) for d, txt in adr_text.items()}
        grep = [d for d in sorted(grep_score, key=lambda d: (-grep_score[d], d)) if grep_score[d] > 0][:K_ADR]
        for name, ranked in (("graph", g), ("fulltext_on_subject", ft), ("graph+fulltext_rrf", fused),
                             ("grep_adr_text", grep), ("most_cited_overall", global_adrs[:K_ADR])):
            hit = [d for d in ranked if d in truth]
            dec[name].append({"hit@5": 1.0 if hit else 0.0, "recall@5": len(hit) / len(truth),
                              "mrr": rr(ranked, truth)})

    result = {
        "repo_rev": head, "split": split, "cutoff_commit": cutoff_sha,
        "past_commits": len(past), "future_commits": len(future),
        "graph": stats,
        "coupling": {"queries": n_q, "graph_coverage": round(cov / n_q, 3) if n_q else None,
                     "methods": [summarize(m, q) for m, q in coup.items() if q]},
        "owner": {"queries": len(owner["graph"]),
                  "all": [summarize(m, q) for m, q in owner.items() if q],
                  "excluding_top_author": {"queries": len(owner_nontop["graph"]),
                                           "methods": [summarize(m, q) for m, q in owner_nontop.items() if q]}},
        "decision": {"tasks": len(dec["graph"]), "methods": [summarize(m, q) for m, q in dec.items() if q]},
    }
    w.close()
    return result


def table(rows, keys):
    head = "| method | n | " + " | ".join(keys) + " |"
    sep = "|---|---|" + "---|" * len(keys)
    lines = [head, sep]
    for r in rows:
        cells = [f"{r[k]:.3f} [{r[k + '_ci'][0]:.2f}, {r[k + '_ci'][1]:.2f}]" for k in keys]
        lines.append(f"| {r['method']} | {r['n']} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def markdown(res):
    out = [f"### split {res['split']:.0%}: index {res['past_commits']} commits, replay {res['future_commits']} later commits",
           f"(rev `{res['repo_rev'][:10]}`, cutoff commit `{res['cutoff_commit'][:10]}`, graph {res['graph']['decisions']} decisions / "
           f"{res['graph']['files']} files / {res['graph']['commits']} commits)", "",
           f"**Coupling** ({res['coupling']['queries']} file queries; graph returned any answer for "
           f"{res['coupling']['graph_coverage']:.0%}); mean and 95% bootstrap interval", "",
           table(res["coupling"]["methods"], ["hit@10", "recall@10", "mrr"]), "",
           f"**Owner** ({res['owner']['queries']} file queries)", "",
           table(res["owner"]["all"], ["top1", "top3"]), "",
           f"Owner, excluding commits by the single most active author ({res['owner']['excluding_top_author']['queries']} queries)", "",
           table(res["owner"]["excluding_top_author"]["methods"], ["top1", "top3"]), "",
           f"**Decision** ({res['decision']['tasks']} future commits that cite an ADR known at the cutoff)", "",
           table(res["decision"]["methods"], ["hit@5", "recall@5", "mrr"]), ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--rev", required=True)
    ap.add_argument("--splits", default="0.5,0.7,0.85")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "results"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    md = []
    for s in [float(x) for x in a.splits.split(",")]:
        res = run(a.repo, a.rev, s)
        with open(os.path.join(a.out, f"split_{int(s * 100)}.json"), "w") as fh:
            json.dump(res, fh, indent=1)
        md.append(markdown(res))
        print(md[-1])
    with open(os.path.join(a.out, "results.md"), "w") as fh:
        fh.write("\n".join(md))


if __name__ == "__main__":
    main()
