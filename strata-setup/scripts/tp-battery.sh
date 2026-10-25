#!/bin/bash
# Coherence + throughput battery for TP2 experiments.
# Usage: PORT=8081 ./tp-battery.sh <tag> <nreq>
# Sends <nreq> identical story prompts (greedy) with distinct max_tokens so each
# request is identifiable in the engine log. Reports garbage count, engine tok/s,
# client wall time per request. Writes runs/tpbat-<tag>.out and /tmp/tpbat-<tag>-*.json.
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
    print(f"req {i}: mt={mt} ct={u.get('completion_tokens')} eng_tps={t.get('predicted_per_second')} "
          f"wall={float(t1)-float(t0):.1f}s garbled={bad} story={story} head={txt[:60]!r}")
except Exception as e:
    print(f"req {i}: ERROR {e} raw={open(path).read()[:200]!r}")
PY
  if /usr/bin/grep -q "garbled=True" <(tail -1 "$OUT"); then garbled=$((garbled+1)); fi
done
echo "== page cache at end:   $(page_cache_state)  |  GGUF expert pages: $(gguf_cache_rate)" | tee -a "$OUT"
echo "== battery $TAG done: $garbled/$N garbled, $(date -Is)" | tee -a "$OUT"
