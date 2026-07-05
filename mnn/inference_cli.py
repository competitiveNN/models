#!/usr/bin/env python3
"""
Simple CLI tool for running inference on Qwen models using PyMNN (MNN-LLM).
"""

import argparse
import sys
import os

try:
    import MNN.llm as mnnllm
except ImportError:
    print("Error: MNN.llm not found. Please install PyMNN with LLM support.")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Run inference on Qwen models using MNN")
    parser.add_argument("model_path", help="Path to the MNN model directory containing config.json")
    parser.add_argument("prompt", help="Input prompt for the model")
    parser.add_argument("--max_tokens", type=int, default=512, help="Maximum number of tokens to generate")
    parser.add_argument("--temperature", type=float, default=0.7, help="Temperature for sampling")
    parser.add_argument("--top_p", type=float, default=0.9, help="Top-p for sampling")
    parser.add_argument("--top_k", type=int, default=50, help="Top-k for sampling")
    parser.add_argument("--stream", action="store_true", help="Stream the output")
    parser.add_argument("--backend", type=str, default=None, choices=["cpu", "opencl", "vulkan", "cuda", "metal"],
                        help="Backend type for inference (cpu, opencl, vulkan, cuda, metal). Overrides config.json setting.")
    parser.add_argument("--threads", type=int, default=None,
                        help="Number of CPU threads for inference. Overrides config.json setting.")

    args = parser.parse_args()

    if not os.path.exists(args.model_path):
        print(f"Error: Model path '{args.model_path}' does not exist.")
        sys.exit(1)

    config_path = os.path.join(args.model_path, "config.json")
    if not os.path.exists(config_path):
        print(f"Error: config.json not found in '{args.model_path}'")
        sys.exit(1)

    try:
        # Create LLM instance
        llm = mnnllm.create(config_path)

        # Load the model
        llm.load()

        # Set backend if specified
        if args.backend:
            backend_config = {"backend_type": args.backend}
            llm.set_config(backend_config)
            print(f"[Backend set to: {args.backend}]")
        
        # Set number of threads if specified
        if args.threads is not None:
            thread_config = {"thread_num": args.threads}
            llm.set_config(thread_config)
            print(f"[Threads set to: {args.threads}]")

        # Configure generation parameters
        # Note: The exact parameter names may vary; adjust based on MNN-LLM API
        # Assuming the API allows setting these via config or method calls

        # Generate response
        if args.stream:
            response = llm.response(args.prompt, stream=True)
            # Handle streaming - response might be a generator or the full string
            if hasattr(response, '__iter__') and not isinstance(response, str):
                for chunk in response:
                    print(chunk, end="", flush=True)
                print()
            else:
                # Response is already printed by C++ backend, or is the full string
                if response and isinstance(response, str):
                    print(response)
        else:
            response = llm.response(args.prompt, stream=False)
            print(response)
        
        # Show performance metrics
        ctx = llm.context
        decode_us = ctx.decode_us
        output_tokens = ctx.output_tokens
        if decode_us > 0 and len(output_tokens) > 0:
            tps = len(output_tokens) / (decode_us / 1_000_000)
            print(f"\n[TPS: {tps:.2f} tokens/sec, {len(output_tokens)} tokens in {decode_us/1000:.2f}ms]")

    except Exception as e:
        print(f"Error during inference: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()