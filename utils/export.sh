#!/bin/bash

optimum-cli export openvino \
  --model AngelSlim/Qwen3-8B_eagle3 \
  --task text-generation-with-past \
  --weight-format int4 \
  --trust-remote-code \
  qwen3_8b_openvino_model
