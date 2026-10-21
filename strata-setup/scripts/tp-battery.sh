#!/bin/bash
# Coherence + throughput battery for TP2 experiments.
# Usage: PORT=8081 ./tp-battery.sh <tag> <nreq>
# Sends <nreq> identical story prompts (greedy) with distinct max_tokens so each
# request is identifiable in the engine log. Reports garbage count, engine tok/s,
# client wall time per request. Writes tpbat-<tag>.out and /tmp/tpbat-<tag>-*.json.
PORT="${PORT:-8081}"
TAG="${1:?tag}"
N="${2:-10}"
OUT="tpbat-$TAG.out"
: > "$OUT"
echo "== battery $TAG: $N requests, $(date -Is)" | tee -a "$OUT"
# Desktop state: the shared card's noise term (chromium / zen hold VRAM and GPU cycles).
# A battery read with browsers alive is not comparable to one without them.
browsers=""
for d in /proc/[0-9]*; do
  comm=""
  while IFS= read -r line; do case $line in Name:*) comm=$line;; esac; done < "$d/status" 2>/dev/null
  c=${comm#Name:}; c=${c#"${c%%[![:space:]]*}"}
  case $c in chromium*|zen-bin|firefox*) browsers="$browsers ${d#/proc/}";; esac
done
if [ -n "$browsers" ]; then echo "== desktop: browsers alive (PIDS:$browsers ) - batteries are noisy" | tee -a "$OUT"
else echo "== desktop: quiet (no browsers)" | tee -a "$OUT"; fi
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
echo "== battery $TAG done: $garbled/$N garbled, $(date -Is)" | tee -a "$OUT"
