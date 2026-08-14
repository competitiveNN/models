#!/usr/bin/env python3
"""Llamacpp launcher — Python replacement for llamacpp.sh with TOML config."""
import argparse
import os
import re
import subprocess
import sys
import tomllib

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.toml")


def load_config(path=CONFIG_PATH):
    with open(path, "rb") as f:
        return tomllib.load(f)


def parse_ctx_size(value):
    """Parse a context size like '64k' or '4m' into a token count."""
    m = re.fullmatch(r"([0-9]+)([kmKM]?)", str(value))
    if not m:
        return value
    num = int(m.group(1))
    suffix = m.group(2).lower()
    if suffix == "k":
        return num * 1024
    if suffix == "m":
        return num * 1024 * 1024
    return num


def parse_size_value(value):
    """Parse a size like '512m' or '2g' into bytes."""
    m = re.fullmatch(r"([0-9]+)([kmgKMG]?)", str(value))
    if not m:
        return value
    num = int(m.group(1))
    suffix = m.group(2).lower()
    if suffix == "k":
        return num * 1024
    if suffix == "m":
        return num * 1024 * 1024
    if suffix == "g":
        return num * 1024 * 1024 * 1024
    return num


def build_docker_args(config, selected_gpus=None, cpu_mode=False):
    cfg_llama = config.get("llama", {})
    devices = cfg_llama.get("gpu", {}).get("devices", [
        "--device /dev/dri/card0 --device /dev/dri/renderD128",
        "--device /dev/dri/card1 --device /dev/dri/renderD129",
        "--device /dev/accel",
    ])
    if selected_gpus is not None:
        devices = []
        for g in selected_gpus:
            if g == "0":
                devices.append("--device /dev/dri/card0 --device /dev/dri/renderD128")
            elif g == "1":
                devices.append("--device /dev/dri/card1 --device /dev/dri/renderD129")
    common = [
        "--net=host",
        "--security-opt", "label=disable",
        "-it", "--rm",
        "-v", f"{os.path.expandvars(cfg_llama.get('models_path', '$HOME/data/models/gguf'))}:/models",
        "--name", "llama-server",
    ]
    for d in devices:
        common.extend(d.split())
    if cpu_mode:
        common.append("-e")
        common.append("GGML_BACKEND=cpu")
    return common


def build_model_args(config, extra_args=None, manual_ctx_size=None, fit_ctx_size=None,
                     use_fit_mode=False, n_gpu_layers="all", n_cpu_moe=0,
                     cpu_mode=False, preserve_thinking=False, reasoning_budget=False):
    model_key = config["defaults"].get("model", "")
    model_path = config.get("model_paths", {}).get(model_key, model_key)
    args = [
        "-m", model_path,
        "-b", str(config["defaults"]["batch_size"]),
        "-ub", str(config["defaults"]["ubatch_size"]),
        "--alias", config["llama"]["alias"],
        "-fa", "on",
        "--reasoning-budget", str(config["defaults"]["reasoning_budget"] if reasoning_budget else 0),
        "--reasoning-budget-message", "\nBased on the analysis above, here is the complete solution:",
        "--no-mmap",
        "-lv", str(config["defaults"]["verbosity"]),
    ]
    # Auto-detect jinja template (use resolved model_path, not config key)
    resolved_path = model_path
    model_dir = os.path.dirname(resolved_path)
    base_path = os.path.expandvars(config["llama"].get("models_path", "$HOME/data/models/gguf"))
    jinja_dir = model_dir.lstrip("/")
    if jinja_dir and not jinja_dir.endswith("/"):
     jinja_dir += "/"
    jinja_path = os.path.join(base_path, jinja_dir, "chat_template.jinja")
    if not os.path.isfile(jinja_path):
     jinja_path = os.path.join(base_path, "chat_template.jinja")
    if os.path.isfile(jinja_path):
        args.append("--chat-template-file")
        args.append(jinja_path)  # jinja_path already has correct /models/ prefix
    # GPU layers
    if use_fit_mode:
        pass
    elif cpu_mode:
        args.extend(["--n-gpu-layers", "0"])
    elif n_gpu_layers == "all":
        args.extend(["--n-gpu-layers", "-1"])
    elif n_gpu_layers is not None:
        args.extend(["--n-gpu-layers", str(n_gpu_layers)])
    args.extend(["--n-cpu-moe", str(n_cpu_moe)])
    args.extend(["--threads", str(config["defaults"].get("threads", 8))])
    # Context size
    if manual_ctx_size is not None:
        args.extend(["--ctx-size", str(manual_ctx_size)])
    elif fit_ctx_size is not None:
        args.extend(["--ctx-size", str(fit_ctx_size)])
    elif not use_fit_mode:
        args.extend(["--ctx-size", str(config["defaults"].get("ctx_size", 16384))])
    if preserve_thinking:
        args.extend(["--chat-template-kwargs", '{"preserve_thinking": true}'])
    return args


def build_spec_args(config, spec_draft_model="", spec_draft_max="", spec_draft_min="",
                    spec_type="ngram-simple", spec_ngram_size_n=24,
                    spec_draft_kv_k="", spec_draft_kv_v="", spec_draft_p_min="",
                    cache_type_k_draft="", cache_type_v_draft="", no_spec=False,
                    ngram_type=None):
    args = []
    if no_spec:
        return args
    spec_cfg = config.get("spec", {})
    # ngram-simple is always enabled: it is only disabled when --no-spec is
    # passed. Add it to the spec type list even when MTP or another draft type
    # is in use, so it is never silently dropped.
    spec_types = [t.strip() for t in (spec_type or "ngram-simple").split(",") if t.strip()]
    if "ngram-simple" not in spec_types:
        spec_types.append("ngram-simple")
    spec_type = ",".join(spec_types)
    if spec_draft_model and spec_draft_model != "1":
        args.extend(["--model-draft", spec_draft_model])
    if spec_draft_max:
        args.extend(["--spec-draft-n-max", str(spec_draft_max)])
    if spec_draft_min:
        args.extend(["--spec-draft-n-min", str(spec_draft_min)])
    if spec_type:
        args.extend(["--spec-type", spec_type])
    if spec_draft_kv_k:
        args.extend(["--spec-draft-type-k", spec_draft_kv_k])
    if spec_draft_kv_v:
        args.extend(["--spec-draft-type-v", spec_draft_kv_v])
    if spec_draft_p_min:
        args.extend(["--spec-draft-p-min", spec_draft_p_min])
    if cache_type_k_draft:
        args.extend(["--cache-type-k-draft", cache_type_k_draft])
    if cache_type_v_draft:
        args.extend(["--cache-type-v-draft", cache_type_v_draft])
    if spec_ngram_size_n and spec_type:
        for spec_type_i in [t.strip() for t in spec_type.split(",") if t.strip()]:
            if spec_type_i == "ngram-simple":
                args.extend(["--spec-ngram-simple-size-n", str(spec_ngram_size_n)])
            elif spec_type_i == "ngram-map-k":
                args.extend(["--spec-ngram-map-k-size-n", str(spec_ngram_size_n)])
            elif spec_type_i == "ngram-map-k4v":
                args.extend(["--spec-ngram-map-k4v-size-n", str(spec_ngram_size_n)])
            elif spec_type_i == "ngram-mod":
                args.extend(["--spec-ngram-mod-n-match", str(spec_ngram_size_n)])
    return args


def build_cmd(config, mode="bench", extra_args=None, manual_ctx_size=None,
             fit_ctx_size=None, use_fit_mode=False, n_gpu_layers="all",
             n_cpu_moe=0, cpu_mode=False, preserve_thinking=False,
             spec_draft_model="",
             spec_draft_max="", spec_draft_min="", spec_type="ngram-simple",
             spec_ngram_size_n=24, spec_draft_kv_k="", spec_draft_kv_v="",
             spec_draft_p_min="", cache_type_k_draft="", cache_type_v_draft="",
             no_spec=False, timeout=3600, reasoning_budget=False):
    model_args = build_model_args(
        config, extra_args=extra_args, manual_ctx_size=manual_ctx_size,
        fit_ctx_size=fit_ctx_size, use_fit_mode=use_fit_mode,
        n_gpu_layers=n_gpu_layers, n_cpu_moe=n_cpu_moe, cpu_mode=cpu_mode,
        preserve_thinking=preserve_thinking,
        reasoning_budget=reasoning_budget,
    )
    cmd_args = model_args[:]
    spec_cfg = config.get("spec", {})
    spec_args = build_spec_args(
        config,
        spec_draft_model=spec_draft_model or spec_cfg.get("spec_draft_model", ""),
        spec_draft_max=str(spec_draft_max or spec_cfg.get("spec_draft_max", "")),
        spec_draft_min=str(spec_draft_min or spec_cfg.get("spec_draft_min", "")),
        spec_type=spec_type or spec_cfg.get("spec_type", "ngram-simple"),
        spec_ngram_size_n=spec_ngram_size_n or spec_cfg.get("ngram_size_n", 24),
        spec_draft_kv_k=spec_draft_kv_k or spec_cfg.get("spec_draft_kv_k", ""),
        spec_draft_kv_v=spec_draft_kv_v or spec_cfg.get("spec_draft_kv_v", ""),
        spec_draft_p_min=str(spec_draft_p_min) if spec_draft_p_min else str(spec_cfg.get("spec_draft_p_min", spec_cfg.get("spec-draft-p-min", ""))),
        cache_type_k_draft=cache_type_k_draft or spec_cfg.get("cache_type_k_draft", ""),
        cache_type_v_draft=cache_type_v_draft or spec_cfg.get("cache_type_v_draft", ""),
        no_spec=no_spec
    )
    if mode == "server":
        cmd_args.extend(spec_args)
        cmd_args.extend([
            "--host", "0.0.0.0", "--port", "8000", "--timeout", str(timeout)
        ])
        if extra_args:
            cmd_args.extend(extra_args)
    else:
        # Bench mode overrides entrypoint; build bench args
        cmd_args = [
            "-m", config["defaults"]["model"],
            "-b", "2048", "-ub", "512",
            "--reasoning-budget-message", "\nBased on the analysis above, here is the complete solution:",
        ]
        if reasoning_budget:
            cmd_args.extend(["--reasoning-budget", str(config["defaults"].get("reasoning_budget", 0))])
        if not use_fit_mode and n_gpu_layers is not None and n_gpu_layers != "all":
            cmd_args.extend(["--n-gpu-layers", str(n_gpu_layers)])
        if preserve_thinking:
            cmd_args.extend(["--chat-template-kwargs", '{"preserve_thinking": true}'])
        cmd_args.extend(spec_args)
        if extra_args:
            cmd_args.extend(extra_args)
    return cmd_args


def main():
    # Use parse_known_args() so unrecognized args (like -np, extra flags) are preserved
    # and forwarded to the container binary like bash EXTRA_ARGS
    parser = argparse.ArgumentParser(description="Llamacpp launcher")
    parser.add_argument("--cpu", action="store_true", help="CPU mode")
    parser.add_argument("--image", type=str, default="", help="Target image (e.g. localhost/bee-llama-cpp-intel)")
    parser.add_argument("--ngl", type=str, default="all", help="GPU layers")
    parser.add_argument("--moe", type=str, default="0", help="CPU MOE layers")
    parser.add_argument("--detect", action="store_true", help="Auto-detect memory")
    parser.add_argument("--mtp", action="store_true", help="Enable MTP")
    parser.add_argument("--no-spec", action="store_true", help="Disable spec decoding")
    parser.add_argument("--pthinking", action="store_true", help="Preserve thinking")
    parser.add_argument("--reasoning-budget", action="store_true", help="Enable reasoning budget")
    parser.add_argument("--gpus", type=str, default="", help="Selected GPUs (comma-separated, e.g. 0,1)")
    parser.add_argument("--draft-model", type=str, default="", help="Draft model path")
    parser.add_argument("--timeout", type=str, default="3600", help="Timeout")
    parser.add_argument("--draft-max", "--spec-draft-n-max", type=str, default="48", dest="draft_max")
    parser.add_argument("--draft-min", "--spec-draft-n-min", type=str, default="12", dest="draft_min")
    parser.add_argument("--spec-type", type=str, default="ngram-simple")
    parser.add_argument("--spec-ngram-map-k-size-n", "--spec-ngram-simple-size-n", "--spec-ngram-size-n", type=str, default="24", dest="spec_ngram_n")
    parser.add_argument("--spec-draft-type-k", "-ctkd", type=str, default="")
    parser.add_argument("--spec-draft-type-v", "-ctvd", type=str, default="")
    parser.add_argument("--spec-draft-p-min", "--draft-p-min", type=str, default="0.8", dest="spec_draft_p_min")
    parser.add_argument("server", nargs="?", const="server", default=None)
    parser.add_argument("--bench", action="store_true")
    parser.add_argument("--fit-ctx", nargs="?", const="fit-ctx", default=None)
    parser.add_argument("--fit", nargs="?", const="fit", default=None)
    parser.add_argument("--fit-target", "--fitt", nargs="?", const="fit-target", default=None)
    parser.add_argument("--ctx-size", nargs="?", const="ctx-size", default=None)
    parser.add_argument("--show-full-help", action="store_true", help="Show full llama-server help")
    args, extra_remaining = parser.parse_known_args()
    if args.show_full_help:
        parser.print_help()
        sys.exit(0)

    # Load config before any access
    config = load_config()

    # Resolve mode
    mode = "bench"
    if args.server == "server":
        mode = "server"
    elif args.bench:
        mode = "bench"

    # Resolve image
    image = config["llama"].get("image", "llama-cpp-intel")
    # Image override based on args
    if args.image:
        image = args.image

    # CPU mode
    cpu_mode = args.cpu

    # GPU layers
    n_gpu_layers = args.ngl
    if cpu_mode:
        n_gpu_layers = "0"

    # GPUs
    selected_gpus = args.gpus.split(",") if args.gpus else None

    # MTP
    mtp = args.mtp
    spec_draft_model = args.draft_model or config.get("spec", {}).get("spec_draft_model", "")
    if mtp:
        spec_draft_model = "1"
        # Keep ngram-based spec enabled: add MTP alongside, don't replace the spec type
        spec_types = [t.strip() for t in args.spec_type.split(",") if t.strip()] if args.spec_type else []
        if "draft-mtp" not in spec_types:
            spec_types.insert(0, "draft-mtp")
        args.spec_type = ",".join(spec_types)
        args.draft_max = "3"
        args.draft_min = "0"
        args.spec_draft_type_k = "q4_0"
        args.spec_draft_type_v = "q4_0"
        args.spec_draft_p_min = "0.75"
        # Add extra MTP args handled by build_spec_args

    # Detect
    detect = args.detect
    # Note: detect functionality (calculate_ngl) omitted for brevity; would call external logic
    if detect and not cpu_mode:
        print("Detected optimal N_GPU_LAYERS: (not implemented in Python version)")
        # Would compute and exit like bash version

    # Fit / ctx
    manual_ctx_size = None
    fit_ctx_size = None
    use_fit_mode = False
    extra_args_for_fit = []
    if args.fit_ctx is not None:
        use_fit_mode = True
        extra_args_for_fit.append("--fit-ctx")
        if args.fit_ctx != "fit-ctx":
            fit_ctx_size = parse_ctx_size(args.fit_ctx)
            extra_args_for_fit.append(str(fit_ctx_size))
        else:
            extra_args_for_fit.append("4096")
    if args.fit is not None:
        use_fit_mode = True
        extra_args_for_fit.append("--fit")
        if args.fit != "fit":
            extra_args_for_fit.append(str(args.fit))
    if args.fit_target is not None:
        use_fit_mode = True
        extra_args_for_fit.append("--fit-target")
        if args.fit_target != "fit-target":
            if re.search(r"[kmgKMG]$", str(args.fit_target)):
                size_mib = parse_size_value(args.fit_target) // (1024 * 1024)
            else:
                size_mib = int(args.fit_target)
            extra_args_for_fit.append(str(size_mib))
    if args.ctx_size is not None and args.ctx_size != "ctx-size":
        manual_ctx_size = parse_ctx_size(args.ctx_size)

    # Preserve thinking
    preserve_thinking = args.pthinking

    # Timeout
    timeout = int(args.timeout) if args.timeout else 3600

    # Build args
    docker_args = build_docker_args(config, selected_gpus=selected_gpus, cpu_mode=cpu_mode)
    # Override image in docker run
    cmd_args = build_cmd(
        config,
        mode=mode,
        extra_args=extra_args_for_fit,
        manual_ctx_size=manual_ctx_size,
        fit_ctx_size=fit_ctx_size,
        use_fit_mode=use_fit_mode,
        n_gpu_layers=n_gpu_layers,
        n_cpu_moe=int(args.moe) if args.moe else 0,
        cpu_mode=cpu_mode,
        preserve_thinking=preserve_thinking,
        spec_draft_model=spec_draft_model,
        spec_draft_max=args.draft_max,
        spec_draft_min=args.draft_min,
        spec_type=args.spec_type,
        spec_ngram_size_n=int(args.spec_ngram_n) if args.spec_ngram_n else 24,
        spec_draft_kv_k=args.spec_draft_type_k,
        spec_draft_kv_v=args.spec_draft_type_v,
        spec_draft_p_min=args.spec_draft_p_min,
        no_spec=args.no_spec,
        timeout=timeout,
        reasoning_budget=args.reasoning_budget,
    )

    # If bench mode, replace cmd_args with bench-specific values
    if mode == "bench":
        cmd_args = [
            "-m", config["defaults"]["model"],
            "-b", "2048", "-ub", "512",
            "--reasoning-budget-message", "\nBased on the analysis above, here is the complete solution:",
        ]
        if not use_fit_mode and n_gpu_layers is not None and n_gpu_layers != "all":
            cmd_args.extend(["--n-gpu-layers", str(n_gpu_layers)])
        if preserve_thinking:
            cmd_args.extend(["--chat-template-kwargs", '{"preserve_thinking": true}'])
        spec_args = build_spec_args(
            config,
            spec_draft_model=spec_draft_model,
            spec_draft_max=args.draft_max,
            spec_draft_min=args.draft_min,
            spec_type=args.spec_type,
            spec_ngram_size_n=int(args.spec_ngram_n) if args.spec_ngram_n else 24,
            spec_draft_kv_k=args.spec_draft_type_k,
            spec_draft_kv_v=args.spec_draft_type_v,
            spec_draft_p_min=args.spec_draft_p_min,
            cache_type_k_draft="",
            cache_type_v_draft="",
            no_spec=args.no_spec,
        )
        cmd_args.extend(spec_args)
        if extra_args_for_fit:
            cmd_args.extend(extra_args_for_fit)

    full_cmd = ["docker", "run"] + docker_args
    if mode != "server" and not args.cpu:
        # bench mode entrypoint override handled by entrypoint param
        # For server: use default entrypoint (llama-server)
        # For bench: override entrypoint to llama-bench
        full_cmd.extend(["--entrypoint", "/app/llama-bench"])
    else:
        # server mode: keep default entrypoint
        pass
    full_cmd.extend([image])
    full_cmd.extend(cmd_args)
    # Forward any remaining unparsed args (like bash EXTRA_ARGS / -np, -ctv) to container
    if extra_remaining:
        for item in extra_remaining:
            if item is not None and item != '':
                full_cmd.append(str(item))

    print(f"{'llama-server' if mode == 'server' else 'llama-bench'} command:")
    # Single-line output (no %q quoting, no per-item newlines)
    print(" ".join(str(arg) for arg in cmd_args))
    # Also include forwarded extra args in the line
    if extra_remaining:
        extra_str = " ".join(str(x) for x in extra_remaining if x is not None and x != '')
        if extra_str:
            print(" (extra: " + extra_str + ")")
    subprocess.run(full_cmd)


if __name__ == "__main__":
    main()
