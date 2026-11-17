# =============================================================================
# strata-sycl-dev — runtime/development image for the Strata SYCL engine
#                    on 2x Intel Arc B580 (Battlemage / BMG-G21)
# =============================================================================
# The repository is NOT baked into this image: sycl/serve/strata-sycl.sh mounts
# it at /work at run time. What lives here is the runtime the engine needs:
#   - oneAPI 2026.2 compiler/MKL/redist/UMF libraries (the binary is linked
#     against these: libsycl.so.9, libmkl_sycl_*.so.6, libsvml, libirng, ...)
#   - the distro Level Zero loader + Intel GPU driver (apt), NOT the oneAPI
#     copy in /opt/intel/oneapi/level-zero: that libze_loader.so.1 requires
#     GLIBC_ABI_GNU2_TLS, which this Ubuntu 24.04 base does not provide.
#
# Build:  podman build -t strata-sycl-dev:latest -f Dockerfile .
# Run:    ./strata-src/sycl/serve/strata-sycl.sh --serve --config <cfg>.json
#   or:   ./scripts/run-strata.sh <cfg-name>
# =============================================================================
FROM docker.io/intel/deep-learning-essentials:2025.3.3-0-devel-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=UTC \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# --- Runtime packages --------------------------------------------------------
# libze1 / libze-intel-gpu1 / intel-opencl-icd / libigc2 / intel-ocloc come from
# the Intel graphics PPA already configured in the base image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        libdrm2 \
        libze1 \
        libze-intel-gpu1 \
        intel-opencl-icd \
        libigc2 \
        intel-ocloc \
        ca-certificates \
        curl \
        procps \
        tini \
    && rm -rf /var/lib/apt/lists/*

# --- oneAPI 2026.2 runtime libraries ----------------------------------------
# NOTE: level-zero is deliberately absent -- its loader is incompatible with
# this image's glibc. The system /lib/x86_64-linux-gnu/libze_loader.so.1 is used.
COPY oneapi-libs/compiler/2026.2/lib/ /opt/intel/oneapi/compiler/2026.2/lib/
COPY oneapi-libs/mkl/2026.2/lib/      /opt/intel/oneapi/mkl/2026.2/lib/
COPY oneapi-libs/redist/lib/          /opt/intel/oneapi/redist/lib/
COPY oneapi-libs/umf/1.2/lib/         /opt/intel/oneapi/umf/1.2/lib/

ENV ONEAPI_ROOT=/opt/intel/oneapi
ENV LD_LIBRARY_PATH=/opt/intel/oneapi/compiler/2026.2/lib:/opt/intel/oneapi/mkl/2026.2/lib:/opt/intel/oneapi/redist/lib:/opt/intel/oneapi/umf/1.2/lib
ENV SYCL_CACHE_PERSISTENT=1
ENV IGC_EnableGEPSimplification=0
ENV ZES_ENABLE_SYSMAN=1
ENV SYCL_DEVICE_FILTER=level_zero
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# --- Python runtime packages (pinned, see strata-src/requirements.txt) -------
RUN pip install --break-system-packages --no-cache-dir --quiet \
        numpy \
        jinja2 \
        regex \
        pyyaml \
        tqdm \
        requests \
        pillow \
        psutil

WORKDIR /work/strata-src

ENTRYPOINT ["/usr/bin/tini", "--", "/bin/bash"]
CMD ["-c", "echo 'strata-sycl-dev: pass a command, e.g. cd /work/strata-src && exec build-sycl-aot/strata --serve ...'"]