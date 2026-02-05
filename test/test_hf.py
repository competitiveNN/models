#!/usr/bin/env python3
"""
Test script for hf.py argument parsing logic.
"""

import sys
import os

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

def get_quantized_repo_id(base_repo_id, quantization):
    """
    Generate the quantized repository ID.
    """
    user, model = base_repo_id.split("/", 1)
    return f"{user}/{model}-{quantization}"

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

def test_get_quantized_repo_id():
    """Test quantized repository ID generation."""
    print("\nTesting get_quantized_repo_id...")
    
    repo_id = get_quantized_repo_id("unsloth/llama-2-7b-chat", "UD-Q4_K_XL")
    assert repo_id == "unsloth/llama-2-7b-chat-UD-Q4_K_XL"
    print("✓ Quantized repo ID: OK")
    
    repo_id = get_quantized_repo_id("microsoft/DialoGPT-medium", "Q4_K_M")
    assert repo_id == "microsoft/DialoGPT-medium-Q4_K_M"
    print("✓ Different quantization: OK")

if __name__ == "__main__":
    test_parse_model_path()
    test_get_quantized_repo_id()
    print("\n✓ All tests passed!")