#!/bin/bash
# Coherence + throughput battery for TP2 experiments.
# Usage: PORT=8081 ./tp-battery.sh <tag> <nreq> [warm]
#   warm=1  one discarded request first, so the measured arm starts with the VRAM expert cache and
#           the GGUF's expert pages resident (req 1 otherwise pays the cold-start premium for the rest)
# Environment:
#   STRATA_REGIME_MIN_MBPS  refuse the arm if the GGUF expert pages start below this rate
#                           (0 = no gate).  A cold page cache measures a different engine.
#   WARM_REQ1_CPU_MAX       with warm=1, refuse the arm if req 1's CPU share exceeds this
#                           percent (0 = no gate).  CI has no GPU, so the warm req-1 CPU-share
#                           regression gate lives here: a warm arm that still pays the
#                           cold-start premium did not warm up and must not be recorded as warm.
# Sends <nreq> identical story prompts (greedy) with distinct max_tokens so each
# request is identifiable in the engine log. Reports garbage count, engine tok/s,
# CPU-expert time and its share, client wall time per request.
# Writes runs/tpbat-<tag>.out and /tmp/tpbat-<tag>-*.json.
PORT="${PORT:-8081}"
TAG="${1:?tag}"
N="${2:-10}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNS="$ROOT/runs"
mkdir -p "$RUNS"
OUT="$RUNS/tpbat-$TAG.out"
: > "$OUT"
echo "== battery $TAG: $N requests, $(date -Is)" | tee -a "$OUT"
# Desktop state: scan /proc for browsers (chromium / zen hold VRAM and GPU cycles).
# A battery read with browsers alive is not comparable to one without them, so the state is
# REPORTED with the numbers - the host belongs to the person using it, and this harness
# does not kill their applications to make a number look better.  A noisy desktop is a
# reason to distrust the reading, not something to fix by force.
browsers=""
for d in /proc/[0-9]*; do
  comm=""
  # a process can exit between the glob and the read: the missing file is not an error worth printing
  [ -r "$d/status" ] || continue
  while IFS= read -r line; do case $line in Name:*) comm=$line;; esac; done < "$d/status" 2>/dev/null
  c=${comm#Name:}; c=${c#"${c%%[![:space:]]*}"}
  case $c in chromium*|zen-bin|firefox*) browsers="$browsers ${d#/proc/}";; esac
done
if [ -n "$browsers" ]; then
  echo "== desktop: BROWSERS ALIVE (PIDS:$browsers ) - the host is busy, these numbers are noisy" | tee -a "$OUT"
else
  echo "== desktop: quiet (no browsers)" | tee -a "$OUT"
fi

# **THE PAGE CACHE IS PART OF THE MEASUREMENT.**  The blob fetch reads the GGUF's expert
# pages: resident, a blob costs ~30 us; not resident, it waits on the SSD and costs ~151 us -
# a 5x difference in the same call count (b580-tp2-pool-phases.md).  A battery that runs with
# a small buff/cache is therefore measuring a DIFFERENT engine, and comparing it to one that
# ran with a warm cache is not a valid A/B.  So the regime goes in the output, next to the
# numbers it belongs to.
page_cache_state() {
  awk '/^MemFree:/ {f=$2} /^Buffers:/ {b=$2} /^Cached:/ {c=$2} /^SReclaimable:/ {r=$2} /^MemAvailable:/ {a=$2}
       END {printf "free %.1f GB  buff/cache %.1f GB  available %.1f GB", f/1048576, (b+c+r)/1048576, a/1048576}' /proc/meminfo
}
# **A DIRECT PROBE OF THE PAGES THE BLOB PATH READS.**  The global buff/cache says how much
# memory the machine has cached, but the blob path reads the GGUF's expert pages: what
# matters is whether THOSE are resident.  A 64 MB read of the native shard is cached at
# several GB/s and comes off the SSD at under 1 GB/s, so the rate says which regime the
# battery is in.  (The shards are 72 GB, so they can never be fully cached - the probe is
# the honest way to see whether the part the engine uses is.)
GGUF_SHARD="${GGUF_SHARD:-/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF/Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00001-of-00002.gguf}"
gguf_cache_rate() {
  [ -r "$GGUF_SHARD" ] || { echo "(no shard)"; return; }
  local t0 t1 mb
  t0=$(date +%s%N)
  dd if="$GGUF_SHARD" of=/dev/null bs=4M count=64 2>/dev/null
  t1=$(date +%s%N)
  mb=$(( (t1 - t0) / 1000000 ))
  awk -v ms="$mb" 'BEGIN { if (ms <= 0) { print "(probe failed)"; exit } r=64*1000/ms;
         printf "%.0f MB/s (%s)", r, (r > 3000 ? "cached" : (r > 1500 ? "partly cached" : "from disk")) }'
}
start_rate="$(gguf_cache_rate)"
echo "== page cache at start: $(page_cache_state)  |  GGUF expert pages: $start_rate" | tee -a "$OUT"
# **REGIME GATE.**  A battery whose expert pages are cold (below STRATA_REGIME_MIN_MBPS,
# default 0 = no gate) measures a different engine - the blob path reads the GGUF's pages,
# and cold pages cost ~5x what warm ones do.  Refuse to collect it instead of poisoning the
# A/B: the paired harness re-runs the arm until it lands in a warm regime.
_min="${STRATA_REGIME_MIN_MBPS:-0}"
if [ "$_min" != "0" ]; then
  _mbps="${start_rate%% *}"   # the leading number, e.g. "188"
  case "$_mbps" in ''|*[!0-9]*) _mbps=0 ;; esac
  if [ "$_mbps" -lt "$_min" ]; then
    echo "ABORT: cold regime at start (${_mbps} MB/s < ${_min} MB/s) - re-run this arm" | tee -a "$OUT"
    exit 3
  fi
fi

garbled=0
# --warm-up (opt-in, default off): one discarded request, so the measured arm starts with the VRAM
# expert cache and the GGUF's expert pages resident.  Cold-start reads cost ~5x warm ones
# (b580-tp2-pool-phases.md) and the cache fills through a run, so req 1 otherwise pays the
# cold-start premium the other nine already covered.  Off by default: a warm arm is a DIFFERENT
# engine from the cold-start one the recorded runs measured, so it stays opt-in and is never mixed
# into a cold-start arm's numbers.
WARM="${3:-0}"
if [ "$WARM" != "0" ]; then
  # Pre-cache the exact max_tokens profile the battery will use (mt=201..200+N), so each arm's
  # req-1 starts with the same GGUF expert pages resident regardless of starting page-cache warmth.
  # This isolates page-cache effects: req-1 variance then reflects only engine state, not disk reads.
  # Off by default: a warm arm is a DIFFERENT engine state from the cold-start one, so it stays opt-in.
  WT=$((200 + N))
  echo "== warm-up: one discarded request, max_tokens=$WT (matches battery profile 201..$WT)" | tee -a "$OUT"
  curl -s -m 400 "http://127.0.0.1:$PORT/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d "{\"model\":\"x\",\"messages\":[{\"role\":\"user\",\"content\":\"Write a short story about a robot discovering flowers. Be specific.\"}],\"max_tokens\":$WT,\"temperature\":0}" \
    > /dev/null
  echo "== warm-up done, GGUF pages now: $(gguf_cache_rate)" | tee -a "$OUT"
fi
for i in $(seq 1 "$N"); do
  mt=$((200 + i))
  t0=$(date +%s.%N)
  curl -s -m 400 "http://127.0.0.1:$PORT/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d "{\"model\":\"x\",\"messages\":[{\"role\":\"user\",\"content\":\"Write a short story about a robot discovering flowers. Be specific.\"}],\"max_tokens\":$mt,\"temperature\":0}" \
    > "/tmp/tpbat-$TAG-$i.json"
  t1=$(date +%s.%N)
  python3 - "$i" "$mt" "$t0" "$t1" "/tmp/tpbat-$TAG-$i.json" >> "$OUT" << 'PY'
import json, sys
i, mt, t0, t1, path = sys.argv[1:6]
try:
    d = json.load(open(path))
    m = d["choices"][0]["message"]
    txt = m.get("content") or ""
    t = d.get("timings", {})
    u = d.get("usage", {})
    bad = txt.startswith("!!") or "!!!!" in txt[:64]
    story = ("robot" in txt.lower()) or ("flower" in txt.lower())
    # CPU expert time: the engine's own clock, the host time inside the pool dispatch this request. None with an
    # older engine that writes no cpu_ms= on its DONE line - said plainly, never a 0 that reads as "no CPU work".
    cpu, dec = t.get("cpu_ms"), t.get("predicted_ms")
    ctxt = f" cpu={cpu:.0f}ms({cpu / dec:.0%})" if isinstance(cpu, (int, float)) and dec else ""
    print(f"req {i}: mt={mt} ct={u.get('completion_tokens')} eng_tps={t.get('predicted_per_second')}{ctxt} "
          f"wall={float(t1)-float(t0):.1f}s garbled={bad} story={story} head={txt[:60]!r}")
except Exception as e:
    print(f"req {i}: ERROR {e} raw={open(path).read()[:200]!r}")
PY
  if /usr/bin/grep -q "garbled=True" <(tail -1 "$OUT"); then garbled=$((garbled+1)); fi
done
echo "== page cache at end:   $(page_cache_state)  |  GGUF expert pages: $(gguf_cache_rate)" | tee -a "$OUT"
echo "== battery $TAG done: $garbled/$N garbled, $(date -Is)" | tee -a "$OUT"
# Aggregate CPU-share summary across the battery arm: visible at a glance, so a regression in
# CPU-expert time (a share of decode time) does not hide behind an unchanged eng_tps average.
SUMMARY="$(awk -v tag="$TAG" -v N="$N" '
  match($0, /cpu=([0-9.]+)ms\(([0-9.]+)%\)/, m) { cpu[++n]=m[1]+0; share[n]=m[2]+0 }
  match($0, /eng_tps=([0-9.]+)/, t) { tps[++nt]=t[1]+0 }
  END {
    if (n == 0) { printf "== battery %s: no cpu_ms readings (older engine or all errors)\n", tag; exit }
    mcs=0; ms=0
    for (k=1;k<=n;k++){mcs+=cpu[k]; ms+=share[k]}
    mtps=0; for(k=1;k<=nt;k++) mtps+=tps[k]
    printf "== battery %s: cpu_ms read %d/%d | mean cpu_ms=%.0f ms | mean share %.0f%% | mean eng_tps=%.2f\n", tag, n, N, mcs/n, ms/n, mtps/nt
  }' "$OUT")"; echo "$SUMMARY" | tee -a "$OUT"

# **LOCAL REGRESSION GUARD for warm req-1 CPU share.**  CI cannot run the engine (no GPU), so the
# enforceable gate lives here: a warm arm's req-1 CPU share is the cold-start-premium canary.  A warm
# arm whose req-1 still pays the cold-start premium means the warm-up did not land (or the cache
# evicted mid-arm) - the numbers are not a warm arm and must not be recorded as one.  Opt-in via
# WARM_REQ1_CPU_MAX (default 0 = no gate, so old recorded arms stay comparable); on violation the
# arm exits 3 and the caller re-runs it.
if [ "$WARM" != "0" ]; then
  _max="${WARM_REQ1_CPU_MAX:-0}"
  if [ "$_max" != "0" ]; then
    _req1_share="$(awk 'match($0, /req 1:.*cpu=[0-9.]+ms\(([0-9.]+)%\)/, m) { print m[1]+0; exit }' "$OUT")"
    case "$_req1_share" in ''|*[!0-9]*) _req1_share=0 ;; esac
    if [ "$_req1_share" -gt "$_max" ]; then
      echo "ABORT: warm req-1 CPU share ${_req1_share}% exceeds ${_max}% - the warm-up did not land; re-run this arm" | tee -a "$OUT"
      exit 3
    fi
    echo "== warm req-1 CPU share ${_req1_share}% <= ${_max}% (guard ok)" | tee -a "$OUT"
  fi
fi

