#!/usr/bin/env bash
# Usage: ./pipeline2-gen-videos.sh [GEMINI_API_KEY] <INPUT_VIDEO_or_OUTPUT_DIR>
# Accepts either the original input video (e.g. ../input-videos/CC-Girl-Scene.mp4)
# or the scene output directory produced by pipeline1 (e.g. output/CC-Girl-Scene).
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
        echo "Usage: $0 [GEMINI_API_KEY] <INPUT_VIDEO_or_OUTPUT_DIR>" >&2
        echo "Or set GEMINI_API_KEY in $SCRIPT_DIR/.env" >&2
        exit 1
    fi
    API_KEY="$GEMINI_API_KEY"
    TARGET="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
elif [[ $# -ge 2 ]]; then
    API_KEY="$1"
    TARGET="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
else
    echo "Usage: $0 [GEMINI_API_KEY] <INPUT_VIDEO_or_OUTPUT_DIR>" >&2
    exit 1
fi

# Resolve OUTPUT_DIR from either a video file or an existing output directory
if [[ -d "$TARGET" ]]; then
    OUTPUT_DIR="$TARGET"
elif [[ -f "$TARGET" ]]; then
    STEM="$(basename "$TARGET" .mp4)"
    OUTPUT_DIR="$SCRIPT_DIR/output/$STEM"
    if [[ ! -d "$OUTPUT_DIR" ]]; then
        echo "Error: Output directory not found: $OUTPUT_DIR" >&2
        echo "Run pipeline1-gen-keyframes.sh first." >&2
        exit 1
    fi
else
    echo "Error: '$TARGET' is neither a video file nor an existing output directory." >&2
    exit 1
fi

echo "Input:  $TARGET"
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

    # Compute shortest valid duration for the API (Veo minimum is 5s)
    CLIP_DUR=$(ffprobe -v error -show_entries format=duration \
        -of default=noprint_wrappers=1:nokey=1 "$ORIGINAL_CLIP" 2>/dev/null | awk '{printf "%d", int($1)+1}')
    TARGET_DUR=$(( CLIP_DUR > 5 ? CLIP_DUR : 5 ))
    echo "  Clip duration: ${CLIP_DUR}s → requesting ${TARGET_DUR}s from video API"

    GENERATED="$SCENE_DIR/frame0_colorized_generated.mp4"
    echo "  [5] Generate video from keyframe + description..."
    python3 "$SCRIPT_DIR/../video/5-video-gen.py" \
        "$COLORIZED" "$DESCRIPTION" \
        --api-key "$API_KEY" \
        --duration "$TARGET_DUR" \
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
