#!/bin/bash
# Reproduce a bench config N times against the current binary, with provenance.
#
# Why this exists: earlier status docs quoted tok/s from log files whose engine,
# binary and config could not be tied to the current build, and from the single
# best run rather than a repeatable median. This driver fixes both:
#   - every run records git commit, binary hash and config hash, so a number can
#     be traced to the artefact that produced it;
#   - it reports the MEDIAN OF RUNS, not the best run.
#
# Usage: scripts/repro-bench.sh <config-name> [runs] [tag]
#   config-name  e.g. strata-swift-iq3_xxs-2gpu-miss108 (a template in strata-src/)
#   runs         how many independent cold starts (default 3)
#   tag          label for the output dir (default derived from config)
#
# Output: bench/runs/<tag>-run<N>.json per run + bench/runs/<tag>-aggregate.json
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CFG_NAME="${1:?usage: repro-bench.sh <config-name> [runs] [tag]}"
NRUNS="${2:-3}"
TAG="${3:-$CFG_NAME}"
OUTDIR="$ROOT/bench/runs"
cd "$ROOT"
mkdir -p "$OUTDIR"

# --- provenance, computed once, identical for every run in this batch ---
GIT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
GIT_DIRTY="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
BIN="$ROOT/strata-src/build-sycl-aot/strata"
BIN_SHA="$(sha256sum "$BIN" 2>/dev/null | cut -d' ' -f1 || echo missing)"
CFG="$ROOT/strata-src/$CFG_NAME.json"
CFG_SHA="$(sha256sum "$CFG" 2>/dev/null | cut -d' ' -f1 || echo missing)"

echo "== repro-bench $TAG"
echo "   config      $CFG_NAME (sha ${CFG_SHA:0:12})"
echo "   git         $GIT_COMMIT (dirty files: $GIT_DIRTY)"
echo "   binary      ${BIN_SHA:0:12} ($(du -h "$BIN" 2>/dev/null | cut -f1))"
echo "   runs        $NRUNS"

PORT="$(python3 -c "import json;print(json.load(open('$CFG')).get('port',8081))" 2>/dev/null || echo 8081)"
MODEL="$(python3 -c "import json;print(json.load(open('$CFG'))['model_name'])" 2>/dev/null || echo missing)"

status=0
for i in $(seq 1 "$NRUNS"); do
    name="repro-${TAG}-run${i}"
    echo
    echo "---- run $i/$NRUNS: $name ----"
    # Fresh cold start each time: the engine re-reads the expert tier, which is
    # what we actually want to measure the steady state after.
    podman rm -f strata-server >/dev/null 2>&1

    if ! BASE="$CFG_NAME" PORT="$PORT" "$ROOT/scripts/run-strata.sh" "$name"; then
        echo "   RUN $i FAILED: engine did not reach ready" >&2
        echo "   see runs/$name.log" >&2
        status=1
        continue
    fi

    # Validate the battery against the real engine (not a stub), and record it.
    python3 "$ROOT/scripts/bench-battery.py" \
        --base-url "http://127.0.0.1:$PORT" \
        --model "$MODEL" \
        --out "$OUTDIR/${name}.json" \
        --tag "$TAG-run$i" \
        --ready-timeout 60
    rc=$?
    echo "   battery exit=$rc"
    [ $rc -ne 0 ] && status=$rc

    podman rm -f strata-server >/dev/null 2>&1
    sleep 5
done

# --- aggregate: median of runs, with the provenance attached ---
python3 - "$OUTDIR" "$TAG" "$GIT_COMMIT" "$GIT_DIRTY" "$BIN_SHA" "$CFG_SHA" "$CFG_NAME" <<'PY'
import glob, json, os, statistics, sys
outdir, tag, commit, dirty, bin_sha, cfg_sha, cfg_name = sys.argv[1:8]
runs = []
for p in sorted(glob.glob(os.path.join(outdir, f"repro-{tag}-run*.json"))):
    try:
        runs.append(json.load(open(p)))
    except Exception as e:
        print(f"  skip {p}: {e}")

def med(key):
    vals = [r["summary"][key] for r in runs if key in r.get("summary", {})]
    return round(statistics.median(vals), 2) if vals else None

agg = {
    "tag": tag,
    "config": cfg_name,
    "provenance": {
        "git_commit": commit,
        "git_dirty_files": int(dirty),
        "binary_sha256": bin_sha,
        "config_sha256": cfg_sha,
    },
    "runs_completed": len(runs),
    "per_run": [
        {"tag": r.get("tag"), "summary": r.get("summary")} for r in runs
    ],
    "median_of_runs": {
        "decode_e2e_tok_s_median": med("decode_e2e_tok_s_median"),
        "prefill_tok_s_median": med("prefill_tok_s_median"),
    },
    "note": "median_of_runs is the median across independent cold starts of the "
            "per-run median; it is the number to quote, not the best single run.",
}
out = os.path.join(outdir, f"{tag}-aggregate.json")
json.dump(agg, open(out, "w"), indent=2)
open(out, "a").write("\n")
print()
print("== aggregate ->", out)
print(json.dumps(agg["median_of_runs"], indent=2))
print(f"   runs completed: {len(runs)}")
PY

exit $status
