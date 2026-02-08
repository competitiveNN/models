ARG ONEAPI_VERSION=2025.2.2-0-devel-ubuntu24.04

FROM intel/deep-learning-essentials:$ONEAPI_VERSION AS build

# Install dependencies for building
RUN apt-get update && \
    apt-get install -y git libssl-dev python3-pip python3-venv

WORKDIR /app

# Create a virtual environment
RUN python3 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# Install llama-cpp-python with SYCL support
# Using the command provided by the user
ARG GGML_SYCL_F16=ON
RUN CMAKE_ARGS="-DGGML_SYCL=on \
    -DCMAKE_C_COMPILER=icx \
    -DCMAKE_CXX_COMPILER=icpx \
    -DGGML_SYCL_F16=${GGML_SYCL_F16} \
    -DGGML_NATIVE=OFF \
    -DGGML_BACKEND_DL=ON \
    -DGGML_CPU_ALL_VARIANTS=ON \
    -DLLAMA_BUILD_TESTS=OFF" \
    pip install --upgrade --no-cache-dir llama-cpp-python

FROM intel/deep-learning-essentials:$ONEAPI_VERSION AS server

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y python3 python3-venv libgomp1 curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy the virtual environment from the build stage
COPY --from=build /app/venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

WORKDIR /app

# Set environment variables for the server
ENV HOST=0.0.0.0
ENV PORT=8000

# Healthcheck
HEALTHCHECK CMD [ "curl", "-f", "http://localhost:8000/docs" ]

# Start the server, binding to 0.0.0.0 to allow external access
CMD ["python3", "-m", "llama_cpp.server", "--host", "0.0.0.0"]
