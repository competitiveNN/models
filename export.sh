#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./export.sh (--fast|--slow) [--task <task>] [--param-size <size>] [--batch] [--target-ram <GB>] [--batch-size <n>] [--sequence_length <n>] [--out <output_dir>] <model>

Examples:
  ./export.sh --fast meta-llama/Llama-3.2-1B-Instruct
  ./export.sh --slow --out ./llama-int4-ov meta-llama/Llama-3.2-1B-Instruct
  ./export.sh --slow --target-ram 32 /path/to/model
  ./export.sh --fast --param-size int8 meta-llama/Llama-3.2-1B-Instruct

Modes:
  --fast   Baseline export
  --slow   Calibrated export (scale estimation, wikitext2)

Options:
  --task <task>        Task to export for (passed to `--task`). If omitted, the
                       script auto-detects from the model name and otherwise
                       defaults to: text-generation-with-past
  --param-size <size>  Weight format/parameter size for export (passed to
                       `--weight-format`). Defaults to: int4
  --batch              OOM-avoidance mode for calibration exports. Internally
                       sets conservative defaults for `--batch-size` and
                       `--sequence_length` (unless you set them explicitly).
  --target-ram <GB>    Target RAM limit for automatic batch calculation.
                       Enables auto-calculation of batch-size and sequence_length.
                       Defaults to: 64
  --batch-size <n>     Used for memory estimation (not passed to optimum-cli).
  --sequence_length <n>
                       Used for memory estimation (not passed to optimum-cli).
  --out <dir>  Output directory. Defaults to:
              <model-name>-int4[-awq]-ov
EOF
}

mode=""
model=""
out_dir=""
weight_format="int4"
task=""
oom_safe_batch="false"
target_ram_gb="${EXPORT_TARGET_RAM:-48}"
dataset="wikitext2"
num_samples=""
batch_size=""
sequence_length=""

is_awq_model() {
  local s="${1}"
  shopt -s nocasematch
  if [[ "${s}" == *awq* ]]; then
    shopt -u nocasematch
    return 0
  fi
  shopt -u nocasematch
  return 1
}

detect_task_for() {
  local s="${1}"
  shopt -s nocasematch

  # Heuristics based on common model naming conventions.
  if [[ "${s}" == *whisper* ]]; then
    shopt -u nocasematch
    echo "automatic-speech-recognition-with-past"
    return 0
  fi

  # Text-to-text encoder/decoder models.
  if [[ "${s}" == *t5* || "${s}" == *bart* || "${s}" == *mbart* ]]; then
    shopt -u nocasematch
    echo "text2text-generation-with-past"
    return 0
  fi

  # Diffusion models.
  if [[ "${s}" == *stable-diffusion* || "${s}" == *sdxl* ]]; then
    shopt -u nocasematch
    echo "text-to-image"
    return 0
  fi

  shopt -u nocasematch
  echo "text-generation-with-past"
}

default_out_dir_for() {
  local m="${1}"
  local base
  base="$(basename "${m}")"
  base="${base%/}"
  base="${base// /-}"
  base="${base//[^A-Za-z0-9._-]/-}"

  local awq_suffix=""
  if is_awq_model "${m}"; then
    awq_suffix="-awq"
  fi

  printf '%s-%s%s-ov' "${base}" "${weight_format}" "${awq_suffix}"
}

# Estimate memory usage in GB for given parameters
estimate_memory_gb() {
  local model="$1" task="$2" weight_format="$3" batch_size="$4" seq_len="$5" mode="$6"

  # Parameter count estimation from model name
  local params
  case "$model" in
    *Llama-3*70B*|*llama-3*70b*|*70B*|*70b*) params=70000000000 ;;
    *Llama-3*8B*|*llama-3*8b*|*8B*|*8b*) params=8000000000 ;;
    *Llama-3*1B*|*llama-3*1b*|*1B*|*1b*) params=1000000000 ;;
    *30B*|*30b*) params=30000000000 ;;
    *20B*|*20b*) params=20000000000 ;;
    *13B*|*13b*) params=13000000000 ;;
    *7B*|*7b*) params=7000000000 ;;
    *3B*|*3b*) params=3000000000 ;;
    *) params=3000000000 ;; # Conservative default for unknown models
  esac

  # Weight format memory per parameter
  local bytes_per_param
  case "$weight_format" in
    int4) bytes_per_param=0.5 ;;
    int8) bytes_per_param=1 ;;
    fp16) bytes_per_param=2 ;;
    fp32) bytes_per_param=4 ;;
    *) bytes_per_param=2 ;; # Default to fp16
  esac

  # Base model memory (includes some overhead for model structure)
  local model_mem_gb=$(echo "scale=2; $params * $bytes_per_param * 1.2 / 1073741824" | bc 2>/dev/null || echo "0")

  # KV cache memory (more realistic estimate: ~2-4KB per token for transformers)
  # Scales with batch_size * seq_len * num_layers * hidden_size * bytes_per_param
  # Rough approximation: ~0.003 GB per 1000 tokens for typical models
  local kv_cache_gb=$(echo "scale=3; $batch_size * $seq_len * 0.000003" | bc 2>/dev/null || echo "0")

  # Activation memory during inference (scales with batch and sequence)
  local activation_gb=$(echo "scale=3; $batch_size * $seq_len * 0.000001" | bc 2>/dev/null || echo "0")

  # Task-specific overhead
  local task_overhead=1
  case "$task" in
    text-to-image|stable-diffusion*) task_overhead=3 ;; # Diffusion models need significantly more memory
    automatic-speech-recognition*) task_overhead=1.5 ;;
    text2text-generation*) task_overhead=1.2 ;;
  esac

  # Calibration overhead for slow mode (scale estimation + dataset loading)
  local calib_overhead=0
  [[ "$mode" == "--slow" ]] && calib_overhead=5  # Increased for more realistic calibration memory

  # Total estimate: model + KV cache + activations, multiplied by task overhead, plus calibration
  local total_gb=$(echo "scale=2; ($model_mem_gb + $kv_cache_gb + $activation_gb) * $task_overhead + $calib_overhead" | bc 2>/dev/null || echo "0")

  # Ensure minimum reasonable estimate
  if (( $(echo "$total_gb < 2" | bc -l 2>/dev/null || echo "1") )); then
    total_gb="2"
  fi

  echo "$total_gb"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fast|--slow)
      if [[ -n "${mode}" ]]; then
        echo "Error: only one of --fast or --slow may be specified." >&2
        usage >&2
        exit 2
      fi
      mode="$1"
      shift
      ;;
    --task)
      if [[ $# -lt 2 ]]; then
        echo "Error: --task requires a value." >&2
        usage >&2
        exit 2
      fi
      task="$2"
      shift 2
      ;;
    --batch)
      oom_safe_batch="true"
      shift
      ;;
    --target-ram)
      if [[ $# -lt 2 ]]; then
        echo "Error: --target-ram requires a value (GB)." >&2
        usage >&2
        exit 2
      fi
      target_ram_gb="$2"
      shift 2
      ;;
    --batch-size)
      if [[ $# -lt 2 ]]; then
        echo "Error: --batch-size requires a value." >&2
        usage >&2
        exit 2
      fi
      batch_size="$2"
      shift 2
      ;;
    --sequence_length|--sequence-length|--seq-len|--seq-len=*)
      if [[ "$1" == *=* ]]; then
        sequence_length="${1#*=}"
        shift
      else
        if [[ $# -lt 2 ]]; then
          echo "Error: $1 requires a value." >&2
          usage >&2
          exit 2
        fi
        sequence_length="$2"
        shift 2
      fi
      ;;
    --out)
      if [[ $# -lt 2 ]]; then
        echo "Error: --out requires a value." >&2
        usage >&2
        exit 2
      fi
      out_dir="$2"
      shift 2
      ;;
    --param-size|--weight-format)
      if [[ $# -lt 2 ]]; then
        echo "Error: $1 requires a value." >&2
        usage >&2
        exit 2
      fi
      weight_format="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      echo "Error: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -n "${model}" ]]; then
        echo "Error: unexpected extra argument: $1" >&2
        usage >&2
        exit 2
      fi
      model="$1"
      shift
      ;;
  esac
done

if [[ -z "${mode}" || -z "${model}" ]]; then
  echo "Error: missing required arguments." >&2
  usage >&2
  exit 2
fi

if [[ -z "${task}" ]]; then
  task="$(detect_task_for "${model}")"
fi

if [[ -z "${out_dir}" ]]; then
  out_dir="$(default_out_dir_for "${model}")"
fi

# Auto-calculate batch parameters based on target RAM if requested
if [[ "${oom_safe_batch}" == "true" || -n "${target_ram_gb}" ]]; then
  echo "Auto-calculating batch parameters for ${target_ram_gb}GB target RAM..."

  # If --batch was specified, start with conservative defaults and auto-adjust
  if [[ "${oom_safe_batch}" == "true" ]]; then
    batch_size="${batch_size:-1}"
    sequence_length="${sequence_length:-128}"
  fi

  # Try increasingly aggressive settings, staying under 80% of target RAM
  best_batch="${batch_size:-1}"
  best_seq="${sequence_length:-128}"
  best_mem="999"

  # Test different batch sizes and sequence lengths
  for try_batch in 1 2 4 8 16; do
    for try_seq in 128 256 512 1024 2048; do
      # Skip if user explicitly set batch_size and we're testing a different value
      if [[ -n "${batch_size}" && "${batch_size}" != "$try_batch" ]]; then
        continue
      fi
      # Skip if user explicitly set sequence_length and we're testing a different value
      if [[ -n "${sequence_length}" && "${sequence_length}" != "$try_seq" ]]; then
        continue
      fi

      mem_estimate=$(estimate_memory_gb "$model" "$task" "$weight_format" "$try_batch" "$try_seq" "$mode")

      # Check if this fits within 80% of target RAM and is better than previous best
      if (( $(echo "$mem_estimate < $target_ram_gb * 0.8 && $mem_estimate < $best_mem" | bc -l 2>/dev/null || echo "0") )); then
        best_batch=$try_batch
        best_seq=$try_seq
        best_mem=$mem_estimate
      fi
    done
  done

  batch_size="${best_batch}"
  sequence_length="${best_seq}"

  echo "Selected: --batch-size $batch_size --sequence_length $sequence_length (est. ${best_mem}GB RAM usage)"
fi

# Note: batch_size and sequence_length are used for memory estimation only
# optimum-cli export openvino does not support --batch-size or --sequence_length flags

case "${mode}" in
  --fast)
    # Baseline (faster export)
    echo "optimum-cli export openvino -m \"${model}\" --task \"${task}\" --weight-format \"${weight_format}\" \"${out_dir}\""
    optimum-cli export openvino -m "${model}" --task "${task}" --weight-format "${weight_format}" "${out_dir}"
    ;;
  --slow)
    # Calibrated (slower export, potential perf/quality gain)
    echo "optimum-cli export openvino -m \"${model}\" --task \"${task}\" --weight-format \"${weight_format}\" --scale-estimation --dataset \"${dataset}\" \"${out_dir}\""
    optimum-cli export openvino -m "${model}" --task "${task}" --weight-format "${weight_format}" --scale-estimation --dataset "${dataset}" "${out_dir}"
    ;;
esac
