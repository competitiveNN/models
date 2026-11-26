#!/usr/bin/env python3
"""Quick single-config measurement: 3 short requests, returns decode tok/s."""
import argparse, json, sys, time, urllib.request
ROOT = None
URL = "http://127.0.0.1:1235/v1/chat/completions"

CASES = [
    ("short", "What is the capital of France?", 64),
    ("code", "Write a Python function to compute fibonacci numbers.", 128),
    ("medium", "Explain how a hash map works in 3 sentences.", 128),
]

def ask(prompt, mt, timeout=120):
    payload = {"model": "swift", "messages": [{"role": "user", "content": prompt}], "max_tokens": mt}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(URL, data=data, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    decodes = []; prefills = []; coh_ok = True
    for name, prompt, mt in CASES:
        try:
            t0 = time.perf_counter()
            d = ask(prompt, mt)
            el = time.perf_counter() - t0
            tm = d.get("timings") or {}
            u = d.get("usage") or {}
            ps = tm.get("prompt_per_second"); ds = tm.get("predicted_per_second")
            pn = tm.get("prompt_n", u.get("prompt_tokens", 0))
            dn = tm.get("predicted_n", u.get("completion_tokens", 0))
            if ps: prefills.append(ps)
            if ds: decodes.append(ds)
            print(f"[{name}] prefill={ps} tok/s ({pn} tok) decode={ds} tok/s ({dn} tok) wall={el:.1f}s", flush=True)
            content = (d["choices"][0]["message"].get("content") or "") + (d["choices"][0]["message"].get("reasoning_content") or "")
            if "!!!!!!" in content:
                coh_ok = False
        except Exception as e:
            print(f"[{name}] ERROR: {e}", flush=True)
    import statistics
    prefill_med = statistics.median(prefills) if prefills else 0
    decode_med = statistics.median(decodes) if decodes else 0
    print(f"SUMMARY prefill_median={prefill_med:.1f} decode_median={decode_med:.1f} coherence={'PASS' if coh_ok else 'FAIL'}", flush=True)
    if args.json:
        Path = __import__("pathlib").Path
        Path(args.json).write_text(json.dumps({"prefill_median": prefill_med, "decode_median": decode_med, "coherence_pass": coh_ok, "prefills": prefills, "decodes": decodes}, indent=2))

if __name__ == "__main__":
    main()