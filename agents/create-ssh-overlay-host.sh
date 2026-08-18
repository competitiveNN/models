#!/usr/bin/env bash
set -euo pipefail

# create-ssh-overlay-host.sh
# Create a single tmpfs-backed overlayfs on the host that exposes
# a merged view of the host's ~/.ssh (lowerdir) with a writable tmpfs
# upper layer. The overlay mount point can be bind-mounted into containers
# as /home/agent/.ssh so container writes do not modify host files.

# Usage:
#   sudo ./create-ssh-overlay-host.sh            # create with sensible defaults
#   sudo ./create-ssh-overlay-host.sh --src /home/alice/.ssh --base /run/agent-ssh-overlay
#   sudo ./create-ssh-overlay-host.sh --remove   # unmount & cleanup

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'
log(){ echo -e "${CYAN}▸${NC} $*"; }
ok(){ echo -e "${GREEN}✓${NC} $*"; }
warn(){ echo -e "${YELLOW}⚠${NC} $*"; }
die(){ echo -e "${RED}✗${NC} $*" >&2; exit 1; }

# Defaults
BASE_DEFAULT="/run/agent-ssh-overlay"
TMPFS_SIZE_DEFAULT="64M"
AGENT_UID_DEFAULT=1001
AGENT_GID_DEFAULT=1001

# Parse args
SRC=""
BASE="${BASE_DEFAULT}"
TMPFS_SIZE="${TMPFS_SIZE_DEFAULT}"
AGENT_UID="${AGENT_UID_DEFAULT}"
AGENT_GID="${AGENT_GID_DEFAULT}"
REMOVE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --src) SRC="$2"; shift 2;;
    --base) BASE="$2"; shift 2;;
    --size) TMPFS_SIZE="$2"; shift 2;;
    --uid) AGENT_UID="$2"; shift 2;;
    --gid) AGENT_GID="$2"; shift 2;;
    --remove|-r) REMOVE=1; shift;;
    -h|--help) echo "Usage: $0 [--src PATH] [--base PATH] [--size SIZE] [--uid UID] [--gid GID] [--remove]"; exit 0;;
    *) die "Unknown argument: $1";;
  esac
done

# Determine sensible default for SRC (prefer sudo user's home if run with sudo)
if [[ -z "${SRC}" ]]; then
  if [[ -n "${SUDO_USER:-}" && "${SUDO_USER:-}" != "root" ]]; then
    USER_HOME="/home/${SUDO_USER}"
  else
    USER_HOME="${HOME:-/root}"
  fi
  SRC="${USER_HOME}/.ssh"
fi

MNT="${BASE}/mnt"
TMPFS_DIR="${BASE}/tmpfs"
UPPER="${TMPFS_DIR}/upper"
WORK="${TMPFS_DIR}/work"

if [[ $REMOVE -eq 1 ]]; then
  log "Removal requested — attempting to unmount overlay and cleanup: ${MNT}"
  if mountpoint -q "${MNT}"; then
    umount "${MNT}" || warn "Failed to umount ${MNT}"
    ok "Unmounted ${MNT}"
  else
    warn "${MNT} is not mounted"
  fi
  if mountpoint -q "${TMPFS_DIR}"; then
    umount "${TMPFS_DIR}" || warn "Failed to umount ${TMPFS_DIR}"
    ok "Unmounted ${TMPFS_DIR}"
  fi
  # best-effort cleanup
  rm -rf "${BASE}" || true
  ok "Cleaned up ${BASE}"
  exit 0
fi

# Must run as root (needs mount privileges)
if [[ $(id -u) -ne 0 ]]; then
  die "This script must be run as root (sudo)."
fi

# Check overlay support
if ! grep -q overlay /proc/filesystems 2>/dev/null; then
  if ! modprobe overlay 2>/dev/null; then
    die "overlay filesystem not available on this host"
  fi
fi

log "Source (lowerdir): ${SRC}"
log "Overlay mount base: ${BASE}"

# Ensure source exists; do NOT modify host SSH if it exists; if absent create empty dir
if [[ ! -d "${SRC}" ]]; then
  warn "Source ${SRC} does not exist — creating an empty directory at that path"
  mkdir -p "${SRC}" || die "Failed to create ${SRC}"
  chmod 700 "${SRC}" || true
fi

# Skip if already mounted
if awk -v m="${MNT}" '($2==m){ found=1; exit } END{ exit !found }' /proc/mounts 2>/dev/null; then
  ok "Overlay already mounted at ${MNT}"
  echo
  ok "To use from containers: docker run -v ${MNT}:/home/agent/.ssh:rw ..."
  exit 0
fi

# Prepare directories
mkdir -p "${BASE}" "${TMPFS_DIR}" "${MNT}"

# Mount a single tmpfs which will host both upper and work (must be same fs)
if ! mountpoint -q "${TMPFS_DIR}"; then
  log "Mounting tmpfs at ${TMPFS_DIR} (size=${TMPFS_SIZE})"
  mount -t tmpfs -o size=${TMPFS_SIZE} tmpfs "${TMPFS_DIR}" || die "Failed to mount tmpfs at ${TMPFS_DIR}"
fi

mkdir -p "${UPPER}" "${WORK}"
chown -R ${AGENT_UID}:${AGENT_GID} "${TMPFS_DIR}" || true
chmod 700 "${UPPER}" || true
chmod 700 "${WORK}" || true

# Mount overlay
log "Mounting overlay: lower=${SRC} upper=${UPPER} work=${WORK} -> ${MNT}"
mount -t overlay overlay -o lowerdir="${SRC}",upperdir="${UPPER}",workdir="${WORK}" "${MNT}" || die "Overlay mount failed"

# Ensure ownership so agent user inside container can write to upper
chown -R ${AGENT_UID}:${AGENT_GID} "${UPPER}" || true
chown -R ${AGENT_UID}:${AGENT_GID} "${WORK}" || true

ok "Overlay mounted at ${MNT} (lowerdir=${SRC})"

cat <<EOF
Usage from Docker:
  docker run -it \
    -v ${MNT}:/home/agent/.ssh:rw \
    --mount type=volume,source=agent_ssh,target=/home/agent/.ssh \
    your-image

Notes:
 - The overlay upper/work are tmpfs-backed and ephemeral (lost on reboot).
 - All containers that bind-mount ${MNT} will share the same writable overlay.
 - To remove the overlay: sudo $0 --remove
EOF

exit 0
