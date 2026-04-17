#!/usr/bin/env python3
"""
Model Responsiveness Tester for OpenAI-compatible APIs

Tests TTFT (Time To First Token) and TPS (Tokens Per Second) for multiple models.
"""

import time
import json
import requests
import argparse
from typing import List, Dict, Tuple

# Global configuration - modify these as needed
API_ENDPOINT = "http://localhost:8000/v1/chat/completions"  # OpenAI-compatible endpoint
API_KEY = "sk-test-key"  # API key (or set via environment)
MODELS = [
    "qwen3.5-9b",
    "mistral-7b-instruct",
    "codellama-7b-instruct",
    "deepseek-coder-6.7b",
]

# Test prompt - keep it short for consistent measurements
TEST_PROMPT = "Write a simple hello world function in Python."
MAX_TOKENS = 100  # Limit response length for testing


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
            endpoint, headers=headers, json=payload, stream=True, timeout=60
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
                                        print(".3f")
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

    print(".1f")
    print(".1f")
    return {"ttft": ttft, "tps": tps, "tokens": tokens}


def main():
    # Declare globals that will be modified
    global API_ENDPOINT, API_KEY, TEST_PROMPT, MAX_TOKENS

    parser = argparse.ArgumentParser(
        description="Test model responsiveness for OpenAI-compatible APIs"
    )
    parser.add_argument(
        "--endpoint",
        default=API_ENDPOINT,
        help=f"API endpoint (default: {API_ENDPOINT})",
    )
    parser.add_argument("--api-key", default=API_KEY, help="API key")
    parser.add_argument("--models", nargs="+", default=MODELS, help="Models to test")
    parser.add_argument("--prompt", default=TEST_PROMPT, help="Test prompt")
    parser.add_argument(
        "--max-tokens", type=int, default=MAX_TOKENS, help="Max tokens to generate"
    )

    args = parser.parse_args()

    # Update globals from args
    API_ENDPOINT = args.endpoint
    API_KEY = args.api_key
    TEST_PROMPT = args.prompt
    MAX_TOKENS = args.max_tokens

    print("🚀 Model Responsiveness Tester")
    print(f"📍 Endpoint: {API_ENDPOINT}")
    print(f"📝 Prompt: {TEST_PROMPT}")
    print(f"🎯 Max tokens: {MAX_TOKENS}")
    print(f"🤖 Models to test: {', '.join(args.models)}")

    results = []
    for model in args.models:
        result = test_model(model, API_KEY, API_ENDPOINT)
        result["model"] = model
        results.append(result)

    # Summary table
    print(f"\n{'=' * 60}")
    print("📊 SUMMARY RESULTS")
    print(f"{'=' * 60}")
    print("<20")
    print("-" * 60)

    for result in results:
        model = result["model"]
        ttft = result["ttft"]
        tps = result["tps"]
        tokens = result["tokens"]

        if ttft == float("inf"):
            print("<20")
        else:
            print("<20")

    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
