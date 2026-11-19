import os
import subprocess

import pytest

ENV = {"GIT_AUTHOR_DATE": "", "GIT_COMMITTER_DATE": ""}

ADR1 = """# ADR-0001: Use a write-ahead log

- Status: Accepted
- Date: 2026-01-01

## Context
We need crash safety.

## Decision
All writes go through a write-ahead log before touching pages.
"""
ADR2 = """# ADR-0002: Page cache eviction

- Status: Accepted
- Date: 2026-01-02

## Decision
Evict pages with a clock sweep.
"""
ADR3 = """# ADR-0003: Group commit

- Status: Accepted
- Date: 2026-01-03
- Amends ADR-0001

## Decision
Batch fsyncs across concurrent writers.
"""


def _git(repo, *args, env=None):
    e = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", **(env or {}))
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=e)


@pytest.fixture(scope="session")
def repo(tmp_path_factory):
    r = tmp_path_factory.mktemp("repo")
    _git(r, "init", "-q", "-b", "main")
    n = [0]

    def commit(author, files, msg):
        n[0] += 1
        for path, text in files.items():
            p = r / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
            _git(r, "add", path)
        d = f"2026-02-{n[0]:02d}T12:00:00 +0000"
        _git(r, "-c", f"user.name={author}", "-c", "user.email=x@example.invalid", "commit", "-q", "-m", msg,
             env={"GIT_AUTHOR_DATE": d, "GIT_COMMITTER_DATE": d})

    commit("Ada", {"docs/adr/0001-wal.md": ADR1, "docs/adr/0002-cache.md": ADR2}, "docs: add ADR-0001 and ADR-0002")
    commit("Ada", {"src/wal.rs": "// implements ADR-0001\n", "src/wal_tests.rs": "t\n"}, "feat: write-ahead log (ADR-0001)")
    commit("Bob", {"src/cache.rs": "// clock sweep\n", "src/pool.rs": "p\n"}, "feat: page cache per ADR-0002")
    commit("Bob", {"src/wal.rs": "// implements ADR-0001\n// fsync batch\n", "src/wal_tests.rs": "t2\n"}, "fix: wal fsync")
    commit("Ada", {"docs/adr/0003-group-commit.md": ADR3}, "docs: ADR-0003 group commit")
    commit("Bob", {"package-lock.json": "{}\n", "src/misc.rs": "m\n"}, "chore: misc")
    return str(r)
