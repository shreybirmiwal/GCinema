#!/usr/bin/env bash
# Usage: ./run-pipeline.sh <GEMINI_API_KEY> <YOUTUBE_URL>
set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <GEMINI_API_KEY> <YOUTUBE_URL>" >&2
    exit 1
fi

API_KEY="$1"
URL="$2"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Step 0: Download video ==="
# Use a temp file as a timestamp anchor to detect newly downloaded file
STAMP=$(mktemp)
python3 "$SCRIPT_DIR/0-downloader.py" "$URL"

VIDEO=$(find "$SCRIPT_DIR" -maxdepth 1 -name "*.mp4" -newer "$STAMP" | head -1)
rm -f "$STAMP"

if [[ -z "$VIDEO" ]]; then
    echo "Error: Could not detect downloaded video file." >&2
    exit 1
fi
echo "Downloaded: $VIDEO"

echo ""
echo "=== Step 1: Segment video ==="
python3 "$SCRIPT_DIR/1-segment.py" "$VIDEO"

STEM="$(basename "$VIDEO" .mp4)"
mapfile -t CLIPS < <(find "$SCRIPT_DIR" -maxdepth 1 -name "${STEM}-Scene-*.mp4" | sort)

if [[ ${#CLIPS[@]} -eq 0 ]]; then
    echo "Error: No scene clips found after segmentation." >&2
    exit 1
fi

echo "Found ${#CLIPS[@]} scene clip(s)"

for CLIP in "${CLIPS[@]}"; do
    CLIP_STEM="$(basename "$CLIP" .mp4)"
    echo ""
    echo "--- Processing: $CLIP_STEM ---"

    echo "  Step 2: Video reasoning..."
    DESC_OUT="$SCRIPT_DIR/${CLIP_STEM}_description.txt"
    python3 "$SCRIPT_DIR/2-gemini-video-reason.py" "$CLIP" \
        --api-key "$API_KEY" \
        --output "$DESC_OUT"

    echo "  Step 3: Extract keyframe..."
    python3 "$SCRIPT_DIR/3-extract-key-frame.py" "$CLIP"
    FRAME="$SCRIPT_DIR/${CLIP_STEM}_frame0.png"

    if [[ ! -f "$FRAME" ]]; then
        echo "  Warning: Keyframe not found at $FRAME, skipping colorization." >&2
        continue
    fi

    echo "  Step 4: Colorize keyframe..."
    python3 "$SCRIPT_DIR/4-colorize-keyframe.py" "$FRAME" --api-key "$API_KEY"
done

echo ""
echo "=== Pipeline complete! ==="
