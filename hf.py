#!/usr/bin/env python3
"""
Hugging Face model downloader script.
Downloads models with specified quantization, similar to git clone behavior.

Usage:
    python hf.py <model_name>
    python hf.py <user>/<model_name>
    python hf.py <user>/<model_name> --quantization <quant>
    python hf.py <model_name> --quantization <quant>

Examples:
    python hf.py llama-2-7b-chat
    python hf.py microsoft/DialoGPT-medium
    python hf.py llama-2-7b-chat --quantization Q4_K_M
"""

import argparse
import os
import sys
from pathlib import Path

try:
    from huggingface_hub import snapshot_download, HfApi
    from huggingface_hub.utils import HfHubHTTPError
except ImportError:
    print("Error: huggingface_hub is required. Install with: pip install huggingface_hub")
    sys.exit(1)


def parse_model_path(model_input, default_user="unsloth"):
    """
    Parse model input and return user/model_name format.
    
    Args:
        model_input: Either 'model_name' or 'user/model_name'
        default_user: Default user if none provided
    
    Returns:
        tuple: (user, model_name, full_repo_id)
    """
    if "/" in model_input:
        user, model_name = model_input.split("/", 1)
    else:
        user = default_user
        model_name = model_input
    
    repo_id = f"{user}/{model_name}"
    return user, model_name, repo_id


def get_quantized_repo_id(base_repo_id, quantization):
    """
    Generate the quantized repository ID.
    
    Args:
        base_repo_id: Base repository ID (user/model)
        quantization: Quantization type
    
    Returns:
        str: Full quantized repository ID
    """
    user, model = base_repo_id.split("/", 1)
    return f"{user}/{model}-{quantization}"


def check_repo_exists(repo_id):
    """
    Check if a repository exists on Hugging Face.
    
    Args:
        repo_id: Repository ID to check
    
    Returns:
        bool: True if repository exists
    """
    try:
        api = HfApi()
        api.repo_info(repo_id)
        return True
    except HfHubHTTPError:
        return False


def download_model(repo_id, local_dir, quantization=None):
    """
    Download model from Hugging Face Hub.
    
    Args:
        repo_id: Repository ID to download
        local_dir: Local directory to save the model
        quantization: Quantization type (for display purposes)
    """
    print(f"Downloading {repo_id}...")
    if quantization:
        print(f"Quantization: {quantization}")
    print(f"Destination: {local_dir}")
    
    try:
        snapshot_download(
            repo_id=repo_id,
            local_dir=local_dir,
            local_dir_use_symlinks=False,
            resume_download=True
        )
        print(f"✓ Successfully downloaded {repo_id} to {local_dir}")
    except Exception as e:
        print(f"✗ Error downloading {repo_id}: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Download models from Hugging Face Hub with quantization support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s llama-2-7b-chat
  %(prog)s microsoft/DialoGPT-medium  
  %(prog)s llama-2-7b-chat --quantization Q4_K_M
  %(prog)s microsoft/DialoGPT-medium --quantization UD-Q8_0
        """
    )
    
    parser.add_argument(
        "model",
        help="Model name or user/model_name to download"
    )
    
    parser.add_argument(
        "--quantization", "-q",
        default="UD-Q4_K_XL",
        help="Quantization type (default: UD-Q4_K_XL)"
    )
    
    parser.add_argument(
        "--user", "-u",
        default="unsloth",
        help="Default user if not specified in model name (default: unsloth)"
    )
    
    parser.add_argument(
        "--no-quantization",
        action="store_true",
        help="Download original model without quantization suffix"
    )
    
    args = parser.parse_args()
    
    # Parse the model input
    user, model_name, base_repo_id = parse_model_path(args.model, args.user)
    
    # Determine the repository to download
    if args.no_quantization:
        repo_id = base_repo_id
        quantization = None
    else:
        repo_id = get_quantized_repo_id(base_repo_id, args.quantization)
        quantization = args.quantization
    
    # Check if repository exists
    if not check_repo_exists(repo_id):
        print(f"✗ Repository {repo_id} not found on Hugging Face Hub")
        if not args.no_quantization:
            print(f"  Try without quantization: --no-quantization")
            print(f"  Or try a different quantization: --quantization <type>")
        sys.exit(1)
    
    # Create local directory (similar to git clone behavior)
    if args.no_quantization:
        local_dir = model_name
    else:
        local_dir = f"{model_name}-{args.quantization}"
    
    # Check if directory already exists
    if os.path.exists(local_dir):
        response = input(f"Directory '{local_dir}' already exists. Continue? [y/N]: ")
        if response.lower() not in ['y', 'yes']:
            print("Aborted.")
            sys.exit(0)
    
    # Create directory
    Path(local_dir).mkdir(exist_ok=True)
    
    # Download the model
    download_model(repo_id, local_dir, quantization)


if __name__ == "__main__":
    main()