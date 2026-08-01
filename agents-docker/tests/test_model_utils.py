"""Tests for model_utils module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from model_utils import (
    normalize_slug,
    fuzzy_match_slug,
    is_model_hidden,
    load_cache,
    save_cache,
    HIDE_MODELS,
    MIN_INTELLIGENCE_SCORE,
    MAX_MODEL_AGE_MONTHS,
)


def test_normalize_slug():
    """Test slug normalization strips org, dots, suffixes, and weight numbers."""
    assert normalize_slug("qwen/qwen3.5-397b-a17b") == "qwen3-5"
    assert normalize_slug("qwen/qwen3.5-122b-a10b") == "qwen3-5"
    assert normalize_slug("nvidia/nemotron-3-ultra-550b-a55b") == "nemotron-3-ultra"
    assert normalize_slug("google/gemma-4-31b-it") == "gemma-4-it"
    assert normalize_slug("google/gemma-4-26b-a4b-it") == "gemma-4-it"
    assert normalize_slug("moonshotai/kimi-k2.7") == "kimi-k2-7"
    assert normalize_slug("moonshotai/kimi-k2.6") == "kimi-k2-6"


def test_fuzzy_match_slug():
    """Test fuzzy matching against AA slugs."""
    aa_slugs = {
        "qwen-3.5-72b": {"intelligence": 50.0},
        "gemma-4-26b-a4b-it": {"intelligence": 9.7},
    }
    assert fuzzy_match_slug("qwen/qwen3.5-397b-a17b", aa_slugs) == "qwen-3.5-72b"
    assert fuzzy_match_slug("qwen/qwen3.5-122b-a10b", aa_slugs) == "qwen-3.5-72b"
    assert fuzzy_match_slug("google/gemma-4-31b-it", aa_slugs) == "gemma-4-26b-a4b-it"
    assert fuzzy_match_slug("google/gemma-4-26b-a4b-it", aa_slugs) == "gemma-4-26b-a4b-it"


def test_is_model_hidden_nvidia_nim():
    """Test hide list filtering only applies to nvidia-nim."""
    # Non-nvidia-nim providers should never be hidden
    assert is_model_hidden("some/model", 10.0, "2024-01", "kilocode") is False
    assert is_model_hidden("some/model", 10.0, "2024-01", "opencode") is False
    assert is_model_hidden("some/model", 10.0, "2024-01", "ollama-cloud") is False
    assert is_model_hidden("some/model", 10.0, "2024-01", "google-ai-studio") is False

    # Models in HIDE_MODELS should be hidden
    assert is_model_hidden("nvidia/nemoguard-3b", 90.0, "2024-01", "nvidia-nim") is True
    assert is_model_hidden("nvidia/nv-embed-v1", 90.0, "2024-01", "nvidia-nim") is True

    # Low intelligence models should be hidden (below MIN_INTELLIGENCE_SCORE=10.0)
    assert is_model_hidden("nvidia/some-model", 5.0, "2024-01", "nvidia-nim") is True
    
    # Models at or above threshold should be kept
    assert is_model_hidden("nvidia/some-model", 10.0, "2024-01", "nvidia-nim") is False
    assert is_model_hidden("nvidia/some-model", 15.0, "2024-01", "nvidia-nim") is False

    # High intelligence models should be kept regardless of age
    assert is_model_hidden("nvidia/some-model", 60.0, "2020-01", "nvidia-nim") is False

    # Models without intelligence score should be filtered by recency (older than MAX_MODEL_AGE_MONTHS)
    assert is_model_hidden("nvidia/some-model", None, "2020-01", "nvidia-nim") is True
    # Recent models without intelligence score should be kept (within 12 months)
    assert is_model_hidden("nvidia/some-model", None, "2025-08", "nvidia-nim") is False


def test_cache_save_load(tmp_path):
    """Test cache save and load functionality."""
    import model_utils
    original_cache_file = model_utils.CACHE_FILE
    model_utils.CACHE_FILE = tmp_path / "test-cache.json"

    try:
        test_data = {
            "model1": {"intelligence": 50.0, "released": "2024-01"},
            "model2": {"intelligence": 60.0, "released": "2024-06"},
        }
        save_cache(test_data)
        loaded = load_cache()
        assert loaded == test_data
    finally:
        model_utils.CACHE_FILE = original_cache_file


def test_hide_models_constants():
    """Test that constants are properly defined."""
    assert isinstance(HIDE_MODELS, set)
    assert len(HIDE_MODELS) > 0
    assert MIN_INTELLIGENCE_SCORE == 10.0
    assert MAX_MODEL_AGE_MONTHS == 12