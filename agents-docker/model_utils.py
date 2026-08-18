"""Shared utilities for model fetching and assignment: caching, hide list, and slug matching."""

import json
import re
from datetime import UTC, datetime
from difflib import get_close_matches
from pathlib import Path
from typing import Any

# Cache for AA enrichment data (intelligence scores + release dates).
# Avoids redundant API calls when the data is still fresh.
CACHE_FILE = Path(__file__).resolve().parent / "free-models-cache.json"
CACHE_TTL_HOURS = 24

# Models to hide — specialized, outdated, or low-quality models
# that we would never use in assignments.
HIDE_MODELS: set[str] = {
    # Embedding / retrieval models
    "nvidia/nv-embed-v1",
    "nvidia/nv-embed-v2",
    "nvidia/nemoretriever-1b",
    "nvidia/nemoretriever-4b",
    "nvidia/nemoguard-3b",
    "nvidia/nemoguard-8b",
    # Vision-only models (not useful for text auxiliary tasks)
    "nvidia/neva-22b",
    "nvidia/vila",
    "microsoft/kosmos-2",
    "adept/fuyu-8b",
    # Outdated / superseded models with low intelligence
    "nvidia/mistral-nemo-minitron-8b-8k-instruct",
    "nvidia/nemotron-mini-4b-instruct",
    # Translation / speech models
    "nvidia/translate",
    "nvidia/tts",
    # Code models that are too specialized or outdated
    "mistralai/codestral-22b-instruct-v0.1",
    "google/codegemma-7b",
    "google/codegemma-1.1-7b",
    # Too old (released >12 months ago with no recent update)
    "nvidia/llama-3.1-nemotron-51b-instruct",
    "nvidia/nemotron-4-340b-instruct",
    "nvidia/llama-3.3-nemotron-super-49b-v1",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    # Low-intelligence specialized models
    "nvidia/nemotron-3.5-content-safety:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    # Writer/Palmyra — creative/financial models, not generalist coding
    "writer/palmyra-creative-122b",
    "writer/palmyra-fin-70b-32k",
    "writer/palmyra-med-70b",
    "writer/palmyra-med-70b-32k",
}

# Minimum intelligence score for a model to be considered usable without recency check.
MIN_INTELLIGENCE_SCORE = 10.0

# Maximum model age in months for models without an explicit tier.
MAX_MODEL_AGE_MONTHS = 12


def load_cache() -> dict[str, Any] | None:
    """Load cached AA enrichment data if it exists and is still fresh."""
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text())
        fetched_at = datetime.fromisoformat(data.get("fetched_at", "").replace("Z", "+00:00"))
        age = datetime.now(UTC) - fetched_at
        if age.total_seconds() > CACHE_TTL_HOURS * 3600:
            return None
        enrichment = data.get("enrichment", {})
        return enrichment if isinstance(enrichment, dict) else None
    except (json.JSONDecodeError, ValueError, OSError):
        return None


def save_cache(enrichment: dict[str, Any]) -> None:
    """Save AA enrichment data to cache with current timestamp."""
    cache = {
        "fetched_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "enrichment": enrichment,
    }
    CACHE_FILE.write_text(json.dumps(cache, indent=2))


def is_model_hidden(
    model_id: str,
    intelligence: float | None,
    released: str | None,
    provider: str | None = None,
) -> bool:
    """Check if a model should be hidden based on the hide list and quality thresholds.

    Only applies filtering for nvidia-nim models. All other providers
    (kilocode, opencode, ollama-cloud, google-ai-studio) always display
    all free models without filtering.
    """
    if provider != "nvidia-nim":
        return False
    if model_id in HIDE_MODELS:
        return True
    # If we have an intelligence score, use it as primary filter
    if intelligence is not None:
        if intelligence < MIN_INTELLIGENCE_SCORE:
            return True
        # High intelligence models are kept regardless of age
        return False
    # No intelligence score available - filter by recency
    if released and MAX_MODEL_AGE_MONTHS > 0:
        try:
            # Handle both "YYYY-MM" string format and Unix timestamp (int)
            if isinstance(released, int):
                rel_date = datetime.fromtimestamp(released, tz=UTC)
            else:
                rel_year, rel_month = released.split("-")
                rel_date = datetime(int(rel_year), int(rel_month), 1, tzinfo=UTC)
            age_months = (datetime.now(UTC) - rel_date).days / 30.44
            if age_months > MAX_MODEL_AGE_MONTHS:
                return True
        except (ValueError, IndexError, OSError):
            pass
    return False





# ── Slug normalization & fuzzy matching ────────────────────────────────────────

# Regex to strip weight numbers from model slugs.
# Matches patterns like: 397b, a17b, 122b, a10b, 550b, a55b, 32b, 72b, etc.
_WEIGHT_RE = re.compile(r"(?:a\d+b|\d+b)\b")


def normalize_slug(slug: str) -> str:
    """Normalize a model slug for matching against AA API slugs.

    Strips org prefix, replaces dots with hyphens, strips common suffixes
    (-chat, -instruct, -free, -latest, -max, -high), and removes weight
    numbers (e.g. 397b, a17b, 122b, a10b) so that models with different
    parameter counts but the same base model can match.
    """
    if "/" in slug:
      slug = slug.split("/", 1)[1]
    slug = slug.replace(".", "-")
    # Strip :free suffix used by Kilo / OpenCode
    if slug.endswith(":free"):
        slug = slug[:-5]
    for suffix in ("-chat", "-instruct", "-free", "-latest", "-max", "-high"):
      if slug.endswith(suffix):
          slug = slug[: -len(suffix)]
          break
    # Remove weight numbers (e.g. 397b, a17b, 122b, a10b)
    slug = _WEIGHT_RE.sub("", slug)
    # Clean up any double hyphens or leading/trailing hyphens left behind
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def fuzzy_match_slug(model_id: str, aa_slugs: dict[str, Any]) -> str | None:
    """Find the best AA slug match for a model ID using normalized + fuzzy matching.

    Args:
      model_id: The model ID from the provider API (e.g. "qwen/qwen3.5-397b-a17b").
      aa_slugs: Dict mapping AA slugs to their enrichment data.

    Returns:
      The best matching AA slug, or None if no match found.
    """
    norm_id = normalize_slug(model_id)

    # Build a normalized slug map for AA slugs
    aa_normalized: dict[str, str] = {}
    for slug in aa_slugs:
      aa_normalized[normalize_slug(slug)] = slug

    # Try exact normalized match first
    if norm_id in aa_normalized:
      return aa_normalized[norm_id]

    # Try fuzzy matching with difflib
    matches = get_close_matches(norm_id, aa_normalized.keys(), n=1, cutoff=0.7)
    if matches:
      return aa_normalized[matches[0]]

    return None
