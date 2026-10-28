#!/bin/bash
# GPU-independent baseline validation + measurement-prep script for 2xB580 inference work.
#
# What it does (no GPU required):
#   1. Validates every strata-swift-iq3_xxs*.json config is well-formed JSON.
#   2. Validates every CLI flag in those configs is recognized by the engine binary
#      (build-sycl-aot/strata --help), if the binary exists.
#   3. Runs tools/check_cpu_ms_parity.py (SYCL <-> CUDA DONE-line plumbing gate).
#   4. Rebuilds the SYCL engine (ninja -C build-sycl-aot strata_engine).
#   5. Prints the measurement protocol to run once a B580 is attached.
#
# When a GPU IS available, run bench-strata.sh / run-swift-iq3_xxs-1gpu.sh /
# run-swift-iq3_xxs.sh against these same configs to measure tok/s.
#
# Usage: ./scripts/measure-baseline.sh [build|validate|parity|protocol|env-check|xpu]
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/strata-src"
CFGS="$SRC/strata-swift-iq3_xxs.json $SRC/strata-swift-iq3_xxs-1gpu-reg.json $SRC/strata-swift-iq3_xxs-2gpu-clean.json"
BIN="$SRC/build-sycl-aot/strata"
MODE="${1:-all}"

fail=0

echo "== measure-baseline: cfg=$CFGS bin=$BIN mode=$MODE =="

# --- 1: validate config JSON ----------------------------------------------
do_validate() {
    for c in $CFGS; do
        echo "  [validate] $c"
        python3 -c "import json,sys; json.load(open('$c',encoding='utf-8'))" || {
            echo "  FAIL: $c is not valid JSON"; fail=1; continue
        }
        # every --flag in args must be a known engine option (if binary exists and runs)
        if [ -x "$BIN" ]; then
            help=$("$BIN" --help 2>/dev/null || true)
            if [ -n "$help" ]; then
                python3 - "$c" "$help" <<'PY'
import json, sys, re
cfg = json.load(open(sys.argv[1], encoding="utf-8"))
help = sys.argv[2]
known = set(re.findall(r"^--([a-z0-9-]+)", help))
bad = []
for a in cfg["args"]:
    if a.startswith("--"):
        name = a[2:].split("=", 1)[0]
        if name not in known:
            bad.append(name)
if bad:
    print("  FAIL: unrecognized flags:", ", ".join(bad)); sys.exit(1)
print("    OK: all flags recognized")
PY
            else
                echo "    SKIP: $BIN exists but cannot run (missing oneAPI libs on this rig)"
            fi
        else
            echo "    SKIP: $BIN not built (run with 'build' or 'all')"
        fi
    done
}

# --- 2: build -------------------------------------------------------------
do_build() {
    echo "  [build] ninja -C $SRC/build-sycl-aot strata_engine"
    ninja -C "$SRC/build-sycl-aot" strata_engine || { echo "  FAIL: build"; fail=1; }
}

# --- 3: parity gate -------------------------------------------------------
do_parity() {
    echo "  [parity] python3 $SRC/tools/check_cpu_ms_parity.py $SRC"
    python3 "$SRC/tools/check_cpu_ms_parity.py" "$SRC" || { echo "  FAIL: parity"; fail=1; }
}

# --- 4: measurement protocol (printed, not run) ---------------------------
do_protocol() {
    cat <<'EOF'
  [protocol] Once an Intel Arc B580 is attached (/dev/dri present), measure tok/s:

    Single-GPU baseline (target ~45+ tok/s decode):
      ./scripts/run-swift-iq3_xxs-1gpu.sh          # strata-swift-iq3_xxs-1gpu-reg config
      ./scripts/bench-strata.sh strata-swift-iq3_xxs-1gpu-reg aot 1gpu 10

    2-GPU layer-split (target ~30+ tok/s decode; was crashing at verify.cpp:1706):
      ./scripts/run-swift-iq3_xxs.sh                # strata-swift-iq3_xxs-2gpu-clean config
      ./scripts/bench-strata.sh strata-swift-iq3_xxs-2gpu-clean aot 2gpu 10

    Measurement discipline (from perf/2xb580-inference branch rules):
      - one change at a time, paired alternating A/B arms
      - n >= 10 per arm, 0 garbled
      - opt-in flags default OFF so recorded baselines stay comparable
      - warm and cold arms never mixed

    Configs now carry basalt-derived values (see perf_review.md):
      --expert-cache 12288   (was auto)   explicit expert budget
      --spec 7               (was 4)      deeper speculation
      --vram-reserve-mib 700 (was 1024/512) smaller VRAM reserve
      --peer-exclusive NOT available in strata CLI; closest equivalent is --peer-device

EOF
}

# --- 5: oneAPI/XPU environment readiness check ---------------------------
do_env_check() {
    echo "  [env-check] oneAPI/XPU readiness"
    local ok=1

    if command -v dpcpp >/dev/null 2>&1 || command -v icpx >/dev/null 2>&1; then
        echo "    OK: SYCL compiler available ($(command -v dpcpp 2>/dev/null || command -v icpx 2>/dev/null))"
    else
        echo "    FAIL: no SYCL compiler (dpcpp/icpx not in PATH)"; ok=0
    fi

    if [ -f /opt/intel/oneapi/setvars.sh ]; then
        echo "    OK: /opt/intel/oneapi/setvars.sh present"
    else
        echo "    FAIL: /opt/intel/oneapi/setvars.sh missing"; ok=0
    fi

    if ls /dev/dri/card* >/dev/null 2>&1 || ls /dev/dri/renderD* >/dev/null 2>&1; then
        echo "    OK: /dev/dri render nodes present: $(ls /dev/dri/ 2>/dev/null | tr '\n' ' ')"
    else
        echo "    WARN: /dev/dri has no render nodes (no GPU detected)"; ok=0
    fi

    if [ -x "$BIN" ]; then
        echo "    OK: engine binary present: $BIN"
    else
        echo "    WARN: engine binary not built (run 'build' or 'all')"; ok=0
    fi

    if [ $ok -eq 1 ]; then echo "    => XPU environment ready"; else echo "    => XPU environment NOT ready (see WARN/FAIL above)"; fi
    return $ok
}

# --- 6: XPU measurement matrix (plan-only, no GPU required) --------------
# Generates a combinatorial measurement plan (CSV + shell commands) for the
# 2xB580 inference matrix.  When a B580 is attached, run the emitted commands
# per the A/B discipline (one change at a time, n>=10 per arm, warm/cold
# arms never mixed).  Nothing here touches the GPU.
do_xpu() {
    local OUT="$ROOT/runs/xpu-measurement-plan.csv"
    local SH="$ROOT/runs/xpu-measurement-plan.sh"
    mkdir -p "$ROOT/runs"

    : > "$OUT"
    : > "$SH"

    cat >> "$SH" <<'SHEOF'
#!/bin/sh
# Auto-generated XPU measurement plan.  Run one line per arm when a B580 is attached.
# Discipline: one change at a time, paired alternating A/B arms, n>=10 per arm,
# warm and cold arms never mixed, 0 garbled.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/strata-src/build-sycl-aot/strata"
PORT=8081
SHEOF

    # Matrix dimensions (one change at a time around the basalt baseline arm).
    local MODES="1gpu 2gpu"
    local BATCHES="1 4 8 16"
    local UBATCHS="1 2 4"
    local KVS="int8 q4_0"
    local CACHES="4096 8192 12288 16384"
    local SPECS="3 5 7 9"
    local CTXS="32768 65536 131072"

    # Baselalt baseline arm: batch=1 ubatch=1 kv=int8 cache=12288 spec=7 ctx=131072.
    echo "mode,batch,ubatch,kv,expert_cache,spec,max_context,config,port,note" >> "$OUT"

    local run_id=0
    local port=8081
    for mode in $MODES; do
        case "$mode" in
            1gpu) CFG="strata-swift-iq3_xxs-1gpu-reg" ;;
            2gpu) CFG="strata-swift-iq3_xxs-2gpu-clean" ;;
        esac
        for batch in $BATCHES; do
            for ubatch in $UBATCHS; do
                for kv in $KVS; do
                    for cache in $CACHES; do
                        for spec in $SPECS; do
                            for ctx in $CTXS; do
                                run_id=$((run_id+1))
                                # Baseline arm = all basalt defaults.
                                note="baseline"
                                if [ "$batch" != "1" ] || [ "$ubatch" != "1" ] || [ "$kv" != "int8" ] \
                                   || [ "$cache" != "12288" ] || [ "$spec" != "7" ] || [ "$ctx" != "131072" ]; then
                                    note="variation"
                                fi
                                echo "$mode,$batch,$ubatch,$kv,$cache,$spec,$ctx,$CFG,$port,$note" >> "$OUT"

                                cat >> "$SH" <<CMEOF
# run $run_id: $mode batch=$batch ubatch=$ubatch kv=$kv cache=$cache spec=$spec ctx=$ctx ($note)
#   ./scripts/bench-strata.sh $CFG aot ${mode}-r${run_id} 10
#     (edit $CFG.json: --batch $batch --ubatch $ubatch --kv $kv --expert-cache $cache --spec $spec --max-context $ctx)
CMEOF
                            done
                        done
                    done
                done
            done
        done
    done

    chmod +x "$SH"
    local total=$run_id
    local baseline=0; local var=0
    baseline=$(grep -c ",baseline$" "$OUT" 2>/dev/null || echo 0)
    var=$((total - baseline))

    echo "  [xpu] measurement plan written:"
    echo "    CSV: $OUT  ($total runs: $baseline baseline arms, $var variation arms)"
    echo "    SH:  $SH  (bench-strata commands, one per run)"
    echo ""
    echo "  Matrix dimensions:"
    echo "    modes:      $MODES"
    echo "    batches:    $BATCHES"
    echo "    ubatches:   $UBATCHS"
    echo "    kv types:   $KVS"
    echo "    expert-cache: $CACHES"
    echo "    spec:       $SPECS"
    echo "    max-context: $CTXS"
    echo ""
    echo "  When a B580 is attached, run arms in A/B pairs around the baseline arm,"
    echo "  n>=10 per arm, warm and cold arms never mixed."
}

case "$MODE" in
    validate) do_validate ;;
    build)    do_build ;;
    parity)   do_parity ;;
    protocol) do_protocol ;;
    env-check) do_env_check ;;
    xpu)      do_xpu ;;
    all)
        do_validate
        do_build
        do_parity
        do_protocol
        ;;
    *) echo "unknown mode: $MODE"; exit 2 ;;
esac

exit $fail
