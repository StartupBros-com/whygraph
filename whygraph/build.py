"""Turn a git repository into a decision graph inside a Relate store.

Graph model:

  (:Person {name})-[:AUTHORED]->(:Commit {sha, subject, ts, nfiles})
  (:Commit)-[:TOUCHES]->(:File {path, module})
  (:Commit)-[:CITES]->(:Decision)         the commit message names an ADR
  (:File)-[:CITES]->(:Decision)           the file's text at the indexed revision names an ADR
  (:Decision)-[:REFERENCES]->(:Decision)  ADR text names another ADR
  (:Decision)-[:AMENDS|SUPERSEDES]->(:Decision)   parsed from the ADR header

A "decision" is an Architecture Decision Record: a numbered markdown file under
an ADR directory (default docs/adr/, files named NNNN-title.md). Nothing else is
specific to one repository.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass, field

import relate

ADR_RE = re.compile(r"ADR-(\d{3,5})")
NOISE_SUFFIXES = (".lock", "package-lock.json", "pnpm-lock.yaml", "CHANGELOG.md")
MAX_FILES_PER_COMMIT = 40  # eval only: commits above this are not replayed as tasks
BATCH = 400


def git(repo: str, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", repo, *args], check=True, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return out.stdout


def _git_bytes(repo: str, *args: str, check: bool = True) -> bytes:
    return subprocess.run(["git", "-C", repo, *args], check=check, capture_output=True).stdout


def _path_text(raw: bytes) -> str | None:
    """Relate file keys are UTF-8 text; do not alias undecodable paths."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def is_noise(path: str) -> bool:
    return path.endswith(NOISE_SUFFIXES)


def module_of(path: str) -> str:
    parts = path.split("/")
    return "/".join(parts[:2]) if len(parts) > 2 else parts[0]


def adr_id(num) -> str:
    return f"ADR-{int(num):04d}"


@dataclass
class Commit:
    sha: str
    author: str
    ts: int
    subject: str
    body: str
    files: list = field(default_factory=list)


@dataclass
class Decision:
    id: str
    num: int
    title: str
    status: str
    date: str
    summary: str
    path: str
    refs: set = field(default_factory=set)
    amends: set = field(default_factory=set)
    supersedes: set = field(default_factory=set)


def read_commits(repo: str, rev: str) -> list:
    """Non-merge commits reachable from rev, oldest first. Author names only, never emails."""
    # The leading empty NUL field marks the next header; Git adds a NUL
    # record terminator and, when names follow, one LF before the first path.
    fmt = "%x00%H%x00%an%x00%at%x00%s%x00%b%x00"
    raw = _git_bytes(repo, "log", "--no-merges", "--no-renames", "--name-only", "-z", f"--format={fmt}", rev)
    fields = iter(raw.split(b"\0"))
    next(fields)
    commits = []
    while sha := next(fields, b""):
        author, ts, subject, body, _ = (next(fields) for _ in range(5))
        files = []
        for index, name in enumerate(iter(lambda: next(fields, b""), b"")):
            path = _path_text(name.removeprefix(b"\n") if index == 0 else name)
            if path is not None:
                files.append(path)
        author_text, subject_text, body_text = (
            part.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n").strip()
            for part in (author, subject, body)
        )
        commits.append(Commit(sha.decode("ascii"), author_text, int(ts), subject_text, body_text, files))
    commits.reverse()
    return commits


def _section(text: str, heading: str) -> str:
    m = re.search(rf"^##\s+{heading}\s*$(.*?)(?=^##\s|\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else ""


def parse_adr(path: str, text: str):
    name = os.path.basename(path)
    m = re.match(r"(\d{3,5})-", name)
    if not m:
        return None
    num = int(m.group(1))
    ident = adr_id(num)
    first = text.strip().split("\n", 1)[0]
    title = re.sub(r"^#\s*(?:ADR-)?\d+[.:]?\s*", "", first).strip() or name
    status = ""
    sm = re.search(r"^(?:- )?\*{0,2}Status\*{0,2}:?\*{0,2}:?\s*(.+)$", text, re.M)
    if sm:
        status = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", sm.group(1)).strip()
    dm = re.search(r"^(?:- )?\*{0,2}Date\*{0,2}:?\*{0,2}:?\s*(\d{4}-\d{2}-\d{2})", text, re.M)
    date = dm.group(1) if dm else ""
    body = _section(text, "Decision") or _section(text, "Context")
    d = Decision(ident, num, title, status, date, re.sub(r"\s+", " ", body)[:400], path)
    for line in text.split("\n"):
        head = line.lstrip("- *").lower()
        ids = {adr_id(n) for n in ADR_RE.findall(line)} - {ident}
        if head.startswith("amends"):
            d.amends |= ids
        elif head.startswith("supersedes"):
            d.supersedes |= ids
    d.refs = {adr_id(n) for n in ADR_RE.findall(text)} - {ident}
    return d


def read_decisions(repo: str, rev: str, adr_dir: str) -> dict:
    names = _git_bytes(repo, "ls-tree", "-r", "-z", "--name-only", rev, "--", adr_dir)
    out = {}
    for name in names.split(b"\0"):
        p = _path_text(name)
        if p is None or not p.endswith(".md"):
            continue
        d = parse_adr(p, git(repo, "show", f"{rev}:{p}"))
        if d:
            out[d.id] = d
    # "Superseded by ADR-N" on the old ADR is also a SUPERSEDES edge from N to the old one.
    for d in list(out.values()):
        m = re.search(r"[Ss]uperseded(?: in part)? by\b.*?(ADR-\d{3,5})", d.status)
        if m and adr_id(m.group(1)[4:]) in out:
            out[adr_id(m.group(1)[4:])].supersedes.add(d.id)
    return out


def read_file_citations(repo: str, rev: str, adr_dir: str) -> dict:
    """path -> set of ADR ids named anywhere in that file's text at rev (outside the ADR dir)."""
    # -o keeps the matched ADR number. With -z each result is
    # REV:path<NUL>ADR-nnnn<LF>, not one ordinary text line per path.
    raw = _git_bytes(
        repo, "grep", "-I", "-o", "-z", "-E", "--no-line-number", "--no-column",
        "--no-heading", "--no-break", "--color=never", r"ADR-[0-9]{3,5}",
        rev, "--", ".", f":!{adr_dir}", check=False,
    )
    cites: dict = {}
    prefix = (rev + ":").encode("utf-8")
    start = 0
    while start < len(raw):
        nul = raw.index(b"\0", start)
        end = raw.index(b"\n", nul + 1)
        name, match = raw[start:nul], raw[nul + 1:end]
        if name.startswith(prefix):
            path = _path_text(name[len(prefix):])
            if path is not None:
                cites.setdefault(path, set()).add(adr_id(match[4:]))
        start = end + 1
    return cites


SCHEMA = [
    "CREATE CONSTRAINT person_name IF NOT EXISTS FOR (p:Person) REQUIRE p.name IS UNIQUE",
    "CREATE CONSTRAINT commit_sha IF NOT EXISTS FOR (c:Commit) REQUIRE c.sha IS UNIQUE",
    "CREATE CONSTRAINT file_path IF NOT EXISTS FOR (f:File) REQUIRE f.path IS UNIQUE",
    "CREATE CONSTRAINT decision_id IF NOT EXISTS FOR (d:Decision) REQUIRE d.id IS UNIQUE",
    "CREATE FULLTEXT INDEX decision_text IF NOT EXISTS FOR (d:Decision) ON EACH [d.title, d.summary]",
    "CREATE FULLTEXT INDEX commit_subject IF NOT EXISTS FOR (c:Commit) ON EACH [c.subject]",
]


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def build(repo: str, rev: str, store: str, adr_dir: str = "docs/adr", db=None, anonymize: bool = False) -> dict:
    """Index repo at rev into store (a path or ':memory:'). A store is rebuilt, never merged.

    Pass an open connection as db to keep an in-memory store open afterwards
    (the caller then owns closing it).
    """
    if db is None and store != ":memory:" and os.path.exists(store):
        raise FileExistsError(f"{store} exists; remove it first (an index is rebuilt, never merged)")
    sha = git(repo, "rev-parse", rev).strip()
    commits = read_commits(repo, sha)
    if anonymize:  # stable pseudonyms, for screenshots and shared demos
        for c in commits:
            c.author = "person-" + hashlib.sha1(c.author.encode()).hexdigest()[:6]
    decisions = read_decisions(repo, sha, adr_dir)
    cites = read_file_citations(repo, sha, adr_dir)
    owns = db is None
    if owns:
        db = relate.connect(store)
    for stmt in SCHEMA:
        db.execute(stmt)

    drows = [dict(id=d.id, num=d.num, title=d.title, status=d.status, date=d.date,
                  summary=d.summary, path=d.path) for d in decisions.values()]
    for chunk in _chunks(drows, BATCH):
        db.execute("UNWIND $rows AS r CREATE (:Decision {id: r.id, num: r.num, title: r.title, "
                   "status: r.status, date: r.date, summary: r.summary, path: r.path})", {"rows": chunk})
    for rel, attr in (("REFERENCES", "refs"), ("AMENDS", "amends"), ("SUPERSEDES", "supersedes")):
        rows = [dict(a=d.id, b=t) for d in decisions.values() for t in sorted(getattr(d, attr))
                if t in decisions and not (rel == "REFERENCES" and (t in d.amends or t in d.supersedes))]
        for chunk in _chunks(rows, BATCH):
            db.execute(f"UNWIND $rows AS r MATCH (a:Decision {{id: r.a}}), (b:Decision {{id: r.b}}) "
                       f"CREATE (a)-[:{rel}]->(b)", {"rows": chunk})

    people = sorted({c.author for c in commits})
    db.execute("UNWIND $rows AS n CREATE (:Person {name: n})", {"rows": people})
    all_files = sorted({f for c in commits for f in c.files if not is_noise(f)} | set(cites))
    for chunk in _chunks([dict(path=f, module=module_of(f)) for f in all_files], BATCH):
        db.execute("UNWIND $rows AS r CREATE (:File {path: r.path, module: r.module})", {"rows": chunk})

    for chunk in _chunks(commits, 100):
        rows = []
        for c in chunk:
            # Mass commits are kept: they still say who touched what, and the coupling score
            # weights each commit by 1 / files-in-commit, so they barely move it.
            files = [f for f in c.files if not is_noise(f)]
            msg_ids = sorted({adr_id(n) for n in ADR_RE.findall(c.subject + "\n" + c.body)} & set(decisions))
            rows.append(dict(sha=c.sha, author=c.author, ts=c.ts, subject=c.subject,
                             nfiles=len(files), files=files, adrs=msg_ids))
        db.execute(
            "UNWIND $rows AS r "
            "MATCH (p:Person {name: r.author}) "
            "CREATE (p)-[:AUTHORED]->(c:Commit {sha: r.sha, subject: r.subject, ts: r.ts, nfiles: r.nfiles}) "
            "WITH c, r "
            "CALL (c, r) { UNWIND r.files AS fp MATCH (f:File {path: fp}) CREATE (c)-[:TOUCHES]->(f) } "
            "CALL (c, r) { UNWIND r.adrs AS id MATCH (d:Decision {id: id}) CREATE (c)-[:CITES]->(d) }",
            {"rows": rows})
    frows = [dict(path=p, id=i) for p, ids in cites.items() for i in sorted(ids) if i in decisions]
    for chunk in _chunks(frows, BATCH):
        db.execute("UNWIND $rows AS r MATCH (f:File {path: r.path}), (d:Decision {id: r.id}) "
                   "CREATE (f)-[:CITES]->(d)", {"rows": chunk})
    db.execute("CREATE (:Meta {repo_rev: $rev, built_with: 'whygraph 0.1.0', adr_dir: $adr})",
               {"rev": sha, "adr": adr_dir})
    if owns:
        db.close()
    return dict(rev=sha, commits=len(commits), people=len(people), files=len(all_files),
                decisions=len(decisions), file_cites=len(frows))
