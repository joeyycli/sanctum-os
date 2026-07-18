#!/bin/sh
# Sanctum OS — local build via Docker/OrbStack on an Apple Silicon Mac.
# Requires a container runtime and ~15-20 GB free disk.
#   ./build/container-build.sh
set -eu

cd "$(dirname "$0")/.."

command -v docker >/dev/null 2>&1 || {
    echo "docker not found. Install OrbStack (brew install --cask orbstack) or Docker Desktop." >&2
    exit 1
}

exec docker run --rm -it \
    --privileged \
    --platform linux/arm64 \
    -v "$(pwd)":/sanctum \
    -w /sanctum \
    debian:trixie \
    ./build/build.sh
