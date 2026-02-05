# For building the docker container on fedora silverblue
use the flag `--security-opt label=disable` like:
```
docker build --security-opt label=disable -f docker/Dockerfile.xpu -t vllm-xpu-env --shm-size=4g . --no-cache
```
to avoid permission denied error of volumes mounted inside container.

Note: 
VLLM from master (0.16) doesn't work, because it lacks IPEX (which has also been deprecated)