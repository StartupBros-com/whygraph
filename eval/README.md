# Eval: does the graph predict what a later commit touches?

Temporal holdout on the Relate repository itself (`relatedb/relate` at `2346dec599`, 483 non-merge commits,
566 ADRs, 9 authors, history spans about two weeks). No LLM and no sampling; the only randomness is a seeded
bootstrap for the intervals. Reproduce (about 4 minutes, under 1 GB RAM):

```bash
git clone https://github.com/relatedb/relate.git /tmp/relate && git -C /tmp/relate checkout 2346dec59924eb730a5041d15bcfbcbf06d5de79
python eval/run_eval.py --repo /tmp/relate --rev 2346dec59924eb730a5041d15bcfbcbf06d5de79 --out eval/results
```

## Protocol

Fixed before looking at numbers: index the first 50%, 70% or 85% of commits (graph, ADRs and ADR citations in source
all as of the cutoff commit), then replay every later commit as a task using only the past graph.

| task | question an agent asks | truth |
|---|---|---|
| coupling | I am editing file A; what else will this change touch? | other files in the same later commit (that exist in the past graph); commits with more than 40 files are not replayed |
| owner | who should review file A? | author of the later commit |
| decision | I am changing these files; which ADR governs them? | ADRs the later commit message cites (that exist at the cutoff) |

Baselines: same folder (busiest first), file-name token overlap, most-touched files; last author, last 3 distinct
authors, top committer overall; BM25-style full text on the commit subject, grep of ADR text for the file names, most-cited ADRs.
Full tables with 95% intervals for all three splits: [results/results.md](results/results.md).

## Result (70% split, the one reported first; the other splits are in the table file)

| task | graph | best simple baseline | verdict |
|---|---|---|---|
| coupling hit@10 (818 queries) | 0.556 | name overlap 0.645 | graph history alone does **not** beat name overlap; same-folder ties it (0.551) |
| coupling hit@10, shipped fusion (history + folder + name, RRF) | **0.694** | name overlap 0.645 | highest at all three splits (0.695 / 0.694 / 0.736 vs 0.663 / 0.645 / 0.653), but the 95% intervals overlap at every split |
| owner top-1 (1189 queries) | 0.637 | top committer overall 0.732 | **loses** to "ask whoever commits most" at 50% and 70%; wins at 85% (0.717 vs 0.659) |
| owner top-3 | 0.787 | last-3 distinct authors 0.786 | tie |
| owner top-1 without the dominant author (319) | 0.586 | last author 0.592 | tie |
| decision hit@5 (12 tasks) | **0.833** | subject full text 0.333 | graph wins here, but see below |

## What this does and does not show

- The strongest, least ambiguous result: ADR lookup by graph traversal beats text search over ADR text, which
  scores zero when the file name never appears in the ADR. But the sample is tiny and unstable: 7, 12 and 3 tasks at the
  three splits; full text ties the graph at 50% (0.857 each) and beats it at 85% (1.0 vs 0.667). Treat it as
  "promising on 22 replayed commits", not as a measured gain.
- Coupling from co-change history alone is weak on a repository this young (two weeks of history). The fusion with
  folder and name signals is what helps, and the result says which signal supported each file, so an agent can weigh it.
- Ownership is dominated by one author. A recency decay (half-life 14 days) beats "last author" but not "top committer".
- One design change was made after seeing a first run: commits touching more than 40 files were originally dropped
  from the graph; the first 70% run gave coupling coverage 72%, owner top-1 0.724 and decision MRR 0.833. Keeping them
  (they are down-weighted by 1/files-in-commit) raised coupling coverage to 100% and hit@10 from 0.504 to 0.556, but owner top-1
  fell to 0.637 and decision MRR to 0.750. The table above is the final code. The eval still skips replaying
  commits over 40 files as tasks.
- A second change was tried after the final run and reverted. The `why` output for `plan_cache.rs` put a Proposed ADR that the file never cites above an Accepted one it does cite, so decisions were re-ordered by kind of evidence (cited in the file first, then cited by a touching commit, then cited by a co-changing file), with Accepted before Proposed in each group. Decision hit@5 fell at every split: 0.857 to 0.429 at 50%, 0.833 to 0.0 at 70%, 0.667 to 0.0 at 85% (MRR 0.714 to 0.357, 0.750 to 0.0, 0.500 to 0.0). Coupling and owner results did not change. Why it fell was not measured. The shipped code keeps the score order above and only adds a `basis` label that names each decision's strongest kind of evidence. Status is shown, not used for ranking: 287 of the 566 ADRs are still Proposed, including the plan-cache design itself.
- One repository, one author mix, ADR-citing commits as ground truth (a commit that cites an ADR is a proxy for "that
  ADR governed the change"). No claim is made about other repositories.
- Not measured: whether an agent that calls these tools writes better code. That needs an LLM-in-the-loop study.
