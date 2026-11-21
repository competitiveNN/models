#!/usr/bin/env python3
"""Benchmark all three Strata container images side-by-side on 2x Intel Arc B580.

Starts each image sequentially, waits for healthy, runs a standardized prompt suite
through the OpenAI-compatible API, collects engine timings + client TTFT, stops
the container, and writes a structured JSON report to runs/bench-containers-<ts>.json.

Usage:
    python3 scripts/bench-containers.py [--images ghcr,old,edge] [--port-base 8081] [--max-tokens 100]
"""
from __future__ import annotations
import argparse, json, subprocess, time, urllib.request, urllib.error, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
MODEL_DIR = "/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF"

IMAGES = {
    "ghcr": ("ghcr.io/niko1221/strata:0.2.13-sycl", "run-strata-2gpu.sh", 1235),
    "old": ("localhost/strata-old:latest", "strata-launch.sh", None),
    "edge": ("localhost/strata-edge:latest", "strata-launch.sh", None),
}

PROMPTS = [
    {"name": "short-chat", "messages": [{"role": "user", "content": "Write a short story about a robot learning to paint."}], "max_tokens": 100},
    {"name": "medium-prompt", "messages": [{"role": "user", "content": "Explain the architecture of a mixture-of-experts language model in detail, including routing, expert selection, and load balancing."}], "max_tokens": 150},
    {"name": "long-prompt", "messages": [{"role": "user", "content": "Write a comprehensive essay about the history of artificial intelligence, covering key milestones from Turing to modern LLMs, including technical details about transformer architectures, training methodologies, and deployment challenges."}], "max_tokens": 200},
]

def wait_healthy(url, timeout=300):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/health", timeout=5) as r:
                data = json.loads(r.read())
                if data.get("loaded"):
                    return True
        except Exception:
            pass
        time.sleep(3)
    return False

def run_prompt(url, prompt, max_tokens_override=None, api_key=None):
    mt = max_tokens_override or prompt["max_tokens"]
    body = json.dumps({"messages": prompt["messages"], "max_tokens": mt, "stream": False}).encode()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    req = urllib.request.Request(url + "/v1/chat/completions", data=body, headers=headers)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read()
            t1 = time.time()
            data = json.loads(raw)
            choices = data.get("choices") or [{}]
            choice = choices[0] if choices else {}
            if not isinstance(choice, dict):
                choice = {}
            message = choice.get("message") or {}
            if isinstance(message, dict):
                content = message.get("content")
                if not content:
                    content = message.get("reasoning_content") or message.get("text") or ""
            else:
                content = ""
            # Degenerate/coherence check: repeated tokens or gibberish (e.g. "!!!!")
            words = (content or "").split()
            degenerate = False
            if len(words) >= 5:
                unique_ratio = len(set(words)) / len(words)
                if unique_ratio < 0.3:
                    degenerate = True
            # catch runs of identical non-word characters (e.g. "!!!!")
            if not degenerate and content and len(set(content.strip())) <= 2 and len(content.strip()) >= 8:
                degenerate = True
            timings = data.get("timings", {}) or {}
            usage = data.get("usage", {}) or {}
            return {
                "ok": True,
                "degenerate": degenerate,
                "wall_s": round(t1 - t0, 2),
                "ttft_s": round(t1 - t0, 2),  # approximate; streaming would give exact TTFT
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "prompt_tps": round(timings.get("prompt_per_second", 0), 1),
                "decode_tps": round(timings.get("predicted_per_second", 0), 1),
                "content_preview": (content or "")[:200],
                "finish_reason": choice.get("finish_reason"),
            }
    except Exception as e:
        detail = str(e)
        try:
            if hasattr(e, "read"):
                detail = e.read().decode("utf-8", "replace")[:300] or detail
        except Exception:
            pass
        return {"ok": False, "error": detail, "degenerate": False, "wall_s": round(time.time() - t0, 2)}

def stop_container(name):
    try:
        subprocess.run(["podman", "rm", "-f", name], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        subprocess.run(["podman", "kill", name], capture_output=True, text=True, timeout=10)
        subprocess.run(["podman", "rm", "-f", name], capture_output=True, text=True, timeout=10)

def run_image_bench(image_key, port, max_tokens, quick=False):
    info = IMAGES[image_key]
    image = info[0]
    api_key = None

    if image_key == "ghcr":
        name = f"strata-bench-{image_key}"
        stop_container(name)
        env = os.environ.copy()
        env["IMAGE"] = image
        env["NAME"] = name
        env["HOST_PORT"] = str(port)
        subprocess.Popen(["bash", str(ROOT / "run-strata-2gpu.sh")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        container_name = name
    elif image_key == "old":
        name = f"strata-bench-{image_key}"
        stop_container(name)
        api_key = "benchkey1234567890"
        env = os.environ.copy()
        env.update({
            "MODEL": "IQ3_XXS", "FAMILY": "swift", "MODEL_PATH": "/gguf",
            "CONTEXT": "64k", "KV": "int8", "GPU": "0,1", "PORT": str(port),
            "VISION": "off", "TUNE": "skip", "API_KEY": api_key,
            "IGC_EnableGEPSimplification": "0",
            "STRATA_SET": "expert-cache=4096 prefill=auto:8192 spec=4 spec-min-p=0.5 pipeline-windows=2 vram-reserve-mib=512 trim-stage-weights mmap-experts pool-workers=12 stream-experts expert-cache-per-layer",
            "STRATA_SPLIT_MISS_MS": "108",
            "STRATA_PREFILL_MMQ": "0",
            "STRATA_WINDOW_SYNC": "1",
            "STRATA_VERIFY_DEVICE_PLAN": "0",
            "ONEAPI_DEVICE_SELECTOR": "level_zero:*",
        })
        cmd = ["podman", "run", "-d", "--privileged", "--name", name, "--network", "host",
               "--device", "/dev/dri", "--device", "/dev/dri/card0", "--device", "/dev/dri/card1",
               "--device", "/dev/dri/renderD128", "--device", "/dev/dri/renderD129",
               "-v", f"{ROOT}/Strata-data:/data/Strata-data:Z",
               "-v", "/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF:/gguf:ro",
               "-v", f"{ROOT}/adopt_patched.py:/opt/strata/terminal/strata_cli/launch/adopt.py:Z"]
        for k in ("STRATA_SPIN_MAX","STRATA_SPLIT_MISS_MS","STRATA_PREFILL_RING","STRATA_VERIFY_DEVICE_PLAN","STRATA_STAGE_TRIM",
                  "STRATA_RING_TIMEOUT_S","STRATA_SPLIT_WAIT_MS","STRATA_VERIFY_DRAIN_TIMEOUT_MS",
                  "STRATA_PREFILL_MMQ","STRATA_WINDOW_SYNC","STRATA_MIRROR_MIB","STRATA_VERIFY_NO_HOST",
                  "STRATA_COPY_ENGINE"):
            if k in os.environ:
                env.setdefault(k, os.environ[k])
        env_args = []
        for k, v in env.items():
            env_args += ["-e", f"{k}={v}"]
        subprocess.Popen(cmd + env_args + [image], env=os.environ.copy(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        container_name = name
    else:
        # strata-launch.sh uses fixed container name strata-2gpu
        container_name = "strata-2gpu"
        stop_container(container_name)
        subprocess.Popen(["bash", str(ROOT / "strata-launch.sh"), "--image", image_key, "--2gpu", str(port),
                          "--config", "strata-edge-fixed.json"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    url = f"http://127.0.0.1:{port}"
    print(f"  Waiting for {image_key} to become healthy on port {port}...")
    if not wait_healthy(url, timeout=300):
        print(f"  FAILED: {image_key} did not become healthy")
        stop_container(container_name)
        return {"image": image_key, "error": "did not become healthy"}

    time.sleep(5)  # warmup
    results = []
    prompts = [PROMPTS[0]] if quick else PROMPTS
    for p in prompts:
        print(f"  Running prompt: {p['name']}...")
        r = run_prompt(url, p, max_tokens, api_key=api_key)
        r["prompt_name"] = p["name"]
        results.append(r)
        status = "OK" if r["ok"] else "FAIL"
        if r.get("degenerate"):
            status = "DEGENERATE"
        tps = r.get("decode_tps", 0)
        print(f"    {status}: decode={tps} tok/s, wall={r['wall_s']}s")

    stop_container(container_name)
    return {"image": image_key, "image_ref": image, "port": port, "results": results}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", default="ghcr,old,edge", help="comma-separated list of images to benchmark")
    ap.add_argument("--port-base", type=int, default=8090, help="base port for old/edge (ghcr uses 1235)")
    ap.add_argument("--max-tokens", type=int, default=None, help="override max_tokens for all prompts")
    ap.add_argument("--quick", action="store_true", help="run only the first prompt per image")
    ap.add_argument("--fail-on-degenerate", action="store_true", help="Exit non-zero if any degenerate output detected")
    args = ap.parse_args()

    images = [x.strip() for x in args.images.split(",")]
    ts = time.strftime("%Y%m%d-%H%M%S")
    all_results = {"timestamp": ts, "images": {}}

    for idx, key in enumerate(images):
        port = 1235 if key == "ghcr" else args.port_base + idx
        print(f"\n=== Benchmarking {key} on port {port} ===")
        res = run_image_bench(key, port, args.max_tokens, args.quick)
        all_results["images"][key] = res

    out_path = RUNS / f"bench-containers-{ts}.json"
    out_path.write_text(json.dumps(all_results, indent=2))
    print(f"\n=== Results written to {out_path} ===")

    degenerate_count = 0
    for key, res in all_results["images"].items():
        for r in res.get("results", []) or []:
            if r.get("degenerate"):
                degenerate_count += 1
    if degenerate_count:
        print(f"\nWARNING: {degenerate_count} degenerate response(s) detected")
    if args.fail_on_degenerate and degenerate_count:
        sys.exit(2)

    # Print summary table
    print("\n{:<12} {:<18} {:>10} {:>10} {:>8}".format("Image", "Prompt", "Prefill", "Decode", "Wall"))
    print("-" * 62)
    for key, res in all_results["images"].items():
        if "error" in res:
            print(f"{key:<12} ERROR: {res['error']}")
            continue
        for r in res.get("results", []):
            print("{:<12} {:<18} {:>10} {:>10} {:>8}".format(
                key, r["prompt_name"], r.get("prompt_tps", 0), r.get("decode_tps", 0), r["wall_s"]))

if __name__ == "__main__":
    main()
