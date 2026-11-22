"""Exercise Git's real record formats without provider calls or a working corpus."""
import os
import subprocess
import tempfile
import unittest

from whygraph import build
from whygraph.query import WhyGraph


class GitPaths(unittest.TestCase):
    paths = ("\nfirst.py", "café.py", "colon:path.py", "line\nbreak.py",
             "carriage\rreturn.py", " path .py", "back\\slash.py", "sep\x1erecord.py",
             "sep\x1ffield.py", "plain.py")
    adr_path = "docs/adr/0123-décision:part\n2.md"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = tmp.name
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Fixture Author")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "core.quotePath", "true")
        for path in self.paths:
            self.stage(path.encode(), b"ADR-0123 plus ADR-0124 then ADR-0123\n")
        self.stage(self.adr_path.encode(), b"# ADR-0123: first\n\n## Decision\nADR-0999\n")
        self.stage(b"nonutf\xff.py", b"ADR-0123")
        self.stage(b"nonutf\xfe.py", b"ADR-0124")
        self.stage(b"binary.py", b"\0ADR-0123")
        self.git("commit", "-qm", "initial", "-m", "line one\nline two")
        self.initial = self.git("rev-parse", "HEAD").decode().strip()
        self.git("commit", "--allow-empty", "-qm", "empty")
        self.stage(self.adr_path.encode(), b"# ADR-0123: rewritten\n")
        self.git("commit", "-qm", "latest")

    def git(self, *args, data=None):
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        return subprocess.run(["git", "-C", self.repo, "-c", f"core.hooksPath={os.devnull}", *args],
                              input=data, capture_output=True, check=True, env=env).stdout

    def stage(self, path, data):
        # Stage by raw index bytes: the fixture need not create a filename
        # that the host filesystem (for example Windows) cannot represent.
        blob = self.git("hash-object", "-w", "--stdin", data=data).strip()
        self.git("update-index", "-z", "--index-info", data=b"100644 " + blob + b"\t" + path + b"\0")

    def test_ascii_path_and_repeated_citations_keep_the_existing_shape(self):
        first = build.read_commits(self.repo, "HEAD")[0]
        self.assertIn("plain.py", first.files)
        cited = build.read_file_citations(self.repo, self.initial, "docs/adr")
        self.assertEqual(cited["plain.py"], {"ADR-0123", "ADR-0124"})

    def test_log_paths_are_exact_and_empty_commits_still_parse(self):
        initial, empty, latest = build.read_commits(self.repo, "HEAD")
        self.assertEqual((initial.sha, initial.author, initial.subject, initial.body),
                         (self.initial, "Fixture Author", "initial", "line one\nline two"))
        self.assertEqual(set(initial.files), {*self.paths, self.adr_path, "binary.py"})
        self.assertEqual((empty.subject, empty.files), ("empty", []))
        self.assertEqual((latest.subject, latest.files), ("latest", [self.adr_path]))

    def test_adr_listing_uses_the_requested_historical_tree(self):
        first = build.read_decisions(self.repo, self.initial, "docs/adr")["ADR-0123"]
        latest = build.read_decisions(self.repo, "HEAD", "docs/adr")["ADR-0123"]
        self.assertEqual((first.path, first.title, first.summary),
                         (self.adr_path, "first", "ADR-0999"))
        self.assertEqual((latest.path, latest.title), (self.adr_path, "rewritten"))

    def test_citations_keep_all_ids_and_ignore_configured_number_fields(self):
        self.git("config", "grep.lineNumber", "true")
        self.git("config", "grep.column", "true")
        self.git("config", "color.grep", "always")
        expected = {path: {"ADR-0123", "ADR-0124"} for path in self.paths}
        self.assertEqual(build.read_file_citations(self.repo, self.initial, "docs/adr"), expected)
        self.assertEqual(build.read_file_citations(self.repo, "HEAD", "."), {})

    def test_indexed_and_cited_keys_resolve_under_their_exact_names(self):
        class Recorder:
            def __init__(self):
                self.files = set()
                self.cited = set()

            def execute(self, cypher, params=None):
                params = params or {}
                if "CREATE (:File {path: r.path" in cypher:
                    self.files.update(row["path"] for row in params["rows"])
                if "CREATE (f)-[:CITES]->(d)" in cypher:
                    self.cited.update(row["path"] for row in params["rows"])
                if "RETURN f.path AS p" in cypher:
                    path = params["p"]
                    if "ENDS WITH" in cypher:
                        return [{"p": name} for name in self.files if name.endswith(path)]
                    return [{"p": path}] if path in self.files else []
                return []

        db = Recorder()
        counts = build.build(self.repo, self.initial, ":memory:", db=db)
        graph = WhyGraph(db=db)
        for path in self.paths:
            with self.subTest(path=path):
                self.assertEqual(graph.resolve_file(path), path)
                self.assertIn(path, db.cited)
        self.assertEqual(counts["file_cites"], len(self.paths))
