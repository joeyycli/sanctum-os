#!/bin/sh
# Sanctum OS — ISO build entrypoint.
# Runs inside a privileged debian:trixie environment (container or CI job).
# Produces dist/sanctum-os-<version>-arm64.iso + SHA256SUMS.
set -eu

cd "$(dirname "$0")/.."
REPO_ROOT=$(pwd)
VERSION=$(cat VERSION)

echo "==> Sanctum OS ${VERSION} build ($(uname -m))"
[ "$(uname -m)" = "aarch64" ] || {
    echo "FATAL: build must run on aarch64 (native, no emulation)." >&2; exit 1; }

echo "==> Installing build dependencies"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
    live-build xorriso mtools dosfstools squashfs-tools \
    librsvg2-bin gpg curl ca-certificates git

echo "==> Rasterizing branding assets"
./build/mkassets.sh

echo "==> live-build: clean + configure"
lb clean --purge >/dev/null 2>&1 || true
lb config

echo "==> live-build: building image (this takes 20-40 minutes)"
lb build

ISO=$(ls sanctum-os-*.iso live-image-*.iso 2>/dev/null | head -n1)
[ -n "$ISO" ] || { echo "FATAL: no ISO produced — see build.log" >&2; exit 1; }

mkdir -p dist
OUT="dist/sanctum-os-${VERSION}-arm64.iso"
mv "$ISO" "$OUT"
( cd dist && sha256sum "$(basename "$OUT")" > SHA256SUMS )

echo "==> Done:"
ls -lh dist/
