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
    from huggingface_hub import snapshot_download, HfApi, hf_hub_download
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


def list_repo_files(repo_id):
    """
    List all files in a repository.
    
    Args:
        repo_id: Repository ID to list files from
    
    Returns:
        list: List of file paths in the repository
    """
    try:
        api = HfApi()
        repo_info = api.repo_info(repo_id)
        files = []
        for sibling in repo_info.siblings:
            files.append(sibling.rfilename)
        return files
    except Exception as e:
        print(f"Error listing files in {repo_id}: {e}")
        return []


def detect_model_format(files):
    """
    Detect the model format based on file extensions.
    
    Args:
        files: List of file paths
    
    Returns:
        str: Model format ('gguf', 'openvino', 'mixed', or 'other')
    """
    has_gguf = any(f.endswith('.gguf') for f in files)
    has_openvino = any(f.endswith(('.xml', '.bin')) and 'openvino' in f.lower() for f in files)
    has_openvino_ir = any(f.endswith('.xml') for f in files) and any(f.endswith('.bin') for f in files)
    
    if has_openvino or has_openvino_ir:
        if has_gguf:
            return 'mixed'
        return 'openvino'
    elif has_gguf:
        return 'gguf'
    else:
        return 'other'


def categorize_gguf_files(gguf_files):
    """
    Categorize GGUF files into model files and special files (like mmproj).
    
    Args:
        gguf_files: List of .gguf files
    
    Returns:
        tuple: (model_files, special_files)
    """
    model_files = []
    special_files = []
    
    for file in gguf_files:
        # Check if it's a special file that should always be included
        if any(keyword in file.lower() for keyword in ['mmproj', 'vision', 'clip']):
            special_files.append(file)
        else:
            model_files.append(file)
    
    return model_files, special_files


def find_quantized_files(files, quantization):
    """
    Find files that match the quantization pattern.
    
    Args:
        files: List of file paths
        quantization: Quantization type to search for
    
    Returns:
        list: List of matching files
    """
    import re
    
    # Common quantization patterns
    patterns = [
        rf".*{re.escape(quantization)}.*\.gguf$",  # Exact match with .gguf extension
        rf".*{re.escape(quantization.lower())}.*\.gguf$",  # Lowercase match
        rf".*{re.escape(quantization.upper())}.*\.gguf$",  # Uppercase match
        rf".*{re.escape(quantization.replace('_', '-'))}.*\.gguf$",  # Replace underscores with hyphens
        rf".*{re.escape(quantization.replace('-', '_'))}.*\.gguf$",  # Replace hyphens with underscores
    ]
    
    matching_files = []
    for pattern in patterns:
        for file in files:
            if re.match(pattern, file, re.IGNORECASE):
                if file not in matching_files:
                    matching_files.append(file)
    
    return matching_files


def download_specific_files(repo_id, files, local_dir):
    """
    Download specific files from a repository.
    
    Args:
        repo_id: Repository ID to download from
        files: List of files to download
        local_dir: Local directory to save files
    """
    print(f"Downloading {len(files)} file(s) from {repo_id}...")
    for file in files:
        print(f"  - {file}")
    
    try:
        for file in files:
            hf_hub_download(
                repo_id=repo_id,
                filename=file,
                local_dir=local_dir
            )
        print(f"✓ Successfully downloaded files to {local_dir}")
    except Exception as e:
        print(f"✗ Error downloading files: {e}")
        sys.exit(1)


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


def download_model(repo_id, local_dir, quantization=None, exclude_quantizations=None, format_type="auto", files=None):
    """
    Download model from Hugging Face Hub.
    
    Args:
        repo_id: Repository ID to download
        local_dir: Local directory to save the model
        quantization: Quantization type to search for (if None, downloads all except excluded)
        exclude_quantizations: List of quantization types to exclude
        format_type: Model format ('auto', 'gguf', 'openvino')
        files: Pre-fetched list of files (optional, will fetch if not provided)
    """
    print(f"Analyzing repository: {repo_id}")
    
    # List all files in the repository (if not already provided)
    if files is None:
        files = list_repo_files(repo_id)
        if not files:
            print(f"✗ Could not list files in repository {repo_id}")
            sys.exit(1)
    
    # Detect model format if auto
    if format_type == "auto":
        detected_format = detect_model_format(files)
        print(f"Detected format: {detected_format}")
    else:
        detected_format = format_type
        print(f"Using specified format: {detected_format}")
    
    # Handle OpenVINO format
    if detected_format == "openvino":
        print(f"OpenVINO format detected - downloading entire repository ({len(files)} files)...")
        try:
            snapshot_download(
                repo_id=repo_id,
                local_dir=local_dir
            )
            print(f"✓ Successfully downloaded OpenVINO model {repo_id} to {local_dir}")
            return
        except Exception as e:
            print(f"✗ Error downloading {repo_id}: {e}")
            sys.exit(1)
    
    # Handle mixed format (both GGUF and OpenVINO)
    if detected_format == "mixed":
        print("Mixed format detected (both GGUF and OpenVINO files)")
        if format_type == "auto":
            choice = input("Download (g)guf files only, (o)penvino files only, or (a)ll files? [g/o/a]: ").lower()
            if choice == 'o':
                # Filter to OpenVINO files only
                openvino_files = [f for f in files if f.endswith(('.xml', '.bin')) or 'openvino' in f.lower()]
                non_model_files = [f for f in files if not f.endswith(('.gguf', '.xml', '.bin'))]
                files_to_download = non_model_files + openvino_files
                download_specific_files(repo_id, files_to_download, local_dir)
                return
            elif choice == 'a':
                # Download everything
                snapshot_download(repo_id=repo_id, local_dir=local_dir)
                print(f"✓ Successfully downloaded all files from {repo_id} to {local_dir}")
                return
            # Default to GGUF processing (choice == 'g' or other)
    
    # Handle GGUF format (original logic)
    # Get all non-gguf files (config, tokenizer, README, etc.)
    non_gguf_files = [f for f in files if not f.endswith('.gguf')]
    gguf_files = [f for f in files if f.endswith('.gguf')]
    
    # Categorize GGUF files into model files and special files (mmproj, etc.)
    model_gguf_files, special_gguf_files = categorize_gguf_files(gguf_files)
    
    if quantization:
        # Find model files matching the specific quantization
        matching_model_files = find_quantized_files(model_gguf_files, quantization)
        
        if not matching_model_files:
            print(f"✗ No model files found matching quantization '{quantization}'")
            print("Available model files:")
            for file in sorted(model_gguf_files):
                print(f"  - {file}")
            if special_gguf_files:
                print("Special files (always included):")
                for file in sorted(special_gguf_files):
                    print(f"  - {file}")
            sys.exit(1)
        
        if len(matching_model_files) > 1:
            print(f"Multiple model files found matching '{quantization}':")
            for i, file in enumerate(matching_model_files, 1):
                print(f"  {i}. {file}")
            
            try:
                choice = input("Select file number (or press Enter for all): ").strip()
                if choice:
                    idx = int(choice) - 1
                    if 0 <= idx < len(matching_model_files):
                        matching_model_files = [matching_model_files[idx]]
                    else:
                        print("Invalid selection")
                        sys.exit(1)
            except (ValueError, KeyboardInterrupt):
                print("Invalid input or cancelled")
                sys.exit(1)
        
        # Combine all files: non-gguf + special gguf + selected model files
        files_to_download = non_gguf_files + special_gguf_files + matching_model_files
        print(f"Downloading {len(files_to_download)} files:")
        print(f"  - {len(non_gguf_files)} config/support files")
        print(f"  - {len(special_gguf_files)} special files (mmproj, vision, etc.)")
        print(f"  - {len(matching_model_files)} quantized model file(s)")
        
    elif exclude_quantizations:
        # Download all model files except excluded quantizations, plus all special files
        excluded_files = []
        for exclude_quant in exclude_quantizations:
            excluded_files.extend(find_quantized_files(model_gguf_files, exclude_quant))
        
        # Remove duplicates
        excluded_files = list(set(excluded_files))
        included_model_files = [f for f in model_gguf_files if f not in excluded_files]
        
        # Combine all files: non-gguf + special gguf + included model files
        files_to_download = non_gguf_files + special_gguf_files + included_model_files
        print(f"Downloading {len(files_to_download)} files:")
        print(f"  - {len(non_gguf_files)} config/support files")
        print(f"  - {len(special_gguf_files)} special files (mmproj, vision, etc.)")
        print(f"  - {len(included_model_files)} model files (excluding {len(excluded_files)} files)")
        if excluded_files:
            print("Excluded files:")
            for file in sorted(excluded_files):
                print(f"  - {file}")
        
    else:
        # Download entire repository
        print(f"Downloading entire repository ({len(files)} files)...")
        try:
            snapshot_download(
                repo_id=repo_id,
                local_dir=local_dir
            )
            print(f"✓ Successfully downloaded {repo_id} to {local_dir}")
            return
        except Exception as e:
            print(f"✗ Error downloading {repo_id}: {e}")
            sys.exit(1)
    
    # Download specific files
    download_specific_files(repo_id, files_to_download, local_dir)


def main():
    parser = argparse.ArgumentParser(
        description="Download models from Hugging Face Hub with quantization support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  hf.py llama-2-7b-chat
  hf.py microsoft/DialoGPT-medium  
  hf.py llama-2-7b-chat --quantization Q4_K_M
  hf.py unsloth/llama-2-7b-bnb-4bit --quantization UD-Q8_0
  hf.py llama-2-7b-chat --exclude-quantization Q2_K --exclude-quantization Q3_K_S
  hf.py intel/llama-2-7b-chat-int4-ov --format openvino"""
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
    
    parser.add_argument(
        "--list-files", "-l",
        action="store_true",
        help="List all .gguf files in the repository without downloading"
    )
    
    parser.add_argument(
        "--exclude-quantization", "-e",
        action="append",
        help="Exclude specific quantization types (can be used multiple times)"
    )
    
    parser.add_argument(
        "--format", "-f",
        choices=["auto", "gguf", "openvino"],
        default="auto",
        help="Model format to download (default: auto-detect)"
    )
    
    args = parser.parse_args()
    
    # Parse the model input
    user, model_name, base_repo_id = parse_model_path(args.model, args.user)
    
    # Use the base repository ID (don't append quantization to repo name)
    repo_id = base_repo_id
    
    # Check if repository exists
    if not check_repo_exists(repo_id):
        print(f"✗ Repository {repo_id} not found on Hugging Face Hub")
        sys.exit(1)
    
    # If user wants to list files, do that and exit
    if args.list_files:
        files = list_repo_files(repo_id)
        detected_format = detect_model_format(files)
        
        print(f"Repository format: {detected_format}")
        print(f"Total files: {len(files)}")
        
        gguf_files = [f for f in files if f.endswith('.gguf')]
        openvino_files = [f for f in files if f.endswith(('.xml', '.bin')) and ('openvino' in f.lower() or f.endswith('.xml'))]
        
        if gguf_files:
            print(f"\nGGUF files ({len(gguf_files)}):")
            for file in sorted(gguf_files):
                print(f"  - {file}")
        
        if openvino_files:
            print(f"\nOpenVINO files ({len(openvino_files)}):")
            for file in sorted(openvino_files):
                print(f"  - {file}")
        
        if not gguf_files and not openvino_files:
            print("\nNo GGUF or OpenVINO model files found")
            print("Other files:")
            for file in sorted(files[:10]):  # Show first 10 files
                print(f"  - {file}")
            if len(files) > 10:
                print(f"  ... and {len(files) - 10} more files")
        
        sys.exit(0)
    
    # Detect format early to determine directory naming
    files = list_repo_files(repo_id)
    if args.format == "auto":
        detected_format = detect_model_format(files)
    else:
        detected_format = args.format
    
    # Determine quantization to search for
    if args.no_quantization:
        quantization = None
        exclude_quantizations = None
        local_dir = model_name
    else:
        quantization = args.quantization if not args.exclude_quantization else None
        exclude_quantizations = args.exclude_quantization
        if quantization:
            local_dir = f"{model_name}-{args.quantization}"
        else:
            local_dir = model_name
    
    # For OpenVINO format (explicit or auto-detected), always use the model name as directory
    if args.format == "openvino" or detected_format == "openvino":
        local_dir = model_name
    
    # Check if directory already exists
    if os.path.exists(local_dir):
        response = input(f"Directory '{local_dir}' already exists. Continue? [y/N]: ")
        if response.lower() not in ['y', 'yes']:
            print("Aborted.")
            sys.exit(0)
    
    # Create directory
    Path(local_dir).mkdir(exist_ok=True)
    
    # Download the model
    download_model(repo_id, local_dir, quantization, exclude_quantizations, detected_format, files)


if __name__ == "__main__":
    main()