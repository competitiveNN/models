#!/usr/bin/env python3
"""Grimoire launcher — Python replacement for manual docker run, with TOML config
for per-model env vars and flag overrides. Mirrors the llamacpp.py pattern.

Usage:
  ./grimoire.py server MODEL_ALIAS
  ./grimoire.py generate MODEL_ALIAS [-p PROMPT] [-n N]
  ./grimoire.py list
  ./grimoire.py show MODEL_ALIAS   (print the docker command without running)
"""
import argparse
import os
import subprocess
import sys
import tomllib

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.toml")


def load_config(path=CONFIG_PATH):
    with open(path, "rb") as f:
        return tomllib.load(f)


def build_docker_args(config):
    cfg = config.get("grimoire", {})
    devices = config.get("devices", {})
    env = config.get("env", {})

    args = [
        "--rm",
        "--init",
        "--net=host",
        "--stop-timeout", "600",
        "--name", cfg.get("container_name", "grimoire-server"),
        "--security-opt", "label=disable",
    ]

    # GPU devices
    if devices.get("render_0"):
        args += ["--device", devices["render_0"]]
    if devices.get("render_1"):
        args += ["--device", devices["render_1"]]
    if devices.get("by_path"):
        args += ["-v", f"{devices['by_path']}:{devices['by_path']}:ro"]

    # Volumes: model dir + cache
    models_path = cfg.get("models_path", "/var/home/fra/data/models/safetensors")
    args += ["-v", f"{models_path}:/models:ro"]
    args += ["-v", "grimoire-cache:/cache"]

    # Shared memory
    shm = cfg.get("shm_size", "2gb")
    args += ["--shm-size", shm]

    # Environment
    for key, val in env.items():
        args += ["-e", f"{key}={val}"]

    return args


def build_model_args(model_cfg, config, mode="server"):
    """Build the grimoire-server/multi arguments for a model."""
    model_path = model_cfg["model"]
    proj = model_cfg.get("proj", "int4")
    ctx = model_cfg.get("ctx", config["grimoire"].get("default_ctx", 4096))
    port = str(model_cfg.get("port", config["grimoire"].get("port", 8000)))

    args = ["multi", "--model", model_path, "--proj", proj, "--ctx", str(ctx), "--port", port]

    # NVFP4 / MoE flags (these ARE passed to grimoire-server binary)
    if model_cfg.get("defer_moe_gather"):
        args += ["--defer-moe-gather"]
    if model_cfg.get("bf16_qkv"):
        args += ["--bf16-qkv"]
    if model_cfg.get("bf16_dn_qkv"):
        args += ["--bf16-dn-qkv"]

    # NOTE: pp_split, mtp, mtp_k, mtp_draft_vocab are handled via env vars
    # by the docker-entrypoint.sh, NOT as CLI args to grimoire-server
    return args


def build_cmd(config, model_alias, mode="server", extra_args=None):
    models = config.get("models", {})
    if model_alias not in models:
        print(f"error: model '{model_alias}' not found in config", file=sys.stderr)
        print(f"available models: {', '.join(models.keys())}", file=sys.stderr)
        sys.exit(1)

    model_cfg = models[model_alias]
    if extra_args:
        model_cfg = dict(model_cfg)
        model_cfg.update(extra_args)

    docker_args = build_docker_args(config)

    # With --net=host the container shares the host network namespace, so
    # the server's --port is reachable directly on the host.  No -p mapping.

    # Per-model env overrides
    model_env = model_cfg.get("env", {})
    for key, val in model_env.items():
        docker_args += ["-e", f"{key}={val}"]

    # Per-model pp_split as env
    if model_cfg.get("pp_split"):
        docker_args += ["-e", f"GRIMOIRE_PP_SPLIT={model_cfg['pp_split']}"]
    if model_cfg.get("mtp"):
        docker_args += ["-e", "GRIMOIRE_MTP=1"]
        if model_cfg.get("mtp_k"):
            docker_args += ["-e", f"GRIMOIRE_MTP_K={model_cfg['mtp_k']}"]
        if model_cfg.get("mtp_draft_vocab"):
            docker_args += ["-e", f"GRIMOIRE_MTP_DRAFT_VOCAB={model_cfg['mtp_draft_vocab']}"]
    if model_cfg.get("defer_moe_gather"):
        docker_args += ["-e", "GRIMOIRE_DEFER_MOE_GATHER=1"]
    if model_cfg.get("bf16_qkv"):
        docker_args += ["-e", "GRIMOIRE_BF16_QKV=1"]

    # shm_size override per model
    if model_cfg.get("shm_size"):
        # Replace default shm_size
        for i, a in enumerate(docker_args):
            if a == "--shm-size":
                docker_args[i + 1] = model_cfg["shm_size"]
                break

    image = config["grimoire"]["image"]

    if mode == "server":
        cmd_args = build_model_args(model_cfg, config, mode="server")
        full_cmd = ["docker", "run"] + docker_args + [image] + cmd_args
    elif mode == "generate":
        prompt = model_cfg.get("prompt", "")
        ntok = model_cfg.get("n", 64)
        cmd_args = [
            "multi", "--model", model_cfg["model"],
            "--proj", model_cfg.get("proj", "int4"),
            "--ctx", str(ctx),
            "-p", prompt, "-n", str(ntok),
        ]
        if model_cfg.get("pp_split"):
            cmd_args += ["--pp-split", str(model_cfg["pp_split"])]
        full_cmd = ["docker", "run"] + docker_args + [image] + cmd_args
    else:
        full_cmd = ["docker", "run"] + docker_args + [image]

    return full_cmd


def main():
    parser = argparse.ArgumentParser(
        description="Grimoire launcher for Intel Arc B580 multi-GPU inference",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("mode", nargs="?", choices=["server", "generate", "list", "show"],
                        default="server")
    parser.add_argument("model", nargs="?", default="")
    parser.add_argument("-p", "--prompt", type=str, default="", help="Prompt for generate mode")
    parser.add_argument("-n", "--n-tokens", type=int, default=None, help="Max tokens for generate")
    parser.add_argument("-c", "--ctx", type=int, default=None, help="Override context size")
    parser.add_argument("-P", "--port", type=int, default=None, help="Override host port")
    parser.add_argument("--dry-run", action="store_true", help="Print command without executing")
    parser.add_argument("--bench", action="store_true", help="One-shot generate (alias for 'generate')")
    args, extra_remaining = parser.parse_known_args()

    config = load_config()
    models = config.get("models", {})

    if args.mode == "list":
        print("Available models:")
        for name, cfg in models.items():
            print(f"  {name}: {cfg.get('proj', 'int4')} ctx={cfg.get('ctx', 4096)} "
                  f"pp_split={cfg.get('pp_split', '-')} mtp={cfg.get('mtp', False)}")
        sys.exit(0)

    if not args.model:
        if models:
            args.model = list(models.keys())[0]
        else:
            print("error: no models configured", file=sys.stderr)
            sys.exit(1)

    if args.model not in models:
        print(f"error: model '{args.model}' not in config", file=sys.stderr)
        print(f"available: {', '.join(models.keys())}", file=sys.stderr)
        sys.exit(1)

    # Apply overrides
    extra = dict(models[args.model])
    if args.ctx:
        extra["ctx"] = args.ctx
    if args.port:
        extra["port"] = args.port
    if args.n_tokens:
        extra["n"] = args.n_tokens
    if args.prompt:
        extra["prompt"] = args.prompt

    mode = "generate" if args.bench else args.mode

    if mode == "show" or args.dry_run:
        full_cmd = build_cmd(config, args.model, mode="server", extra_args=extra)
        print("grimoire-server command:")
        print(" ".join(str(a) for a in full_cmd[1:]))  # skip "docker"
        sys.exit(0)

    if mode == "generate":
        # One-shot generate doesn't bind a port; use generate entrypoint
        model_cfg = dict(models[args.model])
        model_cfg["prompt"] = args.prompt or model_cfg.get("prompt", "")
        if args.n_tokens:
            model_cfg["n"] = args.n_tokens
        model_cfg["ctx"] = args.ctx or model_cfg.get("ctx", 4096)
        if args.port:
            model_cfg["port"] = args.port

        gen_args = ["multi", "--model", model_cfg["model"],
                    "--proj", model_cfg.get("proj", "int4"),
                    "--ctx", str(model_cfg["ctx"]),
                    "-p", model_cfg["prompt"], "-n", str(model_cfg.get("n", 64))]
        if model_cfg.get("pp_split"):
            gen_args += ["--pp-split", str(model_cfg["pp_split"])]

        # Rebuild docker args without -p port binding for generate
        docker_args = build_docker_args(config)
        # Per-model env
        for key, val in model_cfg.get("env", {}).items():
            docker_args += ["-e", f"{key}={val}"]
        if model_cfg.get("pp_split"):
            docker_args += ["-e", f"GRIMOIRE_PP_SPLIT={model_cfg['pp_split']}"]

        image = config["grimoire"]["image"]
        full_cmd = ["docker", "run"] + docker_args + [image] + gen_args

    if mode == "server":
        full_cmd = build_cmd(config, args.model, mode="server", extra_args=extra)

    print(f"Starting grimoire-server: {args.model}")
    subprocess.run(full_cmd)


if __name__ == "__main__":
    main()
