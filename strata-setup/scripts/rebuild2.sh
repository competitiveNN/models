#!/bin/bash
export SETVARS_ARGS=--force
cd /work/strata-src
AOT=bmg-g21 BUILD_DIR=/work/strata-src/build-sycl-aot JOBS=4 ./sycl/tools/build.sh strata > /work/build_rebuild2.log 2>&1
echo EXIT=${PIPESTATUS[0]} >> /work/build_rebuild2.log
