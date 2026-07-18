#!/bin/sh
# Sanctum OS — rasterize SVG branding sources into the PNGs the image needs.
# Driven by branding/rasterize.manifest, one entry per line:
#     <svg path> <output png path> <width> <height>
# Paths are relative to the repo root. Lines starting with # are ignored.
# Keeping sources as SVG makes every pixel of branding reproducible from text.
set -eu

cd "$(dirname "$0")/.."

command -v rsvg-convert >/dev/null 2>&1 || {
    echo "rsvg-convert not found (apt install librsvg2-bin)" >&2; exit 1; }

MANIFEST=branding/rasterize.manifest
[ -f "$MANIFEST" ] || { echo "missing $MANIFEST" >&2; exit 1; }

count=0
while read -r svg out w h; do
    case "$svg" in ''|\#*) continue ;; esac
    [ -f "$svg" ] || { echo "FATAL: missing source $svg" >&2; exit 1; }
    mkdir -p "$(dirname "$out")"
    rsvg-convert -w "$w" -h "$h" -o "$out" "$svg"
    count=$((count + 1))
done < "$MANIFEST"

echo "Rasterized $count assets."
