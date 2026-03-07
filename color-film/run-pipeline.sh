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

# ── Step 0: Download ──────────────────────────────────────────────────────────
echo "=== Step 0: Download ==="
VIDEO=$(python3 "$SCRIPT_DIR/0-downloader.py" "$URL" 2>&1 | tee /dev/stderr | grep '^DOWNLOADED:' | cut -d' ' -f2-)

if [[ -z "$VIDEO" || ! -f "$VIDEO" ]]; then
    echo "Error: Could not detect downloaded video." >&2
    exit 1
fi
echo "Video: $VIDEO"

STEM="$(basename "$VIDEO" .mp4)"
OUTPUT_DIR="$SCRIPT_DIR/output/$STEM"
CLIPS_DIR="$OUTPUT_DIR/clips"
mkdir -p "$CLIPS_DIR"

# ── Step 1: Segment ───────────────────────────────────────────────────────────
echo ""
echo "=== Step 1: Segment ==="
python3 "$SCRIPT_DIR/1-segment.py" "$VIDEO" \
    --output-dir "$CLIPS_DIR" \
    --min-scene-len 90 \
    --threshold 5.0

# bash 3.2-compatible array build (macOS ships bash 3.2; mapfile requires 4+)
CLIPS=()
while IFS= read -r line; do
    CLIPS+=("$line")
done < <(find "$CLIPS_DIR" -maxdepth 1 -name "*.mp4" | sort)

if [[ ${#CLIPS[@]} -eq 0 ]]; then
    echo "Error: No scene clips found after segmentation." >&2
    exit 1
fi
echo "Found ${#CLIPS[@]} scene clip(s)"

# ── Steps 2-4: Per-scene processing ──────────────────────────────────────────
PREV_COLORIZED=""

for CLIP in "${CLIPS[@]}"; do
    CLIP_STEM="$(basename "$CLIP" .mp4)"

    # Extract just the "Scene-NNN" label from the clip filename
    SCENE_LABEL="$(echo "$CLIP_STEM" | grep -o 'Scene-[0-9]*$' || echo "$CLIP_STEM")"
    SCENE_DIR="$OUTPUT_DIR/$SCENE_LABEL"
    mkdir -p "$SCENE_DIR"

    # Move clip into its own scene folder
    mv "$CLIP" "$SCENE_DIR/clip.mp4"
    CLIP="$SCENE_DIR/clip.mp4"

    echo ""
    echo "--- $SCENE_LABEL ---"

    echo "  [2] Video reasoning..."
    python3 "$SCRIPT_DIR/2-gemini-video-reason.py" "$CLIP" \
        --api-key "$API_KEY" \
        --output "$SCENE_DIR/description.txt"

    echo "  [3] Extract keyframe..."
    FRAME="$SCENE_DIR/frame0.png"
    python3 "$SCRIPT_DIR/3-extract-key-frame.py" "$CLIP" --output "$FRAME"

    if [[ ! -f "$FRAME" ]]; then
        echo "  Warning: keyframe not found, skipping colorization." >&2
        continue
    fi

    echo "  [4] Colorize keyframe..."
    COLORIZED="$SCENE_DIR/frame0_colorized.jpg"
    COLORIZE_ARGS=("$FRAME" --api-key "$API_KEY" --output "$COLORIZED")
    if [[ -n "$PREV_COLORIZED" && -f "$PREV_COLORIZED" ]]; then
        COLORIZE_ARGS+=(--reference "$PREV_COLORIZED")
        echo "       (using reference: $PREV_COLORIZED)"
    fi
    python3 "$SCRIPT_DIR/4-colorize-keyframe.py" "${COLORIZE_ARGS[@]}"

    PREV_COLORIZED="$COLORIZED"
done

echo ""
echo "=== Pipeline complete ==="
echo "Output: $OUTPUT_DIR"
echo ""
echo "Structure:"
find "$OUTPUT_DIR" -not -name "*.mp4" | sort | sed "s|$OUTPUT_DIR/||"
