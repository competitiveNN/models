#!/bin/bash
# Start the Strata SYCL server on this rig, and wait until it is really loaded.
#
# Usage: scripts/run-strata.sh <name> [KEY=VALUE ...] [-- <engine args>]
#   <name>        the config's base name without .json (it becomes runs/<name>.log too)
#   KEY=VALUE     env overrides applied to the config (e.g. STRATA_DECODE_TIMING=1)
#   -- <args>     extra engine args appended (e.g. --pipeline-windows 2)
#
# Environment:
#   BASE=<cfg>    the template config the <name> config is derived from when it does not
#                 exist yet (default: strata-swift-iq3_xxs-2gpu-clean, the shipped one)
#   PORT=<n>      the port (default: the template's, or 8081)
#
# WHY IT DERIVES THE CONFIG: a run script that points at a config somebody renamed or
# deleted is silently broken - the engine starts and serves nothing.  Here the config is
# regenerated from the shipped template whenever it is missing, so the run scripts cannot
# go stale.
#
# WHY IT WAITS: "the container started" is not "the model is loaded".  The first start
# reads tens of GB of experts, so the health check has to see `"loaded": true` before
# any measurement is taken - a battery that starts early measures the load, not the model.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/strata-src"
RUNS="$ROOT/runs"
DOCKER="${DOCKER:-/var/home/fra/bin/docker}"
GGUF_DIR="${GGUF_DIR:-/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF}"
IMAGE="${IMAGE:-strata-sycl-dev}"
mkdir -p "$RUNS"

NAME="${1:?usage: run-strata.sh <name> [KEY=VALUE ...] [-- <engine args>]}"; shift
BASE="${BASE:-strata-swift-iq3_xxs-2gpu-clean}"
ENVS=(); ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --) shift; ARGS=("$@"); break ;;
    *=*) ENVS+=("$1"); shift ;;
    *) echo "bad argument '$1' (expected KEY=VALUE or --)"; exit 2 ;;
  esac
done

TEMPLATE="$SRC/$BASE.json"
if [ ! -f "$TEMPLATE" ]; then
  echo "run-strata: the template config $BASE.json is missing" >&2; exit 2
fi
CFG="$SRC/$NAME.json"

# The config, derived from the template if it is not there yet.  The engine's log goes to
# runs/<name>.log (the container sees the repo at /work), and the engine name follows the
# config so the health endpoint says which arm is serving.
python3 - "$TEMPLATE" "$CFG" "$NAME" "$RUNS" "${#ENVS[@]}" "${ENVS[@]}" "${#ARGS[@]}" "${ARGS[@]}" << 'PY'
import json, os, sys
tmpl, out, name, runs = sys.argv[1:5]
c = json.load(open(tmpl))
i = 5
n_envs = int(sys.argv[i]); i += 1
for _ in range(n_envs):
    k, _, v = sys.argv[i].partition("="); i += 1
    c.setdefault("env", {})[k] = v   # command-line env overrides base config
n_args = int(sys.argv[i]); i += 1
args = sys.argv[i:i+n_args]
# Merge args: command-line args replace base config args for the same flag.
# Args come as flag value pairs (e.g. --expert-cache 1). Build a dict from base
# args, then overwrite with command-line args.
def arg_pairs(arglist):
    pairs = {}
    i = 0
    while i < len(arglist):
        flag = arglist[i]
        if flag.startswith("--") and i + 1 < len(arglist) and not arglist[i + 1].startswith("--"):
            pairs[flag] = arglist[i + 1]
            i += 2
        else:
            pairs[flag] = None
            i += 1
    return pairs

base_pairs = arg_pairs(c.get("args", []))
cli_pairs = arg_pairs(args)
merged = {}
for k, v in base_pairs.items():
    merged[k] = v
for k, v in cli_pairs.items():
    merged[k] = v   # CLI overrides base
# Rebuild args list, preserving base order but with CLI values
new_args = []
seen = set()
for k, v in base_pairs.items():
    if k in cli_pairs:
        new_args.append(k)
        if cli_pairs[k] is not None:
            new_args.append(cli_pairs[k])
        seen.add(k)
    else:
        new_args.append(k)
        if v is not None:
            new_args.append(v)
for k, v in cli_pairs.items():
    if k not in seen:
        new_args.append(k)
        if v is not None:
            new_args.append(v)
c["args"] = new_args
c["model_name"] = name
c["log"] = "/work/runs/%s.log" % name
json.dump(c, open(out, "w"), indent=2)
print("run-strata: %s (from %s)%s" % (os.path.basename(out), os.path.basename(tmpl),
                                      (" +" + ",".join(args)) if args else ""))
PY

PORT="${PORT:-$(python3 -c "import json;print(json.load(open('$CFG')).get('port',8081))")}"
echo "run-strata: $NAME on port $PORT"

"$DOCKER" rm -f strata-server >/dev/null 2>&1
sleep 2
"$DOCKER" run -d --privileged --device /dev/dri --device /dev/dri/card0 --device /dev/dri/card1 --device /dev/dri/renderD128 --device /dev/dri/renderD129 --security-opt label=disable \
--name strata-server --replace \
--network host \
-v "$ROOT:/work:Z" \
-v "$GGUF_DIR:/gguf:ro" \
-e LD_LIBRARY_PATH=/opt/intel/oneapi/compiler/2026.2/lib:/opt/intel/oneapi/mkl/2026.2/lib:/opt/intel/oneapi/redist/lib \
-e ZE_FLAT_DEVICE_MEMORY=1 \
-e STRATA_VERIFY_DEVICE_PLAN=0 \
-e STRATA_VERIFY_NO_HOST=0 \
-e STRATA_WINDOW_SYNC=1 \
-e STRATA_STAGE_TRIM=1 \
-e STRATA_PREFILL_MMQ=0 \
-e STRATA_DECODE_TIMING=1 \
-e STRATA_SPLIT_HEADROOM=0 \
-e STRATA_VERIFY_PIPE=0 \
--entrypoint /bin/sh \
"$IMAGE" \
-c "echo '[CONTAINER] Starting server...'; echo '[CONTAINER] ENV:'; env; cd /work/strata-src && python3 sycl/serve/server_intel.py --engine strata --config /work/strata-src/$NAME.json --port $PORT 2>&1 | tee /work/runs/$NAME-container.log" \
> "$RUNS/$NAME-launch.log" 2>&1

for i in $(seq 1 150); do
  if curl -s -m 2 "http://127.0.0.1:$PORT/health" 2>/dev/null | /usr/bin/grep -q '"loaded": true'; then
    echo "run-strata: ready after ${i}x2s: $NAME on port $PORT"
    curl -s -m 2 "http://127.0.0.1:$PORT/health"; echo
    exit 0
  fi
  sleep 2
done
echo "run-strata: NOT READY after 300s: $NAME on port $PORT" >&2
tail -30 "$RUNS/$NAME.log" 2>/dev/null
exit 1
