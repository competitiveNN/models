#!/usr/bin/env python3
"""
Regenerate Hermes auxiliary task model assignments.

Reads:
  - fetch-free-models.py   (OLLAMA_FREE_MODELS, OPENCODE_FREE_MODELS_CTX)
  - python fetch-free-models.py --kilocode-only --json
  - NVIDIA NIM via `curl https://integrate.api.nvidia.com/v1/models`
  - Artificial Analysis API for intelligence scores (requires ARTIFICIAL_ANALYSIS_API_KEY)

Produces:
  - MODEL_RANKING.md (browsable reference with intelligence scores)
  - /tmp/auxiliary_yaml.yaml (drop-in auxiliary: block for ~/.hermes/config.yaml)
  - /tmp/assignments.json (programmatic form)

Run from the repo root:
    python3 tools/regenerate_assignments.py

Override the providers used:
    python3 tools/regenerate_assignments.py --skip-nim
"""

import os
import sys
import json
import argparse
import urllib.request
from pathlib import Path
from collections import Counter
import re
import importlib.util

REPO_ROOT = Path(__file__).resolve().parents[1]
FETCH_SCRIPT = REPO_ROOT / "fetch-free-models.py"
OUTPUT_MD = REPO_ROOT / "MODEL_RANKING.md"
OUTPUT_YAML = Path("/tmp/auxiliary_yaml.yaml")
OUTPUT_JSON = Path("/tmp/assignments.json")

# Ensure repo root is on sys.path so model_utils can be imported
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_utils import CACHE_FILE, CACHE_TTL_HOURS, HIDE_MODELS, fuzzy_match_slug, is_model_hidden, load_cache, normalize_slug, save_cache  # noqa: F401

PROVIDER_BASE_URL = {
    "ollama-cloud":  ("https://ollama.com/v1",                       "OLLAMA_API_KEY"),
    "opencode":      ("https://opencode.ai/zen/v1",                  "OPENCODE_API_KEY"),
    "kilocode":      ("https://api.kilo.ai/api/gateway/v1",          "KILOCODE_API_KEY"),
    "nvidia":        ("https://integrate.api.nvidia.com/v1",         "NVIDIA_API_KEY"),
    "google-ai-studio": ("https://generativelanguage.googleapis.com/v1beta", "GOOGLE_API_KEY"),
    "tencent":       ("https://api.tencent.com/v1",                   "TENCENT_API_KEY"),
}


def fetch_artificial_analysis_scores() -> dict[str, float]:
    """Fetch intelligence scores from Artificial Analysis API.

    Returns a dict mapping model slugs to intelligence index scores.
    Uses a local cache (free-models-cache.json) to avoid redundant API calls.
    Requires ARTIFICIAL_ANALYSIS_API_KEY environment variable.
    """
    # Try cache first
    cached = load_cache()
    if cached is not None:
        scores = {}
        for slug, entry in cached.items():
            if "intelligence" in entry:
                scores[slug] = entry["intelligence"]
        print(f"Artificial Analysis: using cached intelligence scores ({len(scores)} models)", file=sys.stderr)
        return scores

    api_key = os.getenv("ARTIFICIAL_ANALYSIS_API_KEY")
    if not api_key:
        print("Artificial Analysis: API key not set, skipping intelligence scores", file=sys.stderr)
        return {}

    print("Fetching intelligence scores from Artificial Analysis API...", file=sys.stderr)
    req = urllib.request.Request(
        "https://artificialanalysis.ai/api/v2/data/llms/models",
        headers={"Accept": "application/json", "x-api-key": api_key}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Artificial Analysis: fetch failed: {e}", file=sys.stderr)
        return {}

    if not data or not isinstance(data, dict) or "data" not in data:
        print("Artificial Analysis: no data or unexpected format", file=sys.stderr)
        return {}

    scores = {}
    enrichment = {}
    for model in data["data"]:
        slug = model.get("slug", "")
        evaluations = model.get("evaluations", {})
        intelligence = evaluations.get("artificial_analysis_intelligence_index")
        if slug and intelligence is not None:
            scores[slug] = float(intelligence)
        released = model.get("released") or model.get("release_date") or model.get("published_at")
        entry: dict[str, Any] = {}
        if intelligence is not None:
            entry["intelligence"] = float(intelligence)
        if released:
            entry["released"] = str(released)
        if entry:
            enrichment[slug] = entry
    save_cache(enrichment)
    print(f"Artificial Analysis: found {len(scores)} models with intelligence scores", file=sys.stderr)
    return scores


def parse_ollama_marklists() -> dict:
    """Parse OLLAMA_FREE_MODELS + OLLAMA_FREE_MODELS_CTX from fetch script."""
    spec = importlib.util.spec_from_file_location("fetch_free_models", FETCH_SCRIPT)
    fetch_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fetch_module)
    ollama_list = fetch_module.fetch_ollama()
    return {model['id']: {"ctx": model["context_length"]} for model in ollama_list}


def parse_opencode_marklist() -> dict:
    """Parse OPENCODE_FREE_MODELS_CTX from fetch script."""
    spec = importlib.util.spec_from_file_location("fetch_free_models", FETCH_SCRIPT)
    fetch_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fetch_module)
    opencode_list = fetch_module.fetch_opencode()
    return {model['id']: {"ctx": model["context_length"]} for model in opencode_list}


def fetch_kilo() -> list[dict]:
    """Fetch free models from Kilo Code API."""
    print("Fetching from Kilo Code API...", file=sys.stderr)
    req = urllib.request.Request("https://api.kilo.ai/api/gateway/v1/models", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Kilo: fetch failed: {e}", file=sys.stderr)
        return []

    if not data or not isinstance(data, dict) or "data" not in data:
        print("Kilo: no data or unexpected format", file=sys.stderr)
        return []

    free_models = []
    for model in data["data"]:
        model_id = model.get("id", "")
        is_free = (model.get("isFree") is True) or model_id.endswith(":free")
        if is_free:
            free_models.append({
                "id": model_id,
                "ctx": model.get("context_length", 0),
            })

    print(f"Kilo: found {len(free_models)} free models", file=sys.stderr)
    return free_models


def fetch_nim_models() -> dict:
    """Fetch recent generalist coding models from NVIDIA NIM API."""
    print("Fetching from NVIDIA NIM API...", file=sys.stderr)
    req = urllib.request.Request("https://integrate.api.nvidia.com/v1/models", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"NIM: fetch failed: {e}", file=sys.stderr)
        return {}

    if not data or not isinstance(data, dict) or "data" not in data:
        print("NIM: no data or unexpected format", file=sys.stderr)
        return {}

    # Filter to models that are in our TIERS dictionary
    nim_tiers = {k for k, v in TIERS.items() if v.get("provider") == "nvidia"}

    # Context length fallbacks for NIM models (since API returns null)
    NIM_CTX_FALLBACK = {
        "nvidia/nemotron-3-ultra-550b-a55b": 1_000_000,
        "nvidia/llama-3.3-nemotron-super-49b-v1": 262_144,
        "nvidia/llama-3.3-nemotron-super-49b-v1.5": 262_144,
        "nvidia/llama-3.1-nemotron-51b-instruct": 262_144,
        "nvidia/nemotron-4-340b-instruct": 1_000_000,
        "qwen/qwen3.5-397b-a17b": 262_144,
        "moonshotai/kimi-k2.7": 262_144,
        "moonshotai/kimi-k2.6": 262_144,
        "minimaxai/minimax-m3": 262_144,
        "mistralai/mistral-large-2-instruct": 262_144,
        "mistralai/mistral-medium-3.5-128b": 262_144,
        
        "google/gemma-4-31b-it": 262_144,
        "writer/palmyra-creative-122b": 131_072,
        "stepfun-ai/step-3.7-flash": 262_144,
        "thinkingmachines/inkling": 262_144,
        "deepseek-ai/deepseek-v4-pro": 262_144,
        "openai/gpt-oss-120b": 131_072,
        "z-ai/glm-5.2": 262_144,
        "nvidia/nemotron-3-super-120b-a12b": 262_144,
        "nvidia/llama-3.1-nemotron-70b-instruct": 262_144,
        "qwen/qwen3.5-122b-a10b": 262_144,
        "deepseek-ai/deepseek-v4-flash": 262_144,
        "mistralai/codestral-22b-instruct-v0.1": 131_072,
        "ibm/granite-34b-code-instruct": 131_072,
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning": 256_000,
        "nvidia/nemotron-3-nano-30b-a3b": 262_144,
        "nvidia/nemotron-nano-9b-v2": 131_072,
        "nvidia/nemotron-nano-12b-v2-vl": 131_072,
        "microsoft/phi-3.5-moe-instruct": 131_072,
        "writer/palmyra-fin-70b-32k": 32_768,
        "writer/palmyra-med-70b": 32_768,
        "writer/palmyra-med-70b-32k": 32_768,
        "ibm/granite-3.0-8b-instruct": 131_072,
        "ibm/granite-8b-code-instruct": 131_072,
        "google/codegemma-7b": 131_072,
        "google/codegemma-1.1-7b": 131_072,
        "google/gemma-3-12b-it": 131_072,
        "google/gemma-3-4b-it": 131_072,
        "google/diffusiongemma-26b-a4b-it": 262_144,
        "nvidia/nemotron-mini-4b-instruct": 131_072,
        "meta/codellama-70b": 131_072,
        "openai/gpt-oss-20b": 131_072,
        "zyphra/zamba2-7b-instruct": 131_072,
        "aisingapore/sea-lion-7b-instruct": 131_072,
        "databricks/dbrx-instruct": 131_072,
        "bigcode/starcoder2-15b": 131_072,
        "poolside/laguna-xs-2.1": 262_144,
        "adept/fuyu-8b": 131_072,
        "nv-mistralai/mistral-nemo-12b-instruct": 131_072,
        "mistralai/mistral-nemotron": 131_072,
        "01-ai/yi-large": 131_072,
        "ai21labs/jamba-1.5-large-instruct": 131_072,
    }

    models = {}
    for model in data["data"]:
        mid = model.get("id", "")
        if mid in nim_tiers:
            # Prefer API-returned context length, fall back to hard-coded
            ctx = model.get("context_length") or 0
            if ctx == 0:
                ctx = NIM_CTX_FALLBACK.get(mid, 0)
            if ctx > 0:
                models[mid] = {"ctx": ctx}

    print(f"NIM: found {len(models)} recent coding models", file=sys.stderr)
    return models


# Tier map (kept in sync with the SKILL.md)
# Only recent models (≤6 months) from NVIDIA and Google endpoints are included.
# Other providers (Ollama, Kilo, OpenCode) only host latest models.
TIERS = {
    # Tier 1 — Frontier (≥250B MoE / 120B+ reasoning)
    "nemotron-3-ultra": {"tier": 1, "release": "2026-01", "provider": "ollama", "activated_params": 55},
    "nemotron-3-ultra-free": {"tier": 1, "release": "2026-01", "provider": "opencode", "activated_params": 55},
    "nvidia/nemotron-3-ultra-550b-a55b:free": {"tier": 1, "release": "2026-01", "provider": "kilocode", "activated_params": 55},
    "nvidia/nemotron-3-ultra-550b-a55b": {"tier": 1, "release": "2026-01", "provider": "nvidia", "activated_params": 55},
    "nvidia/llama-3.3-nemotron-super-49b-v1": {"tier": 1, "release": "2026-01", "provider": "nvidia", "total_params": 49},
    "nvidia/llama-3.3-nemotron-super-49b-v1.5": {"tier": 1, "release": "2026-03", "provider": "nvidia", "total_params": 49},
    "nvidia/llama-3.1-nemotron-51b-instruct": {"tier": 1, "release": "2025-11", "provider": "nvidia", "total_params": 51},
    "nvidia/nemotron-4-340b-instruct": {"tier": 1, "release": "2025-10", "provider": "nvidia", "total_params": 340},
    "qwen/qwen3.5-397b-a17b": {"tier": 1, "release": "2026-04", "provider": "nvidia", "activated_params": 17},
    "moonshotai/kimi-k2.7": {"tier": 1, "release": "2026-03", "provider": "nvidia", "total_params": 119},
    "moonshotai/kimi-k2.6": {"tier": 1, "release": "2026-01", "provider": "nvidia", "total_params": 119},
    "gemma4:31b": {"tier": 1, "release": "2026-03", "provider": "ollama", "total_params": 31},
    "z-ai/glm-5.2": {"tier": 1, "release": "2026-04", "provider": "nvidia", "total_params": 120},
    "openai/gpt-oss-120b": {"tier": 1, "release": "2026-08", "provider": "nvidia", "total_params": 120},
    "deepseek-ai/deepseek-v4-pro": {"tier": 1, "release": "2026-04", "provider": "nvidia", "total_params": 120},
    "nvidia/nemotron-3-super-120b-a12b": {"tier": 1, "release": "2026-02", "provider": "nvidia", "activated_params": 12},
    "minimaxai/minimax-m3": {"tier": 1, "release": "2026-04", "provider": "nvidia", "total_params": 120},
    "mistralai/mistral-large-2-instruct": {"tier": 1, "release": "2026-04", "provider": "nvidia", "total_params": 123},
    "mistralai/mistral-medium-3.5-128b": {"tier": 1, "release": "2026-02", "provider": "nvidia", "total_params": 128},
    "google/gemma-4-31b-it": {"tier": 1, "release": "2026-03", "provider": "nvidia", "total_params": 31},
    "writer/palmyra-creative-122b": {"tier": 1, "release": "2026-04", "provider": "nvidia", "total_params": 122},
    "stepfun-ai/step-3.7-flash": {"tier": 1, "release": "2026-04", "provider": "nvidia", "total_params": 120},
    "thinkingmachines/inkling": {"tier": 1, "release": "2026-04", "provider": "nvidia", "total_params": 120},
    "tencent/hy3": {"tier": 1, "release": "2026-07", "provider": "tencent", "total_params": 295, "activated_params": 21},

    # Tier 2 — Strong (100–200B / reasoning)
    "minimax-m3": {"tier": 2, "release": "2026-03", "provider": "ollama", "total_params": 120},
    "nemotron-3-super": {"tier": 2, "release": "2026-02", "provider": "ollama", "activated_params": 12},
    "nvidia/nemotron-3-super-120b-a12b:free": {"tier": 2, "release": "2026-02", "provider": "kilocode", "activated_params": 12},
    "nvidia/nemotron-3-super-120b-a12b": {"tier": 2, "release": "2026-02", "provider": "nvidia", "activated_params": 12},
    "nvidia/llama-3.1-nemotron-70b-instruct": {"tier": 2, "release": "2025-10", "provider": "nvidia", "total_params": 70},
    "qwen/qwen3.5-122b-a10b": {"tier": 2, "release": "2026-04", "provider": "nvidia", "activated_params": 10},
    "deepseek-ai/deepseek-v4-flash": {"tier": 2, "release": "2026-04", "provider": "nvidia", "total_params": 70},
    "ibm/granite-34b-code-instruct": {"tier": 2, "release": "2026-04", "provider": "nvidia", "total_params": 34},
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning": {"tier": 2, "release": "2026-04", "provider": "nvidia", "activated_params": 3},
    "google/gemma-3-12b-it": {"tier": 2, "release": "2026-03", "provider": "nvidia", "total_params": 12},
    "mistralai/mistral-small-4-119b": {"tier": 2, "release": "2026-04", "provider": "nvidia", "total_params": 119},
    "nvidia/nemotron-3-nano-30b-a3b": {"tier": 2, "release": "2026-02", "provider": "nvidia", "activated_params": 3},
    "nvidia/nemotron-mini-4b-instruct": {"tier": 2, "release": "2026-01", "provider": "nvidia", "total_params": 4},
    "google/gemma-4-31b-it": {"tier": 2, "release": "2026-03", "provider": "nvidia", "total_params": 31},
    "gemini-flash-latest": {"tier": 2, "release": "2026-08", "provider": "google-ai-studio", "total_params": 120},
    "gemini-flash-lite-latest": {"tier": 2, "release": "2026-08", "provider": "google-ai-studio", "total_params": 120},

    # Tier 3 — Medium (30–120B / flash)
    "nvidia/nemotron-3-nano-30b-a3b": {"tier": 3, "release": "2026-02", "provider": "nvidia", "activated_params": 3},
    "mistralai/codestral-22b-instruct-v0.1": {"tier": 3, "release": "2026-04", "provider": "nvidia", "total_params": 22},
    "ibm/granite-3.0-8b-instruct": {"tier": 3, "release": "2026-04", "provider": "nvidia", "total_params": 8},
    "ibm/granite-8b-code-instruct": {"tier": 3, "release": "2026-04", "provider": "nvidia", "total_params": 8},
    "google/codegemma-7b": {"tier": 3, "release": "2026-04", "provider": "nvidia", "total_params": 7},
    "google/codegemma-1.1-7b": {"tier": 3, "release": "2026-04", "provider": "nvidia", "total_params": 7},
    "google/gemma-3-12b-it": {"tier": 3, "release": "2026-03", "provider": "nvidia", "total_params": 12},
    "microsoft/phi-3.5-moe-instruct": {"tier": 3, "release": "2026-04", "provider": "nvidia", "activated_params": 7},
    "nvidia/nemotron-nano-9b-v2": {"tier": 3, "release": "2026-01", "provider": "nvidia", "total_params": 9},
    "nvidia/mistral-nemo-minitron-8b-8k-instruct": {"tier": 3, "release": "2025-07", "provider": "nvidia", "total_params": 8},
    "nvidia/nemotron-mini-4b-instruct": {"tier": 3, "release": "2026-01", "provider": "nvidia", "total_params": 4},
    "poolside/laguna-s-2.1:free": {"tier": 3, "release": "2026-02", "provider": "kilocode", "total_params": 7},
    "poolside/laguna-xs-2.1:free": {"tier": 3, "release": "2026-04", "provider": "kilocode", "total_params": 3},
    "cohere/north-mini-code:free": {"tier": 3, "release": "2026-01", "provider": "kilocode", "total_params": 3},
    "inclusionai/ling-3.0-flash:free": {"tier": 3, "release": "2026-01", "provider": "kilocode", "total_params": 7},
    "stepfun/step-3.7-flash:free": {"tier": 3, "release": "2026-03", "provider": "kilocode", "total_params": 7},
    "openrouter/free": {"tier": 3, "release": "2026-01", "provider": "kilocode", "total_params": 7},
    "kilo-auto/free": {"tier": 3, "release": "2026-01", "provider": "kilocode", "total_params": 7},
    "nvidia/nemotron-3.5-content-safety:free": {"tier": 3, "release": "2026-01", "provider": "kilocode", "total_params": 7},
    "nvidia/nemotron-3-super-120b-a12b:free": {"tier": 3, "release": "2026-02", "provider": "kilocode", "activated_params": 12},
    "nvidia/nemotron-3-ultra-550b-a55b:free": {"tier": 3, "release": "2026-01", "provider": "kilocode", "activated_params": 55},
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free": {"tier": 3, "release": "2026-04", "provider": "kilocode", "activated_params": 3},
    "nemotron-3-super-free": {"tier": 3, "release": "2026-02", "provider": "opencode", "activated_params": 12},
    "deepseek-v4-flash-free": {"tier": 3, "release": "2026-04", "provider": "opencode", "total_params": 70},
    "mimo-v2.5-free": {"tier": 3, "release": "2026-01", "provider": "opencode", "total_params": 7},
    "ling-3.0-flash-free": {"tier": 3, "release": "2026-01", "provider": "opencode", "total_params": 7},
    "north-mini-code-free": {"tier": 3, "release": "2026-01", "provider": "opencode", "total_params": 3},
    "laguna-s-2.1-free": {"tier": 3, "release": "2026-02", "provider": "opencode", "total_params": 7},

    # Tier 4 — Lightweight (<30B / distilled)
    "google/gemma-3-4b-it": {"tier": 4, "release": "2026-03", "provider": "nvidia"},
    "gemma4:2b": {"tier": 4, "release": "2026-03", "provider": "google-ai-studio"},
    "gemma4:9b": {"tier": 4, "release": "2026-03", "provider": "google-ai-studio"},

    # Vision
    "gemma4:31b": {"tier": "Vision", "release": "2026-03", "provider": "ollama", "vision": True},
    "gemma4:31b": {"tier": "Vision", "release": "2026-03", "provider": "google-ai-studio", "vision": True},
    "google/gemma-4-31b-it": {"tier": "Vision", "release": "2026-03", "provider": "nvidia", "vision": True},
    "google/diffusiongemma-26b-a4b-it": {"tier": "Vision", "release": "2026-03", "provider": "nvidia", "vision": True},
    "microsoft/phi-3-vision-128k-instruct": {"tier": "Vision", "release": "2026-04", "provider": "nvidia", "vision": True},
    "nvidia/nemotron-nano-12b-v2-vl": {"tier": "Vision", "release": "2026-04", "provider": "nvidia", "vision": True},
    "nvidia/neva-22b": {"tier": "Vision", "release": "2025-01", "provider": "nvidia", "vision": True},
    "nvidia/vila": {"tier": "Vision", "release": "2025-01", "provider": "nvidia", "vision": True},
    "adept/fuyu-8b": {"tier": "Vision", "release": "2026-04", "provider": "nvidia", "vision": True},
    "microsoft/kosmos-2": {"tier": "Vision", "release": "2026-04", "provider": "nvidia", "vision": True},
    "gemini-flash-latest": {"tier": "Vision", "release": "2026-08", "provider": "google-ai-studio"},
    "gemini-flash-lite-latest": {"tier": "Vision", "release": "2026-08", "provider": "google-ai-studio"},
    "gemma-4-31b-it": {"tier": "Vision", "release": "2026-03", "provider": "google-ai-studio"},
    "gemma-4-26b-a4b-it": {"tier": "Vision", "release": "2026-03", "provider": "google-ai-studio"},
    "gemma-4-9b-it": {"tier": "Vision", "release": "2026-03", "provider": "google-ai-studio"},
    "gemma-4-2b-it": {"tier": "Vision", "release": "2026-03", "provider": "google-ai-studio"},
}

# Per-provider assignment preference (lower = better)
PROVIDER_FREE_PREF = {"ollama-cloud": 0, "kilocode": 1, "opencode": 2, "google-ai-studio": 3, "nvidia": 4}


def build_catalog(ollama: dict, opencode: dict, kilo: dict, nim: dict, google_ai_studio: dict, scores: dict[str, float]) -> dict:
    """Build unified catalog from all providers."""
    catalog = {}

    def add(slug: str, provider: str, info: dict, vision: bool = False):
        ctx = info.get("ctx", 0)
        if ctx == 0:
            return
        tier_info = TIERS.get(slug, {"tier": 4, "release": "unknown", "provider": provider})
        tier_val = tier_info["tier"]

        # Try to find intelligence score
        intelligence = None
        if scores:
            # Direct match
            if slug in scores:
                intelligence = scores[slug]
            else:
                # Try fuzzy match with weight-stripping
                matched_slug = fuzzy_match_slug(slug, scores)
                if matched_slug:
                    intelligence = scores[matched_slug]

        release = tier_info.get("release", "unknown")

        # Apply hide list — skip models we would never use
        # Only filters nvidia-nim models; all other providers always display
        if is_model_hidden(slug, intelligence, release if release != "unknown" else None, provider):
            return

        catalog[slug] = {
            "provider": provider,
            "base_url": PROVIDER_BASE_URL[provider][0],
            "key_env": PROVIDER_BASE_URL[provider][1],
            "context_length": ctx,
            "tier": tier_val,
            "vision": vision,
            "release": release,
            "intelligence": intelligence,
            "activated_params": tier_info.get("activated_params"),
            "total_params": tier_info.get("total_params"),
        }

    for mid, info in ollama.items():
        add(mid, "ollama-cloud", info, vision=(mid == "gemma4:31b"))
    for mid, info in opencode.items():
        add(mid, "opencode", info)
    for mid, info in kilo.items():
        add(mid, "kilocode", info)
    # Only include NIM models that are in our TIERS (recent models)
    for mid, info in nim.items():
        if mid in TIERS:
            tier_info = TIERS.get(mid, {})
            is_vision = tier_info.get("tier") == "Vision"
            info_with_release = dict(info)
            info_with_release["release"] = tier_info.get("release", "unknown")
            add(mid, "nvidia", info_with_release, vision=is_vision)
    for mid, info in google_ai_studio.items():
        if mid in TIERS:
            tier_info = TIERS.get(mid, {})
            is_vision = tier_info.get("tier") == "Vision"
            info_with_release = dict(info)
            info_with_release["release"] = tier_info.get("release", "unknown")
            # Don't overwrite if already in catalog (e.g., gemma4:31b from ollama has priority for vision)
            if mid not in catalog:
                add(mid, "google-ai-studio", info_with_release, vision=is_vision)

    # Manual entries for models not exposed via live APIs but present in TIERS
    manual_models = {
        "tencent/hy3": {"ctx": 256_000, "provider": "tencent"},
    }
    for slug, meta in manual_models.items():
        if slug in TIERS and slug not in catalog:
            add(slug, meta["provider"], {"ctx": meta["ctx"]})

    return catalog


# Tier-ordered provider+slug bundles for each auxiliary task.
# These are the exact assignments from MODEL_RANKING.md.
# All available Kilo and OpenCode models are distributed across tasks.
# Target distribution: kilocode ~18, opencode ~13, nvidia ~12, ollama-cloud ~9, google-ai-studio ~8
ASSIGNMENTS = {
    "kanban_decomposer": [
        ("kilocode",     "nvidia/nemotron-3-ultra-550b-a55b:free"),
        ("opencode",     "nemotron-3-ultra-free"),
        ("nvidia",       "nvidia/nemotron-3-ultra-550b-a55b"),
    ],
    "curator": [
        ("kilocode",     "nvidia/nemotron-3-super-120b-a12b:free"),
        ("nvidia",       "moonshotai/kimi-k2.6"),
        ("opencode",     "nemotron-3-ultra-free"),
    ],
    "moa_aggregator": [
        ("kilocode",     "nvidia/nemotron-3-super-120b-a12b:free"),
        ("opencode",     "nemotron-3-ultra-free"),
        ("nvidia",       "moonshotai/kimi-k2.6"),
    ],
    "flush_memories": [
        ("kilocode",     "nvidia/nemotron-3-ultra-550b-a55b:free"),
        ("nvidia",       "moonshotai/kimi-k2.6"),
        ("opencode",     "nemotron-3-ultra-free"),
    ],
    "compression": [
        ("kilocode",     "nvidia/nemotron-3-ultra-550b-a55b:free"),
        ("opencode",     "nemotron-3-ultra-free"),
        ("nvidia",       "nvidia/nemotron-3-ultra-550b-a55b"),
    ],
    "mcp": [
        ("kilocode",     "poolside/laguna-xs-2.1:free"),
        ("nvidia",       "microsoft/phi-3.5-moe-instruct"),
        ("opencode",     "deepseek-v4-flash-free"),
    ],
    "moa_reference": [
        ("kilocode",     "nvidia/nemotron-3-super-120b-a12b:free"),
        ("nvidia",       "mistralai/mistral-medium-3.5-128b"),
        ("opencode",     "nemotron-3-ultra-free"),
    ],
    "session_search": [
        ("kilocode",     "stepfun/step-3.7-flash:free"),
        ("nvidia",       "microsoft/phi-3.5-moe-instruct"),
        ("opencode",     "deepseek-v4-flash-free"),
    ],
    "triage_specifier": [
        ("kilocode",     "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"),
        ("nvidia",       "microsoft/phi-3.5-moe-instruct"),
        ("opencode",     "north-mini-code-free"),
    ],
    "web_extract": [
        ("kilocode",     "poolside/laguna-s-2.1:free"),
        ("nvidia",       "mistralai/mistral-medium-3.5-128b"),
        ("opencode",     "mimo-v2.5-free"),
    ],
    "profile_describer": [
        ("kilocode",     "inclusionai/ling-3.0-flash:free"),
        ("nvidia",       "mistralai/mistral-large-2-instruct"),
        ("opencode",     "mimo-v2.5-free"),
    ],
    "approval": [
        ("kilocode",     "cohere/north-mini-code:free"),
        ("nvidia",       "microsoft/phi-3.5-moe-instruct"),
        ("opencode",     "north-mini-code-free"),
    ],
    "title_generation": [
        ("kilocode",     "poolside/laguna-s-2.1:free"),
        ("nvidia",       "google/gemma-3-12b-it"),
        ("opencode",     "ling-3.0-flash-free"),
    ],
    "goal_judge": [
        ("kilocode",     "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"),
        ("nvidia",       "nvidia/nemotron-3-nano-30b-a3b"),
        ("opencode",     "deepseek-v4-flash-free"),
    ],
    "background_review": [
        ("kilocode",     "stepfun/step-3.7-flash:free"),
        ("nvidia",       "writer/palmyra-creative-122b"),
        ("opencode",     "nemotron-3-ultra-free"),
    ],
    "memory_query_rewrite": [
        ("kilocode",     "nvidia/nemotron-3-super-120b-a12b:free"),
        ("nvidia",       "google/gemma-3-4b-it"),
        ("opencode",     "north-mini-code-free"),
    ],
    "skills_hub": [
        ("kilocode",     "nvidia/nemotron-3-super-120b-a12b:free"),
        ("nvidia",       "stepfun-ai/step-3.7-flash"),
        ("opencode",     "laguna-s-2.1-free"),
    ],
    "monitor": [
        ("kilocode",     "poolside/laguna-xs-2.1:free"),
        ("nvidia",       "nvidia/nemotron-mini-4b-instruct"),
        ("opencode",     "laguna-s-2.1-free"),
    ],
    "tts_audio_tags": [
        ("kilocode",     "nvidia/nemotron-3.5-content-safety:free"),
        ("nvidia",       "google/gemma-3-4b-it"),
        ("opencode",     "ling-3.0-flash-free"),
    ],
    "vision": [
        ("ollama-cloud", "gemma4:31b"),
        ("nvidia",       "google/gemma-4-31b-it"),
        ("google-ai-studio", "gemini-flash-latest"),
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
        if task == "vision" and len(providers) != 3:
            errors.append(f"{task}: needs 3 different providers (ollama-cloud, nvidia, google-ai-studio), got {providers}")
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
    """Emit the auxiliary: YAML block."""
    lines = ["auxiliary:"]
    for task, chain in ASSIGNMENTS.items():
        lines.append(f"  {task}:")
        for i, (prov, slug) in enumerate(chain):
            role = ["primary", "fallback1", "fallback2"][i]
            lines.append(f"    {role}:")
            lines.append(f"      provider: {prov}")
            lines.append(f"      model: {slug}")
            ctx = catalog.get(slug, {}).get("context_length", 0)
            if ctx:
                lines.append(f"      context_length: {ctx}")
    return "\n".join(lines)


def emit_markdown(catalog: dict) -> str:
    """Emit a browsable MODEL_RANKING.md reference.

    Merges NIM_FALLBACK into the catalog for slug lookup so the markdown
    is complete even when --skip-nim was passed.
    """
    # Merge in NIM_FALLBACK for complete markdown even without --skip-nim
    for slug, info in catalog.items():
        if info["provider"] == "nvidia" and "release" not in info:
            tier_info = TIERS.get(slug, {})
            info["release"] = tier_info.get("release", "unknown")

    tier_names = {
        1: "Tier 1 — Frontier",
        2: "Tier 2 — Strong",
        3: "Tier 3 — Medium",
        4: "Tier 4 — Lightweight",
        "Vision": "Vision",
    }

    lines = [
        "# Model Ranking",
        "",
        f"Generated: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Catalog",
        "",
    ]

    by_tier = {}
    for slug, info in sorted(catalog.items()):
        tier = info.get("tier", 4)
        by_tier.setdefault(tier, []).append((slug, info))

    for tier_key in [1, 2, 3, 4, "Vision"]:
        if tier_key not in by_tier:
            continue
        lines.append(f"### {tier_names[tier_key]}")
        lines.append("")
        lines.append("| Provider | Slug | Context | Free? | Release | Intelligence | Active B | Total B |")
        lines.append("|----------|------|---------|-------|---------|--------------|----------|---------|")
        # Sort by intelligence score (descending), then by activated_params/total_params for throughput
        tier_items = by_tier[tier_key]
        def sort_key(x):
            info = x[1]
            intel = info.get("intelligence") or -1
            active = info.get("activated_params") or info.get("total_params") or 999
            return (-intel, active)
        tier_items_sorted = sorted(tier_items, key=sort_key)
        for slug, info in tier_items_sorted:
            free = "Y" if info["provider"] in ("ollama-cloud", "kilocode", "opencode", "google-ai-studio") else "N"
            ctx = info.get("context_length", 0)
            rel = info.get("release", "unknown")
            intel = info.get("intelligence")
            intel_str = f"{intel:.1f}" if intel is not None else "N/A"
            active = info.get("activated_params")
            total = info.get("total_params")
            active_str = f"{active}B" if active else "—"
            total_str = f"{total}B" if total else "—"
            lines.append(f"| {info['provider']} | `{slug}` | {ctx:,} | {free} | {rel} | {intel_str} | {active_str} | {total_str} |")
        lines.append("")

    lines.append("## Assignments")
    lines.append("")
    lines.append("| Task | Primary | Fallback1 | Fallback2 |")
    lines.append("|------|---------|-----------|-----------|")
    for task, chain in sorted(ASSIGNMENTS.items()):
        primary = f"{chain[0][0]}/{chain[0][1]}"
        fb1 = f"{chain[1][0]}/{chain[1][1]}"
        fb2 = f"{chain[2][0]}/{chain[2][1]}"
        lines.append(f"| {task} | {primary} | {fb1} | {fb2} |")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-nim", action="store_true", help="Skip live NIM fetch")
    args = parser.parse_args()

    # Fetch intelligence scores from Artificial Analysis
    scores = fetch_artificial_analysis_scores()

    ollama = parse_ollama_marklists()
    opencode = parse_opencode_marklist()
    kilo_list = fetch_kilo()
    kilo = {m["id"]: {"ctx": m["ctx"]} for m in kilo_list}
    google_ai_studio = {}
    # Always fetch Google AI Studio models (has fallback to curated list)
    sys.path.insert(0, str(REPO_ROOT))
    spec = importlib.util.spec_from_file_location("fetch_free_models", FETCH_SCRIPT)
    fetch_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fetch_module)
    google_ai_studio = {m["id"]: {"ctx": m["context_length"]} for m in fetch_module.fetch_google_ai_studio()}

    print(f"Reading curated marklists from fetch-free-models.py...")
    print(f"  ollama: {len(ollama)} curated free IDs")
    print(f"  opencode: {len(opencode)} IDs with ctx")
    print(f"Fetching Kilo Code free list...")
    print(f"  kilocode: {len(kilo)} free IDs")
    print(f"  google-ai-studio: {len(google_ai_studio)} free IDs")

    nim = {}
    if args.skip_nim:
        print("Skipping NIM (--skip-nim)")
    else:
        print("Fetching NVIDIA NIM catalog...")
        nim = fetch_nim_models()
        print(f"  nvidia: {len(nim)} models")

    catalog = build_catalog(ollama, opencode, kilo, nim, google_ai_studio, scores)
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