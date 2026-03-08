#!/usr/bin/env bash
# run.sh — GCinema Full Pipeline Orchestrator
#
# Interactive TUI with arrow-key video picker, parallel scene dashboard,
# audio pipeline, assembly, and localhost viewer.
#
# Usage: ./run.sh
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$SCRIPT_DIR/.env" ]]; then
    # shellcheck source=.env
    source "$SCRIPT_DIR/.env"
fi

PIPELINE_START=$(date +%s)

# ═════════════════════════════════════════════════════════════════════════════
# ANSI Escape Codes
# ═════════════════════════════════════════════════════════════════════════════
RST='\033[0m'
BOLD='\033[1m'
DIM='\033[2m'
ITALIC='\033[3m'
ULINE='\033[4m'

FG_BLACK='\033[30m'
FG_RED='\033[31m'
FG_GREEN='\033[32m'
FG_YELLOW='\033[33m'
FG_BLUE='\033[34m'
FG_MAGENTA='\033[35m'
FG_CYAN='\033[36m'
FG_WHITE='\033[37m'
FG_GRAY='\033[90m'
FG_BGREEN='\033[92m'
FG_BYELLOW='\033[93m'
FG_GOLD='\033[38;5;179m'
FG_AMBER='\033[38;5;214m'

BG_RED='\033[41m'
BG_GREEN='\033[42m'
BG_YELLOW='\033[43m'
BG_BLUE='\033[44m'
BG_MAGENTA='\033[45m'
BG_CYAN='\033[46m'
BG_GRAY='\033[100m'
BG_BGREEN='\033[102m'
BG_DARK='\033[48;5;236m'

SPINNER_FRAMES=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
SPINNER_IDX=0

WORKER_PIDS=()
SERVER_PID=""

# ═════════════════════════════════════════════════════════════════════════════
# Utility Functions
# ═════════════════════════════════════════════════════════════════════════════

cleanup() {
    tput cnorm 2>/dev/null || true
    tput rmcup 2>/dev/null || true
    for pid in "${WORKER_PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    if [[ -n "$SERVER_PID" ]]; then
        kill "$SERVER_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

spin() {
    SPINNER_IDX=$(( (SPINNER_IDX + 1) % ${#SPINNER_FRAMES[@]} ))
    printf '%s' "${SPINNER_FRAMES[$SPINNER_IDX]}"
}

repeat_char() {
    local ch="$1" n="$2"
    printf '%0.s'"$ch" $(seq 1 "$n")
}

pad_right() {
    local str="$1" width="$2"
    printf '%-*s' "$width" "$str"
}

truncate_str() {
    local str="$1" max="$2"
    if (( ${#str} > max )); then
        printf '%s…' "${str:0:$((max - 1))}"
    else
        printf '%s' "$str"
    fi
}

progress_bar() {
    local pct=$1 width=$2
    local filled=$(( pct * width / 100 ))
    local empty=$(( width - filled ))
    if (( filled > 0 )); then repeat_char '▰' "$filled"; fi
    if (( empty > 0 )); then repeat_char '▱' "$empty"; fi
    printf ' %3d%%' "$pct"
}

stage_to_pct() {
    case "$1" in
        pending)        echo 0 ;;
        reasoning)      echo 15 ;;
        keyframe)       echo 28 ;;
        colorize_wait)  echo 35 ;;
        colorize)       echo 48 ;;
        videogen)       echo 70 ;;
        match)          echo 90 ;;
        done)           echo 100 ;;
        error)          echo -1 ;;
        *)              echo 0 ;;
    esac
}

stage_label() {
    case "$1" in
        pending)        echo "PENDING" ;;
        reasoning)      echo "REASONING" ;;
        keyframe)       echo "KEYFRAME" ;;
        colorize_wait)  echo "WAITING" ;;
        colorize)       echo "COLORIZE" ;;
        videogen)       echo "VIDEO GEN" ;;
        match)          echo "MATCHING" ;;
        done)           echo "DONE" ;;
        error)          echo "ERROR" ;;
        *)              echo "..." ;;
    esac
}

stage_color() {
    case "$1" in
        reasoning)      printf '%b' "$BG_BLUE$FG_WHITE$BOLD" ;;
        keyframe)       printf '%b' "$BG_GREEN$FG_BLACK$BOLD" ;;
        colorize_wait)  printf '%b' "$BG_GRAY$FG_WHITE$BOLD" ;;
        colorize)       printf '%b' "$BG_MAGENTA$FG_WHITE$BOLD" ;;
        videogen)       printf '%b' "$BG_YELLOW$FG_BLACK$BOLD" ;;
        match)          printf '%b' "$BG_CYAN$FG_BLACK$BOLD" ;;
        done)           printf '%b' "$BG_BGREEN$FG_BLACK$BOLD" ;;
        error)          printf '%b' "$BG_RED$FG_WHITE$BOLD" ;;
        *)              printf '%b' "$BG_DARK$FG_WHITE" ;;
    esac
}

phase_header() {
    local num="$1" name="$2" color="$3"
    local cols
    cols=$(tput cols)
    local bar
    bar="$(repeat_char '━' "$cols")"
    printf '\n'
    printf '%b%s%b\n' "$color$BOLD" "$bar" "$RST"
    printf '%b  ◼ PHASE %s  %b│%b  %s%b\n' \
        "$color$BOLD" "$num" "$RST$color" "$RST$BOLD" "$name" "$RST"
    printf '%b%s%b\n' "$color$BOLD" "$bar" "$RST"
    printf '\n'
}

log_step() {
    local icon="$1" msg="$2"
    printf '  %b%s%b  %s\n' "$FG_GOLD" "$icon" "$RST" "$msg"
}

log_detail() {
    local msg="$1"
    printf '     %b%s%b\n' "$FG_GRAY" "$msg" "$RST"
}

log_success() {
    local msg="$1"
    printf '  %b✔%b  %s\n' "$FG_BGREEN$BOLD" "$RST" "$msg"
}

log_error() {
    local msg="$1"
    printf '  %b✘%b  %s\n' "$FG_RED$BOLD" "$RST" "$msg" >&2
}

# show_gemini_prompt <model> <purpose>
# Reads prompt text from stdin and renders a styled box
show_gemini_prompt() {
    local model="$1" purpose="$2"
    local cols
    cols=$(tput cols 2>/dev/null || echo 90)
    local inner=$(( cols - 8 ))
    printf '\n'
    printf '  %b┌─ ✦ PROMPT → GEMINI%b  %b%s%b  %b[%s]%b\n' \
        "$FG_BLUE$BOLD" "$RST" \
        "$FG_BLUE" "$purpose" "$RST" \
        "$FG_GRAY$DIM" "$model" "$RST"
    local line
    while IFS= read -r line; do
        [[ -z "$line" ]] && { printf '  %b│%b\n' "$FG_BLUE$DIM" "$RST"; continue; }
        printf '  %b│%b  %b%s%b\n' "$FG_BLUE" "$RST" "$FG_GRAY$ITALIC" \
            "$(truncate_str "$line" "$inner")" "$RST"
    done
    printf '  %b└────────────────────────────────────────%b\n' "$FG_BLUE$DIM" "$RST"
    printf '\n'
}

# show_gemini_response <purpose> [max_lines]
# Reads response text from stdin and renders a styled box
show_gemini_response() {
    local purpose="$1" max_lines="${2:-18}"
    local cols
    cols=$(tput cols 2>/dev/null || echo 90)
    local inner=$(( cols - 8 ))
    printf '\n'
    printf '  %b┌─ ✦ GEMINI RESPONSE%b  %b%s%b\n' \
        "$FG_BGREEN$BOLD" "$RST" "$FG_BGREEN" "$purpose" "$RST"
    local line count=0
    while IFS= read -r line && (( count < max_lines )); do
        [[ -z "$line" ]] && continue
        printf '  %b│%b  %b%s%b\n' "$FG_BGREEN" "$RST" "$FG_WHITE" \
            "$(truncate_str "$line" "$inner")" "$RST"
        (( count++ ))
    done
    printf '  %b└────────────────────────────────────────%b\n' "$FG_BGREEN$DIM" "$RST"
    printf '\n'
}

# show_audio_events_preview <json_file> [max_events]
# Pretty-prints the first N audio events from an S1 JSON events file
show_audio_events_preview() {
    local events_file="$1" max_events="${2:-10}"
    [[ ! -f "$events_file" ]] && return
    printf '  %b┌─ ✦ AUDIO EVENTS PREVIEW%b\n' "$FG_AMBER$BOLD" "$RST"
    python3 - "$events_file" "$max_events" <<'PYEOF' 2>/dev/null | \
        while IFS= read -r line; do
            printf '  \033[38;5;214m│\033[0m  %s\n' "$line"
        done
import json, sys
path, n = sys.argv[1], int(sys.argv[2])
events = json.load(open(path))[:n]
for e in events:
    ts = e.get('timestamp_sec', 0)
    kind = e.get('type', '?')
    if kind == 'speech':
        char = e.get('character', '?')
        utt  = e.get('utterance', '')
        print(f"[{ts:>6.2f}s]  SPEECH  {char:<20}  \"{utt}\"")
    else:
        desc = e.get('description', '?')
        print(f"[{ts:>6.2f}s]  SFX     {desc}")
PYEOF
    printf '  %b└────────────────────────────────────────%b\n' "$FG_AMBER$DIM" "$RST"
    printf '\n'
}

# Number input selection. Returns selected index (0-based) via global SEL_RESULT.
# Usage: number_select "Prompt" option1 option2 ... [--disabled N]
# Disabled indices are not shown as selectable.
SEL_RESULT=0
number_select() {
    local prompt="$1"; shift
    local -a options=()
    local -a disabled=()
    local parsing_disabled=false

    for arg in "$@"; do
        if [[ "$arg" == "--disabled" ]]; then
            parsing_disabled=true
            continue
        fi
        if $parsing_disabled; then
            disabled+=("$arg")
        else
            options+=("$arg")
        fi
    done

    local count=${#options[@]}
    local choice=""

    while true; do
        printf '\n'
        printf '  %b%s%b\n' "$FG_GOLD$BOLD" "$prompt" "$RST"
        printf '\n'

        local num=1
        for i in $(seq 0 $((count - 1))); do
            local is_disabled=false
            for d in "${disabled[@]}"; do
                if (( d == i )); then is_disabled=true; break; fi
            done
            if $is_disabled; then
                printf '    %b%d. %s%b\n' "$FG_GRAY$DIM" "$num" "${options[$i]}" "$RST"
            else
                printf '    %b%d.%b %s\n' "$FG_CYAN" "$num" "$RST" "${options[$i]}"
            fi
            (( num++ ))
        done

        printf '\n'
        printf '  %bEnter choice [1-%d]:%b ' "$FG_GOLD" "$count" "$RST"
        read -r choice
        choice="${choice//[^0-9]/}"
        if [[ -n "$choice" ]]; then
            local idx=$((choice - 1))
            if (( idx >= 0 && idx < count )); then
                local is_disabled=false
                for d in "${disabled[@]}"; do
                    if (( d == idx )); then is_disabled=true; break; fi
                done
                if ! $is_disabled; then
                    SEL_RESULT=$idx
                    return
                fi
            fi
        fi
        printf '  %bInvalid. Try again.%b\n' "$FG_RED" "$RST"
    done
}

# ═════════════════════════════════════════════════════════════════════════════
# PHASE 0: Video Picker
# ═════════════════════════════════════════════════════════════════════════════

VIDEO_FILES=()
VIDEO_LABELS=()
INPUT_DIR="$PROJECT_DIR/input-videos"

while IFS= read -r f; do
    stem="$(basename "$f" .mp4)"
    cuts_file="$INPUT_DIR/$stem.cuts.json"
    scene_count="?"
    if [[ -f "$cuts_file" ]]; then
        scene_count=$(python3 -c "import json; d=json.load(open('$cuts_file')); print(len(d.get('cuts',[]))+1)" 2>/dev/null || echo "?")
    fi
    VIDEO_FILES+=("$f")
    VIDEO_LABELS+=("$(pad_right "$stem.mp4" 36) ${scene_count} scenes")
done < <(find "$INPUT_DIR" -maxdepth 1 -name "*.mp4" ! -name "Charlie*" | sort)

VIDEO_LABELS+=("Upload custom video...                coming soon")

if [[ ${#VIDEO_FILES[@]} -eq 0 ]]; then
    printf '\n  %bNo .mp4 files found in %s%b\n' "$FG_RED" "$INPUT_DIR" "$RST"
    exit 1
fi

DISABLED_INDICES=("${#VIDEO_FILES[@]}")

clear
printf '\n'
printf '  %b┌────────────────────────────────────────────────────┐%b\n' "$FG_GRAY" "$RST"
printf '  %b│%b                                                    %b│%b\n' "$FG_GRAY" "$RST" "$FG_GRAY" "$RST"
printf '  %b│%b    %b██████╗  ██████╗ ██╗ ███╗   ██╗%b               %b│%b\n' "$FG_GRAY" "$RST" "$FG_GOLD$BOLD" "$RST" "$FG_GRAY" "$RST"
printf '  %b│%b    %b██╔════╝ ██╔════╝ ██║ ████╗  ██║%b               %b│%b\n' "$FG_GRAY" "$RST" "$FG_GOLD$BOLD" "$RST" "$FG_GRAY" "$RST"
printf '  %b│%b    %b██║ ███╗ ██║      ██║ ██╔██╗ ██║%b  %bGCinema%b    %b│%b\n' "$FG_GRAY" "$RST" "$FG_GOLD$BOLD" "$RST" "$FG_AMBER$BOLD" "$RST" "$FG_GRAY" "$RST"
printf '  %b│%b    %b██║  ██║ ██║      ██║ ██║╚██╗██║%b               %b│%b\n' "$FG_GRAY" "$RST" "$FG_GOLD$BOLD" "$RST" "$FG_GRAY" "$RST"
printf '  %b│%b    %b╚██████╔╝╚██████╗ ██║ ██║ ╚████║%b               %b│%b\n' "$FG_GRAY" "$RST" "$FG_GOLD$BOLD" "$RST" "$FG_GRAY" "$RST"
printf '  %b│%b    %b ╚═════╝  ╚═════╝ ╚═╝ ╚═╝  ╚═══╝%b              %b│%b\n' "$FG_GRAY" "$RST" "$FG_GOLD" "$RST" "$FG_GRAY" "$RST"
printf '  %b│%b                                                    %b│%b\n' "$FG_GRAY" "$RST" "$FG_GRAY" "$RST"
printf '  %b│%b    %bAI-Powered Silent Film Colorization Pipeline%b    %b│%b\n' "$FG_GRAY" "$RST" "$FG_GRAY$ITALIC" "$RST" "$FG_GRAY" "$RST"
printf '  %b│%b                                                    %b│%b\n' "$FG_GRAY" "$RST" "$FG_GRAY" "$RST"
printf '  %b└────────────────────────────────────────────────────┘%b\n' "$FG_GRAY" "$RST"
printf '\n'

printf '  %bPress any key to continue...%b' "$FG_GRAY" "$RST"
IFS= read -rsn1 _
clear

number_select "Select input video" "${VIDEO_LABELS[@]}" --disabled "${DISABLED_INDICES[@]}"
CHOSEN_IDX=$SEL_RESULT
VIDEO="${VIDEO_FILES[$CHOSEN_IDX]}"
STEM="$(basename "$VIDEO" .mp4)"
OUTPUT_DIR="$SCRIPT_DIR/output/$STEM"
CLIPS_DIR="$OUTPUT_DIR/clips"

clear
printf '\n'
printf '  %b▸ Selected:%b %b%s%b\n' "$FG_CYAN" "$RST" "$BOLD" "$STEM.mp4" "$RST"
printf '\n'
sleep 0.5

# Validate environment
if [[ -z "${GEMINI_API_KEY:-}" ]]; then
    log_error "GEMINI_API_KEY not set. Add it to pipeline/.env"
    exit 1
fi
API_KEY="$GEMINI_API_KEY"

# ═════════════════════════════════════════════════════════════════════════════
# PHASE 1: Segmentation
# ═════════════════════════════════════════════════════════════════════════════

phase_header "1" "SEGMENTATION — Split video into scenes" "$FG_CYAN"

mkdir -p "$CLIPS_DIR"

log_step "▶" "Splitting video into scene clips..."
log_detail "Running: 1-segment-gemini.py"

show_gemini_prompt "gemini-3.1-pro-preview" "Scene Cut Detection" <<'GEMINI_EOF'
Watch this video carefully and identify every single moment where the camera
cuts to a different shot or angle. This includes:

  - Hard cuts between completely different scenes or locations
  - Back-and-forth dialogue cuts (even rapid ones — each cut counts)
  - Reaction shot cuts (cut away to listener, then back to speaker)
  - Any other camera angle change or shot change

Do NOT mark pans, tilts, or zooms within the same continuous shot.

Return ONLY a JSON object in this exact format, with no extra commentary:
  { "cuts": [4.2, 9.7, 14.1, 19.8] }

Each number is the timestamp in seconds where a new shot begins.
The first shot always starts at 0.0, so do NOT include 0.0 in the list.
If there are no cuts at all, return: {"cuts": []}
GEMINI_EOF

SEG_OUTPUT_FILE="$(mktemp)"
python3 "$SCRIPT_DIR/../video/1-segment-gemini.py" "$VIDEO" \
    --api-key "$API_KEY" \
    --output-dir "$CLIPS_DIR" 2>&1 | tee "$SEG_OUTPUT_FILE" | while IFS= read -r line; do
    log_detail "$line"
done

# Show the detected cuts as a Gemini response panel
CUTS_PREVIEW="$(grep -E 'Scene|cut|Detected|sidecar' "$SEG_OUTPUT_FILE" 2>/dev/null | head -20)"
if [[ -n "$CUTS_PREVIEW" ]]; then
    show_gemini_response "Scene Cut Timestamps" <<< "$CUTS_PREVIEW"
fi
rm -f "$SEG_OUTPUT_FILE"

CLIPS=()
while IFS= read -r line; do
    CLIPS+=("$line")
done < <(find "$CLIPS_DIR" -maxdepth 1 -name "*.mp4" | sort)

if [[ ${#CLIPS[@]} -eq 0 ]]; then
    log_error "No scene clips found after segmentation."
    exit 1
fi
log_success "Found ${#CLIPS[@]} scene clip(s)"

printf '\n'
log_step "▶" "Generating master color guide (full film analysis)..."
log_detail "Running: 4a-color-guide.py"
COLOR_GUIDE="$OUTPUT_DIR/color_guide.txt"

show_gemini_prompt "gemini-3.1-pro-preview" "Master Color Guide" <<'GEMINI_EOF'
Watch this entire black-and-white film and produce a master color guide
that will be used to consistently colorize every scene.

For every recurring character, object, animal, and environment you can
identify, specify exact, actionable colors. Examples of detail expected:
  - "Main character (man in suit): charcoal grey pinstripe suit, white
    dress shirt, burgundy tie, warm olive complexion, dark brown hair"
  - "Lion: tawny orange-gold fur, pale cream belly, amber eyes"
  - "Interior parlor: cream walls, mahogany furniture, Persian rug in
    deep reds and golds"
  - "Exterior street: grey cobblestones, brown brick buildings, overcast
    cool daylight"

Also note the overall lighting mood for day/night/interior scenes and any
consistent color temperature (warm golden afternoons, cool blue nights).

Be specific — "dusty rose" not "pink", "tawny orange-gold" not "yellow".
Return only the color guide as plain descriptive text, no markdown headers.
GEMINI_EOF

python3 "$SCRIPT_DIR/../video/4a-color-guide.py" "$VIDEO" \
    --api-key "$API_KEY" \
    --output "$COLOR_GUIDE" 2>&1 | while IFS= read -r line; do
    log_detail "$line"
done

if [[ -f "$COLOR_GUIDE" ]]; then
    show_gemini_response "Master Color Guide" 20 < "$COLOR_GUIDE"
fi
log_success "Color guide saved"

printf '\n'
log_step "▶" "Organizing clips into scene directories..."
SCENE_DIRS=()
for CLIP in "${CLIPS[@]}"; do
    CLIP_STEM="$(basename "$CLIP" .mp4)"
    SCENE_LABEL="$(echo "$CLIP_STEM" | grep -o 'Scene-[0-9]*$' || echo "$CLIP_STEM")"
    SCENE_DIR="$OUTPUT_DIR/$SCENE_LABEL"
    mkdir -p "$SCENE_DIR"
    mv "$CLIP" "$SCENE_DIR/clip.mp4"
    SCENE_DIRS+=("$SCENE_DIR")
    log_detail "$SCENE_LABEL/"
done
log_success "${#SCENE_DIRS[@]} scene directories ready"

printf '\n'
printf '  %b─── Phase 1 complete ──────────────────────────────────────────%b\n' "$FG_CYAN$DIM" "$RST"
sleep 1

# ═════════════════════════════════════════════════════════════════════════════
# PHASE 2: Parallel Scene Processing (Dashboard)
# ═════════════════════════════════════════════════════════════════════════════

NUM_SCENES=${#SCENE_DIRS[@]}

phase_header "2" "PARALLEL SCENE PROCESSING — $NUM_SCENES scenes" "$FG_MAGENTA"
printf '  %bLaunching workers... Dashboard will appear momentarily.%b\n\n' "$FG_GRAY" "$RST"
sleep 1

# Launch background workers
WORKER_PIDS=()
for i in $(seq 0 $((NUM_SCENES - 1))); do
    SCENE_DIR="${SCENE_DIRS[$i]}"
    if (( i == 0 )); then
        PREV="none"
    else
        PREV="${SCENE_DIRS[$((i - 1))]}"
    fi
    # Initialize stage
    printf 'pending' > "$SCENE_DIR/.stage"
    bash "$SCRIPT_DIR/_scene-worker.sh" "$SCENE_DIR" "$API_KEY" "$SCRIPT_DIR" "$PREV" &
    WORKER_PIDS+=($!)
done

# Dashboard rendering
COLS=2
if (( NUM_SCENES > 6 )); then COLS=3; fi
ROWS=$(( (NUM_SCENES + COLS - 1) / COLS ))

tput smcup
tput civis

DASH_START=$(date +%s)

render_dashboard() {
    local term_w term_h
    term_w=$(tput cols)
    term_h=$(tput lines)

    local box_w=$(( (term_w - (COLS + 1) * 2) / COLS ))
    if (( box_w < 30 )); then box_w=30; fi
    local inner_w=$(( box_w - 4 ))
    local box_h=8

    tput cup 0 0
    tput ed

    # Header
    local elapsed=$(( $(date +%s) - DASH_START ))
    local elapsed_m=$(( elapsed / 60 ))
    local elapsed_s=$(( elapsed % 60 ))
    local done_count=0
    local error_count=0
    for sd in "${SCENE_DIRS[@]}"; do
        local st
        st="$(cat "$sd/.stage" 2>/dev/null || echo "pending")"
        if [[ "$st" == "done" ]]; then (( done_count++ )); fi
        if [[ "$st" == "error" ]]; then (( error_count++ )); fi
    done

    printf '%b' "$FG_GOLD$BOLD"
    printf '  GCinema'
    printf '%b' "$RST$FG_GRAY"
    printf '  │  %s  │  Phase 2: Parallel Scene Processing  │  ' "$STEM"
    printf '%b%d%b/%d done' "$FG_BGREEN" "$done_count" "$FG_GRAY" "$NUM_SCENES"
    if (( error_count > 0 )); then
        printf '  %b%d errors%b' "$FG_RED" "$error_count" "$FG_GRAY"
    fi
    printf '  │  %02d:%02d elapsed' "$elapsed_m" "$elapsed_s"
    printf '%b\n' "$RST"

    local sep
    sep="$(repeat_char '─' "$term_w")"
    printf '%b%s%b\n' "$FG_GRAY$DIM" "$sep" "$RST"

    # Grid
    local sp
    sp="$(spin)"

    for row in $(seq 0 $((ROWS - 1))); do
        for line_offset in $(seq 0 $((box_h - 1))); do
            for col in $(seq 0 $((COLS - 1))); do
                local idx=$(( row * COLS + col ))
                if (( idx >= NUM_SCENES )); then
                    printf '%*s' "$((box_w + 2))" ""
                    continue
                fi

                local sd="${SCENE_DIRS[$idx]}"
                local label
                label="$(basename "$sd")"
                local stage
                stage="$(cat "$sd/.stage" 2>/dev/null || echo "pending")"
                local slabel
                slabel="$(stage_label "$stage")"
                local pct
                pct="$(stage_to_pct "$stage")"

                # Padding between columns
                if (( col > 0 )); then printf '  '; fi

                case $line_offset in
                    0)  # Top border with scene label and stage badge
                        local badge
                        badge=" $slabel "
                        local badge_len=${#badge}
                        local name_part="── $label "
                        local name_len=${#name_part}
                        local fill_len=$(( box_w - name_len - badge_len - 4 ))
                        if (( fill_len < 1 )); then fill_len=1; fi

                        printf '%b┌%s%b' "$FG_GRAY" "$name_part" "$RST"
                        printf '%b%s%b' "$FG_GRAY$DIM" "$(repeat_char '─' "$fill_len")" "$RST"
                        printf ' '
                        stage_color "$stage"
                        printf '%s' "$badge"
                        printf '%b' "$RST"
                        printf '%b ┐%b' "$FG_GRAY" "$RST"
                        ;;
                    1)  # Progress bar
                        printf '%b│%b ' "$FG_GRAY" "$RST"
                        if (( pct >= 0 )); then
                            local bar_w=$(( inner_w - 6 ))
                            if (( bar_w < 5 )); then bar_w=5; fi
                            local bar_str
                            bar_str="$(progress_bar "$pct" "$bar_w")"
                            if [[ "$stage" == "done" ]]; then
                                printf '%b%s%b' "$FG_BGREEN" "$bar_str" "$RST"
                            elif [[ "$stage" == "error" ]]; then
                                printf '%b%s%b' "$FG_RED" "$bar_str" "$RST"
                            else
                                printf '%b%s%b' "$FG_GOLD" "$bar_str" "$RST"
                            fi
                            printf '%*s' $(( inner_w - bar_w - 5 )) ""
                        else
                            printf '%b%s%b' "$FG_RED" "$(pad_right "FAILED" "$inner_w")" "$RST"
                        fi
                        printf ' %b│%b' "$FG_GRAY" "$RST"
                        ;;
                    2|3|4)  # Log lines
                        printf '%b│%b ' "$FG_GRAY" "$RST"
                        local log_line_idx=$(( line_offset - 2 ))
                        local log_line=""
                        if [[ -f "$sd/.worker.log" ]]; then
                            log_line="$(tail -3 "$sd/.worker.log" 2>/dev/null | sed -n "$((log_line_idx + 1))p" || echo "")"
                            log_line="${log_line#*] }"
                        fi
                        local trunc
                        trunc="$(truncate_str "$log_line" "$inner_w")"
                        printf '%b%s%b' "$FG_GRAY" "$(pad_right "$trunc" "$inner_w")" "$RST"
                        printf ' %b│%b' "$FG_GRAY" "$RST"
                        ;;
                    5)  # Spinner / status
                        printf '%b│%b ' "$FG_GRAY" "$RST"
                        if [[ "$stage" == "done" ]]; then
                            printf '%b%s%b' "$FG_BGREEN" "$(pad_right "✔ Complete" "$inner_w")" "$RST"
                        elif [[ "$stage" == "error" ]]; then
                            printf '%b%s%b' "$FG_RED" "$(pad_right "✘ Failed" "$inner_w")" "$RST"
                        else
                            printf '%b%s %s%b' "$FG_AMBER" "$sp" "$(pad_right "Working..." "$((inner_w - 2))")" "$RST"
                        fi
                        printf ' %b│%b' "$FG_GRAY" "$RST"
                        ;;
                    6)  # Bottom border
                        printf '%b└%s┘%b' "$FG_GRAY" "$(repeat_char '─' "$((box_w - 2))")" "$RST"
                        ;;
                    7)  # Gap
                        printf '%*s' "$box_w" ""
                        ;;
                esac
            done
            printf '\n'
        done
    done

    # Bottom status
    printf '\n'
    printf '  %bCtrl+C to abort%b' "$FG_GRAY$DIM" "$RST"
    printf '\n'
}

# Dashboard loop
while true; do
    render_dashboard
    sleep 0.6

    # Check if all workers are done
    all_done=true
    for sd in "${SCENE_DIRS[@]}"; do
        stage="$(cat "$sd/.stage" 2>/dev/null || echo "pending")"
        if [[ "$stage" != "done" && "$stage" != "error" ]]; then
            all_done=false
            break
        fi
    done
    if $all_done; then
        render_dashboard
        sleep 2
        break
    fi
done

tput rmcup
tput cnorm

# Check for errors
ERROR_SCENES=()
for sd in "${SCENE_DIRS[@]}"; do
    stage="$(cat "$sd/.stage" 2>/dev/null || echo "")"
    if [[ "$stage" == "error" ]]; then
        ERROR_SCENES+=("$(basename "$sd")")
    fi
done

if (( ${#ERROR_SCENES[@]} > 0 )); then
    printf '\n'
    log_error "The following scenes had errors: ${ERROR_SCENES[*]}"
    printf '  %bCheck .worker.log in each Scene directory for details.%b\n' "$FG_GRAY" "$RST"
    printf '\n'
fi

DONE_SCENES=0
for sd in "${SCENE_DIRS[@]}"; do
    [[ "$(cat "$sd/.stage" 2>/dev/null)" == "done" ]] && (( DONE_SCENES++ ))
done
log_success "Phase 2 complete — $DONE_SCENES/$NUM_SCENES scenes processed"
printf '\n'

# Show Gemini scene descriptions for each completed scene
if (( DONE_SCENES > 0 )); then
    printf '  %b◆ Gemini Scene Descriptions:%b\n' "$FG_MAGENTA$BOLD" "$RST"
    printf '\n'
    for sd in "${SCENE_DIRS[@]}"; do
        sl="$(basename "$sd")"
        stage="$(cat "$sd/.stage" 2>/dev/null || echo "")"
        if [[ "$stage" == "done" && -f "$sd/description.txt" ]]; then
            printf '  %b── %s%b\n' "$FG_MAGENTA" "$sl" "$RST"
            head -5 "$sd/description.txt" | while IFS= read -r dline; do
                [[ -z "$dline" ]] && continue
                printf '  %b  %s%b\n' "$FG_GRAY$ITALIC" \
                    "$(truncate_str "$dline" $(( $(tput cols 2>/dev/null || echo 90) - 6 )))" "$RST"
            done
            printf '\n'
        fi
    done
fi

sleep 1

WORKER_PIDS=()

# ═════════════════════════════════════════════════════════════════════════════
# PHASE 3: Audio Pipeline
# ═════════════════════════════════════════════════════════════════════════════

phase_header "3" "AUDIO PIPELINE — Generating soundtrack" "$FG_BLUE"

AUDIO_DIR="$PROJECT_DIR/audio"
WORK_DIR="$OUTPUT_DIR/audio"
mkdir -p "$WORK_DIR"

MUSIC_PROMPT="$WORK_DIR/music_prompt.txt"
AUDIO_EVENTS="$WORK_DIR/audio_events.json"
SCORE_WAV="$WORK_DIR/score.wav"
FOLEY_WAV="$WORK_DIR/foley.wav"
FINAL_MP3="$WORK_DIR/final_audio.mp3"

DURATION=$(ffprobe -v error -show_entries format=duration \
    -of default=noprint_wrappers=1:nokey=1 "$VIDEO" 2>/dev/null || echo "0")
DURATION_INT=$(python3 -c "import math; print(max(1, round($DURATION)))" 2>/dev/null || echo "30")

log_detail "Video duration: ${DURATION}s"
printf '\n'

# S1
log_step "♫" "S1 — Gemini: video analysis → music prompt + audio events"
if [[ -z "${GEMINI_API_KEY:-}" ]]; then
    log_error "GEMINI_API_KEY not found in .env — skipping audio"
else
    show_gemini_prompt "gemini-2.0-flash" "Silent Film Audio Design (2 passes)" <<'GEMINI_EOF'
Pass 1 — Character Identification:
  Identify every character who appears in this clip.
  Return a JSON array with: id, description, gender, role, approximate_age.

Pass 2 — Full Audio Soundscape:
  You are an expert silent-film sound designer restoring a classic film.
  INVENT the full soundscape AND dialogue as a 1920s restoration team would.

  Generate two things:
  1. "music_prompt" — 2-5 sentences describing the ideal background music
     (genre, tempo, instruments, mood arc across the clip)

  2. "audio_events" — 20+ chronological sound moments including:
     - SPEECH: invent real dialogue matching character expressions
       ("Watch out!", "Oh my goodness!", "Ha! Take that!", "Are you alright?")
       Never use "..." — always write actual words. Mark as high/medium confidence.
     - SFX: footsteps, impacts, ambience, object interactions, crowd reactions

  Return only raw JSON: { "music_prompt": "...", "audio_events": [...] }
GEMINI_EOF

    python3 "$AUDIO_DIR/S1-sound-gen-prompt.py" "$VIDEO" \
        --output-music "$MUSIC_PROMPT" \
        --output-lipsync "$AUDIO_EVENTS" \
        --api-key "$API_KEY" 2>&1 | while IFS= read -r line; do
        log_detail "$line"
    done

    if [[ -f "$MUSIC_PROMPT" ]]; then
        show_gemini_response "Music Composition Prompt" 10 < "$MUSIC_PROMPT"
    fi
    if [[ -f "$AUDIO_EVENTS" ]]; then
        show_audio_events_preview "$AUDIO_EVENTS" 12
    fi
    log_success "Music prompt and audio events generated"

    printf '\n'

    # S2
    log_step "♫" "S2 — Lyria: generating background music score"
    python3 "$AUDIO_DIR/S2-sound-gen-lyria.py" "$MUSIC_PROMPT" \
        --output "$SCORE_WAV" \
        --duration "$DURATION_INT" \
        --api-key "$API_KEY" 2>&1 | while IFS= read -r line; do
        log_detail "$line"
    done
    log_success "Background score generated"

    printf '\n'

    # S3
    if [[ -n "${ELEVENLABS_API_KEY:-}" ]]; then
        log_step "♫" "S3 — ElevenLabs: generating foley + vocals"
        python3 "$AUDIO_DIR/S3-vocal-gen.py" "$AUDIO_EVENTS" \
            --output "$FOLEY_WAV" \
            --duration "$DURATION" \
            --api-key "$ELEVENLABS_API_KEY" 2>&1 | while IFS= read -r line; do
            log_detail "$line"
        done
        log_success "Foley and vocals generated"
    else
        log_error "ELEVENLABS_API_KEY not set — skipping foley/vocals"
    fi

    printf '\n'

    # S4
    log_step "♫" "S4 — Mixing score + foley → final audio"
    if [[ -f "$SCORE_WAV" ]]; then
        MIXARGS=("$SCORE_WAV")
        if [[ -f "$FOLEY_WAV" ]]; then
            MIXARGS+=("$FOLEY_WAV")
        else
            MIXARGS+=("$SCORE_WAV")
        fi
        python3 "$AUDIO_DIR/S4-mix-audio.py" "${MIXARGS[@]}" \
            --duration "$DURATION" \
            --output "$FINAL_MP3" 2>&1 | while IFS= read -r line; do
            log_detail "$line"
        done
        log_success "Final audio: $FINAL_MP3"
    else
        log_error "Score not found — skipping mix"
    fi
fi

printf '\n'
printf '  %b─── Phase 3 complete ──────────────────────────────────────────%b\n' "$FG_BLUE$DIM" "$RST"
sleep 1

# ═════════════════════════════════════════════════════════════════════════════
# PHASE 4: Assembly
# ═════════════════════════════════════════════════════════════════════════════

phase_header "4" "ASSEMBLY — Piecing everything together" "$FG_YELLOW"

MATCHED_CLIPS=()
while IFS= read -r line; do
    MATCHED_CLIPS+=("$line")
done < <(find "$OUTPUT_DIR" -maxdepth 2 -name "frame0_colorized_generated_matched.mp4" | sort)

if [[ ${#MATCHED_CLIPS[@]} -eq 0 ]]; then
    log_error "No matched scene clips found. Cannot assemble."
else
    log_step "▶" "Concatenating ${#MATCHED_CLIPS[@]} scene clips..."

    CONCAT_LIST="$OUTPUT_DIR/concat_list.txt"
    : > "$CONCAT_LIST"
    for clip in "${MATCHED_CLIPS[@]}"; do
        echo "file '$clip'" >> "$CONCAT_LIST"
        log_detail "+ $(basename "$(dirname "$clip")")/$(basename "$clip")"
    done

    CONCAT_VIDEO="$OUTPUT_DIR/concat_no_audio.mp4"
    ffmpeg -y -f concat -safe 0 -i "$CONCAT_LIST" \
        -filter_complex "[0:v]setpts=PTS-STARTPTS,format=yuv420p,fps=24[v]" \
        -map "[v]" -c:v libx264 -preset fast -crf 18 -an -movflags +faststart "$CONCAT_VIDEO" 2>/dev/null
    log_success "Scenes concatenated"

    printf '\n'

    AUDIO_FILE="$OUTPUT_DIR/audio/final_audio.mp3"
    FINAL_VIDEO="$OUTPUT_DIR/final_colorized.mp4"

    if [[ -f "$AUDIO_FILE" ]]; then
        log_step "▶" "Muxing audio track..."
        ffmpeg -y \
            -i "$CONCAT_VIDEO" \
            -i "$AUDIO_FILE" \
            -c:v copy \
            -c:a aac \
            -b:a 192k \
            -shortest \
            "$FINAL_VIDEO" 2>/dev/null
        rm -f "$CONCAT_VIDEO"
        log_success "Final video with audio: $FINAL_VIDEO"
    else
        log_detail "No audio found — outputting video-only"
        mv "$CONCAT_VIDEO" "$FINAL_VIDEO"
        log_success "Final video: $FINAL_VIDEO"
    fi

    rm -f "$CONCAT_LIST"

fi

printf '\n'
printf '  %b─── Phase 4 complete ──────────────────────────────────────────%b\n' "$FG_YELLOW$DIM" "$RST"
sleep 1

# ═════════════════════════════════════════════════════════════════════════════
# PHASE 5: Complete
# ═════════════════════════════════════════════════════════════════════════════

TOTAL_ELAPSED=$(( $(date +%s) - PIPELINE_START ))
TOTAL_M=$(( TOTAL_ELAPSED / 60 ))
TOTAL_S=$(( TOTAL_ELAPSED % 60 ))

printf '\n'
printf '%b' "$FG_GOLD$BOLD"
printf '  ═══════════════════════════════════════════════════════════════\n'
printf '    PIPELINE COMPLETE\n'
printf '  ═══════════════════════════════════════════════════════════════\n'
printf '%b' "$RST"
printf '\n'
printf '  %bVideo:%b   %s\n' "$FG_CYAN" "$RST" "${FINAL_VIDEO:-N/A}"
printf '  %bScenes:%b  %d processed\n' "$FG_CYAN" "$RST" "$DONE_SCENES"
printf '  %bTime:%b    %02d:%02d\n' "$FG_CYAN" "$RST" "$TOTAL_M" "$TOTAL_S"

if [[ -f "${FINAL_VIDEO:-}" ]]; then
    FSIZE=$(du -h "$FINAL_VIDEO" 2>/dev/null | awk '{print $1}')
    printf '  %bSize:%b    %s\n' "$FG_CYAN" "$RST" "$FSIZE"
fi

printf '\n'

# Final menu
FINAL_OPTIONS=(
    "Open both videos (original + colorized)"
    "Quit"
)
number_select "What would you like to do?" "${FINAL_OPTIONS[@]}"

if (( SEL_RESULT == 0 )); then
    printf '\n'
    log_step "▶" "Opening videos in default player..."
    ORIGINAL_VIDEO="$PROJECT_DIR/input-videos/$STEM.mp4"
    if [[ -f "$ORIGINAL_VIDEO" ]]; then
        open "$ORIGINAL_VIDEO" 2>/dev/null || xdg-open "$ORIGINAL_VIDEO" 2>/dev/null || log_detail "Original: $ORIGINAL_VIDEO"
    fi
    if [[ -f "${FINAL_VIDEO:-}" ]]; then
        open "$FINAL_VIDEO" 2>/dev/null || xdg-open "$FINAL_VIDEO" 2>/dev/null || log_detail "Colorized: $FINAL_VIDEO"
    fi
    log_success "Videos opened"
else
    printf '\n'
    log_success "Done. Output at: $OUTPUT_DIR"
fi
printf '\n'
