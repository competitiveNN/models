#!/bin/bash
# Rebuild the self-contained Strata container images from scratch.
# Survives a /tmp wipe; uses persistent repo state only.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== 1/4: base strata-sycl-dev image ==="
podman build -t localhost/strata-sycl-dev:latest -f Dockerfile .

WORK=/tmp/strata-build
rm -rf "$WORK"; mkdir -p "$WORK"
stage() {
  # $1 src dir, $2 stage name
  local src="$ROOT/$1" dst="$WORK/$2"
  rm -rf "$dst"; mkdir -p "$dst"
  rsync -a \
    --include='/build-sycl-aot/' --include='/build-sycl-aot/**' \
    --exclude='.git' --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='*.log' \
    --exclude='build*/' --exclude='sycl/build*/' --exclude='test_build/' --exclude='pack/' --exclude='packs/' \
    --exclude='swift-iq3_xxs-pack/' --exclude='models/' --exclude='Strata-data/' --exclude='bench/results/' \
    --exclude='third_party/' \
    "$src/" "$dst/"
  rm -rf "$dst/build-sycl-aot"; mkdir -p "$dst/build-sycl-aot"
  cp "$src/build-sycl-aot/strata" "$dst/build-sycl-aot/strata"
  rm -f "$dst/.dockerignore" "$dst/bin/strata"
}

echo "=== 2/4: stage old (36011f87) ==="
stage strata-src pkg-old

echo "=== 3/4: stage edge (strata-src-clean) ==="
stage strata-src-clean pkg-edge
# edge fixes: normalize paths + direct exec script
mkdir -p "$WORK/pkg-edge/sycl/serve"
cp "$ROOT/strata-src/sycl/serve/strata-sycl-direct.sh" "$WORK/pkg-edge/sycl/serve/strata-sycl-direct.sh"
chmod +x "$WORK/pkg-edge/sycl/serve/strata-sycl-direct.sh"
python3 - "$WORK/pkg-edge" << 'PY'
import json,sys
d=json.load(open(sys.argv[1]+'/strata-swift-iq3_xxs-2gpu-clean.json'))
def fix(o):
    if isinstance(o,str): return o.replace('strata-src-clean','strata-src')
    if isinstance(o,list): return [fix(x) for x in o]
    if isinstance(o,dict): return {k:fix(v) for k,v in o.items()}
    return o
d=fix(d); d['exe']='/work/strata-src/sycl/serve/strata-sycl-direct.sh'; d['cwd']='/work/strata-src'
json.dump(d, open(sys.argv[1]+'/strata-swift-iq3_xxs-2gpu-clean.json','w'), indent=2)
PY

CF_OLD="$WORK/Containerfile.pkg-old"; CF_EDGE="$WORK/Containerfile.pkg-edge"
cat > "$CF_OLD" << 'EOF'
FROM localhost/strata-sycl-dev:latest
COPY . /work/strata-src
WORKDIR /work/strata-src
RUN chmod +x /work/strata-src/build-sycl-aot/strata
ENV STRATA_CONFIG=/work/strata-src/strata-swift-iq3_xxs-2gpu-clean.json STRATA_PORT=8081
ENTRYPOINT ["/usr/bin/tini", "--", "/bin/bash"]
CMD ["-c", "cd /work/strata-src && exec python3 sycl/serve/server_intel.py --engine strata --config ${STRATA_CONFIG} --port ${STRATA_PORT}"]
EOF
cp "$CF_OLD" "$CF_EDGE"

echo "=== 4/4: build images ==="
cd "$WORK/pkg-old"  && podman build -t localhost/strata-old:latest  -f "$CF_OLD"  .
cd "$WORK/pkg-edge" && podman build -t localhost/strata-edge:latest -f "$CF_EDGE" .

echo "DONE: images built"
podman images | grep -i strata
