#!/bin/bash
# docker-entrypoint.sh -- dispatches to bin/grimoire-server or bin/grimoire,
# and ALWAYS wraps the real work in `timeout --signal=TERM --kill-after=60`
# so a `docker stop` gets a graceful TERM with time to drain GPU work
# before anything resorts to SIGKILL.  A B70 that gets SIGKILLed mid-
# submission can fall off the PCI bus and need a power cycle -- this is
# not a hypothetical, it is this project's most repeated failure mode.
#
# That protects against a SLOW stop.  It does NOT replace --init: without
# it, THIS script is PID 1, gets the kernel's default (do-nothing) signal
# disposition for most signals, and never reaps the binary's children --
# so `docker stop` still has no clean way to ask the workload to finish.
# Pass --init on `docker run` every time.  The warning below fires if you
# forget.
set -u

if [ "$$" -eq 1 ]; then
    echo "WARNING: no --init on this container (docker-entrypoint.sh is PID 1)." >&2
    echo "         docker stop can only SIGKILL from here -- GPU work in flight" >&2
    echo "         may wedge the card. Re-run with 'docker run --init ...'." >&2
fi

TIMEOUT_SECS="${GRIMOIRE_TIMEOUT_SECS:-0}"   # 0 = no limit (a server should not have one)
run() {
    if [ "$TIMEOUT_SECS" -gt 0 ]; then
        exec timeout --signal=TERM --kill-after=60 "$TIMEOUT_SECS" "$@"
    else
        exec "$@"
    fi
}

# ---------------------------------------------------------------------
#  _multi_launch <binary> <args...>
#
#  One process per GPU, pipeline-parallel.  Each rank sees ONLY the card
#  it is assigned (one render node per process -- the B70 cookbook found
#  that two-card workers which can each see both cards use ~11 GB of host
#  memory per process and crash a dual-B70 host).
#
#  Rank 0 is the front end; later ranks connect to it.  Start the back
#  ranks first so they are listening when rank 0 connects.  The trap hands
#  TERM on and keeps waiting so GPU work can drain before SIGKILL.
# ---------------------------------------------------------------------
_multi_launch() {
    local bin="$1"; shift
    local mode=PP
    case "${1:-}" in PP|TP) mode=$1; shift ;; esac
    local n="${GRIMOIRE_MULTI_GPUS:-2}"

    if [ "$mode" = TP ]; then
        export GRIMOIRE_TP_WORLD_SIZE="$n"
        export GRIMOIRE_TP_SOCKET="${GRIMOIRE_TP_SOCKET:-/tmp/grimoire-tp-serve.sock}"
        local sock="$GRIMOIRE_TP_SOCKET"
    else
        export GRIMOIRE_PP_WORLD_SIZE="$n"
        export GRIMOIRE_PP_SOCKET="${GRIMOIRE_PP_SOCKET:-/tmp/grimoire-pp-serve.sock}"
        local sock="$GRIMOIRE_PP_SOCKET"
    fi
    rm -f "${sock}"* 2>/dev/null || true

    # One card per process: rank r sees ONLY the r-th device of
    # GRIMOIRE_MULTI_DEVICES (default: the container's ZE_AFFINITY_MASK,
    # e.g. 0,1).  GRIMOIRE_DEVICES then maps every rank to index 0, the
    # one card its process sees.
    IFS=',' read -r -a devs <<< "${GRIMOIRE_MULTI_DEVICES:-${ZE_AFFINITY_MASK:-}}"
    if [ "${#devs[@]}" -lt "$n" ]; then
        echo "multi: $n ranks need $n devices in GRIMOIRE_MULTI_DEVICES or ZE_AFFINITY_MASK" \
             "(got '${GRIMOIRE_MULTI_DEVICES:-${ZE_AFFINITY_MASK:-}}')" >&2
        exit 2
    fi
    local zeros; zeros=$(printf '0,%.0s' $(seq 1 "$n")); zeros=${zeros%,}
    local pids=()

    for ((r = n - 1; r >= 0; --r)); do
        env "GRIMOIRE_${mode}_RANK=$r" "ZE_AFFINITY_MASK=${devs[r]}" "GRIMOIRE_DEVICES=$zeros" \
            "$bin" "$@" &
        pids[r]=$!
    done

    trap 'kill -TERM "${pids[@]}" 2>/dev/null' TERM INT
    reap() { local st=0; wait "$1"; st=$?
            while kill -0 "$1" 2>/dev/null; do wait "$1"; st=$?; done; return "$st"; }
    local st; reap "${pids[0]}"; st=$?
    kill -TERM "${pids[@]}" 2>/dev/null || true
    for ((r = 1; r < n; ++r)); do reap "${pids[r]}" || true; done
    exit "$st"
}

case "${1:-server}" in
    server)
        shift
        run /grimoire/bin/grimoire-server "$@"
        ;;
    generate|cli)
        shift
        run /grimoire/bin/grimoire "$@"
        ;;
    multi)
        shift
        _multi_launch /grimoire/bin/grimoire-server "$@"
        ;;
    generate-pp)
        shift
        _multi_launch /grimoire/bin/grimoire "$@"
        ;;
    /grimoire/bin/*|bin/*)
        run "$@"
        ;;
    *)
        echo "usage: docker run ... <image> {server|multi|generate-pp|generate} [args...]" >&2
        echo "  server      -> bin/grimoire-server (OpenAI-compatible HTTP), e.g.:" >&2
        echo "                 server --model /models/K2-Horizon-MoVA-36B-A4B --proj mxfp4 --ctx 8192 --port 8000" >&2
        echo "  multi       -> one server rank per GPU (pipeline parallel; 'multi TP' = tensor parallel), e.g.:" >&2
        echo "                 multi --model /models/Ornith-1.5-35B-A3B-FP8 --proj fp8 --ctx 32000 --port 8000" >&2
        echo "  generate-pp -> bin/grimoire CLI across two cards, e.g.:" >&2
        echo "                 generate-pp -m /models/Qwen3.8-27B-GPTQ-Int4-sym-G128-MTP-BF16 --proj int4 -p \"Hello\" -n 64" >&2
        echo "  generate    -> bin/grimoire (one-shot CLI), e.g.:" >&2
        echo "                 generate -m /models/K2-Horizon-MoVA-36B-A4B --proj mxfp4 --ctx 8192 -p \"...\" -n 256" >&2
        exit 2
        ;;
esac