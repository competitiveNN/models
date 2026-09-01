#!/usr/bin/env python3
"""Llamacpp launcher — Python replacement for llamacpp.sh with TOML config."""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import tomllib

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.toml")


def load_config(path=CONFIG_PATH):
    with open(path, "rb") as f:
        return tomllib.load(f)


def first_preset_model(presets_path):
    """Return the model path from the first section of a presets INI file.

    Parses as plain text instead of configparser so the top-level
    ``version = N`` line used by llama-server presets doesn't break parsing.
    """
    with open(presets_path) as f:
        text = f.read()
    m = re.search(r"(?m)^\[([^\]]+)\]", text)
    if not m:
        return ""
    block = text[m.end():]
    nm = re.search(r"(?m)^\[", block)
    if nm:
        block = block[:nm.start()]
    for key in ("model", "m"):
        km = re.search(r"(?m)^\s*" + key + r"\s*=\s*(.+?)\s*$", block)
        if km:
            return km.group(1)
    return ""


def preset_model_draft(presets_path, section):
    """Return the model-draft path from a preset section, or '' if absent.

    Plain-text parse so the top-level ``version = N`` line doesn't break it.
    """
    if not presets_path or not section:
        return ""
    try:
        with open(presets_path) as f:
            text = f.read()
    except OSError:
        return ""
    m = re.search(r"(?m)^\[" + re.escape(section) + r"\]", text)
    if not m:
        return ""
    block = text[m.end():]
    nm = re.search(r"(?m)^\[", block)
    if nm:
        block = block[:nm.start()]
    dm = re.search(r"(?m)^\s*model-draft\s*=\s*(.+?)\s*$", block)
    return dm.group(1) if dm else ""


def first_preset_draft_model(presets_path):
    """Return the model-draft of the first preset section that defines one."""
    if not presets_path:
        return ""
    try:
        with open(presets_path) as f:
            text = f.read()
    except OSError:
        return ""
    for m in re.finditer(r"(?m)^\[([^\]]+)\]", text):
        start = m.end()
        nm = re.search(r"(?m)^\[", text[start:])
        end = start + nm.start() if nm else len(text)
        dm = re.search(r"(?m)^\s*model-draft\s*=\s*(.+?)\s*$", text[start:end])
        if dm:
            return dm.group(1)
    return ""


def apply_preset_default(presets_text, section):
    """Return presets text with the given section flagged as both
    load-on-startup and default-model. Works on raw INI text so the top-level
    ``version`` line is preserved. Returns (text, error).
    """
    header = re.compile(r"(?m)^\[" + re.escape(section) + r"\]\s*$")
    m = header.search(presets_text)
    if not m:
        return presets_text, f"section '[{section}]' not found in presets file"
    insert_at = m.end()
    if presets_text[insert_at:insert_at + 1] == "\n":
        insert_at += 1
    rest = presets_text[insert_at:]
    nm = re.search(r"(?m)^\[", rest)
    end = insert_at + nm.start() if nm else len(presets_text)
    block = presets_text[insert_at:end]
    additions = []
    if not re.search(r"(?m)^\s*load-on-startup\s*=", block):
        additions.append("load-on-startup = true")
    if not re.search(r"(?m)^\s*default-model\s*=", block):
        additions.append("default-model = true")
    if not additions:
        return presets_text, None
    new_text = presets_text[:insert_at] + "".join(a + "\n" for a in additions) + presets_text[insert_at:]
    return new_text, None


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
        "-e", "ZES_ENABLE_SYSMAN=1",
        "-e", "GGML_SYCL_ENABLE_OPT=1",
    ]
    for d in devices:
        common.extend(d.split())
    if cpu_mode:
        common.append("-e")
        common.append("GGML_BACKEND=cpu")
    return common


def is_kvarn(value):
    """Return True if value is a KVarN cache type (kvarn2..kvarn8)."""
    return bool(re.fullmatch(r"kvarn[0-9]+", str(value).strip()))


def build_model_args(config, extra_args=None, manual_ctx_size=None, fit_ctx_size=None,
                      use_fit_mode=False, n_gpu_layers="all", n_cpu_moe=0,
                      cpu_mode=False, preserve_thinking=False, reasoning_budget=False,
                      use_presets=False, cache_type_k="", cache_type_v="", kv_tail_tokens="", load_mode="auto"):
    args = []
    if not use_presets:
        model_key = config["defaults"].get("model", "")
        model_path = config.get("model_paths", {}).get(model_key, model_key)
        args.extend([
            "-m", model_path,
            "--alias", config["llama"]["alias"],
        ])
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
    args.extend([
        "-b", str(config["defaults"]["batch_size"]),
        "-ub", str(config["defaults"]["ubatch_size"]),
        "-fa", "on",
        "--reasoning-budget", str(config["defaults"]["reasoning_budget"] if reasoning_budget else 0),
        "--reasoning-budget-message", "\nBased on the analysis above, here is the complete solution:",
        *(["--load-mode", load_mode] if load_mode else []),
        "--context-shift",
        "-lv", str(config["defaults"]["verbosity"]),
    ])
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
    if cache_type_k:
        args.extend(["-ctk", cache_type_k])
    if cache_type_v:
        args.extend(["-ctv", cache_type_v])
    if kv_tail_tokens and is_kvarn(cache_type_k) and is_kvarn(cache_type_v):
        args.extend(["--kv-tail-tokens", str(kv_tail_tokens)])
    if preserve_thinking:
        args.extend(["--chat-template-kwargs", '{"preserve_thinking": true}'])
    return args


def build_spec_args(config, spec_draft_model="", spec_draft_max="", spec_draft_min="",
                    spec_type="ngram-map-k4v", spec_ngram_size_n=24,
                    spec_draft_kv_k="", spec_draft_kv_v="", spec_draft_p_min="",
                    cache_type_k_draft="", cache_type_v_draft="", no_spec=False,
                    ngram_type=None, spec_draft_ngl="", spec_dm_controller="",
                    spec_dflash_cross_ctx=""):
    args = []
    if no_spec:
        return args
    spec_cfg = config.get("spec", {})
    # Default ngram drafter: applied only when no spec type is configured.
    # An explicit spec type list (--spec-type / config) is honored literally,
    # so e.g. ngram-simple is not silently extended with ngram-map-k4v.
    spec_types = [t.strip() for t in (spec_type or "").split(",") if t.strip()]
    if not spec_types:
        spec_types = ["ngram-map-k4v"]
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
    if spec_draft_ngl:
        args.extend(["--spec-draft-ngl", str(spec_draft_ngl)])
    if spec_dm_controller:
        args.extend(["--spec-dm-controller", str(spec_dm_controller)])
    if spec_dflash_cross_ctx:
        args.extend(["--spec-dflash-cross-ctx", str(spec_dflash_cross_ctx)])
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
              spec_draft_max="", spec_draft_min="", spec_type="ngram-map-k4v",
              spec_ngram_size_n=24, spec_draft_kv_k="", spec_draft_kv_v="",
              spec_draft_p_min="", cache_type_k_draft="", cache_type_v_draft="",
              no_spec=False, timeout=3600, reasoning_budget=False,
              spec_draft_ngl="", spec_dm_controller="", spec_dflash_cross_ctx="",
              use_presets=False, presets_path="", presets_local_path="", cache_type_k="", cache_type_v="", kv_tail_tokens="", load_mode="auto"):
    model_args = build_model_args(
        config, extra_args=extra_args, manual_ctx_size=manual_ctx_size,
        fit_ctx_size=fit_ctx_size, use_fit_mode=use_fit_mode,
        n_gpu_layers=n_gpu_layers, n_cpu_moe=n_cpu_moe, cpu_mode=cpu_mode,
        preserve_thinking=preserve_thinking,
        reasoning_budget=reasoning_budget,
        use_presets=use_presets,
        cache_type_k=cache_type_k,
        cache_type_v=cache_type_v,
        kv_tail_tokens=kv_tail_tokens,
        load_mode=load_mode,
    )
    cmd_args = model_args[:]
    spec_cfg = config.get("spec", {})
    spec_args = build_spec_args(
        config,
        spec_draft_model=spec_draft_model or spec_cfg.get("spec_draft_model", ""),
        spec_draft_max=str(spec_draft_max or spec_cfg.get("spec_draft_max", "")),
        spec_draft_min=str(spec_draft_min or spec_cfg.get("spec_draft_min", "")),
        spec_type=spec_type or spec_cfg.get("spec_type", "ngram-map-k4v"),
        spec_ngram_size_n=spec_ngram_size_n or spec_cfg.get("ngram_size_n", 24),
        spec_draft_kv_k=spec_draft_kv_k or spec_cfg.get("spec_draft_kv_k", ""),
        spec_draft_kv_v=spec_draft_kv_v or spec_cfg.get("spec_draft_kv_v", ""),
        spec_draft_p_min=str(spec_draft_p_min) if spec_draft_p_min else str(spec_cfg.get("spec_draft_p_min", spec_cfg.get("spec-draft-p-min", ""))),
        cache_type_k_draft=cache_type_k_draft or spec_cfg.get("cache_type_k_draft", ""),
        cache_type_v_draft=cache_type_v_draft or spec_cfg.get("cache_type_v_draft", ""),
        no_spec=no_spec,
        spec_draft_ngl=spec_draft_ngl or spec_cfg.get("spec_draft_ngl", ""),
        spec_dm_controller=spec_dm_controller or spec_cfg.get("spec_dm_controller", ""),
        spec_dflash_cross_ctx=spec_dflash_cross_ctx or spec_cfg.get("spec_dflash_cross_ctx", "")
    )
    if mode == "server":
        cmd_args.extend(spec_args)
        if use_presets and presets_path:
            cmd_args.extend(["--models-preset", presets_path])
        cmd_args.extend([
            "--host", "0.0.0.0", "--port", "8000", "--timeout", str(timeout)
        ])
        if extra_args:
            cmd_args.extend(extra_args)
    else:
        # Bench mode overrides entrypoint; build bench args
        if use_presets and presets_local_path:
            bench_model = first_preset_model(presets_local_path)
        else:
            bench_model = config["defaults"].get("model", "")
        cmd_args = [
            "-m", bench_model,
            "-b", "2048", "-ub", "512",
            "--reasoning-budget-message", "\nBased on the analysis above, here is the complete solution:",
        ]
        if cache_type_k:
            cmd_args.extend(["-ctk", cache_type_k])
        if cache_type_v:
            cmd_args.extend(["-ctv", cache_type_v])
        if kv_tail_tokens and is_kvarn(cache_type_k) and is_kvarn(cache_type_v):
            cmd_args.extend(["--kv-tail-tokens", str(kv_tail_tokens)])
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
    parser.add_argument("--dflash2", "--dflash", dest="dflash2", action="store_true", help="Enable DFlash/DFlash2 speculative decoding (--spec-type draft-dflash; DFlash2 is auto-detected from the draft model)")
    parser.add_argument("--dspark", action="store_true", help="Enable DSpark speculative decoding (--spec-type draft-dspark)")
    parser.add_argument("--no-spec", action="store_true", help="Disable spec decoding")
    parser.add_argument("--spec-draft-ngl", "-ngld", type=str, default="", dest="spec_draft_ngl", help="Draft model GPU layers for DFlash (e.g. all)")
    parser.add_argument("--spec-dm-controller", type=str, default="", dest="spec_dm_controller", help="DFlash adaptive draft controller (profit|fringe|off)")
    parser.add_argument("--spec-dflash-cross-ctx", type=str, default="", dest="spec_dflash_cross_ctx", help="DFlash cross-attention hidden-state window size")
    parser.add_argument("--pthinking", action="store_true", help="Preserve thinking")
    parser.add_argument("--reasoning-budget", action="store_true", help="Enable reasoning budget")
    parser.add_argument("--gpus", type=str, default="", help="Selected GPUs (comma-separated, e.g. 0,1)")
    parser.add_argument("--draft-model", type=str, default="", help="Draft model path")
    parser.add_argument("--timeout", type=str, default="3600", help="Timeout")
    parser.add_argument("--draft-max", "--spec-draft-n-max", type=str, default="48", dest="draft_max")
    parser.add_argument("--draft-min", "--spec-draft-n-min", type=str, default="12", dest="draft_min")
    parser.add_argument("--spec-type", type=str, default="")
    parser.add_argument("--spec-ngram-map-k-size-n", "--spec-ngram-simple-size-n", "--spec-ngram-size-n", type=str, default="24", dest="spec_ngram_n")
    parser.add_argument("--spec-draft-type-k", "-ctkd", type=str, default="")
    parser.add_argument("--spec-draft-type-v", "-ctvd", type=str, default="")
    parser.add_argument("--cache-type-k", "--ctk", "-ctk", type=str, default="", dest="ctk", help="Target KV cache type (e.g. kvarn5). On beellama, KVarN types enable the precision tail.")
    parser.add_argument("--cache-type-v", "--ctv", "-ctv", type=str, default="", dest="ctv", help="Target KV cache type (e.g. kvarn4). On beellama, KVarN types enable the precision tail.")
    parser.add_argument("--spec-draft-p-min", "--draft-p-min", type=str, default="0.8", dest="spec_draft_p_min")
    parser.add_argument("server", nargs="?", const="server", default=None)
    parser.add_argument("--bench", action="store_true")
    parser.add_argument("--fit-ctx", nargs="?", const="fit-ctx", default=None)
    parser.add_argument("--fit", nargs="?", const="fit", default=None)
    parser.add_argument("--fit-target", "--fitt", nargs="?", const="fit-target", default=None)
    parser.add_argument("--ctx-size", nargs="?", const="ctx-size", default=None)
    parser.add_argument("--show-full-help", action="store_true", help="Show full llama-server help")
    parser.add_argument("--full-help", dest="show_full_help", action="store_true", help="Show full llama-server help")
    args, extra_remaining = parser.parse_known_args()
    if args.show_full_help:
        config = load_config()
        image = config["llama"].get("image", "llama-cpp-intel")
        if args.image:
            image = args.image
        selected_gpus = args.gpus.split(",") if args.gpus else None
        docker_args = build_docker_args(config, selected_gpus=selected_gpus, cpu_mode=args.cpu)
        full_cmd = ["docker", "run"] + docker_args + [image, "--help"]
        subprocess.run(full_cmd)
        sys.exit(0)
    config = load_config()

    # Presets (--models-preset) support
    presets_cfg = config.get("presets", {})
    presets_path = presets_cfg.get("path", "")
    use_presets = bool(presets_path)
    presets_container_path = ""
    presets_default = presets_cfg.get("default", "")
    presets_abs = ""
    if use_presets:
        if not os.path.isabs(presets_path):
            presets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), presets_path)
        presets_abs = os.path.abspath(presets_path)
        presets_dir = os.path.dirname(presets_abs)
        presets_name = os.path.basename(presets_abs)
        presets_container_path = f"/presets/{presets_name}"
        # Build the served preset copy. Strip model-draft from sections when no
        # drafter that needs an external draft model (--dflash/--dspark) is
        # active, so llama-server does not auto-load the draft model (which
        # would make MTP try to load layers from it).
        with open(presets_abs) as f:
            presets_text = f.read()
        modified = False
        if presets_default:
            presets_text, err = apply_preset_default(presets_text, presets_default)
            if err:
                print(f"error: {err}", file=sys.stderr)
                sys.exit(2)
            modified = True
        if not (args.dspark or args.dflash2):
            stripped = re.sub(r"(?m)^\s*model-draft\s*=.*\n?", "", presets_text)
            if stripped != presets_text:
                presets_text = stripped
                modified = True
        if modified:
            tmp_dir = tempfile.mkdtemp(prefix="llamacpp-presets-")
            tmp_path = os.path.join(tmp_dir, presets_name)
            with open(tmp_path, "w") as f:
                f.write(presets_text)
            presets_dir = tmp_dir

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

    # Resolve the spec type default (CLI > config > built-in) before MTP
    # pairing below, so the default ngram drafter combines with MTP while
    # explicit values pass through untouched.
    args.spec_type = args.spec_type or config.get("spec", {}).get("spec_type", "") or "ngram-map-k4v"

    # Pick a single draft-model spec type. llama.cpp allows at most one draft
    # type combined with one ngram type, so the drafter flags are mutually
    # exclusive: dspark > dflash > mtp.
    chosen_draft = None
    if args.dspark:
        chosen_draft = "draft-dspark"
    elif args.dflash2:
        chosen_draft = "draft-dflash"
    elif args.mtp:
        chosen_draft = "draft-mtp"

    spec_draft_model = args.draft_model or config.get("spec", {}).get("spec_draft_model", "")

    if chosen_draft == "draft-mtp":
        spec_draft_model = "1"
        args.draft_max = "3"
        args.draft_min = "0"
        args.spec_draft_type_k = "q4_0"
        args.spec_draft_type_v = "q4_0"
        args.spec_draft_p_min = "0.75"
    elif chosen_draft == "draft-dflash":
        if not spec_draft_model or spec_draft_model == "1":
            print("error: --dflash requires a draft model (use --draft-model)", file=sys.stderr)
            sys.exit(2)
    elif chosen_draft == "draft-dspark":
        # Draft model comes from the preset (models.ini model-draft) so it
        # tracks the served model; --draft-model overrides it on the CLI.
        # Fall back to the first section with a model-draft when no default is set.
        spec_draft_model = (spec_draft_model
                            or preset_model_draft(presets_abs, presets_default)
                            or first_preset_draft_model(presets_abs))
        if not spec_draft_model or spec_draft_model == "1":
            print("error: --dspark requires a draft model (set model-draft in the served preset or use --draft-model)", file=sys.stderr)
            sys.exit(2)
        # DSpark block size is 7 per the model card; propose up to 7 draft tokens.
        args.draft_max = "7"
        args.draft_min = "0"
    else:
        # No drafter that uses an external draft model; never load one.
        spec_draft_model = ""

    # Build the spec type list: one chosen drafter plus the base ngram. When a
    # drafter flag is active, force the base ngram to ngram-map-k4v.
    spec_types = [t.strip() for t in args.spec_type.split(",") if t.strip()] if args.spec_type else []
    if chosen_draft:
        spec_types = [t for t in spec_types
                      if not t.startswith("ngram-")
                      and t not in ("draft-dspark", "draft-dflash", "draft-mtp")]
        spec_types.insert(0, chosen_draft)
        spec_types.append("ngram-map-k4v")
    args.spec_type = ",".join(spec_types)

    if not args.mtp:
        # Normalize kvarn-based quantization for draft cache types to q*_0 when MTP is disabled
        for field in ("spec_draft_type_k", "spec_draft_type_v"):
            val = getattr(args, field)
            if isinstance(val, str):
                m = re.match(r'^kvarn(\d+)', val)
                if m:
                    setattr(args, field, f'q{m.group(1)}_0')

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

    # Tensor split mode distributes the model across GPUs, so the single-GPU
    # "fit" context sizing does not apply. Drop all --fit-* arguments then.
    split_mode_tensor = False
    for i, tok in enumerate(extra_remaining):
        if tok == "--split-mode" and i + 1 < len(extra_remaining) and extra_remaining[i + 1] == "tensor":
            split_mode_tensor = True
        elif tok.startswith("--split-mode=") and tok.split("=", 1)[1] == "tensor":
            split_mode_tensor = True
    if split_mode_tensor:
        use_fit_mode = False
        extra_args_for_fit = []

    # Preserve thinking
    preserve_thinking = args.pthinking

    # Timeout
    timeout = int(args.timeout) if args.timeout else 3600

    # beellama-only precision tail (KV cache exact suffix); only meaningful for
    # the beellama ("bee intel") build. Leave empty for a plain llama.cpp image.
    bee_cfg = config.get("beellama", {})
    kv_tail = str(bee_cfg.get("kv_tail_tokens", "")).strip()
    cache_type_k = (args.ctk or str(bee_cfg.get("cache_type_k", ""))).strip()
    cache_type_v = (args.ctv or str(bee_cfg.get("cache_type_v", ""))).strip()

    # Detect user-supplied --load-mode in extra args to override the default
    load_mode = "auto"
    for i, tok in enumerate(extra_remaining):
        if tok == "--load-mode" and i + 1 < len(extra_remaining):
            load_mode = extra_remaining[i + 1]
            break
        elif tok.startswith("--load-mode="):
            load_mode = tok.split("=", 1)[1]
            break

    # Build args
    docker_args = build_docker_args(config, selected_gpus=selected_gpus, cpu_mode=cpu_mode)
    if use_presets:
        docker_args.extend(["-v", f"{presets_dir}:/presets"])
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
        spec_draft_ngl=args.spec_draft_ngl,
        spec_dm_controller=args.spec_dm_controller,
        spec_dflash_cross_ctx=args.spec_dflash_cross_ctx,
        use_presets=use_presets,
        presets_path=presets_container_path,
        presets_local_path=presets_abs if use_presets else "",
        cache_type_k=cache_type_k,
        cache_type_v=cache_type_v,
        kv_tail_tokens=kv_tail,
        load_mode=load_mode,
    )

    # If bench mode, replace cmd_args with bench-specific values
    if mode == "bench":
        if use_presets and presets_path:
            bench_model = first_preset_model(presets_path)
        else:
            bench_model = config["defaults"].get("model", "")
        cmd_args = [
            "-m", bench_model,
            "-b", "2048", "-ub", "512",
            "--reasoning-budget-message", "\nBased on the analysis above, here is the complete solution:",
        ]
        if cache_type_k:
            cmd_args.extend(["-ctk", cache_type_k])
        if cache_type_v:
            cmd_args.extend(["-ctv", cache_type_v])
        if kv_tail and is_kvarn(cache_type_k) and is_kvarn(cache_type_v):
            cmd_args.extend(["--kv-tail-tokens", kv_tail])
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
            spec_draft_ngl=args.spec_draft_ngl,
            spec_dm_controller=args.spec_dm_controller,
            spec_dflash_cross_ctx=args.spec_dflash_cross_ctx,
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
