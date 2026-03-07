#!/usr/bin/env bash
# Usage: ./pipeline1-gen-keyframes.sh [GEMINI_API_KEY] <INPUT_VIDEO>
# If GEMINI_API_KEY is not passed, it will be read from .env or the environment.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Source .env if present
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    # shellcheck source=.env
    source "$SCRIPT_DIR/.env"
fi

if [[ $# -eq 1 ]]; then
    if [[ -z "${GEMINI_API_KEY:-}" ]]; then
        echo "Usage: $0 [GEMINI_API_KEY] <INPUT_VIDEO>" >&2
        echo "Or set GEMINI_API_KEY in $SCRIPT_DIR/.env" >&2
        exit 1
    fi
    API_KEY="$GEMINI_API_KEY"
    VIDEO="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
elif [[ $# -ge 2 ]]; then
    API_KEY="$1"
    VIDEO="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
else
    echo "Usage: $0 [GEMINI_API_KEY] <INPUT_VIDEO>" >&2
    exit 1
fi
if [[ ! -f "$VIDEO" ]]; then
    echo "Error: Input video not found: $VIDEO" >&2
    exit 1
fi

STEM="$(basename "$VIDEO" .mp4)"
OUTPUT_DIR="$SCRIPT_DIR/output/$STEM"
CLIPS_DIR="$OUTPUT_DIR/clips"
mkdir -p "$CLIPS_DIR"

echo "Input:  $VIDEO"
echo "Output: $OUTPUT_DIR"

# ── Step 1: Segment (Gemini) ──────────────────────────────────────────────────
echo ""
echo "=== Step 1: Segment (Gemini) ==="
python3 "$SCRIPT_DIR/../video/1-segment-gemini.py" "$VIDEO" \
    --api-key "$API_KEY" \
    --output-dir "$CLIPS_DIR"

CLIPS=()
while IFS= read -r line; do
    CLIPS+=("$line")
done < <(find "$CLIPS_DIR" -maxdepth 1 -name "*.mp4" | sort)

if [[ ${#CLIPS[@]} -eq 0 ]]; then
    echo "Error: No scene clips found after segmentation." >&2
    exit 1
fi
echo "Found ${#CLIPS[@]} scene clip(s)"

# ── Step 1.5: Master color guide (watches entire film) ────────────────────────
echo ""
echo "=== Step 1.5: Generate master color guide (full film analysis) ==="
COLOR_GUIDE="$OUTPUT_DIR/color_guide.txt"
python3 "$SCRIPT_DIR/../video/4a-color-guide.py" "$VIDEO" \
    --api-key "$API_KEY" \
    --output "$COLOR_GUIDE"

# ── Steps 2-4: Per-scene processing ──────────────────────────────────────────
PREV_COLORIZED=""

for CLIP in "${CLIPS[@]}"; do
    CLIP_STEM="$(basename "$CLIP" .mp4)"

    SCENE_LABEL="$(echo "$CLIP_STEM" | grep -o 'Scene-[0-9]*$' || echo "$CLIP_STEM")"
    SCENE_DIR="$OUTPUT_DIR/$SCENE_LABEL"
    mkdir -p "$SCENE_DIR"

    mv "$CLIP" "$SCENE_DIR/clip.mp4"
    CLIP="$SCENE_DIR/clip.mp4"

    echo ""
    echo "--- $SCENE_LABEL ---"

    echo "  [2] Video reasoning..."
    python3 "$SCRIPT_DIR/../video/2-gemini-video-reason.py" "$CLIP" \
        --api-key "$API_KEY" \
        --output "$SCENE_DIR/description.txt"

    echo "  [3] Extract keyframes..."
    FRAME="$SCENE_DIR/frame0.png"
    FRAME2="$SCENE_DIR/frame0_9.png"
    python3 "$SCRIPT_DIR/../video/3-extract-key-frame.py" "$CLIP" --output "$FRAME"
    python3 "$SCRIPT_DIR/../video/3-extract-key-frame.py" "$CLIP" --skip-seconds 0.9 --output "$FRAME2" || true

    if [[ ! -f "$FRAME" ]]; then
        echo "  Warning: keyframe not found, skipping colorization." >&2
        continue
    fi

    echo "  [4] Colorize keyframe..."
    COLORIZED="$SCENE_DIR/frame0_colorized.jpg"
    COLORIZE_ARGS=("$FRAME" --api-key "$API_KEY" --output "$COLORIZED")
    if [[ -f "$FRAME2" ]]; then
        COLORIZE_ARGS+=(--input2 "$FRAME2")
        echo "       (using second frame: $FRAME2)"
    fi
    if [[ -n "$PREV_COLORIZED" && -f "$PREV_COLORIZED" ]]; then
        COLORIZE_ARGS+=(--reference "$PREV_COLORIZED")
        echo "       (using reference: $PREV_COLORIZED)"
    fi
    python3 "$SCRIPT_DIR/../video/4-colorize-keyframe.py" "${COLORIZE_ARGS[@]}"

    PREV_COLORIZED="$COLORIZED"
done

echo ""
echo "=== Pipeline complete ==="
echo "Output: $OUTPUT_DIR"
echo ""
echo "Structure:"
find "$OUTPUT_DIR" -not -name "*.mp4" | sort | sed "s|$OUTPUT_DIR/||"
