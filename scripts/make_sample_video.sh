#!/usr/bin/env bash
# Generate a 10-second 1280x720 test video (with audio) using FFmpeg.
set -euo pipefail
OUT="${1:-sample.mp4}"
ffmpeg -y -f lavfi -i testsrc=duration=10:size=1280x720:rate=24 \
  -f lavfi -i sine=frequency=440:duration=10 \
  -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "$OUT"
echo "Created $OUT"
