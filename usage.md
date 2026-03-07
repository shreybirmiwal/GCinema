# color-film pipeline

Colorizes black-and-white YouTube videos by scene.

## Setup

```bash
pip install -r requirements.txt
# Also requires: ffmpeg, Node.js
```

## Run (full pipeline)

```bash
./run-pipeline.sh <GEMINI_API_KEY> <YOUTUBE_URL>
```

Downloads the video, splits it into scenes, then for each scene: generates an AI description, extracts the first frame, and colorizes it (each scene uses the previous scene's colorized frame as a color reference for consistency).

## Run steps individually

```bash
# 1. Download (video-only, no audio)
python3 0-downloader.py "https://youtube.com/watch?v=..." [--cookies-from-browser safari]

# 2. Segment into scenes
python3 1-segment.py video.mp4

# 3. Describe a scene with Gemini
python3 2-gemini-video-reason.py clip.mp4 --api-key KEY --output desc.txt

# 4. Extract first frame
python3 3-extract-key-frame.py clip.mp4

# 5. Colorize frame (optionally pass a reference for color consistency)
python3 4-colorize-keyframe.py frame.png --api-key KEY [--reference prev_colorized.jpg]
```

## Outputs (per scene clip)

| File | Description |
|------|-------------|
| `<clip>_description.txt` | AI scene description |
| `<clip>_frame0.png` | Extracted keyframe |
| `<clip>_frame0_colorized.jpg` | Colorized keyframe |
