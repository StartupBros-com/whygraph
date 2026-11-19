### split 50%: index 241 commits, replay 242 later commits
(rev `2346dec599`, cutoff commit `ec7c56f37c`, graph 532 decisions / 3786 files / 241 commits)

**Coupling** (1313 file queries; graph returned any answer for 100%); mean and 95% bootstrap interval

| method | n | hit@10 | recall@10 | mrr |
|---|---|---|---|---|
| graph | 1313 | 0.482 [0.46, 0.51] | 0.176 [0.16, 0.19] | 0.291 [0.27, 0.31] |
| graph_count_only | 1313 | 0.482 [0.46, 0.51] | 0.176 [0.16, 0.19] | 0.287 [0.27, 0.31] |
| graph_then_samedir | 1313 | 0.483 [0.46, 0.51] | 0.176 [0.16, 0.19] | 0.291 [0.27, 0.31] |
| graph+name+samedir_rrf | 1313 | 0.695 [0.67, 0.72] | 0.249 [0.23, 0.26] | 0.445 [0.42, 0.47] |
| same_dir | 1313 | 0.573 [0.55, 0.60] | 0.189 [0.17, 0.20] | 0.405 [0.38, 0.43] |
| name_overlap | 1313 | 0.663 [0.64, 0.69] | 0.215 [0.20, 0.23] | 0.360 [0.34, 0.38] |
| popular | 1313 | 0.243 [0.22, 0.27] | 0.040 [0.04, 0.04] | 0.085 [0.07, 0.10] |

**Owner** (1750 file queries)

| method | n | top1 | top3 |
|---|---|---|---|
| graph | 1750 | 0.576 [0.55, 0.60] | 0.686 [0.67, 0.71] |
| last_author | 1750 | 0.454 [0.43, 0.48] | 0.454 [0.43, 0.48] |
| last3_distinct_authors | 1750 | 0.454 [0.43, 0.48] | 0.686 [0.67, 0.71] |
| graph_recent3 | 1750 | 0.454 [0.43, 0.48] | 0.686 [0.67, 0.71] |
| top_committer_overall | 1750 | 0.774 [0.76, 0.79] | 0.774 [0.76, 0.79] |

Owner, excluding commits by the single most active author (395 queries)

| method | n | top1 | top3 |
|---|---|---|---|
| graph | 395 | 0.471 [0.42, 0.52] | 0.633 [0.58, 0.68] |
| last_author | 395 | 0.504 [0.46, 0.55] | 0.504 [0.46, 0.55] |
| last3_distinct_authors | 395 | 0.504 [0.46, 0.55] | 0.641 [0.59, 0.69] |
| graph_recent3 | 395 | 0.504 [0.46, 0.55] | 0.641 [0.59, 0.69] |
| top_committer_overall | 395 | 0.000 [0.00, 0.00] | 0.000 [0.00, 0.00] |

**Decision** (7 future commits that cite an ADR known at the cutoff)

| method | n | hit@5 | recall@5 | mrr |
|---|---|---|---|---|
| graph | 7 | 0.857 [0.57, 1.00] | 0.857 [0.57, 1.00] | 0.714 [0.43, 0.93] |
| fulltext_on_subject | 7 | 0.857 [0.57, 1.00] | 0.857 [0.57, 1.00] | 0.557 [0.27, 0.86] |
| graph+fulltext_rrf | 7 | 0.857 [0.57, 1.00] | 0.857 [0.57, 1.00] | 0.690 [0.41, 0.93] |
| grep_adr_text | 7 | 0.000 [0.00, 0.00] | 0.000 [0.00, 0.00] | 0.000 [0.00, 0.00] |
| most_cited_overall | 7 | 0.000 [0.00, 0.00] | 0.000 [0.00, 0.00] | 0.000 [0.00, 0.00] |

### split 70%: index 338 commits, replay 145 later commits
(rev `2346dec599`, cutoff commit `d47c8d2de8`, graph 543 decisions / 3923 files / 338 commits)

**Coupling** (818 file queries; graph returned any answer for 100%); mean and 95% bootstrap interval

| method | n | hit@10 | recall@10 | mrr |
|---|---|---|---|---|
| graph | 818 | 0.556 [0.52, 0.59] | 0.172 [0.16, 0.19] | 0.335 [0.31, 0.36] |
| graph_count_only | 818 | 0.556 [0.52, 0.59] | 0.172 [0.16, 0.19] | 0.326 [0.30, 0.35] |
| graph_then_samedir | 818 | 0.557 [0.52, 0.59] | 0.174 [0.16, 0.19] | 0.336 [0.31, 0.36] |
| graph+name+samedir_rrf | 818 | 0.694 [0.66, 0.73] | 0.211 [0.20, 0.23] | 0.435 [0.41, 0.46] |
| same_dir | 818 | 0.551 [0.52, 0.59] | 0.150 [0.14, 0.16] | 0.386 [0.36, 0.42] |
| name_overlap | 818 | 0.645 [0.61, 0.68] | 0.185 [0.17, 0.20] | 0.362 [0.33, 0.39] |
| popular | 818 | 0.298 [0.27, 0.33] | 0.046 [0.04, 0.05] | 0.098 [0.08, 0.12] |

**Owner** (1189 file queries)

| method | n | top1 | top3 |
|---|---|---|---|
| graph | 1189 | 0.637 [0.61, 0.66] | 0.787 [0.76, 0.81] |
| last_author | 1189 | 0.588 [0.56, 0.62] | 0.588 [0.56, 0.62] |
| last3_distinct_authors | 1189 | 0.588 [0.56, 0.62] | 0.786 [0.76, 0.81] |
| graph_recent3 | 1189 | 0.588 [0.56, 0.62] | 0.786 [0.76, 0.81] |
| top_committer_overall | 1189 | 0.732 [0.71, 0.76] | 0.732 [0.71, 0.76] |

Owner, excluding commits by the single most active author (319 queries)

| method | n | top1 | top3 |
|---|---|---|---|
| graph | 319 | 0.586 [0.53, 0.64] | 0.853 [0.81, 0.89] |
| last_author | 319 | 0.592 [0.54, 0.65] | 0.592 [0.54, 0.65] |
| last3_distinct_authors | 319 | 0.592 [0.54, 0.65] | 0.856 [0.81, 0.89] |
| graph_recent3 | 319 | 0.592 [0.54, 0.65] | 0.856 [0.81, 0.89] |
| top_committer_overall | 319 | 0.000 [0.00, 0.00] | 0.000 [0.00, 0.00] |

**Decision** (12 future commits that cite an ADR known at the cutoff)

| method | n | hit@5 | recall@5 | mrr |
|---|---|---|---|---|
| graph | 12 | 0.833 [0.58, 1.00] | 0.833 [0.58, 1.00] | 0.750 [0.50, 0.96] |
| fulltext_on_subject | 12 | 0.333 [0.08, 0.58] | 0.333 [0.08, 0.58] | 0.211 [0.03, 0.44] |
| graph+fulltext_rrf | 12 | 0.833 [0.58, 1.00] | 0.833 [0.58, 1.00] | 0.451 [0.28, 0.62] |
| grep_adr_text | 12 | 0.000 [0.00, 0.00] | 0.000 [0.00, 0.00] | 0.000 [0.00, 0.00] |
| most_cited_overall | 12 | 0.000 [0.00, 0.00] | 0.000 [0.00, 0.00] | 0.000 [0.00, 0.00] |

### split 85%: index 410 commits, replay 73 later commits
(rev `2346dec599`, cutoff commit `9885d087f9`, graph 554 decisions / 4075 files / 410 commits)

**Coupling** (401 file queries; graph returned any answer for 100%); mean and 95% bootstrap interval

| method | n | hit@10 | recall@10 | mrr |
|---|---|---|---|---|
| graph | 401 | 0.581 [0.53, 0.63] | 0.164 [0.14, 0.18] | 0.325 [0.29, 0.36] |
| graph_count_only | 401 | 0.581 [0.53, 0.63] | 0.164 [0.14, 0.18] | 0.326 [0.29, 0.36] |
| graph_then_samedir | 401 | 0.584 [0.53, 0.63] | 0.167 [0.15, 0.19] | 0.327 [0.29, 0.37] |
| graph+name+samedir_rrf | 401 | 0.736 [0.69, 0.78] | 0.199 [0.18, 0.22] | 0.438 [0.40, 0.48] |
| same_dir | 401 | 0.576 [0.53, 0.62] | 0.150 [0.13, 0.17] | 0.391 [0.35, 0.43] |
| name_overlap | 401 | 0.653 [0.61, 0.70] | 0.162 [0.14, 0.18] | 0.395 [0.36, 0.44] |
| popular | 401 | 0.379 [0.33, 0.43] | 0.053 [0.04, 0.06] | 0.120 [0.10, 0.14] |

**Owner** (633 file queries)

| method | n | top1 | top3 |
|---|---|---|---|
| graph | 633 | 0.717 [0.68, 0.75] | 0.850 [0.82, 0.88] |
| last_author | 633 | 0.664 [0.63, 0.70] | 0.664 [0.63, 0.70] |
| last3_distinct_authors | 633 | 0.664 [0.63, 0.70] | 0.852 [0.82, 0.88] |
| graph_recent3 | 633 | 0.664 [0.63, 0.70] | 0.852 [0.82, 0.88] |
| top_committer_overall | 633 | 0.659 [0.62, 0.69] | 0.659 [0.62, 0.69] |

Owner, excluding commits by the single most active author (216 queries)

| method | n | top1 | top3 |
|---|---|---|---|
| graph | 216 | 0.593 [0.52, 0.66] | 0.856 [0.81, 0.90] |
| last_author | 216 | 0.417 [0.35, 0.48] | 0.417 [0.35, 0.48] |
| last3_distinct_authors | 216 | 0.417 [0.35, 0.48] | 0.866 [0.82, 0.91] |
| graph_recent3 | 216 | 0.417 [0.35, 0.48] | 0.866 [0.82, 0.91] |
| top_committer_overall | 216 | 0.000 [0.00, 0.00] | 0.000 [0.00, 0.00] |

**Decision** (3 future commits that cite an ADR known at the cutoff)

| method | n | hit@5 | recall@5 | mrr |
|---|---|---|---|---|
| graph | 3 | 0.667 [0.00, 1.00] | 0.667 [0.00, 1.00] | 0.500 [0.00, 1.00] |
| fulltext_on_subject | 3 | 1.000 [1.00, 1.00] | 1.000 [1.00, 1.00] | 0.511 [0.20, 1.00] |
| graph+fulltext_rrf | 3 | 0.667 [0.00, 1.00] | 0.667 [0.00, 1.00] | 0.667 [0.00, 1.00] |
| grep_adr_text | 3 | 0.000 [0.00, 0.00] | 0.000 [0.00, 0.00] | 0.000 [0.00, 0.00] |
| most_cited_overall | 3 | 0.000 [0.00, 0.00] | 0.000 [0.00, 0.00] | 0.000 [0.00, 0.00] |
