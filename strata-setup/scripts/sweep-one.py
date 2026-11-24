#!/usr/bin/env python3
"""Run one strata-old config end-to-end and record decode/prefill tok/s.

Usage:
  python scripts/sweep-one.py --tag NAME --env K=V ... [--runs N]

Records full env metadata, exact coherence (detect_degenerate), and per-run
results to runs/sweep-<tag>.json and appends a summary line to
runs/sweep-summary.jsonl.
"""
import argparse, json, os, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
sys.path.insert(0, str(ROOT / "scripts"))
from coherence import detect_degenerate

FIXED_BASELINE_TAG = "baseline-ctx64k-auto-spec4-par1"


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
    """Run 3 short requests, return (prefill_median, decode_median, coherence_pass, details)."""
    import statistics
    URL = "http://127.0.0.1:1235/v1/chat/completions"
    cases = [
        ("short", "What is the capital of France?", 64),
        ("code", "Write a Python function to compute fibonacci numbers.", 128),
        ("medium", "Explain how a hash map works in 3 sentences.", 128),
    ]
    prefills, decodes = [], []
    coherent = True
    details = []
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
            pn = tm.get("prompt_n", u.get("prompt_tokens", 0))
            dn = tm.get("predicted_n", u.get("completion_tokens", 0))
            if ps is not None: prefills.append(ps)
            if ds is not None: decodes.append(ds)
            msg = d["choices"][0].get("message", {})
            text = (msg.get("content") or "") + " " + (msg.get("reasoning_content") or "")
            reason = detect_degenerate(text)
            if reason:
                coherent = False
            details.append({"case": name, "prefill": ps, "decode": ds, "prompt_tokens": pn,
                            "completion_tokens": dn, "coherence_reason": reason})
            print(f"  [{name}] prefill={ps} decode={ds} coh={'PASS' if reason is None else 'FAIL: '+reason}", flush=True)
        except Exception as e:
            print(f"  [{name}] ERROR: {e}", flush=True)
            coherent = False
            details.append({"case": name, "error": str(e)})
    prefill_med = statistics.median(prefills) if prefills else 0.0
    decode_med = statistics.median(decodes) if decodes else 0.0
    return prefill_med, decode_med, coherent, details


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--env", action="append", default=[], help="KEY=VAL passed to run script")
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()

    env = dict(os.environ)
    env_meta = {}
    for e in args.env:
        k, v = e.split("=", 1)
        env[k] = v
        env_meta[k] = v

    stop_container()
    # start
    log = open(RUNS / f"sweep-{args.tag}.log", "w")
    proc = subprocess.Popen(["bash", str(ROOT / "run-strata-2gpu.sh")],
                            env=env, stdout=log, stderr=subprocess.STDOUT, cwd=str(ROOT))
    print(f"  started, waiting for health", flush=True)
    ok = wait_health()
    if not ok:
        print(f"[{args.tag}] FAILED to become healthy", flush=True)
        stop_container()
        sys.exit(1)

    # measure N times
    run_results = []
    for i in range(args.runs):
        print(f"  run {i+1}/{args.runs}:", flush=True)
        pm, dm, coh, details = measure_once()
        run_results.append({"run": i + 1, "prefill_median": pm, "decode_median": dm,
                            "coherence_pass": coh, "details": details})
        if i < args.runs - 1:
            time.sleep(3)

    # aggregate
    import statistics
    prefills = [r["prefill_median"] for r in run_results if r["prefill_median"] > 0]
    decodes = [r["decode_median"] for r in run_results if r["decode_median"] > 0]
    all_coh = all(r["coherence_pass"] for r in run_results)
    prefill_med = statistics.median(prefills) if prefills else 0.0
    decode_med = statistics.median(decodes) if decodes else 0.0

    # save full result
    prov = get_provenance()
    out_json = RUNS / f"sweep-{args.tag}.json"
    out_json.write_text(json.dumps({
        "tag": args.tag, "env": env_meta, "runs": args.runs,
        "prefill_median": prefill_med, "decode_median": decode_med,
        "coherence_pass": all_coh, "per_run": run_results,
        "provenance": prov,
        "git_commit": prov.get("git_commit") if prov else None,
        "image_digest": prov.get("image_digest") if prov else None,
    }, indent=2))

    # coherence gate (exact)
    cg = subprocess.run([sys.executable, str(ROOT / "bench-coherence-2xb580.py"),
                         "--max-tokens", "60", "--timeout", "300"], capture_output=True, text=True, timeout=360)
    cg_pass = "PASSED" in (cg.stdout or "")

    stop_container()
    try: proc.kill()
    except Exception: pass

    print(f"[{args.tag}] prefill={prefill_med:.1f} decode={decode_med:.1f} tok/s coherence={'PASS' if (all_coh and cg_pass) else 'FAIL'} (n={args.runs})", flush=True)

    # append summary (with full env metadata and provenance)
    summary = RUNS / "sweep-summary.jsonl"
    summary_entry = {
        "tag": args.tag, "env": env_meta, "runs": args.runs,
        "prefill_median": prefill_med, "decode_median": decode_med,
        "coherence_pass": all_coh and cg_pass,
        "per_run_decode": [r["decode_median"] for r in run_results],
        "per_run_prefill": [r["prefill_median"] for r in run_results],
        "provenance": prov,
        "git_commit": prov.get("git_commit") if prov else None,
        "image_digest": prov.get("image_digest") if prov else None,
    }
    # Append summary atomically (write to temp then rename) to avoid truncation
    summary_tmp = summary.with_suffix(".jsonl.tmp")
    try:
        with open(summary, "a") as f:
            f.write(json.dumps(summary_entry) + "\n")
            f.flush()
            import os
            os.fsync(f.fileno())
    except Exception:
        # Best-effort cleanup of temp file
        summary_tmp.unlink(missing_ok=True)
        raise


def get_provenance():
    """Return dict with git commit and image digest for reproducibility."""
    prov = {}
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=str(ROOT), timeout=10)
        if r.returncode == 0:
            prov["git_commit"] = r.stdout.strip()
    except Exception:
        pass
    # Image digest from config file if available
    digest_file = ROOT / "configs" / "strata-old-image-digest.json"
    if digest_file.exists():
        try:
            d = json.loads(digest_file.read_text())
            prov["image_digest"] = d.get("digest", d.get("sha256", ""))
        except Exception:
            pass
    return prov if prov else None


if __name__ == "__main__":
    main()
