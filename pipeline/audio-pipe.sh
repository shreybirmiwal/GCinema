#!/usr/bin/env bash
# Audio pipeline: video → synchronized audio MP3
#
# Usage:
#   ./audio-pipe.sh <input_video> <gemini_api_key> <elevenlabs_api_key> [output.mp3] [--language LANG]
#
# Examples:
#   ./audio-pipe.sh clip.mp4 AIza... sk-... final_audio.mp3
#   ./audio-pipe.sh clip.mp4 AIza... sk-...                        # default English output
#   ./audio-pipe.sh clip.mp4 AIza... sk-... out.mp3 --language Spanish
#   ./audio-pipe.sh clip.mp4 AIza... sk-... --language French      # language without output path
#
# Optional env vars (instead of positional args):
#   GEMINI_API_KEY, ELEVENLABS_API_KEY, AUDIO_LANGUAGE

set -euo pipefail

# ---- Args ----------------------------------------------------------------
VIDEO="${1:?Usage: $0 <video> <gemini_key> <elevenlabs_key> [output.mp3] [--language LANG]}"
GEMINI_KEY="${2:-${GEMINI_API_KEY:-}}"
ELEVENLABS_KEY="${3:-${ELEVENLABS_API_KEY:-}}"

# Parse remaining positional/named args (output path and --language)
OUTPUT=""
LANGUAGE="${AUDIO_LANGUAGE:-English}"
shift 3 || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --language|-l)
      LANGUAGE="${2:?--language requires a value (e.g. Spanish)}"
      shift 2
      ;;
    --language=*)
      LANGUAGE="${1#*=}"
      shift
      ;;
    *)
      OUTPUT="$1"
      shift
      ;;
  esac
done

if [[ -z "$GEMINI_KEY" ]]; then
  echo "Error: Gemini API key required (arg 2 or GEMINI_API_KEY env var)" >&2
  exit 1
fi
if [[ -z "$ELEVENLABS_KEY" ]]; then
  echo "Error: ElevenLabs API key required (arg 3 or ELEVENLABS_API_KEY env var)" >&2
  exit 1
fi

echo "Language: $LANGUAGE"

# ---- Paths ---------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUDIO_DIR="$(cd "$SCRIPT_DIR/../audio" && pwd)"

# Derive output directory from the video stem so audio lives next to the
# scene clips: pipeline/output/<STEM>/audio/
VIDEO_STEM="$(basename "$VIDEO" .mp4)"
WORK_DIR="$SCRIPT_DIR/output/$VIDEO_STEM/audio"
mkdir -p "$WORK_DIR"

MUSIC_PROMPT="$WORK_DIR/music_prompt.txt"
AUDIO_EVENTS="$WORK_DIR/audio_events.json"
SCORE_WAV="$WORK_DIR/score.wav"
FOLEY_WAV="$WORK_DIR/foley.wav"
FINAL_MP3="${OUTPUT:-$WORK_DIR/final_audio.mp3}"

# ---- Video duration ------------------------------------------------------
echo "Detecting video duration..."
DURATION=$(ffprobe -v error -show_entries format=duration \
  -of default=noprint_wrappers=1:nokey=1 "$VIDEO")
DURATION_INT=$(python3 -c "import math; print(max(1, round($DURATION)))")
echo "  Duration: ${DURATION}s (rounded: ${DURATION_INT}s)"

# ---- S1: Gemini video analysis -------------------------------------------
echo ""
echo "============================================================"
echo "  S1 — Gemini: analyze video → music prompt + audio events"
echo "============================================================"
python3 "$AUDIO_DIR/S1-sound-gen-prompt.py" "$VIDEO" \
  --output-music "$MUSIC_PROMPT" \
  --output-lipsync "$AUDIO_EVENTS" \
  --language "$LANGUAGE" \
  --api-key "$GEMINI_KEY"

# ---- S2: Lyria music generation ------------------------------------------
echo ""
echo "============================================================"
echo "  S2 — Lyria: generate background music"
echo "============================================================"
python3 "$AUDIO_DIR/S2-sound-gen-lyria.py" "$MUSIC_PROMPT" \
  --output "$SCORE_WAV" \
  --duration "$DURATION_INT" \
  --api-key "$GEMINI_KEY"

# ---- S3: ElevenLabs foley/vocals -----------------------------------------
echo ""
echo "============================================================"
echo "  S3 — ElevenLabs: generate foley + vocals"
echo "============================================================"
python3 "$AUDIO_DIR/S3-vocal-gen.py" "$AUDIO_EVENTS" \
  --output "$FOLEY_WAV" \
  --duration "$DURATION" \
  --language "$LANGUAGE" \
  --api-key "$ELEVENLABS_KEY"

# ---- S4: Mix to exact video length ---------------------------------------
echo ""
echo "============================================================"
echo "  S4 — Mix: combine music + foley → final MP3"
echo "============================================================"
python3 "$AUDIO_DIR/S4-mix-audio.py" "$SCORE_WAV" "$FOLEY_WAV" \
  --duration "$DURATION" \
  --output "$FINAL_MP3"

echo ""
echo "Done. Final audio: $FINAL_MP3"
