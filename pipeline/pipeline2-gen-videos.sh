#!/usr/bin/env bash
# Usage: ./pipeline2-gen-videos.sh <GEMINI_API_KEY> <INPUT_VIDEO>
# Expects pipeline1-gen-keyframes.sh to have already been run on INPUT_VIDEO.
set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <GEMINI_API_KEY> <INPUT_VIDEO>" >&2
    exit 1
fi

API_KEY="$1"
VIDEO="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ ! -f "$VIDEO" ]]; then
    echo "Error: Input video not found: $VIDEO" >&2
    exit 1
fi

STEM="$(basename "$VIDEO" .mp4)"
OUTPUT_DIR="$SCRIPT_DIR/output/$STEM"

if [[ ! -d "$OUTPUT_DIR" ]]; then
    echo "Error: Output directory not found: $OUTPUT_DIR" >&2
    echo "Run pipeline1-gen-keyframes.sh first." >&2
    exit 1
fi

echo "Input:  $VIDEO"
echo "Output: $OUTPUT_DIR"

SCENE_DIRS=()
while IFS= read -r line; do
    SCENE_DIRS+=("$line")
done < <(find "$OUTPUT_DIR" -maxdepth 1 -type d -name "Scene-*" | sort)

if [[ ${#SCENE_DIRS[@]} -eq 0 ]]; then
    echo "Error: No Scene-* directories found in $OUTPUT_DIR" >&2
    echo "Run pipeline1-gen-keyframes.sh first." >&2
    exit 1
fi

echo "Found ${#SCENE_DIRS[@]} scene(s)"

for SCENE_DIR in "${SCENE_DIRS[@]}"; do
    SCENE_LABEL="$(basename "$SCENE_DIR")"
    echo ""
    echo "--- $SCENE_LABEL ---"

    COLORIZED="$SCENE_DIR/frame0_colorized.jpg"
    DESCRIPTION="$SCENE_DIR/description.txt"
    ORIGINAL_CLIP="$SCENE_DIR/clip.mp4"

    if [[ ! -f "$COLORIZED" ]]; then
        echo "  Warning: colorized keyframe not found ($COLORIZED), skipping." >&2
        continue
    fi
    if [[ ! -f "$DESCRIPTION" ]]; then
        echo "  Warning: description not found ($DESCRIPTION), skipping." >&2
        continue
    fi
    if [[ ! -f "$ORIGINAL_CLIP" ]]; then
        echo "  Warning: original clip not found ($ORIGINAL_CLIP), skipping." >&2
        continue
    fi

    GENERATED="$SCENE_DIR/frame0_colorized_generated.mp4"
    echo "  [5] Generate video from keyframe + description..."
    python3 "$SCRIPT_DIR/../video/5-video-gen.py" \
        "$COLORIZED" "$DESCRIPTION" \
        --api-key "$API_KEY" \
        --output "$GENERATED"

    MATCHED="$SCENE_DIR/frame0_colorized_generated_matched.mp4"
    echo "  [6] Match video length to original clip..."
    python3 "$SCRIPT_DIR/../video/6-match-video-length.py" \
        "$ORIGINAL_CLIP" "$GENERATED" \
        --output "$MATCHED"
done

echo ""
echo "=== Pipeline 2 complete ==="
echo "Output: $OUTPUT_DIR"
echo ""
echo "Structure:"
find "$OUTPUT_DIR" | sort | sed "s|$OUTPUT_DIR/||"
