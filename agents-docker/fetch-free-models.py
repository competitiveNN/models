#!/usr/bin/env python3
"""
Fetch currently available free models from Kilo Code, OpenCode, Ollama Cloud, Google AI Studio, and NVIDIA NIM APIs.

Usage:
    python fetch-free-models.py --table
    python fetch-free-models.py --json --save free-models.json
    python fetch-free-models.py --csv --save free-models.csv
    python fetch-free-models.py --kilocode-only --table
    python fetch-free-models.py --opencode-only --json
    python fetch-free-models.py --ollama-only --table
    python fetch-free-models.py --google-ai-studio-only --table
    python fetch-free-models.py --nvidia-nim-only --table

Ollama Cloud free-tier models (hard-coded — there is no public endpoint
that exposes the free/metered flag):
    gemma4:31b, nemotron-3-super, nemotron-3-ultra, minimax-m3
Anything else returned by ollama.com/v1/models is treated as metered.
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


# ── Configuration ──────────────────────────────────────────────────────────────
KILO_ENDPOINT = "https://api.kilo.ai/api/gateway/v1/models"
OPENCODE_ENDPOINT = "https://opencode.ai/zen/v1/models"
GOOGLE_AI_STUDIO_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"
NVIDIA_NIM_ENDPOINT = "https://integrate.api.nvidia.com/v1/models"
TIMEOUT = 30
MAX_RETRIES = 3
BACKOFF_BASE = 2



# Authoritative free-tier list for Ollama Cloud (curated by user).  Ollama
# does not expose this flag in /v1/models or any chat-completions header,
# so the only reliable signal is a user-curated marklist.  Anything NOT
# in this set is treated as METERED — we never silently route to a paid
# model.  Update this set when Ollama adds new free tiers.
OLLAMA_FREE_MODELS: set[str] = {
    "gemma4:31b",
    "nemotron-3-super",
    "nemotron-3-ultra",
    "minimax-m3",
}

# Google AI Studio free model patterns (prefix match).
# Models matching these prefixes are considered free tier.
# Pro/Ultra models and image/video/audio generation models are NOT free.
# For gemini-* family, ONLY keep *-latest versions (handled in fetch function).
GOOGLE_AI_STUDIO_FREE_PREFIXES: tuple[str, ...] = (
    # Gemma models (open weights) - keep all
    "gemma-4-",
    # Flash experimental/preview - keep *-latest only (filtered in fetch function)
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
)

# Models that are explicitly NOT free (paid/enterprise)
GOOGLE_AI_STUDIO_PAID_PATTERNS: tuple[str, ...] = (
    "pro",
    "ultra",
    "imagen",
    "veo",
    "lyria",
    "embedding",
    "aqa",
    "robotics",
    "deep-research",
    "antigravity",
    "computer-use",
    "tts",
    "nano-banana",
    "image",
    "video",
    "audio",
)

# Context-length marklists.  Ollama's /v1/models does not expose
# context_length, OpenCode's does not either.  Populate from live lookups
# so the ctx column is never 0 in the table.
OLLAMA_FREE_MODELS_CTX: dict[str, int] = {
    "gemma4:31b":       262_144,
    "minimax-m3":       262_144,
    "nemotron-3-super": 262_144,
    "nemotron-3-ultra": 1_000_000,
}

OPENCODE_FREE_MODELS_CTX: dict[str, int] = {
    "deepseek-v4-flash-free":   131_072,
    "laguna-s-2.1-free":        131_072,
    "ling-3.0-flash-free":      131_072,
    "mimo-v2.5-free":           131_072,
    "nemotron-3-ultra-free":  1_000_000,
    "north-mini-code-free":     131_072,
}

GOOGLE_AI_STUDIO_FREE_MODELS_CTX: dict[str, int] = {
    "gemini-flash-latest":        1_048_576,
    "gemini-flash-lite-latest":   1_048_576,
    "gemma-4-31b-it":             262_144,
    "gemma-4-26b-a4b-it":         262_144,
    "gemma-4-9b-it":              262_144,
    "gemma-4-2b-it":              262_144,
}

# Curated free model list for Google AI Studio (used when API key not available)
GOOGLE_AI_STUDIO_FREE_MODELS: set[str] = {
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemma-4-31b-it",
    "gemma-4-26b-a4b-it",
    "gemma-4-9b-it",
    "gemma-4-2b-it",
}

# NVIDIA NIM context length estimates by model family
NVIDIA_NIM_CTX: dict[str, int] = {
    "nemotron-3-ultra": 1_000_000,
    "nemotron-3-super": 262_144,
    "nemotron-3-nano": 262_144,
    "nemotron-4-340b": 1_000_000,
    "nemotron-mini": 131_072,
    "nemotron-nano": 131_072,
    "mistral-nemo": 131_072,
    "mistral-large": 131_072,
    "mistral-medium": 131_072,
    "codestral": 131_072,
    "llama-3.3": 131_072,
    "llama-3.2": 131_072,
    "llama-3.1": 131_072,
    "llama-3": 131_072,
    "codellama": 131_072,
    "granite": 131_072,
    "phi-3": 131_072,
    "starcoder": 131_072,
    "deepseek": 131_072,
    "dbrx": 131_072,
    "yi-large": 131_072,
    "jamba": 131_072,
    "sea-lion": 131_072,
    "glm": 131_072,
    "zamba": 131_072,
    "palmyra": 131_072,
    "step": 131_072,
    "inkling": 131_072,
    "qwen": 131_072,
    "gpt-oss": 131_072,
}

HEADERS = {
    "User-Agent": "fetch-free-models/1.0 (+https://github.com/defnlnotme/models)",
    "Accept": "application/json",
}

# NVIDIA NIM release date mapping: model_id -> "YYYY-MM"
# These are the ORIGINAL MODEL RELEASE DATES, not when NVIDIA added them to NIM.
# Only models released within the last 4 months are considered recent (from current date).
# Format: "YYYY-MM"
NVIDIA_NIM_RELEASE_DATES: dict[str, str] = {
    # Add known release dates here as discovered
    "nvidia/nemotron-3-nano-30b-a3b": "2026-04",
    "nvidia/nemotron-3-super-120b-a12b": "2026-04",
    "nvidia/nemotron-3-ultra-550b-a55b": "2026-04",
    "google/gemma-4-31b-it": "2026-03",
    "google/gemma-4-26b-a4b-it": "2026-03",
    # Note: Add more mappings as needed
}

# ── Helpers ────────────────────────────────────────────────────────────────
# ── Helpers ────────────────────────────────────────────────────────────────────
def fetch_json(url: str, attempt: int = 1) -> dict[str, Any] | list[Any] | None:
    """Fetch JSON with retry on 429/5xx and timeout handling."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429 and attempt <= MAX_RETRIES:
            retry_after = int(e.headers.get("Retry-After", str(BACKOFF_BASE ** attempt)))
            print(f"Rate limited (429), waiting {retry_after}s... (attempt {attempt}/{MAX_RETRIES})", file=sys.stderr)
            time.sleep(retry_after)
            return fetch_json(url, attempt + 1)
        if 500 <= e.code < 600 and attempt <= MAX_RETRIES:
            wait = BACKOFF_BASE ** attempt
            print(f"Server error {e.code}, retrying in {wait}s... (attempt {attempt}/{MAX_RETRIES})", file=sys.stderr)
            time.sleep(wait)
            return fetch_json(url, attempt + 1)
        print(f"HTTP {e.code}: {e.reason}", file=sys.stderr)
        if e.code == 401:
            print("Check auth credentials", file=sys.stderr)
        elif e.code == 403:
            print("Access forbidden — check permissions", file=sys.stderr)
    except urllib.error.URLError as e:
        print(f"Network error: {e.reason}", file=sys.stderr)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
    except TimeoutError:
        print(f"Request timed out after {TIMEOUT}s", file=sys.stderr)
    return None


def normalize_kilo(model: dict[str, Any]) -> dict[str, Any] | None:
    """Convert Kilo model format to common schema."""
    pricing = model.get("pricing", {})
    def to_float(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    return {
        "id": model.get("id"),
        "name": model.get("name"),
        "provider": "kilocode",
        "context_length": model.get("context_length", 0),
        "pricing": {
            "input": to_float(pricing.get("prompt", 0)),
            "output": to_float(pricing.get("completion", 0)),
            "cache_read": to_float(pricing.get("input_cache_read", 0)),
            "cache_write": to_float(pricing.get("input_cache_write", 0)),
        },
        "capabilities": {
            "reasoning": "reasoning" in model.get("supported_parameters", []),
            "tool_call": "tools" in model.get("supported_parameters", []),
            "vision": "image" in model.get("architecture", {}).get("input_modalities", []),
            "open_weights": False,
        },
        "source": "kilocode",
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "raw": model,
    }


def normalize_opencode(model_id: str) -> dict[str, Any] | None:
    """Convert OpenCode model format to common schema."""
    return {
        "id": model_id,
        "name": model_id,
        "provider": "opencode",
        "context_length": OPENCODE_FREE_MODELS_CTX.get(model_id, 0),
        "pricing": {
            "input": 0,
            "output": 0,
            "cache_read": 0,
            "cache_write": 0,
        },
        "capabilities": {
            "reasoning": False,
            "tool_call": True,
            "vision": False,
            "open_weights": False,
        },
        "source": "opencode",
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "raw": {"id": model_id},
    }


def normalize_ollama(model_id: str) -> dict[str, Any] | None:
    """Convert curated Ollama Cloud free-tier entry to common schema."""
    return {
        "id": model_id,
        "name": model_id,
        "provider": "ollama-cloud",
        "context_length": OLLAMA_FREE_MODELS_CTX.get(model_id, 0),
        "pricing": {
            "input": 0,
            "output": 0,
            "cache_read": 0,
            "cache_write": 0,
        },
        "capabilities": {
            "reasoning": False,
            "tool_call": True,
            "vision": "gemma4:31b" in model_id,
            "open_weights": False,
        },
        "source": "ollama-cloud",
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "raw": {"id": model_id},
    }


def is_google_ai_studio_free(model_id: str) -> bool:
    """Determine if a Google AI Studio model is free tier."""
    model_lower = model_id.lower()

    # Explicitly paid patterns - return False immediately
    for pattern in GOOGLE_AI_STUDIO_PAID_PATTERNS:
        if pattern in model_lower:
            return False

    # Free patterns - must match at least one
    for pattern in GOOGLE_AI_STUDIO_FREE_PREFIXES:
        if pattern in model_lower:
            return True

    return False


def is_gemini_latest(model_id: str) -> bool:
    """Check if a gemini-* model is a *-latest version (preferred alias)."""
    model_lower = model_id.lower()
    return model_lower.startswith("gemini-") and model_lower.endswith("-latest")


def normalize_google_ai_studio(model: dict[str, Any], model_id: str) -> dict[str, Any] | None:
    """Convert Google AI Studio model from API response to common schema."""
    def normalize_nvidia_nim(model: dict[str, Any], model_id: str) -> dict[str, Any] | None:
        """Convert NVIDIA NIM model from API response to common schema."""
        model_lower = model_id.lower()

        # Determine context length
        ctx = 131_072  # default
        for key, val in NVIDIA_NIM_CTX.items():
            if key in model_lower:
                ctx = val
                break

        # Determine capabilities
        has_reasoning = any(x in model_lower for x in ["nemotron", "reasoning", "thinking", "r1", "r1-"])
        has_vision = any(x in model_lower for x in ["vision", "vl", "vlm", "vila", "neva", "kosmos", "phi-3-vision"])
        has_tool_call = "instruct" in model_lower or "chat" in model_lower or "coder" in model_lower

        # Get release date from mapping if available
        released = NVIDIA_NIM_RELEASE_DATES.get(model_id)

        return {
            "id": model_id,
            "name": model_id,
            "provider": "nvidia-nim",
            "context_length": ctx,
            "pricing": {
                "input": 0,
                "output": 0,
                "cache_read": 0,
                "cache_write": 0,
            },
            "capabilities": {
                "reasoning": has_reasoning,
                "tool_call": has_tool_call,
                "vision": has_vision,
                "open_weights": False,
            },
            "source": "nvidia-nim",
            "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "raw": model,
            "released": released,
        }


def normalize_google_ai_studio_curated(model_id: str) -> dict[str, Any] | None:
    """Convert curated Google AI Studio free-tier entry to common schema.
    
    Uses the curated marklist (no API key needed) with context from GOOGLE_AI_STUDIO_FREE_MODELS_CTX.
    """
    return {
        "id": model_id,
        "name": model_id,
        "provider": "google-ai-studio",
        "context_length": GOOGLE_AI_STUDIO_FREE_MODELS_CTX.get(model_id, 0),
        "pricing": {
            "input": 0,
            "output": 0,
            "cache_read": 0,
            "cache_write": 0,
        },
        "capabilities": {
            "reasoning": "3.6" in model_id.lower() or "pro" in model_id.lower(),
            "tool_call": True,
            "vision": "gemini" in model_id.lower() or "gemma4" in model_id.lower(),
            "open_weights": "gemma" in model_id.lower(),
        },
        "source": "google-ai-studio",
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "raw": {"id": model_id},
    }


def is_nvidia_nim_recent_coding(model_id: str) -> bool:
    """Check if a NVIDIA NIM model is a generalist coding model."""
    model_lower = model_id.lower()

    # Exclude embedding, retriever, safety, translation, vision-specialized, etc.
    exclude_patterns = (
        "embed",
        "nemoretriever",
        "nemoguard",
        "safety",
        "topic-control",
        "content-safety",
        "translate",
        "riva-translate",
        "nvclip",
        "vila",
        "cosmos",
        "ising",
        "detector",
        "reward",
        "neva",
        "diffusion",
        "video",
        "audio",
        "speech",
        "tts",
        "voice",
        "writer/",
        "mistral-nemo",
        "nvidia/llama",
        "meta/",
        "gemma-2",
        "gemma-3",
        "recurrentgemma",
        "codegemma",
    )
    for pattern in exclude_patterns:
        if pattern in model_lower:
            return False

    # If not excluded, assume it's a generalist LLM (text-based)
    return True


def normalize_nvidia_nim(model: dict[str, Any], model_id: str) -> dict[str, Any] | None:
    """Convert NVIDIA NIM model from API response to common schema."""
    model_lower = model_id.lower()

    # Determine context length
    ctx = 131_072  # default
    for key, val in NVIDIA_NIM_CTX.items():
        if key in model_lower:
            ctx = val
            break

    # Determine capabilities
    has_reasoning = any(x in model_lower for x in ["nemotron", "reasoning", "thinking", "r1", "r1-"])
    has_vision = any(x in model_lower for x in ["vision", "vl", "vlm", "vila", "neva", "kosmos", "phi-3-vision"])
    has_tool_call = "instruct" in model_lower or "chat" in model_lower or "coder" in model_lower

    # Get release date from our mapping if available
    released = NVIDIA_NIM_RELEASE_DATES.get(model_id)

    return {
        "id": model_id,
        "name": model_id,
        "provider": "nvidia-nim",
        "context_length": ctx,
        "released": released,
        "pricing": {
            "input": 0,
            "output": 0,
            "cache_read": 0,
            "cache_write": 0,
        },
        "capabilities": {
            "reasoning": has_reasoning,
            "tool_call": has_tool_call,
            "vision": has_vision,
            "open_weights": False,
        },
        "source": "nvidia-nim",
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "raw": model,
    }


def fetch_kilo() -> list[dict[str, Any]]:
    """Fetch and normalize free models from Kilo API."""
    print("Fetching from Kilo Code API...", file=sys.stderr)
    data = fetch_json(KILO_ENDPOINT)
    if not data or not isinstance(data, dict) or "data" not in data:
        print("Kilo: no data or unexpected format", file=sys.stderr)
        return []

    free_models = []
    for model in data["data"]:
        model_id = model.get("id", "")
        is_free = (model.get("isFree") is True) or model_id.endswith(":free")
        if is_free:
            normalized = normalize_kilo(model)
            if normalized:
                free_models.append(normalized)

    print(f"Kilo: found {len(free_models)} free models", file=sys.stderr)
    return free_models


def fetch_opencode() -> list[dict[str, Any]]:
    """Fetch OpenCode models; free ones have slug ending in -free."""
    print("Fetching from OpenCode API...", file=sys.stderr)
    data = fetch_json(OPENCODE_ENDPOINT)
    if not data or not isinstance(data, dict) or "data" not in data:
        print("OpenCode: no data or unexpected format", file=sys.stderr)
        return []

    free_models = []
    for model in data.get("data", []):
        model_id = model.get("id", "")
        if model_id.endswith("-free"):
            normalized = normalize_opencode(model_id)
            if normalized:
                free_models.append(normalized)

    print(f"OpenCode: found {len(free_models)} free models (only '-free' suffix kept)", file=sys.stderr)
    return free_models


def fetch_ollama() -> list[dict[str, Any]]:
    """Return the curated Ollama Cloud free-tier marklist."""
    print(
        f"Ollama: emitting {len(OLLAMA_FREE_MODELS)} curated free models "
        f"(no API call)",
        file=sys.stderr,
    )
    return [m for m in (normalize_ollama(mid) for mid in sorted(OLLAMA_FREE_MODELS)) if m is not None]


def fetch_google_ai_studio() -> list[dict[str, Any]]:
    """Fetch and normalize free models from Google AI Studio API.
    Note: We always use the curated list because the API does not provide
    the models in the form we want (with -latest suffixes) and we want to show
    only the specific models in the curated list.
    """
    result = []
    for mid in sorted(GOOGLE_AI_STUDIO_FREE_MODELS):
        m = normalize_google_ai_studio_curated(mid)
        if m is not None:
            result.append(m)
    return result

    print(f"Google AI Studio: found {len(filtered_models)} free models ({len(gemini_latest_models)} gemini-*-latest)", file=sys.stderr)
    return filtered_models


def fetch_nvidia_nim() -> list[dict[str, Any]]:
    """Fetch and normalize recent generalist coding models from NVIDIA NIM API."""
    print("Fetching from NVIDIA NIM API...", file=sys.stderr)
    data = fetch_json(NVIDIA_NIM_ENDPOINT)

    if not data or not isinstance(data, dict) or "data" not in data:
        print("NVIDIA NIM: no data or unexpected format", file=sys.stderr)
        return []

    free_models = []
    for model in data["data"]:
        model_id = model.get("id", "")
        if not model_id:
            continue

        if is_nvidia_nim_recent_coding(model_id):
            normalized = normalize_nvidia_nim(model, model_id)
            if normalized:
                free_models.append(normalized)

    print(f"NVIDIA NIM: found {len(free_models)} recent generalist coding models", file=sys.stderr)
    return free_models


# ── Output ─────────────────────────────────────────────────────────────────────
def output_json(data: list[dict], path: str | None):
    out = json.dumps(data, indent=2)
    if path:
        Path(path).write_text(out)
        print(f"Saved {len(data)} records to {path}", file=sys.stderr)
    else:
        print(out)


def output_csv(data: list[dict], path: str | None):
    if not data:
        return

    flat = []
    for d in data:
        caps = d.get("capabilities", {})
        pricing = d.get("pricing", {})
        row = {
            "id": d.get("id"),
            "provider": d.get("provider"),
            "context_length": d.get("context_length"),
            "pricing_input": pricing.get("input"),
            "pricing_output": pricing.get("output"),
            "pricing_cache_read": pricing.get("cache_read"),
            "pricing_cache_write": pricing.get("cache_write"),
            "reasoning": caps.get("reasoning"),
            "tool_call": caps.get("tool_call"),
            "vision": caps.get("vision"),
            "open_weights": caps.get("open_weights"),
            "source": d.get("source"),
            "fetched_at": d.get("fetched_at"),
        }
        flat.append(row)

    fieldnames = list(flat[0].keys())
    out_io = sys.stdout if path is None else open(path, "w", newline="")
    try:
        writer = csv.DictWriter(out_io, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat)
        if path:
            print(f"Saved {len(data)} records to {path}", file=sys.stderr)
    finally:
        if path:
            out_io.close()


def output_table(data: list[dict]):
    if not data:
        print("No records")
        return

    cols = [
        ("id", 35),
        ("provider", 16),
        ("released", 12),
        ("ctx", 10),
        ("reason", 6),
        ("tools", 5),
        ("vision", 6),
    ]

    header = " | ".join(f"{name:<{w}}" for name, w in cols)
    print(header)
    print("-" * len(header))

    for d in data:
        caps = d.get("capabilities", {})
        ctx_val = d.get("context_length", 0) or 0
        ctx_disp = f"{ctx_val:,}" if ctx_val else "-"
        
        release_val = d.get("released")
        if release_val is not None:
            # If it's a timestamp, convert to YYYY-MM format
            if isinstance(release_val, (int, float)) and release_val > 0:
                from datetime import datetime
                try:
                    dt = datetime.fromtimestamp(release_val)
                    release_disp = dt.strftime("%Y-%m")
                except:
                    release_disp = str(release_val)
            else:
                release_disp = str(release_val)
        else:
            release_disp = "-"
            
        row = [
            d.get("id", "")[:35],
            d.get("provider", "")[:16],
            release_disp,
            ctx_disp,
            "Y" if caps.get("reasoning") else "N",
            "Y" if caps.get("tool_call") else "N",
            "Y" if caps.get("vision") else "N",
        ]
        print(" | ".join(f"{v:<{w}}" for (_, w), v in zip(cols, row)))


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Fetch free models from Kilo Code, OpenCode, Ollama Cloud, Google AI Studio, and NVIDIA NIM APIs"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--csv", action="store_true", help="Output as CSV")
    parser.add_argument("--table", action="store_true", help="Output as table (default)")
    parser.add_argument("--save", metavar="FILE", help="Save output to file instead of stdout")
    parser.add_argument("--kilocode-only", action="store_true", help="Only fetch from Kilo Code API")
    parser.add_argument("--opencode-only", action="store_true", help="Only fetch from OpenCode API")
    parser.add_argument("--ollama-only", action="store_true", help="Only fetch from Ollama Cloud API")
    parser.add_argument("--google-ai-studio-only", action="store_true", help="Only fetch from Google AI Studio API")
    parser.add_argument("--nvidia-nim-only", action="store_true", help="Only fetch from NVIDIA NIM API")
    args = parser.parse_args()

    # Default to table if no format specified
    if not (args.json or args.csv or args.table):
        args.table = True

    # Validate mutually exclusive flags
    only_count = sum([args.kilocode_only, args.opencode_only, args.ollama_only, args.google_ai_studio_only, args.nvidia_nim_only])
    if only_count > 1:
        print(
            "Error: --kilocode-only, --opencode-only, --ollama-only, --google-ai-studio-only, and --nvidia-nim-only are mutually exclusive",
            file=sys.stderr,
        )
        sys.exit(1)

    # Fetch data
    all_models = []

    if not args.opencode_only and not args.ollama_only and not args.google_ai_studio_only and not args.nvidia_nim_only:
        kilo_models = fetch_kilo()
        all_models.extend(kilo_models)

    if not args.kilocode_only and not args.ollama_only and not args.google_ai_studio_only and not args.nvidia_nim_only:
        opencode_models = fetch_opencode()
        all_models.extend(opencode_models)

    if not args.kilocode_only and not args.opencode_only and not args.google_ai_studio_only and not args.nvidia_nim_only:
        ollama_models = fetch_ollama()
        all_models.extend(ollama_models)

    if not args.kilocode_only and not args.opencode_only and not args.ollama_only:
        google_models = fetch_google_ai_studio()
        all_models.extend(google_models)

    if not args.kilocode_only and not args.opencode_only and not args.ollama_only and not args.google_ai_studio_only:
        nvidia_models = fetch_nvidia_nim()
        all_models.extend(nvidia_models)

    if not all_models:
        print("No free models found", file=sys.stderr)
        sys.exit(1)

    # Per-source breakdown in the summary line
    by_source = {}
    for m in all_models:
        by_source.setdefault(m.get("source", "?"), 0)
        by_source[m["source"]] += 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(by_source.items()))
    print(f"Total models: {len(all_models)} ({summary})", file=sys.stderr)

    # Output
    if args.json:
        output_json(all_models, args.save)
    elif args.csv:
        output_csv(all_models, args.save)
    else:
        output_table(all_models)


if __name__ == "__main__":
    main()
