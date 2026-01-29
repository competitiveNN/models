#!/usr/bin/env python3
"""
Model Export Tool for OpenVINO

A comprehensive tool for exporting AI/ML models to OpenVINO format with
optimized quantization, calibration, and shape handling.
"""

import os
import sys
import argparse
from pathlib import Path

# Try to import torch for memory optimization
try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


def is_awq_model(model_name):
    """Check if model name contains AWQ quantization."""
    return 'awq' in model_name.lower()


def detect_task_for(model_name):
    """Detect model task from name using heuristics."""
    name_lower = model_name.lower()

    # Heuristics based on common model naming conventions
    if 'whisper' in name_lower:
        return "automatic-speech-recognition-with-past"
    elif any(x in name_lower for x in ['t5', 'bart', 'mbart']):
        return "text2text-generation-with-past"
    elif any(x in name_lower for x in ['stable-diffusion', 'sdxl']):
        return "text-to-image"

    return "text-generation-with-past"


def default_out_dir_for(model_name, weight_format):
    """Generate default output directory name."""
    # Extract base name from model path
    base = os.path.basename(model_name)
    base = base.split('/')[0] if '/' in base else base
    base = base.replace('/', '-').replace(' ', '-')
    base = ''.join(c for c in base if c.isalnum() or c in '._-')

    awq_suffix = "-awq" if is_awq_model(model_name) else ""

    return f"{base}-{weight_format}{awq_suffix}-ov"


def export_model(model_id, task, output_dir, mode='fast', dataset='wikitext2', low_cpu_mem_usage=True, cache_dir=None, revision=None, token=None, weight_format='int4'):
    """Export model using Optimum Intel."""
    os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'

    # Determine the appropriate model class based on task
    task_classes = {
        'text-generation-with-past': 'OVModelForCausalLM',
        'text2text-generation-with-past': 'OVModelForSeq2SeqLM',
        'automatic-speech-recognition-with-past': 'OVModelForSpeechSeq2Seq',
        'text-to-image': 'OVStableDiffusionPipeline'
    }

    # Import required classes
    from optimum.intel import (
        OVModelForCausalLM,
        OVModelForSeq2SeqLM,
        OVModelForSpeechSeq2Seq,
        OVStableDiffusionPipeline
    )

    # Try to import quantization config
    try:
        from optimum.intel import OVWeightQuantizationConfig
        HAS_QUANTIZATION = True
    except ImportError:
        HAS_QUANTIZATION = False

    # Create mapping of class names to actual classes
    class_mapping = {
        'OVModelForCausalLM': OVModelForCausalLM,
        'OVModelForSeq2SeqLM': OVModelForSeq2SeqLM,
        'OVModelForSpeechSeq2Seq': OVModelForSpeechSeq2Seq,
        'OVStableDiffusionPipeline': OVStableDiffusionPipeline
    }

    task = task or 'text-generation-with-past'
    model_class_name = task_classes.get(task, 'OVModelForCausalLM')
    model_class = class_mapping[model_class_name]

    mode_desc = "with calibration" if mode == 'slow' else "fast"
    print(f'Exporting {task} model {mode_desc}')

    # Export model
    # Note: Scale estimation for slow mode is not currently supported in Python API
    # This exports without calibration
    if mode == 'slow':
        print("Warning: Scale estimation (calibration) not yet supported in Python API")
        print("Falling back to export without calibration")
    # Use comprehensive loading parameters for optimal export
    load_kwargs = {
        "export": True,
        "trust_remote_code": True,
        "low_cpu_mem_usage": low_cpu_mem_usage,
        "force_download": False,  # Don't force download, use cache if available
        "local_files_only": False,  # Allow downloading if needed
    }

    # Add quantization config if available and not fp32
    if HAS_QUANTIZATION and weight_format != 'fp32':
        if weight_format == 'int4':
            quant_config = OVWeightQuantizationConfig(bits=4)
        elif weight_format == 'int8':
            quant_config = OVWeightQuantizationConfig(bits=8)
        elif weight_format == 'fp16':
            # fp16 might not need quantization config, but we'll handle it
            quant_config = OVWeightQuantizationConfig(bits=16)
        else:
            quant_config = OVWeightQuantizationConfig(bits=4)  # default fallback

        load_kwargs["quantization_config"] = quant_config
        print(f"Using quantization: {weight_format}")

    # Add optional parameters if specified
    if cache_dir:
        load_kwargs["cache_dir"] = cache_dir
    if revision:
        load_kwargs["revision"] = revision
    if token:
        load_kwargs["token"] = token

    # Add torch_dtype for memory efficiency if torch is available
    if HAS_TORCH:
        load_kwargs["torch_dtype"] = torch.float16

    model = model_class.from_pretrained(model_id, **load_kwargs)

    # Ensure output directory exists
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Save the model
    model.save_pretrained(output_dir)
    print(f'Export completed to: {output_dir}')


def main():
    parser = argparse.ArgumentParser(
        description='Export AI/ML models to OpenVINO format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --fast meta-llama/Llama-3.2-1B-Instruct
  %(prog)s --slow --out ./my-model meta-llama/Llama-3.2-1B-Instruct
  %(prog)s --fast --low-memory meta-llama/Llama-2-70b-chat-hf

Modes:
  --fast   Baseline export (faster)
  --slow   Calibrated export with scale estimation (slower)

For more help: %(prog)s --help
        """
    )

    # Mutually exclusive mode selection
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--fast', action='store_const', dest='mode', const='fast',
                           help='Baseline export (faster)')
    mode_group.add_argument('--slow', action='store_const', dest='mode', const='slow',
                           help='Calibrated export with scale estimation (slower)')

    # Required model argument
    parser.add_argument('model', help='Model ID on Hugging Face or local path')

    # Optional arguments
    parser.add_argument('--task', help='Model task (auto-detected if not specified)')
    parser.add_argument('--param-size', '--weight-format', default='int4',
                       choices=['int4', 'int8', 'fp16', 'fp32'],
                       help='Weight format for quantization (default: int4)')
    parser.add_argument('--out', help='Output directory (auto-generated if not specified)')
    parser.add_argument('--no-low-cpu-mem-usage', action='store_true',
                       help='Disable low CPU memory usage mode (enabled by default)')
    parser.add_argument('--cache-dir', help='Directory to cache downloaded models')
    parser.add_argument('--revision', help='Specific model revision to load')
    parser.add_argument('--token', help='Authentication token for remote models')

    args = parser.parse_args()

    # Auto-detect task if not specified
    task = args.task or detect_task_for(args.model)

    # Generate output directory if not specified
    out_dir = args.out or default_out_dir_for(args.model, args.param_size)

    options = {
        "model_id": args.model,
        "task": task,
        "output_dir": out_dir,
        "mode": args.mode,
        "weight_format": args.param_size,
        "low_cpu_mem_usage": not getattr(args, 'no_low_cpu_mem_usage', False),
        "cache_dir": getattr(args, 'cache_dir', None),
        "revision": getattr(args, 'revision', None),
        "token": "<set>" if getattr(args, 'token', None) else None,
    }

    print("Export options:")
    for k in sorted(options.keys()):
        print(f"  {k}={options[k]}")

    # Always use model export
    export_model(
        model_id=args.model,
        task=task,
        output_dir=out_dir,
        mode=args.mode,
        low_cpu_mem_usage=not getattr(args, 'no_low_cpu_mem_usage', False),
        cache_dir=getattr(args, 'cache_dir', None),
        revision=getattr(args, 'revision', None),
        token=getattr(args, 'token', None),
        weight_format=args.param_size
    )

    # Export completed


if __name__ == '__main__':
    main()