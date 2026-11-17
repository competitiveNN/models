#!/bin/bash
# Sweep --prefill auto:<N> chunk sizes and record prefill throughput for each.
#
# Why: prefill sits at 1247 tok/s peak against a 1400 tok/s target, and the whole
# conclusion rests on 3 qualifying samples from one config. docs/prefill-ceiling.md
# shows PCIe is not the binding constraint, so the remaining question is how chunk
# size moves throughput. This measures it instead of guessing.
#
# Usage: scripts/prefill-sweep.sh [chunk-sizes...]   (default: 1024 2048 4096 8192)
# Output: bench/runs/prefill-sweep-<N>.json per chunk + prefill-sweep-aggregate.json
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUTDIR="$ROOT/bench/runs"
mkdir -p "$OUTDIR"
BASE_CFG="${BASE_CFG:-strata-swift-iq3_xxs-2gpu-miss108}"
PORT="${PORT:-8081}"
CHUNKS=("$@")
[ ${#CHUNKS[@]} -eq 0 ] && CHUNKS=(1024 2048 4096 8192)

GIT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
BIN_SHA="$(sha256sum "$ROOT/strata-src/build-sycl-aot/strata" 2>/dev/null | cut -d' ' -f1 || echo missing)"
echo "== prefill sweep over ${CHUNKS[*]} (git $GIT_COMMIT, bin ${BIN_SHA:0:12})"

for n in "${CHUNKS[@]}"; do
    name="prefill-chunk${n}"
    echo
    echo "---- chunk $n ----"
    podman rm -f strata-server >/dev/null 2>&1
    if ! BASE="$BASE_CFG" PORT="$PORT" "$ROOT/scripts/run-strata.sh" "$name" \
            -- --prefill "auto:$n"; then
        echo "   chunk $n: engine did not reach ready" >&2
        continue
    fi
    python3 "$ROOT/scripts/bench-battery.py" \
        --base-url "http://127.0.0.1:$PORT" \
        --out "$OUTDIR/prefill-sweep-${n}.json" \
        --tag "prefill-chunk${n}" \
        --ready-timeout 60
    echo "   battery exit=$?"
    podman rm -f strata-server >/dev/null 2>&1
    sleep 5
done

python3 - "$OUTDIR" "$GIT_COMMIT" "$BIN_SHA" <<'PY'
import glob, json, os, sys
outdir, commit, bin_sha = sys.argv[1:4]
rows = []
for p in sorted(glob.glob(os.path.join(outdir, "prefill-sweep-*.json"))):
    if p.endswith("aggregate.json"):
        continue
    try:
        d = json.load(open(p))
    except Exception:
        continue
    pf = [c for c in d.get("cases", []) if c["name"].startswith("prefill")]
    if not pf:
        continue
    c = pf[0]
    chunk = int(os.path.basename(p).split("-")[-1].split(".")[0])
    rows.append({
        "prefill_chunk": chunk,
        "prompt_tokens": c["prompt_tokens"],
        "wall_s": c["wall_s"],
        "prefill_tok_s": round(c["prompt_tokens"] / c["wall_s"], 1),
    })
rows.sort(key=lambda r: r["prefill_chunk"])
agg = {
    "git_commit": commit,
    "binary_sha256": bin_sha,
    "target_prefill_tok_s": 1400.0,
    "samples": rows,
    "best": max(rows, key=lambda r: r["prefill_tok_s"]) if rows else None,
}
out = os.path.join(outdir, "prefill-sweep-aggregate.json")
json.dump(agg, open(out, "w"), indent=2)
open(out, "a").write("\n")
print()
print("== prefill sweep ->", out)
for r in rows:
    print(f"   chunk {r['prefill_chunk']:5}: {r['prompt_tokens']:5} tok in "
          f"{r['wall_s']:6.2f}s = {r['prefill_tok_s']:7.1f} tok/s")
PY
