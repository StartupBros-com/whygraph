from unittest.mock import Mock

import pytest

from whygraph.query import WhyGraph


@pytest.mark.parametrize("target, busy, quiet, foreign", [
    ("new.py", "busy.py", "quiet.py", "docs/foreign.py"),
    ("/new.py", "busy.py", "/quiet.py", "docs/foreign.py"),
    ("docs/new.py", "docs/busy.py", "docs/quiet.py", "busy.py"),
    ("docs//new.py", "docs//busy.py", "docs//quiet.py", "docs/foreign.py"),
    (r"café\src/new.py", r"café\src/busy.py", r"café\src/quiet.py", "café/src/foreign.py"),
])
def test_location_groups_use_the_unmodified_folder(target, busy, quiet, foreign):
    db = Mock()
    db.execute.return_value = [
        {"p": target, "n": 100},
        {"p": quiet, "n": 1},
        {"p": busy, "n": 10},
        {"p": foreign, "n": 99},
    ]
    graph = WhyGraph(db=db)
    assert graph.related_by_location(target)[0] == [busy, quiet]
    assert graph.related_by_location(target, limit=1)[0] == [busy]
    db.execute.assert_called_once()


@pytest.mark.parametrize("path, prefix", [
    ("new.py", "/"),
    ("/new.py", "/"),
    ("docs/new.py", "docs/"),
    ("docs//new.py", "docs//"),
    (r"café\src/new.py", "café\\src/"),
])
def test_owner_and_author_fallback_keep_the_exact_prefix(path, prefix):
    db = Mock()
    db.execute.side_effect = [
        [],
        [{"person": "Reader", "tss": [1]}],
        [],
        [{"person": "Reader", "last_ts": 1}],
    ]
    graph = WhyGraph(db=db)
    graph._meta = {"latest": 1}
    assert graph.owners(path) == [
        {"person": "Reader", "commits": 1, "weight": 1.0, "last_ts": 1, "scope": "folder"}
    ]
    assert graph.recent_authors(path) == [{"person": "Reader", "last_ts": 1}]
    assert [call.args[1] for call in db.execute.call_args_list] == [
        {"p": path}, {"d": prefix}, {"p": path, "n": 3}, {"d": prefix, "n": 3}
    ]
