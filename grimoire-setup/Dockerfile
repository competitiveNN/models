# =====================================================================
#  GRIMOIRE for 2x Intel Arc B580 (Battlemage, BMG-G21).
#
#  Builds from the GRIMOIRE source at ./GRIMOIRE (a git checkout, not
#  copied into the build context twice -- the build context IS this
#  directory, GRIMOIRE/ is the source).
#
#  Two-stage: the builder carries the whole oneAPI DPC++ toolchain and
#  compiles the engine AOT for BOTH Battlemage dies (bmg_g31 for the
#  B70/B65, bmg_g21 for the B580/B60/B50 -- one AOT image does NOT run
#  on the other die).  The runtime stage carries only the binaries, the
#  Intel GPU driver userspace (Level Zero / OpenCL / IGC, pinned to the
#  exact versions every GRIMOIRE number has been measured against) and
#  the recipe wrapper.  No Python, no PyTorch, no vLLM.
#
#  Build (from grimoire-setup/):
#      docker build -t grimoire-b580 .
#
#  Run: see docker-compose.yml and RUN.md.  Models are MOUNTED from the
#  host, never copied into the image:
#      ~/data/models/safetensors -> /models:ro
# =====================================================================

# ---------------------------------------------------------------------
#  Stage 1 -- builder.  oneAPI DPC++ + ocloc + the GRIMOIRE source.
# ---------------------------------------------------------------------
FROM ubuntu:24.04 AS builder

ARG DEBIAN_FRONTEND=noninteractive
# Both Battlemage dies in one binary: AOT for g31 does NOT execute on a
# g21 and vice versa.  Set B70_TARGET=intel_gpu_bmg_g21 to halve the
# compile time when the box will only ever hold B580-class cards.
ARG B70_TARGET=intel_gpu_bmg_g31,intel_gpu_bmg_g21

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates gnupg wget build-essential make \
    && rm -rf /var/lib/apt/lists/*

# oneAPI DPC++ compiler (the exact build every GRIMOIRE kernel has been
# measured against; icpx 2026.1.x).
RUN wget -qO- https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB \
      | gpg --dearmor -o /usr/share/keyrings/oneapi-archive-keyring.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main" \
      > /etc/apt/sources.list.d/oneAPI.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends intel-oneapi-compiler-dpcpp-cpp-2026.1 \
 && rm -rf /var/lib/apt/lists/*

# ocloc (AOT codegen).  Ubuntu's 23.43 predates Battlemage and fails the
# build's own probe, so pin the compute-runtime release the driver in
# the runtime stage comes from.
ARG COMPUTE_RUNTIME_VERSION=26.27.39122.11
ARG IGC_VERSION=2.38.2
ARG IGC_BUILD=22051
ARG GMMLIB_VERSION=22.10.0
RUN mkdir -p /tmp/neo && cd /tmp/neo \
 && wget -q "https://github.com/intel/intel-graphics-compiler/releases/download/v${IGC_VERSION}/intel-igc-core-2_${IGC_VERSION}+${IGC_BUILD}_amd64.deb" \
 && wget -q "https://github.com/intel/intel-graphics-compiler/releases/download/v${IGC_VERSION}/intel-igc-opencl-2_${IGC_VERSION}+${IGC_BUILD}_amd64.deb" \
 && wget -q "https://github.com/intel/compute-runtime/releases/download/${COMPUTE_RUNTIME_VERSION}/intel-ocloc_${COMPUTE_RUNTIME_VERSION}-0_amd64.deb" \
 && wget -q "https://github.com/intel/compute-runtime/releases/download/${COMPUTE_RUNTIME_VERSION}/libigdgmm12_${GMMLIB_VERSION}_amd64.deb" \
 && dpkg -i *.deb \
 && cd / && rm -rf /tmp/neo

WORKDIR /src
COPY GRIMOIRE/ /src/

# Build the engine, the server and libgrimoire_gemm.so.  build_b70.sh
# builds both dies by default and fails hard if any REQUIRED target
# fails, so a silent partial build cannot ship.
RUN export OCL_ICD_FILENAMES= \
 && source /opt/intel/oneapi/setvars.sh --force >/dev/null 2>&1 || true \
 && B70_TARGET="${B70_TARGET}" bash build_b70.sh 2>&1 | tee /src/build.log \
 && test -x bin/grimoire && test -x bin/grimoire-server && test -f bin/libgrimoire_gemm.so

# ---------------------------------------------------------------------
#  Stage 2 -- runtime.  Only the driver stack the three binaries need.
# ---------------------------------------------------------------------
FROM ubuntu:24.04 AS runtime

ARG DEBIAN_FRONTEND=noninteractive
ARG ONEAPI_VERSION=2026.1
ARG COMPUTE_RUNTIME_VERSION=26.27.39122.11
ARG IGC_VERSION=2.38.2
ARG IGC_BUILD=22051
ARG GMMLIB_VERSION=22.10.0
ARG LEVEL_ZERO_VERSION=1.32.0

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates gnupg wget curl ocl-icd-libopencl1 \
 && wget -qO- https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB \
      | gpg --dearmor -o /usr/share/keyrings/oneapi-archive-keyring.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main" \
      > /etc/apt/sources.list.d/oneAPI.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
        intel-oneapi-compiler-dpcpp-cpp-runtime-${ONEAPI_VERSION} \
        intel-oneapi-compiler-shared-runtime-${ONEAPI_VERSION} \
        intel-oneapi-umf \
 && rm -rf /var/lib/apt/lists/*

# Intel GPU compute-runtime / Level Zero, straight from Intel's GitHub
# releases (same versions the GRIMOIRE numbers were measured with).
RUN mkdir -p /tmp/neo && cd /tmp/neo \
 && wget -q "https://github.com/intel/intel-graphics-compiler/releases/download/v${IGC_VERSION}/intel-igc-core-2_${IGC_VERSION}+${IGC_BUILD}_amd64.deb" \
 && wget -q "https://github.com/intel/intel-graphics-compiler/releases/download/v${IGC_VERSION}/intel-igc-opencl-2_${IGC_VERSION}+${IGC_BUILD}_amd64.deb" \
 && wget -q "https://github.com/intel/compute-runtime/releases/download/${COMPUTE_RUNTIME_VERSION}/intel-ocloc_${COMPUTE_RUNTIME_VERSION}-0_amd64.deb" \
 && wget -q "https://github.com/intel/compute-runtime/releases/download/${COMPUTE_RUNTIME_VERSION}/intel-opencl-icd_${COMPUTE_RUNTIME_VERSION}-0_amd64.deb" \
 && wget -q "https://github.com/intel/compute-runtime/releases/download/${COMPUTE_RUNTIME_VERSION}/libigdgmm12_${GMMLIB_VERSION}_amd64.deb" \
 && wget -q "https://github.com/intel/compute-runtime/releases/download/${COMPUTE_RUNTIME_VERSION}/libze-intel-gpu1_${COMPUTE_RUNTIME_VERSION}-0_amd64.deb" \
 && wget -q "https://github.com/oneapi-src/level-zero/releases/download/v${LEVEL_ZERO_VERSION}/libze1_${LEVEL_ZERO_VERSION}+u24.04_amd64.deb" \
 && dpkg -i *.deb \
 && cd / && rm -rf /tmp/neo \
 && apt-get purge -y wget gnupg \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

# Every oneAPI component installs lib/ under a DIFFERENT versioned
# subdir; none are on the default linker path.  ldconfig at BUILD time,
# not LD_LIBRARY_PATH at run time, so this survives any invocation.
RUN find /opt/intel/oneapi -mindepth 1 -maxdepth 3 -type d -name lib \
        > /etc/ld.so.conf.d/intel-oneapi.conf \
 && ldconfig

WORKDIR /grimoire
COPY --from=builder /src/bin/grimoire           bin/grimoire
COPY --from=builder /src/bin/grimoire-server    bin/grimoire-server
COPY --from=builder /src/bin/libgrimoire_gemm.so bin/libgrimoire_gemm.so
# The entrypoint lives OUTSIDE the GRIMOIRE source tree (./docker-entrypoint.sh,
# not GRIMOIRE/docker-entrypoint.sh) on purpose: GRIMOIRE/ is copied wholesale
# into the builder stage, so editing anything in it invalidates that COPY and
# forces a full rebuild.  The source tree stays pristine; this file carries the
# only change (generate-pp, the two-card one-shot CLI).
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh bin/grimoire bin/grimoire-server

# Models are MOUNTED, never baked in.  /cache holds the SYCL kernel
# cache so the JIT cost is paid once, on a named volume.
VOLUME ["/models", "/cache"]

ENV ONEAPI_DEVICE_SELECTOR=level_zero:gpu \
    SYCL_CACHE_PERSISTENT=1 \
    SYCL_CACHE_DIR=/cache/sycl \
    UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
# Default: OpenAI-compatible server.  Override with one of:
#   server    -> bin/grimoire-server
#   multi     -> one server rank per GPU (PP or TP)
#   generate  -> bin/grimoire (one-shot CLI)
CMD ["server"]
