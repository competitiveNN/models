#!/bin/bash

docker build -t llama-cpp-intel-server \
    --build-arg="GGML_SYCL_F16=ON" \
    --target build -f llama-cpp-intel.Dockerfile \
    llama.cpp