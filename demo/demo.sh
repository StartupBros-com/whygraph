#!/usr/bin/env bash
# Reproducible demo: index the open-source Relate repository (Apache-2.0, 483 commits, 566 ADRs)
# at a pinned revision and ask the three questions an agent asks before editing a file.
# Usage: demo/demo.sh [workdir]      (needs git, python >= 3.9; ~10 s, < 200 MB RAM)
set -euo pipefail
REV=2346dec59924eb730a5041d15bcfbcbf06d5de79
WORK="${1:-$(mktemp -d)}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
python3 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install -q "$HERE"
[ -d "$WORK/relate" ] || git clone -q https://github.com/relatedb/relate.git "$WORK/relate"
git -C "$WORK/relate" checkout -q "$REV"
WG="$WORK/venv/bin/whygraph --store $WORK/relate.rl --text"
rm -f "$WORK/relate.rl"
"$WORK/venv/bin/whygraph" --store "$WORK/relate.rl" index --repo "$WORK/relate" --rev "$REV" --anonymize
echo; echo '$ whygraph why relate/relate/src/plan_cache.rs'; $WG why relate/relate/src/plan_cache.rs --limit 4
echo; echo '$ whygraph search "plan cache invalidation"';   $WG search "plan cache invalidation" --limit 4
echo; echo '$ whygraph decision 345';                        $WG decision 345
echo; echo "store: $WORK/relate.rl   (point an MCP client at: whygraph --store $WORK/relate.rl mcp)"
