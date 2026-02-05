#!/usr/bin/env python3
"""
Test script for hf.py argument parsing and file matching logic.
"""

import sys
import os
import re

def parse_model_path(model_input, default_user="unsloth"):
    """
    Parse model input and return user/model_name format.
    """
    if "/" in model_input:
        user, model_name = model_input.split("/", 1)
    else:
        user = default_user
        model_name = model_input
    
    repo_id = f"{user}/{model_name}"
    return user, model_name, repo_id

def detect_model_format(files):
    """
    Detect the model format based on file extensions.
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
    """
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

def test_parse_model_path():
    """Test model path parsing."""
    print("Testing parse_model_path...")
    
    # Test with just model name
    user, model, repo_id = parse_model_path("llama-2-7b-chat")
    assert user == "unsloth"
    assert model == "llama-2-7b-chat"
    assert repo_id == "unsloth/llama-2-7b-chat"
    print("✓ Model name only: OK")
    
    # Test with user/model
    user, model, repo_id = parse_model_path("microsoft/DialoGPT-medium")
    assert user == "microsoft"
    assert model == "DialoGPT-medium"
    assert repo_id == "microsoft/DialoGPT-medium"
    print("✓ User/model format: OK")
    
    # Test with custom default user
    user, model, repo_id = parse_model_path("llama-2-7b", "meta-llama")
    assert user == "meta-llama"
    assert model == "llama-2-7b"
    assert repo_id == "meta-llama/llama-2-7b"
    print("✓ Custom default user: OK")

def test_find_quantized_files():
    """Test quantized file matching."""
    print("\nTesting find_quantized_files...")
    
    # Sample file list
    files = [
        "model-Q4_K_M.gguf",
        "model-q4_k_m.gguf",
        "model-Q4-K-M.gguf",
        "llama-2-7b-chat-UD-Q4_K_XL.gguf",
        "llama-2-7b-chat-ud-q4_k_xl.gguf",
        "other-file.txt",
        "README.md"
    ]
    
    # Test exact match
    matches = find_quantized_files(files, "Q4_K_M")
    assert "model-Q4_K_M.gguf" in matches
    assert "model-q4_k_m.gguf" in matches
    assert "model-Q4-K-M.gguf" in matches
    print("✓ Q4_K_M matching: OK")
    
    # Test UD-Q4_K_XL match
    matches = find_quantized_files(files, "UD-Q4_K_XL")
    assert "llama-2-7b-chat-UD-Q4_K_XL.gguf" in matches
    assert "llama-2-7b-chat-ud-q4_k_xl.gguf" in matches
    print("✓ UD-Q4_K_XL matching: OK")
    
    # Test no matches
    matches = find_quantized_files(files, "Q8_0")
    assert len(matches) == 0
    print("✓ No matches for Q8_0: OK")

def test_categorize_gguf_files():
    """Test GGUF file categorization."""
    print("\nTesting categorize_gguf_files...")
    
    # Sample file list
    files = [
        "model-Q4_K_M.gguf",
        "model-Q8_0.gguf", 
        "mmproj-model-f16.gguf",
        "vision-encoder.gguf",
        "clip-vit-large-patch14.gguf",
        "llama-2-7b-chat-UD-Q4_K_XL.gguf"
    ]
    
    model_files, special_files = categorize_gguf_files(files)
    
    # Check special files
    assert "mmproj-model-f16.gguf" in special_files
    assert "vision-encoder.gguf" in special_files
    assert "clip-vit-large-patch14.gguf" in special_files
    print("✓ Special files identified: OK")
    
    # Check model files
    assert "model-Q4_K_M.gguf" in model_files
    assert "model-Q8_0.gguf" in model_files
    assert "llama-2-7b-chat-UD-Q4_K_XL.gguf" in model_files
    print("✓ Model files identified: OK")
    
    # Ensure no overlap
    assert len(set(model_files) & set(special_files)) == 0
    print("✓ No overlap between categories: OK")

def test_detect_model_format():
    """Test model format detection."""
    print("\nTesting detect_model_format...")
    
    # Test GGUF format
    gguf_files = ["model-Q4_K_M.gguf", "config.json", "tokenizer.json"]
    assert detect_model_format(gguf_files) == "gguf"
    print("✓ GGUF format detection: OK")
    
    # Test OpenVINO format
    openvino_files = ["openvino_model.xml", "openvino_model.bin", "config.json"]
    assert detect_model_format(openvino_files) == "openvino"
    print("✓ OpenVINO format detection: OK")
    
    # Test OpenVINO IR format (without 'openvino' in filename)
    ir_files = ["model.xml", "model.bin", "config.json"]
    assert detect_model_format(ir_files) == "openvino"
    print("✓ OpenVINO IR format detection: OK")
    
    # Test mixed format
    mixed_files = ["model-Q4_K_M.gguf", "openvino_model.xml", "openvino_model.bin", "config.json"]
    assert detect_model_format(mixed_files) == "mixed"
    print("✓ Mixed format detection: OK")
    
    # Test other format
    other_files = ["pytorch_model.bin", "config.json", "tokenizer.json"]
    assert detect_model_format(other_files) == "other"
    print("✓ Other format detection: OK")

if __name__ == "__main__":
    test_parse_model_path()
    test_find_quantized_files()
    test_categorize_gguf_files()
    test_detect_model_format()
    print("\n✓ All tests passed!")