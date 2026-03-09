# GCinema — AI-Powered Silent Film Colorization Pipeline

GCinema takes a black-and-white silent film and produces a fully colorized version with an AI-generated soundtrack. Run `./pipeline/run.sh` and the pipeline handles everything automatically.

---

## Pipeline Overview

```
Input: black-and-white .mp4
        │
        ├── Phase 1: Segmentation
        │     ├── Detect scene cuts  →  split into clips
        │     └── Generate master color guide
        │
        ├── Phase 2: Per-Scene Processing  (all scenes run in parallel)
        │     ├── Step 2: Gemini describes the scene in detail
        │     ├── Step 3: Extract first frame as keyframe image
        │     ├── Step 4: Colorize the keyframe (Gemini image generation)
        │     ├── Step 5: Generate a full colorized video clip (Veo / Kling / Wan)
        │     └── Step 6: Time-stretch clip to match original duration
        │
        ├── Phase 3: Audio Pipeline
        │     ├── S1: Gemini analyzes video → music prompt + timestamped audio events
        │     ├── S2: Gemini Lyria generates background music score
        │     ├── S3: ElevenLabs generates speech and sound effects at timestamps
        │     └── S4: Mix score + foley into final audio track
        │
        └── Phase 4: Assembly
              ├── Concatenate all colorized scene clips
              └── Mux final audio onto video  →  final_colorized.mp4
```

---

## Phase 0: Video Picker

The script presents an interactive menu listing all `.mp4` files in `input-videos/`. You pick which film to process. If a scene-cuts sidecar file (`<stem>.cuts.json`) already exists from a previous run, the menu shows how many scenes were detected.

---

## Phase 1: Segmentation

**Script:** `video/1-segment-gemini.py` + `video/4a-color-guide.py`

**1a — Scene cut detection**
The entire video is uploaded to Gemini (gemini-3.1-pro-preview). The model watches the film and returns a JSON list of every timestamp where a camera cut occurs — hard cuts, dialogue cuts, reaction shots, etc. Pans and zooms within the same shot are ignored. ffmpeg then splits the video at those timestamps into individual `clip.mp4` files, one per scene, organized into `Scene-1/`, `Scene-2/`, ... directories.

Fallback: if Gemini segmentation fails, PyMovieDB scene-change detection is used; if that also fails, fixed-interval timestamps are used.

<img width="1512" height="977" alt="Segmentation screenshot" src="https://github.com/user-attachments/assets/aa31bdd9-4462-4149-935f-fc7370e1fa32" />

**1b — Master color guide**
The full video is sent to Gemini again with a prompt asking for a detailed color palette for every recurring character, animal, object, and environment in the film. Examples: "Main character: charcoal grey pinstripe suit, burgundy tie, olive complexion", "Exterior street: grey cobblestones, overcast cool daylight". This guide is saved to `color_guide.txt` and referenced in later colorization steps to keep colors consistent across scenes.

---

## Phase 2: Parallel Scene Processing

Each scene is processed by a background worker (`pipeline/_scene-worker.sh`). All scenes run in parallel and their progress is shown in a live dashboard. Within each scene the steps run sequentially:

**Step 2 — Scene reasoning** (`video/2-gemini-video-reason.py`)
The scene clip is uploaded to Gemini (gemini-3.1-pro-preview). The model writes a 400+ word detailed description covering every action, character movement, emotion, body language, and environment — written in flowing prose so that a video generation AI can recreate it. Saved as `description.txt`.

**Step 3 — Keyframe extraction** (`video/3-extract-key-frame.py`)
ffmpeg pulls the very first frame of the clip as a PNG image (`frame0.png`). This single frame becomes the visual seed for colorization and video generation.

**Step 4 — Keyframe colorization** (`video/4-colorize-keyframe.py`)
The black-and-white `frame0.png` is sent to Gemini's image generation model (gemini-3.1-flash-image-preview). The model colorizes it with natural, realistic colors. For every scene after the first, the previous scene's already-colorized frame is passed as a reference image, ensuring color consistency across scenes (same skin tones, clothing colors, and environment palette). Saved as `frame0_colorized.jpg`.

**Step 5 — Video generation** (`video/5-video-gen.py`)
The colorized keyframe + scene description are fed into a video generation model to produce a full colorized clip. Three backends are tried in order:
- **Veo 3.1** (Google) — highest quality, primary backend
- **Kling v3 Pro** (fal.ai) — fallback if Veo's content filter blocks the clip
- **Wan 2.2 Turbo** (fal.ai) — final fallback, cheapest and fastest

The model is instructed to produce silent visuals only (audio is handled separately). Output: `frame0_colorized_generated.mp4`.

**Step 6 — Duration matching** (`video/6-match-video-length.py`)
AI-generated video clips have a fixed duration (e.g. 6s from Veo) that rarely matches the original scene length. ffmpeg's `setpts` filter time-stretches or compresses the generated clip to exactly match the original clip's duration. Output: `frame0_colorized_generated_matched.mp4`.

---

## Phase 3: Audio Pipeline

<img width="1512" height="843" alt="Audio pipeline screenshot" src="https://github.com/user-attachments/assets/90e467d1-db18-4906-a0d3-f0a4535ad017" />

**S1 — Video analysis** (`audio/S1-sound-gen-prompt.py`)
The full video is uploaded to Gemini (gemini-2.0-flash) for a two-pass analysis:
- **Pass 1:** Identifies every character (name/id, appearance, gender, role, age).
- **Pass 2:** Acts as a 1920s sound restoration team — invents the complete soundscape: a music prompt describing the ideal background score, plus 20+ timestamped audio events including invented dialogue ("Watch out!", "Are you alright?") and sound effects (footsteps, impacts, crowd noise, ambience).

Outputs: `music_prompt.txt` and `audio_events.json`.

**S2 — Music generation** (`audio/S2-sound-gen-lyria.py`)
The music prompt from S1 is fed into Gemini Lyria RealTime (`lyria-realtime-exp`), a generative music model. It produces a background score WAV file sized to the full video duration. Output: `score.wav`.

**S3 — Speech and foley** (`audio/S3-vocal-gen.py`)
Each timestamped audio event from S1 is sent to ElevenLabs:
- **Speech events** → ElevenLabs TTS synthesizes the invented dialogue using a period-appropriate voice.
- **SFX events** → ElevenLabs Sound Effects generation creates the described sound (e.g. "wooden floorboard creak").

All clips are placed at their timestamps and mixed into a single foley track. Output: `foley.wav`.

**S4 — Audio mix** (`audio/S4-mix-audio.py`)
The background score (`score.wav`) and foley/vocals (`foley.wav`) are mixed together and encoded as a final MP3. Output: `final_audio.mp3`.

---

## Phase 4: Assembly

All per-scene `frame0_colorized_generated_matched.mp4` files are sorted and concatenated into a single video using ffmpeg. The `final_audio.mp3` is then muxed onto the video track. Output: `pipeline/output/<stem>/final_colorized.mp4`.

---

## Requirements

- Python 3.10+
- ffmpeg
- `GEMINI_API_KEY` in `pipeline/.env` (required — used for segmentation, reasoning, colorization, video generation, and audio analysis)
- `FAL_KEY` in `pipeline/.env` (optional — enables Kling/Wan fallback for video generation)
- `ELEVENLABS_API_KEY` in `pipeline/.env` (optional — enables speech and foley generation)

```
# pipeline/.env
GEMINI_API_KEY=your_key_here
FAL_KEY=your_key_here
ELEVENLABS_API_KEY=your_key_here
```

```
pip install google-genai pillow elevenlabs pydub fal-client
```

---

## Running

```bash
cd pipeline
./run.sh
```

Output files land in `pipeline/output/<video-stem>/`.

**Video backends:** `main` uses Veo → Kling → Wan. For xAI Grok Imagine Video instead, use the `grok-video` branch.
