ARG UBUNTU_VERSION=24.04

FROM ubuntu:$UBUNTU_VERSION AS build

# Install build tools and Vulkan dependencies
# glslc might be needed for shader compilation if not bundled
RUN apt-get update && \
    apt-get install -y git build-essential cmake wget python3-pip python3-venv \
    libssl-dev libvulkan-dev glslc

WORKDIR /app

# Create a virtual environment
RUN python3 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# Install llama-cpp-python with Vulkan support
# We enable GGML_VULKAN via CMake args
RUN CMAKE_ARGS="-DGGML_VULKAN=on \
    -DGGML_NATIVE=OFF \
    -DGGML_BACKEND_DL=ON \
    -DLLAMA_BUILD_TESTS=OFF" \
    pip install --upgrade --no-cache-dir llama-cpp-python

FROM ubuntu:$UBUNTU_VERSION AS server

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y python3 python3-venv libgomp1 curl \
    libvulkan1 mesa-vulkan-drivers && \
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
