#!/bin/sh
# Concurrency sweep against a running server.  Usage: ./conc2.sh TAG
set -u
TAG="${1:-conc}"
LOG="/var/home/fra/dev/models/strata-setup/conc2-$TAG.out"
PORT="${PORT:-8081}"
: > "$LOG"
say() { printf '%s\n' "$1" | tee -a "$LOG"; }
for n in 2 4 8; do
    say "===== concurrency $n ====="
    pids=""
    rm -f /tmp/conc-r*.json
    i=0
    while [ "$i" -lt "$n" ]; do
        i=$((i+1))
        ( t0=$(date +%s)
          curl -s --max-time 900 -X POST http://127.0.0.1:$PORT/v1/chat/completions \
            -H "Content-Type: application/json" \
            -d "{\"model\":\"swift-1.5-iq3_xxs\",\"messages\":[{\"role\":\"user\",\"content\":\"What is $i times $i? One short answer.\"}],\"max_tokens\":60,\"temperature\":0.6}" \
            > /tmp/conc-r$i.json 2>>"$LOG"
          echo "$i $(( $(date +%s) - t0 ))" > /tmp/conc-t$i ) &
        pids="$pids $!"
    done
    for p in $pids; do wait "$p"; done
    i=0
    while [ "$i" -lt "$n" ]; do
        i=$((i+1))
        printf '  r%s: ' "$i" | tee -a "$LOG"
        python3 -c "
import json,sys
try: d = json.load(open('/tmp/conc-r$i.json'))
except Exception as e:
    print('FAIL not json: ' + repr(e)[:100]); sys.exit(0)
c = d.get('choices') or [{}]
c = c[0] if c else {}
u = d.get('usage') or {}
if d.get('error') or not c.get('finish_reason'):
    print('FAIL ' + repr(d.get('error'))[:80] + ' finish=' + repr(c.get('finish_reason'))); sys.exit(0)
m = (c.get('message') or {}).get('content') or ''
print('OK tok=' + str(u.get('completion_tokens')) + ' finish=' + str(c.get('finish_reason')) + ' content=' + repr(m[:40]))
" | tee -a "$LOG"
    done
    for i in $(seq 1 "$n"); do
        [ -f /tmp/conc-t$i ] && printf '  wall r%s: %ss\n' "$i" "$(cat /tmp/conc-t$i)" | tee -a "$LOG"
    done
    say "  engine tail:"; tail -2 /var/home/fra/dev/models/strata-setup/strata-src/strata-swift-iq3_xxs.log | sed 's/^/    /' | tee -a "$LOG"
done
say "=== $TAG sweep done ==="