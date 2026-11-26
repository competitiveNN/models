#!/usr/bin/env python3
import urllib.request, json, time, sys

URL = "http://127.0.0.1:1235/v1/chat/completions"

def test_prompt(length, max_tokens=16):
    prompt = "The quick brown fox jumps over the lazy dog. " * (length // 9 + 1)
    prompt = prompt[:length]
    payload = {"model": "swift", "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(URL, data=data, method="POST", headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=300) as res:
            d = json.loads(res.read().decode())
            el = time.perf_counter() - t0
            t = d.get("timings") or {}
            u = d.get("usage") or {}
            print(f"[len={length}] prompt_n={t.get('prompt_n', u.get('prompt_tokens'))} prefill_tok_s={t.get('prompt_per_second')} prompt_ms={t.get('prompt_ms')} wall={el:.2f}s", flush=True)
            return {"len": length, "prompt_n": t.get("prompt_n"), "prompt_per_second": t.get("prompt_per_second"), "prompt_ms": t.get("prompt_ms"), "wall": el}
    except Exception as e:
        print(f"[len={length}] ERROR: {e}", flush=True)
        return {"len": length, "error": str(e)}

def main():
    results = []
    for length in [1024, 4096, 16384, 32768, 49152, 65536]:
        print(f"Testing prompt length {length}...")
        res = test_prompt(length)
        results.append(res)
        time.sleep(1)
    with open("runs/prefill-64k-result.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Saved runs/prefill-64k-result.json")

if __name__ == "__main__":
    main()
