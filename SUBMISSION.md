# Devpost submission: Relate by Neo4j Hackathon

Rules: https://relate.devpost.com/rules (read 2026-11-18). Deadline: Fri 2026-12-11 6:00 PM PST (2026-12-12 02:00 UTC).
Work started 2026-11-18, inside the Contest Period (starts 2026-11-11). Prizes: 1st Mac Studio M5 Max, 2nd Mac mini M6 32GB, 3rd Mac mini M6 16GB.

## Fields to paste

**Project title:** whygraph

**Tagline:** Ask "why is this file the way it is?" before an agent edits it: a decision graph on embedded Relate, served over MCP.

**Description (what it does and why it is useful):**
Coding agents edit files without knowing the reasons behind them. The reasons live in architecture decision records, commit history and the heads of the people who wrote the code, and an agent that cannot see them re-opens settled decisions, breaks invariants and misses the file that always changes together with the one it is editing.

whygraph turns a git repository into a graph inside an embedded Relate store: people, commits, files and decisions (ADRs), with edges for who authored what, what each commit touched, which ADRs commits and source files cite, and which ADRs amend or supersede which. One call, `why_file`, returns what an agent needs before editing: the decisions that govern the file ranked with the evidence for each ("cited in this file", "2 commits touching it cite it", "3 files that change with it cite it"), whether a newer decision supersedes them, who to ask (recency-weighted), the files that usually change with it, and its recent commits. Other tools search decisions by text, show one decision with its supersession chain and where it is cited in code, and find files.

It runs in-process (one `.rl` file, no server, indexes the 483-commit / 566-ADR Relate repository in about 6 seconds) and speaks MCP, so Claude Code, Cursor or Codex can call it directly. A small honest eval replays later commits against a graph built from earlier ones: graph traversal found the governing ADR more often than text search at the 70% split (12 tasks, hit@5 0.83 vs 0.33 for full text), while full text tied it at 50% and beat it at 85% (7 and 3 tasks), fusing history with folder and name signals gives the best co-change prediction (hit@10 0.69 vs 0.65 for name overlap, intervals overlap), and for "who to ask" simply asking the top committer is hard to beat on a repository with one dominant author. The write-up reports where the graph does not win.

**Built with:** Relate embedded database (`relate-db` Python binding), Cypher, full-text indexes, MCP, Python standard library, git, pytest.

**Product capabilities used (Relate):** embedded `relate.connect()` stores on disk and in memory (the eval builds ~20 graphs in memory); Cypher `UNWIND` batch ingestion and `CALL (c, r) { ... }` subqueries; uniqueness constraints; full-text indexes queried with `SEARCH d IN (FULLTEXT INDEX ... ) SCORE`; multi-hop pattern queries for co-change and for "decisions reachable through neighbouring files"; MCP as the agent interface. Not used: vector search, Bolt/HTTP, WebAssembly (stated so judges do not look for them).

**How it was built:** One Python package with a single dependency (`relate-db`). `build.py` reads `git log --name-only` and ADR markdown (numbered files under `docs/adr/`) and writes the graph in batches. `query.py` holds the Cypher plus a few lines of ranking: co-change score `sum(1/files-in-commit)`, ownership with a 14-day recency half-life, decision score weighted by `1/ln(2+citations)` so a decision cited everywhere does not drown a specific one (each result also names its strongest kind of evidence), and reciprocal-rank fusion of history, same-folder and file-name signals. `cli.py` is the command line (JSON when piped, readable digest on a terminal, errors that say how to fix the call). `mcp.py` is a dependency-free stdio MCP server. 15 pytest tests run on synthetic git repositories. The eval (`eval/run_eval.py`) is a temporal holdout with bootstrap intervals and simple baselines, with protocol and caveats in `eval/README.md`; one design change made after a first run, and one ranking change that was tried and reverted, are disclosed there.

**Challenges / what we learned:** History-only co-change is weak on a two-week-old repository; the useful signal is the fusion. The first version dropped mass-refactor commits from the graph, which left 28% of file queries with no answer; keeping them down-weighted fixed coverage but cost some owner accuracy. Both numbers are reported.

**What is next:** vector search over ADR text and commit messages for hybrid retrieval (Relate supports it; not used yet), an LLM-in-the-loop study of whether agents using the tools write better changes, indexing issues and PR discussions as decisions.

**AI tools disclosure (paste as-is):**
Claude Code (Anthropic; Claude models) did this work under the entrant's standing instruction to find and enter contests. It picked this hackathon from a sweep of open contests, chose the project, and wrote the code, tests, eval harness, documentation, screenshots and demo video, and ran every command whose result is reported. The entrant is responsible for the submission, including originality and licence compliance. The video's narration is a synthetic voice (Piper TTS, en_US-joe-medium, run locally). No AI model runs inside whygraph: indexing, ranking, the MCP server and the eval are deterministic code. Third-party software: relate-db (Apache-2.0), Python standard library, pytest (MIT). The demo and eval use the public Apache-2.0 repository relatedb/relate as read-only input data (commit 2346dec599); `--anonymize` replaces author names in the demo.

**Reuse of earlier work (rules section 3):** none. The first commit is dated 2026-11-18, and no code comes from earlier projects. A search of the entrant's past coding-agent sessions found no earlier decision-graph, ADR or co-change tool. It ran four queries: decision graph / ADR / git history; Neo4j graph of commits and co-change; "why is this file this way" and architecture decision records; embedded graph database. All four completed without timing out, and the Neo4j co-change query returned nothing. The other hits were unrelated documents and one past note on which embedded store to prefer if a knowledge graph is ever needed. A look at the entrant's other repositories also found nothing to reuse.

**IP note:** entering grants Neo4j a non-exclusive licence to the submitted material; the code is Apache-2.0 anyway.

**Demo:** https://youtu.be/EBa4CtHUoP4 (1:38). Six terminal screens with a synthetic voice (Piper TTS, en_US-joe-medium): title, `why`, a real Claude Code session calling `why_file` over MCP, `search`, `decision`, and the eval. Rebuild it with `demo/render_screens.py` and `demo/make_video.py` from `demo/narration.json` and the `.txt` sources in `docs/screenshots/`; the builder refuses to write a video over the 2-minute limit. The screen texts are real command output, and the MCP screen is an excerpt of the Claude Code transcript.

**Setup instructions (paste):**
```
git clone https://github.com/StartupBros-com/whygraph && cd whygraph
python3 -m venv .venv && . .venv/bin/activate && pip install .
whygraph --store data/relate.rl why relate/relate/src/plan_cache.rs   # the committed store (data/relate.rl), no build needed
demo/demo.sh          # clones relatedb/relate at a pinned commit, indexes it, runs three queries (~10 s)
pip install pytest && pytest -q      # 15 passed
claude mcp add whygraph -- whygraph --store "$PWD/whygraph.rl" mcp   # after: whygraph index --repo <your repo> --store whygraph.rl
```
Verified 2026-11-19 on a fresh clone of github.com/StartupBros-com/whygraph at abe22a6, with relate-db 1.1.0: 16 tests pass on Python 3.12.3 and 3.9.25; the `data/relate.rl` commands above run and leave the store byte-identical; `demo/demo.sh` rebuilds the graph from a clone of relatedb/relate and its `why` output matches the committed store line for line. MCP checked with a real client the same day: `claude mcp add --scope project whygraph -- whygraph --store "$PWD/data/relate.rl" mcp`, then Claude Code 2.1.328 in print mode reported the server connected, called `why_file` on `relate/relate/src/plan_cache.rs` and answered from the result. Earlier runs: Python 3.15.2 tests on 2026-11-18.
