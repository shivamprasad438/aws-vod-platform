#!/usr/bin/env bash
# Upload a sample video to a running API and print its playback URL.
set -euo pipefail
API="${API:-http://localhost:8000}"
FILE="${1:-sample.mp4}"
[ -f "$FILE" ] || ./scripts/make_sample_video.sh "$FILE"
ID=$(curl -fsS -F "title=Demo video" -F "file=@${FILE}" "$API/videos" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
echo "Uploaded video id: $ID"
for _ in $(seq 1 60); do
  STATUS=$(curl -fsS "$API/videos/$ID" | python3 -c 'import sys,json; print(json.load(sys.stdin)["status"])')
  [ "$STATUS" != "processing" ] && break
  sleep 1
done
curl -fsS "$API/videos/$ID" | python3 -m json.tool
