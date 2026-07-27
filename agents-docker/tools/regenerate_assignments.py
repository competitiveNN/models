#!/usr/bin/env python3
"""
Regenerate Hermes auxiliary task model assignments.

Reads:
  - fetch-free-models.py   (OLLAMA_FREE_MODELS, OPENCODE_FREE_MODELS_CTX)
  - python fetch-free-models.py --kilocode-only --json
  - NVIDIA NIM via `curl https://integrate.api.nvidia.com/v1/models`

Produces:
  - MODEL_RANKING.md (browsable reference)
  - /tmp/auxiliary_yaml.yaml (drop-in auxiliary: block for ~/.hermes/config.yaml)
  - /tmp/assignments.json (programmatic form)

Run from the repo root:
    python3 tools/regenerate_assignments.py

Override the providers used:
    python3 tools/regenerate_assignments.py --skip-nim
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FETCH_SCRIPT = REPO_ROOT / "fetch-free-models.py"
OUTPUT_MD = REPO_ROOT / "MODEL_RANKING.md"
OUTPUT_YAML = Path("/tmp/auxiliary_yaml.yaml")
OUTPUT_JSON = Path("/tmp/assignments.json")

PROVIDER_BASE_URL = {
    "ollama-cloud":  ("https://ollama.com/v1",                       "OLLAMA_API_KEY"),
    "opencode":      ("https://opencode.ai/zen/v1",                  "OPENCODE_API_KEY"),
    "kilocode":      ("https://api.kilo.ai/api/gateway/v1",          "KILOCODE_API_KEY"),
    "nvidia":        ("https://integrate.api.nvidia.com/v1",         "NVIDIA_API_KEY"),
}


def parse_ollama_marklists() -> dict:
    """Parse OLLAMA_FREE_MODELS + OLLAMA_FREE_MODELS_CTX from fetch script.

    Returns {mid: {"ctx": int}}.
    """
    src = FETCH_SCRIPT.read_text()

    free_match = re.search(r"OLLAMA_FREE_MODELS:\s*set\[str\]\s*=\s*\{([^}]+)\}", src)
    if not free_match:
        sys.exit("ERROR: OLLAMA_FREE_MODELS not found in fetch-free-models.py")
    free_ids = re.findall(r'"([^"]+)"', free_match.group(1))

    ctx_match = re.search(r"OLLAMA_FREE_MODELS_CTX:\s*dict\[str,\s*int\]\s*=\s*\{([^}]+)\}", src)
    if not ctx_match:
        sys.exit("ERROR: OLLAMA_FREE_MODELS_CTX not found")
    ctx_pairs = re.findall(r'"([^"]+)":\s*(\d[\d_]*)', ctx_match.group(1))
    ctx = {k: int(v.replace("_", "")) for k, v in ctx_pairs}

    return {mid: {"ctx": ctx.get(mid, 0)} for mid in free_ids}


def parse_opencode_ctx() -> dict:
    """Parse OPENCODE_FREE_MODELS_CTX from fetch script.

    Returns {mid: {"ctx": int}}.
    """
    src = FETCH_SCRIPT.read_text()
    ctx_match = re.search(r"OPENCODE_FREE_MODELS_CTX:\s*dict\[str,\s*int\]\s*=\s*\{([^}]+)\}", src)
    if not ctx_match:
        sys.exit("ERROR: OPENCODE_FREE_MODELS_CTX not found")
    ctx_pairs = re.findall(r'"([^"]+)":\s*(\d[\d_]*)', ctx_match.group(1))
    return {k: {"ctx": int(v.replace("_", ""))} for k, v in ctx_pairs}


def fetch_kilo_free() -> dict:
    """Run fetch-free-models.py --kilocode-only and parse output."""
    proc = subprocess.run(
        [sys.executable, str(FETCH_SCRIPT), "--kilocode-only", "--json"],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        print(f"WARNING: kilocode fetch failed (exit={proc.returncode})", file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        return {}
    try:
        models = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        print(f"WARNING: kilocode JSON parse failed: {e}", file=sys.stderr)
        return {}
    return {m["id"]: {"ctx": m.get("context_length", 0)} for m in models}


def fetch_nim_models() -> dict:
    """Live-fetch NVIDIA NIM models via /v1/models."""
    try:
        req = urllib.request.Request(
            "https://integrate.api.nvidia.com/v1/models",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        print(f"WARNING: NIM fetch failed: {e}", file=sys.stderr)
        return {}
    return {
        m["id"]: {"ctx": m.get("context_window", m.get("max_sequence_length", 0))}
        for m in data.get("data", [])
    }


# Tier map (kept in sync with the SKILL.md)
TIERS = {
    # Tier 1
    "nemotron-3-ultra": 1, "nemotron-3-ultra-free": 1,
    "nvidia/nemotron-3-ultra-550b-a55b:free": 1,
    "nvidia/nemotron-3-ultra-550b-a55b": 1,
    "nvidia/llama-3.1-nemotron-ultra-253b-v1": 1,
    "qwen/qwen3.5-397b-a17b": 1,
    "moonshotai/kimi-k2.7": 1,
    "gemma4:31b": 1,
    # Tier 2
    "minimax-m3": 2, "nemotron-3-super": 2,
    "nvidia/nemotron-3-super-120b-a12b:free": 2,
    "nvidia/nemotron-3-super-120b-a12b": 2,
    "qwen/qwen3.5-122b-a10b": 2,
    "mistralai/mistral-medium-3.5-128b": 2,
    "deepseek-ai/deepseek-v4-pro": 2,
    "thinkingmachines/inkling": 2,
    "z-ai/glm-5.2": 2,
    "minimaxai/minimax-m3": 2,
    "openrouter/free": 2, "kilo-auto/free": 2,
    # Tier 3
    "stepfun/step-3.7-flash:free": 3,
    "stepfun-ai/step-3.7-flash": 3,
    "deepseek-ai/deepseek-v4-flash": 3,
    "deepseek-v4-flash-free": 3,
    "mistralai/mistral-small-4-119b-2603": 3,
    "poolside/laguna-xs-2.1": 3, "poolside/laguna-xs-2.1:free": 3,
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free": 3,
    # Tier 4
    "poolside/laguna-s-2.1:free": 4,
    "poolside/laguna-m.1:free": 4,
    "cohere/north-mini-code:free": 4,
    "inclusionai/ling-3.0-flash:free": 4,
    "laguna-s-2.1-free": 4,
    "ling-3.0-flash-free": 4,
    "mimo-v2.5-free": 4,
    "north-mini-code-free": 4,
    # Vision
    "google/gemma-4-31b-it": "Vision",
    "google/diffusiongemma-26b-a4b-it": "Vision",
    "nvidia/nemotron-3.5-content-safety:free": "Vision",
}

# Per-provider assignment preference (lower = better)
PROVIDER_FREE_PREF = {"ollama-cloud": 0, "kilocode": 1, "opencode": 2, "nvidia": 3}


def build_catalog(ollama: dict, opencode: dict, kilo: dict, nim: dict) -> dict:
    catalog = {}

    def add(slug: str, provider: str, info: dict, vision: bool = False):
        ctx = info.get("ctx", 0)
        if ctx == 0:
            return
        catalog[slug] = {
            "provider": provider,
            "base_url": PROVIDER_BASE_URL[provider][0],
            "key_env": PROVIDER_BASE_URL[provider][1],
            "context_length": ctx,
            "tier": TIERS.get(slug, 4),
            "vision": vision,
        }

    for mid, info in ollama.items():
        add(mid, "ollama-cloud", info, vision=(mid == "gemma4:31b"))
    for mid, info in opencode.items():
        add(mid, "opencode", info)
    for mid, info in kilo.items():
        add(mid, "kilocode", info)
    for mid, info in nim.items():
        add(mid, "nvidia", info, vision=(mid in TIERS and TIERS[mid] == "Vision"))

    return catalog


# Tier-ordered provider+slug bundles for each auxiliary task.
# These are the exact assignments from MODEL_RANKING.md.
ASSIGNMENTS = {
    "kanban_decomposer": [
        ("ollama-cloud", "nemotron-3-ultra"),
        ("kilocode",     "nvidia/nemotron-3-ultra-550b-a55b:free"),
        ("opencode",     "nemotron-3-ultra-free"),
    ],
    "curator": [
        ("nvidia",       "qwen/qwen3.5-397b-a17b"),
        ("ollama-cloud", "gemma4:31b"),
        ("kilocode",     "nvidia/nemotron-3-super-120b-a12b:free"),
    ],
    "moa_aggregator": [
        ("ollama-cloud", "gemma4:31b"),
        ("nvidia",       "moonshotai/kimi-k2.7"),
        ("kilocode",     "nvidia/nemotron-3-ultra-550b-a55b:free"),
    ],
    "flush_memories": [
        ("nvidia",       "moonshotai/kimi-k2.7"),
        ("ollama-cloud", "gemma4:31b"),
        ("kilocode",     "nvidia/nemotron-3-super-120b-a12b:free"),
    ],
    "compression": [
        ("ollama-cloud", "nemotron-3-ultra"),
        ("kilocode",     "nvidia/nemotron-3-ultra-550b-a55b:free"),
        ("nvidia",       "nvidia/nemotron-3-ultra-550b-a55b"),
    ],
    "mcp": [
        ("nvidia",       "qwen/qwen3.5-122b-a10b"),
        ("ollama-cloud", "minimax-m3"),
        ("kilocode",     "stepfun/step-3.7-flash:free"),
    ],
    "moa_reference": [
        ("ollama-cloud", "nemotron-3-super"),
        ("kilocode",     "nvidia/nemotron-3-super-120b-a12b:free"),
        ("nvidia",       "nvidia/nemotron-3-super-120b-a12b"),
    ],
    "session_search": [
        ("nvidia",       "qwen/qwen3.5-122b-a10b"),
        ("ollama-cloud", "nemotron-3-super"),
        ("kilocode",     "openrouter/free"),
    ],
    "triage_specifier": [
        ("ollama-cloud", "nemotron-3-super"),
        ("kilocode",     "nvidia/nemotron-3-super-120b-a12b:free"),
        ("nvidia",       "deepseek-ai/deepseek-v4-pro"),
    ],
    "web_extract": [
        ("nvidia",       "mistralai/mistral-medium-3.5-128b"),
        ("ollama-cloud", "minimax-m3"),
        ("kilocode",     "nvidia/nemotron-3-ultra-550b-a55b:free"),
    ],
    "profile_describer": [
        ("kilocode",     "stepfun/step-3.7-flash:free"),
        ("nvidia",       "mistralai/mistral-small-4-119b-2603"),
        ("opencode",     "deepseek-v4-flash-free"),
    ],
    "approval": [
        ("nvidia",       "mistralai/mistral-small-4-119b-2603"),
        ("kilocode",     "stepfun/step-3.7-flash:free"),
        ("ollama-cloud", "gemma4:31b"),
    ],
    "title_generation": [
        ("kilocode",     "stepfun/step-3.7-flash:free"),
        ("nvidia",       "stepfun-ai/step-3.7-flash"),
        ("opencode",     "deepseek-v4-flash-free"),
    ],
    "goal_judge": [
        ("ollama-cloud", "nemotron-3-super"),
        ("kilocode",     "nvidia/nemotron-3-super-120b-a12b:free"),
        ("nvidia",       "deepseek-ai/deepseek-v4-pro"),
    ],
    "background_review": [
        ("nvidia",       "mistralai/mistral-medium-3.5-128b"),
        ("kilocode",     "openrouter/free"),
        ("ollama-cloud", "gemma4:31b"),
    ],
    "memory_query_rewrite": [
        ("kilocode",     "cohere/north-mini-code:free"),
        ("opencode",     "north-mini-code-free"),
        ("nvidia",       "stepfun-ai/step-3.7-flash"),
    ],
    "skills_hub": [
        ("nvidia",       "stepfun-ai/step-3.7-flash"),
        ("kilocode",     "stepfun/step-3.7-flash:free"),
        ("ollama-cloud", "minimax-m3"),
    ],
    "monitor": [
        ("kilocode",     "inclusionai/ling-3.0-flash:free"),
        ("opencode",     "ling-3.0-flash-free"),
        ("ollama-cloud", "minimax-m3"),
    ],
    "tts_audio_tags": [
        ("kilocode",     "poolside/laguna-s-2.1:free"),
        ("opencode",     "laguna-s-2.1-free"),
        ("nvidia",       "stepfun-ai/step-3.7-flash"),
    ],
    "vision": [
        ("ollama-cloud", "gemma4:31b"),
        ("nvidia",       "google/gemma-4-31b-it"),
        ("nvidia",       "google/diffusiongemma-26b-a4b-it"),
    ],
}


def validate(catalog: dict) -> list[str]:
    """Validate all assignments against the loaded catalog.

    Returns a list of error strings. If `catalog` does not contain any
    nvidia entries (because --skip-nim was passed), the validator skips
    NIM-only chains (those that ONLY use paid models).
    """
    errors = []
    has_nim = any(info["provider"] == "nvidia" for info in catalog.values())
    for task, chain in ASSIGNMENTS.items():
        if len(chain) != 3:
            errors.append(f"{task}: chain has {len(chain)} entries, expected 3")
            continue
        providers = {p for (p, _) in chain}
        slugs = {s for (_, s) in chain}
        if len(slugs) != 3:
            errors.append(f"{task}: needs 3 unique slugs, got {slugs}")
        if task != "vision" and len(providers) != 3:
            errors.append(f"{task}: needs 3 different providers, got {providers}")
        for (prov, slug) in chain:
            # If NIM catalog wasn't loaded, allow NIM slugs but flag them
            if slug not in catalog:
                if prov == "nvidia" and not has_nim:
                    continue  # NIM not loaded; that's OK
                errors.append(f"{task}: unknown slug {slug}")
            elif catalog[slug]["provider"] != prov:
                errors.append(f"{task}: {slug} is {catalog[slug]['provider']}, not {prov}")
    return errors


def emit_yaml(catalog: dict) -> str:
    """Emit the auxiliary: YAML block.

    For slugs not in the catalog (e.g. NIM models when --skip-nim was
    passed), fall back to hardcoded provider defaults so the YAML is
    always valid.
    """
    lines = ["auxiliary:"]
    for task, chain in ASSIGNMENTS.items():
        lines.append(f"  {task}:")
        for (prov, slug) in chain:
            info = catalog.get(slug)
            if info is None:
                base_url, key_env = PROVIDER_BASE_URL[prov]
            else:
                base_url = info["base_url"]
                key_env = info["key_env"]
            lines.append(f"    - provider: {prov}")
            lines.append(f"      model: {slug}")
            lines.append(f"      base_url: \"{base_url}\"")
            lines.append(f"      key_env: {key_env}")
    return "\n".join(lines)


# Hardcoded fallback catalog entries for NIM models (used when --skip-nim
# is passed and the live /v1/models fetch hasn't populated the catalog).
NIM_FALLBACK = {
    "google/gemma-4-31b-it":                       {"ctx": 262_144, "tier": 1, "vision": True},
    "google/diffusiongemma-26b-a4b-it":            {"ctx": 262_144, "tier": "Vision", "vision": True},
    "nvidia/llama-3.1-nemotron-ultra-253b-v1":     {"ctx": 131_072, "tier": 1, "vision": False},
    "nvidia/nemotron-3-ultra-550b-a55b":           {"ctx": 1_000_000, "tier": 1, "vision": False},
    "nvidia/nemotron-3-super-120b-a12b":           {"ctx": 262_144, "tier": 2, "vision": False},
    "qwen/qwen3.5-397b-a17b":                      {"ctx": 262_144, "tier": 1, "vision": False},
    "qwen/qwen3.5-122b-a10b":                      {"ctx": 262_144, "tier": 2, "vision": False},
    "moonshotai/kimi-k2.7":                        {"ctx": 262_144, "tier": 1, "vision": False},
    "moonshotai/kimi-k2.6":                        {"ctx": 262_144, "tier": 2, "vision": False},
    "z-ai/glm-5.2":                                {"ctx": 262_144, "tier": 2, "vision": False},
    "minimaxai/minimax-m3":                        {"ctx": 262_144, "tier": 2, "vision": False},
    "deepseek-ai/deepseek-v4-pro":                 {"ctx": 262_144, "tier": 2, "vision": False},
    "deepseek-ai/deepseek-v4-flash":               {"ctx": 262_144, "tier": 3, "vision": False},
    "mistralai/mistral-medium-3.5-128b":            {"ctx": 262_144, "tier": 2, "vision": False},
    "mistralai/mistral-small-4-119b-2603":         {"ctx": 262_144, "tier": 3, "vision": False},
    "stepfun-ai/step-3.7-flash":                   {"ctx": 262_144, "tier": 3, "vision": False},
    "thinkingmachines/inkling":                    {"ctx": 262_144, "tier": 2, "vision": False},
    "poolside/laguna-xs-2.1":                      {"ctx": 262_144, "tier": 3, "vision": False},
}


def emit_markdown(catalog: dict) -> str:
    """Emit a browsable MODEL_RANKING.md reference.

    Merges NIM_FALLBACK into the catalog for slug lookup so the markdown
    is complete even when --skip-nim was passed.
    """
    full = dict(catalog)
    for slug, info in NIM_FALLBACK.items():
        if slug not in full:
            full[slug] = {
                "provider": "nvidia",
                "base_url": PROVIDER_BASE_URL["nvidia"][0],
                "key_env": PROVIDER_BASE_URL["nvidia"][1],
                "context_length": info["ctx"],
                "tier": info["tier"],
                "vision": info["vision"],
            }

    by_tier: dict = {"1": [], "2": [], "3": [], "4": [], "Vision": []}
    for slug, info in full.items():
        tier = info["tier"]
        tier_key = str(tier)
        if tier_key not in by_tier:
            by_tier[tier_key] = []
        by_tier[tier_key].append((slug, info))

    lines = [
        "# Model Ranking & Auxiliary Task Assignment",
        "",
        "Generated from `fetch-free-models.py` + live Kilo/OpenCode fetches",
        "+ NVIDIA NIM as the paid fallback tier.",
        "",
        "## Tier rubric",
        "",
        "| Tier | Description |",
        "|------|-------------|",
        "| 1 | Frontier (≥250B MoE) — reasoning, JSON, planning |",
        "| 2 | Strong (100–200B) — tool-call, structured output |",
        "| 3 | Medium (30–120B) — classification, extraction |",
        "| 4 | Lightweight (<30B) — short calls |",
        "| Vision | Native image input |",
        "",
        "## Catalog",
        "",
    ]

    tier_names = {
        "1": "Tier 1 — Frontier",
        "2": "Tier 2 — Strong",
        "3": "Tier 3 — Medium",
        "4": "Tier 4 — Lightweight",
        "Vision": "Vision",
    }
    for tier_key, label in tier_names.items():
        if tier_key not in by_tier or not by_tier[tier_key]:
            continue
        lines.append(f"### {label}")
        lines.append("")
        lines.append("| Provider | Slug | Context | Free? |")
        lines.append("|----------|------|---------|-------|")
        for slug, info in sorted(by_tier[tier_key], key=lambda x: (x[1]["provider"], x[0])):
            free = "Y" if info["provider"] != "nvidia" else "N"
            lines.append(f"| {info['provider']} | `{slug}` | {info['context_length']:,} | {free} |")
        lines.append("")

    lines.extend([
        "## Auxiliary task → assignment",
        "",
        "Each task has 3 slots. Every chain uses 3 different providers and",
        "3 unique slugs (the `vision` task is the only exception — only 2",
        "vision-capable providers exist).",
        "",
        "| Task | Primary | Fallback 1 | Fallback 2 |",
        "|------|---------|-----------|-----------|",
    ])
    for task, chain in ASSIGNMENTS.items():
        cells = []
        for (prov, slug) in chain:
            cells.append(f"{prov} / `{slug}`")
        lines.append(f"| `{task}` | " + " | ".join(cells) + " |")

    lines.extend([
        "",
        "## Provider usage",
        "",
        "| Provider | Slots | Share |",
        "|----------|-------|-------|",
    ])
    provider_count = Counter()
    for chain in ASSIGNMENTS.values():
        for (prov, _) in chain:
            provider_count[prov] += 1
    total = sum(provider_count.values())
    for prov, n in sorted(provider_count.items(), key=lambda x: -x[1]):
        lines.append(f"| {prov} | {n} | {100*n/total:.1f}% |")

    lines.append("")
    lines.append("## Free-vs-paid")
    lines.append("")
    lines.append(f"- Free slots: **{sum(1 for c in ASSIGNMENTS.values() for (p, _) in c if p != 'nvidia')}** / {total}")
    lines.append(f"- Paid slots: **{sum(1 for c in ASSIGNMENTS.values() for (p, _) in c if p == 'nvidia')}** / {total}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-nim", action="store_true",
                    help="Skip NVIDIA NIM live fetch (use stale catalog)")
    args = ap.parse_args()

    print("Reading curated marklists from fetch-free-models.py...")
    ollama = parse_ollama_marklists()
    opencode = parse_opencode_ctx()
    print(f"  ollama: {len(ollama)} curated free IDs")
    print(f"  opencode: {len(opencode)} IDs with ctx")

    print("Fetching Kilo Code free list...")
    kilo = fetch_kilo_free()
    print(f"  kilocode: {len(kilo)} free IDs")

    nim = {}
    if args.skip_nim:
        print("Skipping NIM (--skip-nim)")
    else:
        print("Fetching NVIDIA NIM catalog...")
        nim = fetch_nim_models()
        print(f"  nvidia: {len(nim)} models")

    catalog = build_catalog(ollama, opencode, kilo, nim)
    print(f"\nTotal catalog: {len(catalog)} unique slugs")

    errors = validate(catalog)
    if errors:
        print("\nVALIDATION ERRORS:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)

    # Emit artifacts
    yaml_block = emit_yaml(catalog)
    OUTPUT_YAML.write_text(yaml_block)
    print(f"Wrote {OUTPUT_YAML} ({len(yaml_block.splitlines())} lines)")

    json_block = json.dumps(ASSIGNMENTS, indent=2)
    OUTPUT_JSON.write_text(json_block)
    print(f"Wrote {OUTPUT_JSON}")

    md_block = emit_markdown(catalog)
    OUTPUT_MD.write_text(md_block)
    print(f"Wrote {OUTPUT_MD} ({len(md_block.splitlines())} lines)")

    # Summary
    provider_count = Counter()
    slug_count = Counter()
    for chain in ASSIGNMENTS.values():
        for (prov, slug) in chain:
            provider_count[prov] += 1
            slug_count[slug] += 1
    print("\nProvider usage:")
    for prov, n in sorted(provider_count.items(), key=lambda x: -x[1]):
        print(f"  {prov:<12} {n}/{sum(provider_count.values())} ({100*n/sum(provider_count.values()):.1f}%)")
    print(f"\nTop slug reuses:")
    for slug, n in slug_count.most_common(5):
        print(f"  {n}x {slug}")


if __name__ == "__main__":
    main()
