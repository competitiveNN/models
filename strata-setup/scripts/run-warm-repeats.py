#!/usr/bin/env python3
"""Run N warm repeats of a config and save per-run decode/prefill medians."""
import argparse, json, os, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"

def container_alive():
    r = subprocess.run(["podman", "ps", "-q", "--filter", "name=strata"], capture_output=True, text=True)
    return bool(r.stdout.strip())

def wait_health(timeout=400):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not container_alive():
            time.sleep(3)
            continue
        try:
            with urllib.request.urlopen("http://127.0.0.1:1235/health", timeout=5) as r:
                d = json.loads(r.read())
                if d.get("loaded"):
                    return True
        except Exception:
            pass
        time.sleep(5)
    return False

def stop_container():
    subprocess.run(["podman", "kill", "strata"], capture_output=True, timeout=15)
    time.sleep(2)
    subprocess.run(["podman", "rm", "-f", "strata"], capture_output=True, timeout=30)
    time.sleep(2)

def measure_once():
    import statistics
    URL = "http://127.0.0.1:1235/v1/chat/completions"
    cases = [
        ("short", "What is the capital of France?", 64),
        ("code", "Write a Python function to compute fibonacci numbers.", 128),
        ("medium", "Explain how a hash map works in 3 sentences.", 128),
    ]
    prefills, decodes = [], []
    for name, prompt, mt in cases:
        payload = {"model": "swift", "messages": [{"role": "user", "content": prompt}], "max_tokens": mt}
        data = json.dumps(payload).encode()
        req = urllib.request.Request(URL, data=data, method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as res:
                d = json.loads(res.read().decode())
            tm = d.get("timings") or {}
            u = d.get("usage") or {}
            ps = tm.get("prompt_per_second")
            ds = tm.get("predicted_per_second")
            if ps is not None: prefills.append(ps)
            if ds is not None: decodes.append(ds)
        except Exception as e:
            print(f"  ERROR: {e}", flush=True)
            # If connection refused, the server may have crashed; abort
            if "Connection refused" in str(e) or "Remote end closed" in str(e):
                raise
    return (statistics.median(prefills) if prefills else 0.0,
            statistics.median(decodes) if decodes else 0.0)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--repeats", type=int, default=10)
    ap.add_argument("--warmup", type=int, default=3)
    args = ap.parse_args()

    env = dict(os.environ)
    for e in args.env:
        k, v = e.split("=", 1)
        env[k] = v

    stop_container()
    log = open(RUNS / f"warm-{args.tag}.log", "w")
    proc = subprocess.Popen(["bash", str(ROOT / "run-strata-2gpu.sh")],
                            env=env, stdout=log, stderr=subprocess.STDOUT, cwd=str(ROOT))
    print(f"  started, waiting for health", flush=True)
    if not wait_health():
        print(f"[{args.tag}] FAILED to become healthy", flush=True)
        stop_container()
        sys.exit(1)

    # Warm-up
    print(f"  warming up ({args.warmup} requests)...", flush=True)
    URL = "http://127.0.0.1:1235/v1/chat/completions"
    for _ in range(args.warmup):
        payload = {"model": "swift", "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 20}
        data = json.dumps(payload).encode()
        req = urllib.request.Request(URL, data=data, method="POST", headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=120).read()
        except Exception:
            pass
        time.sleep(2)

    # Run repeats
    results = []
    for i in range(args.repeats):
        try:
            pm, dm = measure_once()
            results.append({"run": i + 1, "prefill": pm, "decode": dm})
            print(f"  run {i+1}/{args.repeats}: prefill={pm:.1f} decode={dm:.1f}", flush=True)
        except Exception as e:
            print(f"  run {i+1}/{args.repeats}: SKIPPED ({e})", flush=True)
        time.sleep(5)

    import statistics
    prefills = [r["prefill"] for r in results]
    decodes = [r["decode"] for r in results]
    valid_prefills = [p for p in prefills if p and p > 0]
    valid_decodes = [d for d in decodes if d and d > 0]
    if not valid_prefills or not valid_decodes:
        print("ERROR: no valid warm measurements; aborting", file=sys.stderr)
        stop_container()
        try:
            proc.kill()
        except Exception:
            pass
        sys.exit(1)
    out = {
        "tag": args.tag, "env": {e.split("=",1)[0]: e.split("=",1)[1] for e in args.env},
        "repeats": args.repeats, "warmup": args.warmup,
        "per_run": results,
        "decode_median": statistics.median(valid_decodes),
        "decode_mean": statistics.mean(valid_decodes),
        "decode_stdev": statistics.stdev(valid_decodes) if len(valid_decodes) > 1 else 0,
        "prefill_median": statistics.median(valid_prefills),
        "prefill_mean": statistics.mean(valid_prefills),
        "prefill_stdev": statistics.stdev(valid_prefills) if len(valid_prefills) > 1 else 0,
    }
    out_path = RUNS / f"warm-{args.tag}.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\n[{args.tag}] decode: median={out['decode_median']:.2f} mean={out['decode_mean']:.2f} stdev={out['decode_stdev']:.2f}", flush=True)
    print(f"[{args.tag}] prefill: median={out['prefill_median']:.2f} mean={out['prefill_mean']:.2f} stdev={out['prefill_stdev']:.2f}", flush=True)

    stop_container()
    try: proc.kill()
    except: pass


if __name__ == "__main__":
    main()
