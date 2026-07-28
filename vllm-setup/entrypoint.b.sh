#!/usr/bin/env bash
# Entrypoint for vllm-b. All XPU/CCL env is set by docker-compose.
exec vllm serve --config /config.yaml
