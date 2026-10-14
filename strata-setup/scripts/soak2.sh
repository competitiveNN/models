#!/bin/sh
# Sequential soak against an already-running server.  Usage: PORT=8081 ./soak2.sh NREQ TAG
set -u
NREQ="${1:-20}"
TAG="${2:-soak}"
LOG="/var/home/fra/dev/models/strata-setup/soak2-$TAG.out"
PORT="${PORT:-8081}"
: > "$LOG"
pass=0; fail=0; slow=0
i=0
while [ "$i" -lt "$NREQ" ]; do
    i=$((i+1))
    msg="Round $i: Give me a two-sentence fact about the number $i."
    t0=$(date +%s)
    out=$(curl -s --max-time 600 -X POST http://127.0.0.1:$PORT/v1/chat/completions \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"swift-1.5-iq3_xxs\",\"messages\":[{\"role\":\"user\",\"content\":\"$msg\"}],\"max_tokens\":80,\"temperature\":0.6}" 2>>"$LOG")
    t1=$(date +%s)
    dt=$((t1-t0))
    line=$(printf '%s' "$out" | python3 -c "
import sys, json
try: d = json.load(sys.stdin)
except Exception as e:
    print('FAIL not json: ' + repr(e)[:120] + ' raw: ' + sys.stdin.read()[:120]); sys.exit(0)
c = d.get('choices') or [{}]
c = c[0] if c else {}
u = d.get('usage') or {}
err = d.get('error')
if err or not c.get('finish_reason'):
    print('FAIL err=' + repr(err)[:80] + ' finish=' + repr(c.get('finish_reason'))); sys.exit(0)
print('OK tok=' + str(u.get('completion_tokens')) + ' prompt=' + str(u.get('prompt_tokens')) + ' finish=' + str(c.get('finish_reason')))
")
    echo "round $i ($dt s): $line" | tee -a "$LOG"
    case "$line" in OK*) pass=$((pass+1));; *) fail=$((fail+1));; esac
    [ "$dt" -gt 60 ] && slow=$((slow+1))
done
echo "=== $TAG done: pass=$pass fail=$fail slow_over_60s=$slow ===" | tee -a "$LOG"