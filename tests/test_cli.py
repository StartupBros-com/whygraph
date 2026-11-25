import json
import sys

import pytest

from whygraph import cli


@pytest.fixture
def fake_store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("WHYGRAPH_STORE", raising=False)

    class Graph:
        def __init__(self, store):
            self.store = store

        def find(self, target, limit):
            return [{"path": f"{self.store}/{target}", "commits": limit}]

        def close(self):
            pass

    monkeypatch.setattr(cli, "WhyGraph", Graph)
    return tmp_path


@pytest.mark.parametrize("args,store", [
    (["--store", "chosen.rl", "--limit", "9", "--json", "find", "x"], "chosen.rl"),
    (["find", "x", "--store", "chosen.rl", "--limit", "9", "--json"], "chosen.rl"),
    (["--json", "--store", "chosen.rl", "find", "x", "--limit", "9"], "chosen.rl"),
    (["--store", "first.rl", "--limit", "2", "find", "x",
      "--store", "second.rl", "--limit", "9", "--json"], "second.rl"),
])
def test_common_option_order(fake_store, monkeypatch, capsys, args, store):
    monkeypatch.setenv("WHYGRAPH_STORE", "env.rl")
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    (fake_store / store).touch()
    assert cli.main(args) == 0
    assert json.loads(capsys.readouterr().out) == [{"path": f"{store}/x", "commits": 9}]


@pytest.mark.parametrize("env,store", [(None, "whygraph.rl"), ("env.rl", "env.rl")])
def test_common_defaults(fake_store, monkeypatch, capsys, env, store):
    if env is not None:
        monkeypatch.setenv("WHYGRAPH_STORE", env)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    (fake_store / store).touch()
    assert cli.main(["find", "x"]) == 0
    assert json.loads(capsys.readouterr().out) == [{"path": f"{store}/x", "commits": 6}]


@pytest.mark.parametrize("before,after,tty,want_json", [
    (["--text"], [], False, False),
    ([], ["--text"], False, False),
    ([], [], True, False),
    (["--json"], ["--text"], True, True),
    (["--text"], ["--json"], True, True),
])
def test_common_output_flags(fake_store, monkeypatch, capsys, before, after, tty, want_json):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: tty)
    (fake_store / "whygraph.rl").touch()
    assert cli.main([*before, "find", "x", *after]) == 0
    output = capsys.readouterr().out
    if want_json:
        assert json.loads(output) == [{"path": "whygraph.rl/x", "commits": 6}]
    else:
        assert output == "whygraph.rl/x  (6 commits)\n"


@pytest.mark.parametrize("args", [
    ["--limit", "bad", "find", "x"],
    ["find", "x", "--limit", "bad"],
])
def test_invalid_limit_in_both_positions(capsys, args):
    with pytest.raises(SystemExit) as exc:
        cli.main(args)
    assert exc.value.code == 2
    diagnostic = capsys.readouterr().err
    assert "--limit" in diagnostic and "'bad'" in diagnostic


def test_common_options_are_documented_at_root(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "WHYGRAPH_STORE" in output and "default 6" in output
    assert all(flag in output for flag in ("--store", "--json", "--text", "--limit"))


@pytest.mark.parametrize("command", ["index", "why", "who", "coupled", "find", "decision", "search", "mcp"])
def test_common_options_are_hidden_in_command_help(capsys, command):
    with pytest.raises(SystemExit) as exc:
        cli.main([command, "--help"])
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert output.startswith("usage: whygraph " + command + " ")
    assert not any(flag in output for flag in ("--store", "--json", "--text", "--limit"))
