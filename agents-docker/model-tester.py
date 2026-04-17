#!/usr/bin/env python3
"""
Model Responsiveness Tester for NVIDIA Developer Build API

Tests TTFT (Time To First Token) and TPS (Tokens Per Second) for NVIDIA models.
Set NVIDIA_API_KEY environment variable with your API key from: https://build.nvidia.com/
"""

import time
import json
import os
import requests
import argparse
from typing import List, Dict, Tuple

# Global configuration - modify these as needed
API_ENDPOINT = (
    "https://integrate.api.nvidia.com/v1/chat/completions"  # NVIDIA Developer Build API
)
API_KEY = os.getenv("NVIDIA_API_KEY", "")  # NVIDIA API key from environment variable
MODELS = [
    "google/gemma-4-31b-it",
    "qwen/qwen3.5-397b-a17b",
    "moonshotai/kimi-k2.5",
    "z-ai/glm5",
    "minimaxai/minimax-m2.7",
    "nvidia/nemotron-3-super-120b-a12b",
    "stepfun-ai/step-3.5-flash",
    "qwen/qwen3-next-80b-a3b-thinking",
    "qwen/qwen3.5-122b-a10b",
    "deepseek-ai/deepseek-v3_2",
]

# Test prompt - keep it short for consistent measurements
TEST_PROMPT = "Write a simple hello world function in Python."
MAX_TOKENS = 100  # Limit response length for testing
TIMEOUT = 20  # Request timeout in seconds


def validate_endpoint(api_key: str, endpoint: str, models_to_test: List[str]) -> bool:
    """
    Validate that the endpoint is working and supports the required models.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    models_url = endpoint.replace("/chat/completions", "/models")

    try:
        print("🔍 Validating endpoint and API key...")
        response = requests.get(models_url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()

        data = response.json()
        available_models = [model["id"] for model in data.get("data", [])]

        print(f"✅ Endpoint reachable. Found {len(available_models)} available models.")

        # Check if our test models are available
        missing_models = []
        for model in models_to_test:
            if model not in available_models:
                missing_models.append(model)

        if missing_models:
            print(f"⚠️  Warning: {len(missing_models)} requested models not available:")
            for model in missing_models[:5]:  # Show first 5
                print(f"   - {model}")
            if len(missing_models) > 5:
                print(f"   ... and {len(missing_models) - 5} more")

        return True

    except requests.exceptions.RequestException as e:
        print(f"❌ Endpoint validation failed: {e}")
        if "401" in str(e):
            print("💡 Check your API key - authentication failed")
        elif "403" in str(e):
            print("💡 Check your API permissions - access denied")
        elif "404" in str(e):
            print("💡 Models endpoint not found - API may not support model listing")
        return False
    except Exception as e:
        print(f"❌ Unexpected error during validation: {e}")
        return False


def make_streaming_request(
    model: str, prompt: str, api_key: str, endpoint: str
) -> Tuple[float, float, int]:
    """
    Make a streaming request to the API and measure timing.

    Returns:
        ttft (float): Time to first token in seconds
        tps (float): Tokens per second for generation
        total_tokens (int): Total tokens generated
    """
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_TOKENS,
        "stream": True,
        "temperature": 0.7,
    }

    start_time = time.time()
    ttft = None
    token_count = 0
    last_token_time = start_time

    try:
        with requests.post(
            endpoint, headers=headers, json=payload, stream=True, timeout=TIMEOUT
        ) as response:
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    line = line.decode("utf-8")
                    if line.startswith("data: "):
                        data = line[6:]  # Remove 'data: ' prefix

                        if data == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data)
                            if "choices" in chunk and chunk["choices"]:
                                delta = chunk["choices"][0].get("delta", {})
                                content = delta.get("content", "")

                                if content:  # Actual token content
                                    current_time = time.time()

                                    if ttft is None:
                                        # First token received
                                        ttft = current_time - start_time
                                    token_count += 1

                                    last_token_time = current_time

                        except json.JSONDecodeError:
                            continue

        # Calculate final metrics
        end_time = time.time()
        total_time = end_time - start_time

        if ttft is None:
            # No tokens received
            return float("inf"), 0.0, 0

        generation_time = total_time - ttft
        tps = token_count / generation_time if generation_time > 0 else 0.0

        return ttft, tps, token_count

    except Exception as e:
        print(f"Error testing model {model}: {e}")
        return float("inf"), 0.0, 0


def test_model(model: str, api_key: str, endpoint: str) -> Dict[str, float]:
    """Test a single model and return results."""
    print(f"\n🔍 Testing model: {model}")

    ttft, tps, tokens = make_streaming_request(model, TEST_PROMPT, api_key, endpoint)

    if ttft == float("inf"):
        print(f"❌ Model {model} failed to respond")
        return {"ttft": float("inf"), "tps": 0.0, "tokens": 0}

    print(f"TTFT: {ttft * 1000:.1f} ms")
    print(f"TPS: {tps:.1f} tokens/sec")
    return {"ttft": ttft, "tps": tps, "tokens": tokens}


def main():
    # Declare globals that will be modified
    global API_ENDPOINT, API_KEY, TEST_PROMPT, MAX_TOKENS, TIMEOUT

    parser = argparse.ArgumentParser(
        description="Test model responsiveness for NVIDIA Developer Build API"
    )
    parser.add_argument(
        "--endpoint",
        default=API_ENDPOINT,
        help=f"API endpoint (default: {API_ENDPOINT})",
    )
    parser.add_argument(
        "--api-key", default=API_KEY, help="API key (overrides NVIDIA_API_KEY env var)"
    )
    parser.add_argument("--models", nargs="+", default=MODELS, help="Models to test")
    parser.add_argument("--prompt", default=TEST_PROMPT, help="Test prompt")
    parser.add_argument(
        "--max-tokens", type=int, default=MAX_TOKENS, help="Max tokens to generate"
    )
    parser.add_argument(
        "--timeout", type=int, default=TIMEOUT, help="Request timeout in seconds"
    )

    args = parser.parse_args()

    # Update globals from args
    API_ENDPOINT = args.endpoint
    API_KEY = args.api_key or API_KEY  # Use arg if provided, otherwise env var
    TEST_PROMPT = args.prompt
    MAX_TOKENS = args.max_tokens
    TIMEOUT = args.timeout

    # Validate API key is set
    if not API_KEY:
        print("❌ NVIDIA_API_KEY environment variable not set!")
        print("💡 Get your API key from: https://build.nvidia.com/")
        print("💡 Set it with: export NVIDIA_API_KEY=your-api-key-here")
        exit(1)

    print("🚀 NVIDIA Model Responsiveness Tester")
    print(f"📍 Endpoint: {API_ENDPOINT}")
    print(f"📝 Prompt: {TEST_PROMPT}")
    print(f"🎯 Max tokens: {MAX_TOKENS}")
    print(f"⏱️  Timeout: {TIMEOUT}s")
    print(f"🤖 Models to test: {', '.join(args.models)}")
    print(f"🔑 API Key: {'*' * 8 + API_KEY[-4:] if len(API_KEY) > 12 else API_KEY}")

    # Validate endpoint before starting tests
    if not validate_endpoint(API_KEY, API_ENDPOINT, args.models):
        print("💥 Cannot proceed with tests due to endpoint/API issues.")
        exit(1)

    results = []
    for model in args.models:
        result = test_model(model, API_KEY, API_ENDPOINT)
        result["model"] = model
        results.append(result)

    # Sort results by TTFT (ascending, failed models last)
    results.sort(key=lambda x: x["ttft"] if x["ttft"] != float("inf") else float("inf"))

    # Summary table
    print(f"\n{'=' * 80}")
    print("📊 SUMMARY RESULTS")
    print(f"{'=' * 80}")
    print(f"{'Model':<45} {'TTFT (ms)':>12} {'TPS':>10} {'Tokens':>8}")
    print("-" * 80)

    for result in results:
        model = result["model"]
        ttft = result["ttft"]
        tps = result["tps"]
        tokens = result["tokens"]

        if ttft == float("inf"):
            print(f"{model:<45} {'FAILED':>12} {'-':>10} {'-':>8}")
        else:
            print(f"{model:<45} {ttft * 1000:>12.1f} {tps:>10.1f} {tokens:>8}")

    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
