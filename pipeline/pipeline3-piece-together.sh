#!/usr/bin/env bash
# pipeline3-piece-together.sh
#
# Usage:
#   ./pipeline3-piece-together.sh <INPUT_VIDEO_or_OUTPUT_DIR>
#
# Takes the per-scene output from pipeline1 + pipeline2 and:
#   1. Concatenates all frame0_colorized_generated_matched.mp4 clips in order
#   2. Muxes in audio/final_audio.mp3 if the audio pipeline has been run
#   3. Writes pipeline/output/<STEM>/final_colorized.mp4
#   4. Opens both videos (original + colorized) in system default player
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$SCRIPT_DIR/.env" ]]; then
    # shellcheck source=.env
    source "$SCRIPT_DIR/.env"
fi

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <INPUT_VIDEO_or_OUTPUT_DIR>" >&2
    exit 1
fi

TARGET="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"

# ── Resolve OUTPUT_DIR and STEM ───────────────────────────────────────────────
if [[ -d "$TARGET" ]]; then
    OUTPUT_DIR="$TARGET"
    STEM="$(basename "$OUTPUT_DIR")"
elif [[ -f "$TARGET" ]]; then
    STEM="$(basename "$TARGET" .mp4)"
    OUTPUT_DIR="$SCRIPT_DIR/output/$STEM"
    if [[ ! -d "$OUTPUT_DIR" ]]; then
        echo "Error: Output directory not found: $OUTPUT_DIR" >&2
        echo "Run pipeline1-gen-keyframes.sh and pipeline2-gen-videos.sh first." >&2
        exit 1
    fi
else
    echo "Error: '$TARGET' is neither a video file nor an existing output directory." >&2
    exit 1
fi

echo "Stem:       $STEM"
echo "Output dir: $OUTPUT_DIR"

# ── Find original input video (for the viewer) ────────────────────────────────
ORIGINAL_VIDEO=""
for candidate in \
    "$PROJECT_DIR/input-videos/$STEM.mp4" \
    "$TARGET"
do
    if [[ -f "$candidate" ]]; then
        ORIGINAL_VIDEO="$candidate"
        break
    fi
done

if [[ -n "$ORIGINAL_VIDEO" ]]; then
    echo "Original:   $ORIGINAL_VIDEO"
else
    echo "Warning: Could not locate original video — viewer will show colorized only." >&2
fi

# ── Collect matched scene clips ───────────────────────────────────────────────
MATCHED_CLIPS=()
while IFS= read -r line; do
    MATCHED_CLIPS+=("$line")
done < <(find "$OUTPUT_DIR" -maxdepth 2 -name "frame0_colorized_generated_matched.mp4" | sort)

if [[ ${#MATCHED_CLIPS[@]} -eq 0 ]]; then
    echo "" >&2
    echo "Error: No frame0_colorized_generated_matched.mp4 files found in $OUTPUT_DIR" >&2
    echo "Run pipeline2-gen-videos.sh first." >&2
    exit 1
fi

echo "Found ${#MATCHED_CLIPS[@]} colorized scene clip(s)"

# ── Build ffmpeg concat list ──────────────────────────────────────────────────
CONCAT_LIST="$OUTPUT_DIR/concat_list.txt"
: > "$CONCAT_LIST"
for clip in "${MATCHED_CLIPS[@]}"; do
    echo "file '$clip'" >> "$CONCAT_LIST"
    echo "  + $(basename "$(dirname "$clip")")/$(basename "$clip")"
done

# ── Step 1: Concatenate scene clips (re-encode to CFR for compatibility) ──────
echo ""
echo "=== Concatenating ${#MATCHED_CLIPS[@]} scene clips ==="
CONCAT_VIDEO="$OUTPUT_DIR/concat_no_audio.mp4"
ffmpeg -y -f concat -safe 0 -i "$CONCAT_LIST" \
    -filter_complex "[0:v]setpts=PTS-STARTPTS,format=yuv420p,fps=24[v]" \
    -map "[v]" -c:v libx264 -preset fast -crf 18 -an -movflags +faststart "$CONCAT_VIDEO" 2>&1 \
    | grep -E "(Output|Error|frame=|fps=|time=)" || true
echo "Concat done: $CONCAT_VIDEO"
read -r -p "  [Step 1 done] Verify concat locally? Press Enter to continue, or Ctrl+C to stop... " _

# ── Step 2: Mux audio ─────────────────────────────────────────────────────────
AUDIO_FILE="$OUTPUT_DIR/audio/final_audio.mp3"
FINAL_VIDEO="$OUTPUT_DIR/final_colorized.mp4"

echo ""
if [[ -f "$AUDIO_FILE" ]]; then
    echo "=== Muxing audio: $AUDIO_FILE ==="
    ffmpeg -y \
        -i "$CONCAT_VIDEO" \
        -i "$AUDIO_FILE" \
        -c:v copy \
        -c:a aac \
        -b:a 192k \
        -shortest \
        -movflags +faststart \
        "$FINAL_VIDEO" 2>&1 \
        | grep -E "(Output|Error|frame=|fps=|time=)" || true
    rm -f "$CONCAT_VIDEO"
    echo "Final video (with audio): $FINAL_VIDEO"
else
    echo "No audio found at $AUDIO_FILE — outputting video-only"
    mv "$CONCAT_VIDEO" "$FINAL_VIDEO"
    echo "Final video: $FINAL_VIDEO"
fi

rm -f "$CONCAT_LIST"

# ── Ensure final file is fully written ─────────────────────────────────────────
sync
if [[ ! -f "$FINAL_VIDEO" || ! -s "$FINAL_VIDEO" ]]; then
    echo "Error: Final video was not created or is empty: $FINAL_VIDEO" >&2
    exit 1
fi
echo "Final file ready: $FINAL_VIDEO"
read -r -p "  [Step 2 done] Verify final file locally? Press Enter to continue, or Ctrl+C to stop... " _

# ── Step 3: Open both videos in system default player ─────────────────────────
echo ""
echo "=== Opening videos in default player ==="
if [[ -n "$ORIGINAL_VIDEO" && -f "$ORIGINAL_VIDEO" ]]; then
    open "$ORIGINAL_VIDEO" 2>/dev/null || xdg-open "$ORIGINAL_VIDEO" 2>/dev/null || echo "Original: $ORIGINAL_VIDEO"
fi
open "$FINAL_VIDEO" 2>/dev/null || xdg-open "$FINAL_VIDEO" 2>/dev/null || echo "Colorized: $FINAL_VIDEO"
echo "Done."
