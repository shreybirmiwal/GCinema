#!/usr/bin/env bash
# _scene-worker.sh — Per-scene background worker (steps 2-6)
# Tracks progress via .stage file and logs to .worker.log
#
# Usage: _scene-worker.sh <SCENE_DIR> <API_KEY> <PIPELINE_DIR> [PREV_SCENE_DIR|none]
set -uo pipefail

SCENE_DIR="$1"
API_KEY="$2"
PIPELINE_DIR="$3"
PREV_SCENE_DIR="${4:-none}"

VIDEO_DIR="$PIPELINE_DIR/../video"
SCENE_LABEL="$(basename "$SCENE_DIR")"
STAGE_FILE="$SCENE_DIR/.stage"
LOG_FILE="$SCENE_DIR/.worker.log"

: > "$LOG_FILE"

set_stage() { printf '%s' "$1" > "$STAGE_FILE"; }

log() { printf '[%s] %s\n' "$SCENE_LABEL" "$*" >> "$LOG_FILE"; }

fail() { set_stage "error"; log "ERROR: $*"; exit 1; }

trap 'set_stage "error"; exit 1' ERR

# ── Step 2: Video reasoning ──────────────────────────────────────────────────
set_stage "reasoning"
log "Prompt → Gemini: Describe every action, movement, emotion, and"
log "  environment in exhaustive detail for a video generation AI (400+ words)."
python3 "$VIDEO_DIR/2-gemini-video-reason.py" "$SCENE_DIR/clip.mp4" \
    --api-key "$API_KEY" \
    --output "$SCENE_DIR/description.txt" >> "$LOG_FILE" 2>&1 \
    || fail "Video reasoning failed"
# Show first line of description in the log
if [[ -f "$SCENE_DIR/description.txt" ]]; then
    FIRST_LINE="$(head -1 "$SCENE_DIR/description.txt" | cut -c1-80)"
    log "Gemini: \"${FIRST_LINE}...\""
fi
log "Description saved."

# ── Step 3: Extract keyframe ─────────────────────────────────────────────────
set_stage "keyframe"
log "Extracting first frame as keyframe..."
python3 "$VIDEO_DIR/3-extract-key-frame.py" "$SCENE_DIR/clip.mp4" \
    --output "$SCENE_DIR/frame0.png" >> "$LOG_FILE" 2>&1 \
    || fail "Keyframe extraction failed"

if [[ ! -f "$SCENE_DIR/frame0.png" ]]; then
    fail "Keyframe file not found after extraction"
fi
log "Keyframe saved: frame0.png"

# ── Step 4: Colorize (wait for prev scene chain) ─────────────────────────────
if [[ "$PREV_SCENE_DIR" != "none" && -n "$PREV_SCENE_DIR" ]]; then
    set_stage "colorize_wait"
    log "Waiting for $(basename "$PREV_SCENE_DIR") colorization..."
    while true; do
        prev_stage="$(cat "$PREV_SCENE_DIR/.stage" 2>/dev/null || echo "pending")"
        case "$prev_stage" in
            videogen|match|done) break ;;
            error)
                log "Previous scene errored — proceeding without reference"
                PREV_SCENE_DIR="none"
                break
                ;;
        esac
        sleep 2
    done
fi

set_stage "colorize"
if [[ "$PREV_SCENE_DIR" != "none" && -f "$PREV_SCENE_DIR/frame0_colorized.jpg" ]]; then
    log "Prompt → Gemini: Colorize this B&W frame using reference for consistent"
    log "  palette, skin tones, and clothing. Keep colors natural, not over-saturated."
    log "Using color reference from $(basename "$PREV_SCENE_DIR")"
else
    log "Prompt → Gemini: Add natural, realistic color to this black and white"
    log "  image. Keep it subtle and grounded — do not over-saturate."
fi
log "Colorizing keyframe with Gemini Image..."
COLORIZE_ARGS=("$SCENE_DIR/frame0.png" --api-key "$API_KEY" --output "$SCENE_DIR/frame0_colorized.jpg")
if [[ "$PREV_SCENE_DIR" != "none" && -f "$PREV_SCENE_DIR/frame0_colorized.jpg" ]]; then
    COLORIZE_ARGS+=(--reference "$PREV_SCENE_DIR/frame0_colorized.jpg")
fi
python3 "$VIDEO_DIR/4-colorize-keyframe.py" "${COLORIZE_ARGS[@]}" >> "$LOG_FILE" 2>&1 \
    || fail "Colorization failed"
log "Gemini: [image generated] → frame0_colorized.jpg saved."

# ── Step 5: Video generation ─────────────────────────────────────────────────
set_stage "videogen"
CLIP_DUR=$(ffprobe -v error -show_entries format=duration \
    -of default=noprint_wrappers=1:nokey=1 "$SCENE_DIR/clip.mp4" 2>/dev/null \
    | awk '{printf "%d", int($1)+1}')
TARGET_DUR=$(( CLIP_DUR > 5 ? CLIP_DUR : 5 ))
if [[ -f "$SCENE_DIR/description.txt" ]]; then
    PROMPT_SNIPPET="$(head -1 "$SCENE_DIR/description.txt" | cut -c1-72)"
    log "Prompt → Veo: \"${PROMPT_SNIPPET}...\""
fi
log "Generating colorized video (${TARGET_DUR}s target)..."
python3 "$VIDEO_DIR/5-video-gen.py" \
    "$SCENE_DIR/frame0_colorized.jpg" "$SCENE_DIR/description.txt" \
    --api-key "$API_KEY" \
    --duration "$TARGET_DUR" \
    --output "$SCENE_DIR/frame0_colorized_generated.mp4" >> "$LOG_FILE" 2>&1 \
    || fail "Video generation failed"
log "Generated video saved."

# ── Step 6: Match video length ───────────────────────────────────────────────
set_stage "match"
log "Time-stretching to match original clip duration..."
python3 "$VIDEO_DIR/6-match-video-length.py" \
    "$SCENE_DIR/clip.mp4" "$SCENE_DIR/frame0_colorized_generated.mp4" \
    --output "$SCENE_DIR/frame0_colorized_generated_matched.mp4" >> "$LOG_FILE" 2>&1 \
    || fail "Video length matching failed"
log "Matched video saved."

# ── Done ─────────────────────────────────────────────────────────────────────
set_stage "done"
log "All steps complete!"
