#!/usr/bin/env python3
"""Aggressive speculative execution and prefill/decode measurement harness."""
import urllib.request, json, time, sys

URL = "http://127.0.0.1:1235/v1/chat/completions"

def run_test():
    payload = {
        "model": "swift-1.5-iq3_xxs",
        "messages": [{"role": "user", "content": "Explain quantum computing in detail, covering qubits, superposition, entanglement, and error correction."}],
        "max_tokens": 256
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(URL, data=data, method="POST", headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=300) as res:
            d = json.loads(res.read().decode())
            el = time.perf_counter() - t0
            t = d.get("timings") or {}
            print(f"SUCCESS: wall={el:.2f}s prefill_tps={t.get('prompt_per_second')} decode_tps={t.get('predicted_per_second')}")
            return d
    except Exception as e:
        print(f"ERROR: {e}")
        return None

if __name__ == "__main__":
    run_test()
