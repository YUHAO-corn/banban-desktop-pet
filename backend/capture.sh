#!/bin/bash
# Capture webcam frame, base64 encode, output to stdout
# Usage: ./capture.sh [output_path]

OUTPUT="${1:-/tmp/oc_emotion_frame.jpg}"

imagesnap -q -w 1 "$OUTPUT" 2>/dev/null

if [ ! -f "$OUTPUT" ]; then
  echo "CAPTURE_FAILED"
  exit 1
fi

base64 -i "$OUTPUT"
