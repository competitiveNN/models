#!/usr/bin/env python3
"""Boot a strata config once, then fire N warm requests and report the median
decode tok/s (steady state). Usage: battery_cfg.py <config> <port> [n] [max_tokens]
"""
import json
import os
import signal
import statistics
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, "..", "strata-src"))


def health(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:
            return json.load(r)
    except Exception:
        return None


def ask(port, model, prompt, max_tokens):
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                       "max_tokens": max_tokens, "stream": False}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as r:
        resp = json.load(r)
    return time.time() - t0, resp.get("usage", {}).get("completion_tokens", 0)


def main():
    cfg = sys.argv[1]
    port = int(sys.argv[2])
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    max_tokens = int(sys.argv[4]) if len(sys.argv) > 4 else 64
    prompt = "Write one paragraph about the ocean."
    cfg_path = cfg if os.path.isabs(cfg) else os.path.join(SRC, cfg)
    model = json.load(open(cfg_path))["model_name"]

    subprocess.run(["podman", "rm", "-f", "strata-sycl-serve"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log = open(f"/tmp/battery-{port}.log", "w")
    proc = subprocess.Popen(
        [sys.executable, "sycl/serve/server_intel.py", "--engine", "strata",
         "--config", os.path.basename(cfg_path), "--port", str(port)],
        cwd=SRC, stdout=log, stderr=subprocess.STDOUT, preexec_fn=os.setsid)
    rates = []
    try:
        t0 = time.time()
        while time.time() - t0 < 240:
            h = health(port)
            if h and h.get("loaded"):
                break
            if proc.poll() is not None:
                print("SERVER DIED during load"); return 1
            time.sleep(3)
        else:
            print("NOT READY"); return 1
        print(f"READY in {time.time()-t0:.1f}s")
        for i in range(n):
            try:
                dt, nt = ask(port, model, prompt, max_tokens)
                r = nt / dt if dt > 0 else 0
                rates.append(r)
                print(f"  req {i+1}: {nt} tok in {dt:.2f}s = {r:.2f} tok/s")
            except Exception as e:
                print(f"  req {i+1}: FAILED {e}")
        if rates:
            print(f"MEDIAN {statistics.median(rates):.2f}  MEAN {statistics.mean(rates):.2f}  "
                  f"MIN {min(rates):.2f}  MAX {max(rates):.2f} tok/s  (n={len(rates)})")
        return 0
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            pass
        time.sleep(2)
        subprocess.run(["podman", "rm", "-f", "strata-sycl-serve"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    sys.exit(main())