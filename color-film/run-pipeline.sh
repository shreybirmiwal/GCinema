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

echo "=== Step 0: Download ==="
VIDEO=$(python3 "$SCRIPT_DIR/0-downloader.py" "$URL" | tee /dev/stderr | grep '^DOWNLOADED:' | cut -d' ' -f2-)

if [[ -z "$VIDEO" || ! -f "$VIDEO" ]]; then
    echo "Error: Could not detect downloaded video." >&2
    exit 1
fi
echo "Video: $VIDEO"

echo ""
echo "=== Step 1: Segment ==="
python3 "$SCRIPT_DIR/1-segment.py" "$VIDEO"

STEM="$(basename "$VIDEO" .mp4)"
mapfile -t CLIPS < <(find "$SCRIPT_DIR" -maxdepth 1 -name "${STEM}-Scene-*.mp4" | sort)

if [[ ${#CLIPS[@]} -eq 0 ]]; then
    echo "Error: No scene clips found after segmentation." >&2
    exit 1
fi
echo "Found ${#CLIPS[@]} scene clip(s)"

PREV_COLORIZED=""

for CLIP in "${CLIPS[@]}"; do
    CLIP_STEM="$(basename "$CLIP" .mp4)"
    echo ""
    echo "--- $CLIP_STEM ---"

    echo "  [2] Video reasoning..."
    python3 "$SCRIPT_DIR/2-gemini-video-reason.py" "$CLIP" \
        --api-key "$API_KEY" \
        --output "$SCRIPT_DIR/${CLIP_STEM}_description.txt"

    echo "  [3] Extract keyframe..."
    python3 "$SCRIPT_DIR/3-extract-key-frame.py" "$CLIP"
    FRAME="$SCRIPT_DIR/${CLIP_STEM}_frame0.png"

    if [[ ! -f "$FRAME" ]]; then
        echo "  Warning: keyframe not found, skipping colorization." >&2
        continue
    fi

    echo "  [4] Colorize keyframe..."
    COLORIZE_ARGS=("$FRAME" --api-key "$API_KEY")
    if [[ -n "$PREV_COLORIZED" && -f "$PREV_COLORIZED" ]]; then
        COLORIZE_ARGS+=(--reference "$PREV_COLORIZED")
        echo "       (using reference: $(basename "$PREV_COLORIZED"))"
    fi
    python3 "$SCRIPT_DIR/4-colorize-keyframe.py" "${COLORIZE_ARGS[@]}"

    PREV_COLORIZED="$SCRIPT_DIR/${CLIP_STEM}_frame0_colorized.jpg"
done

echo ""
echo "=== Pipeline complete ==="
