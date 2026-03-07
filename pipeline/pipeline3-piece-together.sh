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
#   4. Launches a side-by-side localhost viewer (original vs colorized)
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

# ── Step 1: Concatenate scene clips ───────────────────────────────────────────
echo ""
echo "=== Concatenating ${#MATCHED_CLIPS[@]} scene clips ==="
CONCAT_VIDEO="$OUTPUT_DIR/concat_no_audio.mp4"
ffmpeg -y -f concat -safe 0 -i "$CONCAT_LIST" -c:v copy -an "$CONCAT_VIDEO" 2>&1 \
    | grep -E "(Output|Error|frame=|fps=|time=)" || true
echo "Concat done: $CONCAT_VIDEO"

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

# ── Step 3: Write viewer HTML ─────────────────────────────────────────────────
VIEWER_HTML="$OUTPUT_DIR/viewer.html"

ORIGINAL_VIDEO_REL=""
if [[ -n "$ORIGINAL_VIDEO" ]]; then
    ORIGINAL_VIDEO_REL="/$(python3 -c "import os; print(os.path.relpath('$ORIGINAL_VIDEO', '$PROJECT_DIR'))")"
fi
FINAL_VIDEO_REL="/$(python3 -c "import os; print(os.path.relpath('$FINAL_VIDEO', '$PROJECT_DIR'))")"

cat > "$VIEWER_HTML" << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>GCinema — __STEM__</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Crimson+Pro:ital,wght@0,300;0,400;1,300&display=swap" rel="stylesheet" />
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --bg:     #080808;
      --panel:  #111111;
      --accent: #c8a96e;
      --gold2:  #e8c98a;
      --text:   #e0d4c0;
      --dim:    #555;
      --border: #1e1e1e;
      --green:  #5ec87a;
    }

    html, body {
      height: 100%;
      background: var(--bg);
      color: var(--text);
      font-family: 'Crimson Pro', Georgia, serif;
    }

    body {
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: stretch;
    }

    /* ── Film-strip header ── */
    .filmstrip {
      height: 28px;
      background: #0d0d0d;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      padding: 0 8px;
      gap: 6px;
      flex-shrink: 0;
    }
    .hole {
      width: 14px;
      height: 10px;
      background: var(--bg);
      border-radius: 2px;
      border: 1px solid #2a2a2a;
    }

    header {
      padding: 18px 36px 14px;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: baseline;
      gap: 14px;
      flex-shrink: 0;
    }
    header h1 {
      font-family: 'Cinzel', serif;
      font-size: 1.45rem;
      font-weight: 700;
      letter-spacing: 0.14em;
      color: var(--accent);
    }
    header .stem {
      font-size: 1rem;
      color: var(--dim);
      letter-spacing: 0.05em;
    }
    header .badge {
      margin-left: auto;
      font-size: 0.7rem;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      color: var(--dim);
      border: 1px solid var(--border);
      padding: 3px 10px;
      border-radius: 2px;
    }

    /* ── Video area ── */
    .videos {
      display: flex;
      flex: 1;
      padding: 20px 36px 0;
      gap: 0;
      min-height: 0;
    }

    .pane {
      flex: 1;
      display: flex;
      flex-direction: column;
      min-width: 0;
    }
    .pane + .pane {
      border-left: 1px solid var(--border);
      padding-left: 24px;
      margin-left: 24px;
    }

    .pane-label {
      font-family: 'Cinzel', serif;
      font-size: 0.7rem;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      color: var(--dim);
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      gap: 7px;
    }
    .pane-label .dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--accent);
      flex-shrink: 0;
    }

    video {
      width: 100%;
      aspect-ratio: 16/9;
      object-fit: contain;
      background: #000;
      display: block;
      border: 1px solid var(--border);
    }

    .pane-missing {
      width: 100%;
      aspect-ratio: 16/9;
      background: #0a0a0a;
      border: 1px dashed var(--border);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      color: var(--dim);
      gap: 8px;
    }
    .pane-missing .icon { font-size: 2rem; opacity: 0.3; }
    .pane-missing .msg { font-size: 0.85rem; letter-spacing: 0.06em; }

    /* ── Controls ── */
    .controls {
      padding: 16px 36px 28px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      flex-shrink: 0;
    }

    /* Progress bar */
    .progress-wrap {
      position: relative;
      height: 6px;
      background: var(--border);
      border-radius: 3px;
      cursor: pointer;
    }
    .progress-fill {
      position: absolute;
      left: 0; top: 0; bottom: 0;
      background: linear-gradient(90deg, var(--accent), var(--gold2));
      border-radius: 3px;
      pointer-events: none;
      width: 0%;
    }
    #seekBar {
      position: absolute;
      inset: -6px 0;
      width: 100%;
      opacity: 0;
      cursor: pointer;
    }

    /* Thumb visible range input */
    input[type=range] {
      -webkit-appearance: none;
      appearance: none;
      background: transparent;
      outline: none;
      cursor: pointer;
    }
    input[type=range]::-webkit-slider-runnable-track {
      background: transparent;
      height: 6px;
    }
    input[type=range]::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: var(--accent);
      margin-top: -4px;
    }

    .button-row {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    button {
      background: transparent;
      border: 1px solid var(--accent);
      color: var(--accent);
      font-family: 'Cinzel', serif;
      font-size: 0.7rem;
      letter-spacing: 0.18em;
      padding: 7px 18px;
      cursor: pointer;
      transition: background 0.12s, color 0.12s;
      flex-shrink: 0;
    }
    button:hover {
      background: var(--accent);
      color: var(--bg);
    }

    #timeDisplay {
      font-size: 0.82rem;
      color: var(--dim);
      font-variant-numeric: tabular-nums;
      letter-spacing: 0.06em;
      min-width: 88px;
    }

    .status {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 0.78rem;
      color: var(--dim);
      letter-spacing: 0.06em;
    }
    #statusDot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--dim);
      transition: background 0.2s;
      flex-shrink: 0;
    }
    #statusDot.playing { background: var(--green); box-shadow: 0 0 6px var(--green); }

    .vol-group {
      margin-left: auto;
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--dim);
      font-size: 0.75rem;
      letter-spacing: 0.1em;
    }
    #volSlider { width: 80px; }
  </style>
</head>
<body>

  <div class="filmstrip">
    <div class="hole"></div><div class="hole"></div><div class="hole"></div>
    <div class="hole"></div><div class="hole"></div><div class="hole"></div>
    <div class="hole"></div><div class="hole"></div><div class="hole"></div>
    <div class="hole"></div><div class="hole"></div><div class="hole"></div>
    <div class="hole"></div><div class="hole"></div><div class="hole"></div>
    <div class="hole"></div><div class="hole"></div><div class="hole"></div>
    <div class="hole"></div><div class="hole"></div>
  </div>

  <header>
    <h1>GCinema</h1>
    <span class="stem">__STEM__</span>
    <span class="badge">Side-by-Side Comparison</span>
  </header>

  <div class="videos">

    <div class="pane" id="paneA">
      <div class="pane-label"><span class="dot"></span> Original (B&amp;W)</div>
      <div id="originalContainer"></div>
    </div>

    <div class="pane">
      <div class="pane-label"><span class="dot"></span> Colorized</div>
      <video id="vidB" preload="metadata">
        <source src="__FINAL_PATH__" type="video/mp4" />
      </video>
    </div>

  </div>

  <div class="controls">
    <div class="progress-wrap">
      <div class="progress-fill" id="progressFill"></div>
      <input type="range" id="seekBar" min="0" step="0.001" value="0" />
    </div>

    <div class="button-row">
      <button id="playBtn">&#9654; PLAY</button>
      <button id="restartBtn">&#8635; RESTART</button>
      <span id="timeDisplay">0:00 / 0:00</span>
      <div class="status">
        <div id="statusDot"></div>
        <span id="statusText">Paused</span>
      </div>
      <div class="vol-group">
        <span>VOL</span>
        <input type="range" id="volSlider" min="0" max="1" step="0.01" value="1" />
      </div>
    </div>
  </div>

  <script>
    const ORIGINAL_PATH = '__ORIGINAL_PATH__';
    const FINAL_PATH    = '__FINAL_PATH__';

    // ── Build original pane ──────────────────────────────────────────────────
    const originalContainer = document.getElementById('originalContainer');
    if (ORIGINAL_PATH && ORIGINAL_PATH !== '__NOT_FOUND__') {
      const v = document.createElement('video');
      v.id = 'vidA';
      v.preload = 'metadata';
      v.muted = true; // original has no audio; colorized is the primary audio source
      const s = document.createElement('source');
      s.src = ORIGINAL_PATH;
      s.type = 'video/mp4';
      v.appendChild(s);
      originalContainer.appendChild(v);
    } else {
      originalContainer.innerHTML = `
        <div class="pane-missing">
          <div class="icon">&#127909;</div>
          <div class="msg">Original video not found</div>
          <div class="msg" style="font-size:0.75rem;margin-top:4px;opacity:.6;">Place it at input-videos/__STEM__.mp4</div>
        </div>`;
    }

    // ── Refs ─────────────────────────────────────────────────────────────────
    const vidB       = document.getElementById('vidB');
    const vidA       = document.getElementById('vidA'); // may be null
    const playBtn    = document.getElementById('playBtn');
    const restartBtn = document.getElementById('restartBtn');
    const seekBar    = document.getElementById('seekBar');
    const progressFill = document.getElementById('progressFill');
    const timeDisplay = document.getElementById('timeDisplay');
    const volSlider  = document.getElementById('volSlider');
    const statusDot  = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');

    // Primary = colorized (B) — it has audio; secondary = original (A)
    const primary   = vidB;
    const secondary = vidA;

    let isSeeking = false;
    let syncLock  = false;

    function fmt(s) {
      if (!isFinite(s)) return '0:00';
      const m  = Math.floor(s / 60);
      const ss = Math.floor(s % 60).toString().padStart(2, '0');
      return `${m}:${ss}`;
    }

    function setStatus(playing) {
      if (playing) {
        statusDot.className = 'playing';
        statusText.textContent = 'Playing';
        playBtn.innerHTML = '&#9646;&#9646; PAUSE';
      } else {
        statusDot.className = '';
        statusText.textContent = 'Paused';
        playBtn.innerHTML = '&#9654; PLAY';
      }
    }

    function syncSecondary(t) {
      if (!secondary) return;
      if (Math.abs(secondary.currentTime - t) > 0.3) {
        secondary.currentTime = t;
      }
    }

    // ── Primary events ───────────────────────────────────────────────────────
    primary.addEventListener('loadedmetadata', () => {
      seekBar.max = primary.duration;
      seekBar.step = 0.001;
      timeDisplay.textContent = `0:00 / ${fmt(primary.duration)}`;
    });

    primary.addEventListener('timeupdate', () => {
      if (isSeeking) return;
      const t = primary.currentTime;
      const d = primary.duration || 0;
      seekBar.value = t;
      progressFill.style.width = d ? `${(t / d) * 100}%` : '0%';
      timeDisplay.textContent = `${fmt(t)} / ${fmt(d)}`;
      syncSecondary(t);
    });

    primary.addEventListener('play', () => {
      if (!syncLock && secondary) {
        syncLock = true;
        secondary.play().catch(() => {});
        syncLock = false;
      }
      setStatus(true);
    });

    primary.addEventListener('pause', () => {
      if (!syncLock && secondary) {
        syncLock = true;
        secondary.pause();
        syncLock = false;
      }
      setStatus(false);
    });

    primary.addEventListener('seeking', () => {
      if (secondary) secondary.currentTime = primary.currentTime;
    });

    primary.addEventListener('ended', () => setStatus(false));

    // ── Secondary events (keep them in sync if user clicks secondary) ────────
    if (secondary) {
      secondary.addEventListener('play', () => {
        if (primary.paused && !syncLock) {
          syncLock = true;
          primary.play().catch(() => {});
          syncLock = false;
        }
      });
      secondary.addEventListener('pause', () => {
        if (!primary.paused && !syncLock) {
          syncLock = true;
          primary.pause();
          syncLock = false;
        }
      });
      secondary.addEventListener('seeking', () => {
        primary.currentTime = secondary.currentTime;
      });
    }

    // ── Controls ─────────────────────────────────────────────────────────────
    playBtn.addEventListener('click', () => {
      if (primary.paused) primary.play().catch(() => {});
      else                primary.pause();
    });

    restartBtn.addEventListener('click', () => {
      primary.currentTime = 0;
      if (secondary) secondary.currentTime = 0;
      primary.play().catch(() => {});
    });

    seekBar.addEventListener('mousedown', () => { isSeeking = true; });
    seekBar.addEventListener('touchstart', () => { isSeeking = true; }, { passive: true });

    seekBar.addEventListener('input', () => {
      const t = parseFloat(seekBar.value);
      primary.currentTime = t;
      if (secondary) secondary.currentTime = t;
      const d = primary.duration || 1;
      progressFill.style.width = `${(t / d) * 100}%`;
    });

    seekBar.addEventListener('mouseup', () => { isSeeking = false; });
    seekBar.addEventListener('touchend', () => { isSeeking = false; });

    volSlider.addEventListener('input', () => {
      primary.volume = parseFloat(volSlider.value);
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT') return;
      if (e.code === 'Space') {
        e.preventDefault();
        if (primary.paused) primary.play().catch(() => {});
        else                primary.pause();
      } else if (e.code === 'ArrowLeft') {
        primary.currentTime = Math.max(0, primary.currentTime - 5);
      } else if (e.code === 'ArrowRight') {
        primary.currentTime = Math.min(primary.duration || 0, primary.currentTime + 5);
      }
    });
  </script>

</body>
</html>
HTMLEOF

# ── Replace placeholders ──────────────────────────────────────────────────────
ORIG_PATH_PLACEHOLDER="${ORIGINAL_VIDEO_REL:-__NOT_FOUND__}"
sed -i '' \
    -e "s|__STEM__|${STEM}|g" \
    -e "s|__ORIGINAL_PATH__|${ORIG_PATH_PLACEHOLDER}|g" \
    -e "s|__FINAL_PATH__|${FINAL_VIDEO_REL}|g" \
    "$VIEWER_HTML"

echo ""
echo "=== Viewer written: $VIEWER_HTML ==="

# ── Step 4: Launch HTTP server + open browser ─────────────────────────────────
PORT=8765
VIEWER_REL="$(python3 -c "import os; print(os.path.relpath('$VIEWER_HTML', '$PROJECT_DIR'))")"

# Kill any stale process on our port
lsof -ti "tcp:$PORT" | xargs kill -9 2>/dev/null || true
sleep 0.3

echo ""
echo "=== Starting viewer on http://localhost:${PORT} ==="
echo "    Serving from: $PROJECT_DIR"
echo "    Viewer page:  http://localhost:${PORT}/${VIEWER_REL}"
echo ""
echo "Controls:  Space = play/pause   ←/→ = seek ±5s   Ctrl+C = quit"
echo ""

cd "$PROJECT_DIR"
python3 -m http.server "$PORT" &
SERVER_PID=$!

# Give server a moment to start
sleep 0.5

VIEWER_URL="http://localhost:${PORT}/${VIEWER_REL}"
open "$VIEWER_URL" 2>/dev/null \
    || xdg-open "$VIEWER_URL" 2>/dev/null \
    || echo "Open in your browser: $VIEWER_URL"

# Trap Ctrl+C to cleanly shut down the server
trap 'echo ""; echo "Shutting down server (PID $SERVER_PID)..."; kill "$SERVER_PID" 2>/dev/null; exit 0' INT TERM

echo "Server running (PID $SERVER_PID). Press Ctrl+C to stop."
wait "$SERVER_PID"
