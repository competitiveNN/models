#!/usr/bin/env python3
"""Final 64k-context prefill measurement against the live Strata server."""
import json
import time
import urllib.request

URL = "http://127.0.0.1:1235/v1/chat/completions"


def ask(prompt, max_tokens=8):
    payload = {"model": "swift", "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), method="POST", headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as res:
        d = json.loads(res.read().decode())
        el = time.perf_counter() - t0
        t = d.get("timings") or {}
        return {
            "prompt_n": t.get("prompt_n", (d.get("usage") or {}).get("prompt_tokens", 0)),
            "prompt_ms": t.get("prompt_ms"),
            "prompt_per_second": t.get("prompt_per_second"),
            "wall_s": el,
        }


def main():
    prompt = "The quick brown fox jumps over the lazy dog. " * (65536 // 9 + 1)
    prompt = prompt[:65536]
    r = ask(prompt, max_tokens=8)
    out = {"prompt_tokens": r["prompt_n"], "prompt_ms": r["prompt_ms"], "prompt_per_second": r["prompt_per_second"], "wall_s": r["wall_s"]}
    with open("runs/closure-64k-prefill.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
