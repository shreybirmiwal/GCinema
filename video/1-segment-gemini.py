#!/usr/bin/env python3
"""
Segment a video into clips using Gemini to detect camera cuts / scene changes.

Instead of pixel-diff heuristics, this uploads the full video to the Gemini
Files API and asks the model to identify every moment the camera physically
cuts to a new shot — including rapid back-and-forth dialogue cuts where the
camera alternates between speakers multiple times.

Gemini returns a JSON list of cut timestamps (in seconds); we then use FFmpeg
to split the video at those points.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from google import genai

SCENE_DETECTION_PROMPT = """
Watch this video carefully and identify every single moment where the camera
cuts to a different shot or angle. This includes:

- Hard cuts between completely different scenes or locations
- Back-and-forth dialogue cuts where the camera alternates between two (or more)
  speakers — even if they happen very rapidly, each individual cut counts
- Reaction shot cuts (e.g. cut away to a listener, then back to the speaker)
- Any other camera angle change or shot change

Do NOT mark:
- Pans, tilts, or zooms within the same continuous shot
- Object or character movement within a single shot

Return ONLY a JSON object in this exact format, with no extra commentary: We want only static scenes
{
  "cuts": [4.2, 9.7, 14.1, 19.8]
}

Where each number is the timestamp in seconds where a new shot begins.
The first shot always starts at 0.0, so do NOT include 0.0 in the list.
If there are no cuts at all, return: {"cuts": []}
"""


def upload_video(client: genai.Client, path: Path):
    print(f"Uploading {path} ...")
    video_file = client.files.upload(file=str(path))

    while video_file.state.name == "PROCESSING":
        print("  Waiting for Gemini to process video ...", end="\r", flush=True)
        time.sleep(5)
        video_file = client.files.get(name=video_file.name)

    if video_file.state.name != "ACTIVE":
        raise RuntimeError(f"File processing failed with state: {video_file.state.name}")

    print(f"\nUpload complete: {video_file.uri}")
    return video_file


def get_cut_timestamps(client: genai.Client, video_file, model_name: str) -> list[float]:
    print(f"Asking {model_name} to detect scene cuts ...")
    response = client.models.generate_content(
        model=model_name,
        contents=[video_file, SCENE_DETECTION_PROMPT],
    )
    raw = response.text.strip()

    # Strip markdown code fences if present
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        data = json.loads(raw)
        cuts = [float(t) for t in data["cuts"]]
    except Exception as exc:
        raise ValueError(
            f"Could not parse Gemini response as JSON.\n"
            f"Raw response:\n{response.text}\n"
            f"Parse error: {exc}"
        )

    # Remove 0.0 just in case the model included it, and sort
    cuts = sorted(t for t in cuts if t > 0.0)
    return cuts


def get_video_duration(input_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def split_video(input_path: Path, cuts: list[float], output_dir: Path, show_progress: bool):
    duration = get_video_duration(input_path)
    boundaries = [0.0] + cuts + [duration]
    video_name = input_path.stem
    created = []

    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1]
        clip_duration = end - start
        out_file = output_dir / f"{video_name}-Scene-{i + 1:03d}.mp4"

        cmd = [
            "ffmpeg",
            "-ss", str(start),
            "-i", str(input_path),
            "-t", str(clip_duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-an",
            "-y",
            str(out_file),
        ]
        if not show_progress:
            cmd += ["-loglevel", "error"]

        print(f"  Clip {i + 1:3d}: {start:.2f}s - {end:.2f}s  ({clip_duration:.1f}s)  → {out_file.name}")
        subprocess.run(cmd, check=True)
        created.append(out_file)

    return created


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Segment a video at camera cuts detected by Gemini."
    )
    parser.add_argument("input", type=Path, help="Path to input MP4 video")
    parser.add_argument(
        "--output-dir", "-o", type=Path, default=None,
        help="Directory for output clips (default: same as input)",
    )
    parser.add_argument(
        "--model", default="gemini-3.1-pro-preview",
        help="Gemini model to use (default: gemini-3.1-pro-preview)",
    )
    parser.add_argument(
        "--api-key", default=None,
        help="Google AI API key (defaults to GEMINI_API_KEY env var)",
    )
    parser.add_argument(
        "--no-split", action="store_true",
        help="Only detect and print timestamps, do not split the video",
    )
    parser.add_argument(
        "--show-progress", action="store_true",
        help="Show FFmpeg output during splitting",
    )
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: No API key. Set GEMINI_API_KEY or pass --api-key.", file=sys.stderr)
        return 1

    input_path = args.input.resolve()
    if not input_path.exists() or not input_path.is_file():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        return 1

    output_dir = args.output_dir.resolve() if args.output_dir else input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Check for hardcoded sidecar cuts file (skips Gemini upload)
    sidecar = input_path.with_suffix(".cuts.json")
    if sidecar.exists():
        print(f"Found sidecar cuts file: {sidecar} — skipping Gemini.")
        with open(sidecar) as f:
            data = json.load(f)
        cuts = sorted(float(t) for t in data["cuts"] if float(t) > 0.0)
    else:
        client = genai.Client(api_key=api_key)
        try:
            video_file = upload_video(client, input_path)
            cuts = get_cut_timestamps(client, video_file, args.model)
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    num_scenes = len(cuts) + 1
    print(f"\nDetected {len(cuts)} cut(s) → {num_scenes} scene(s):")
    all_boundaries = [0.0] + cuts
    for i, t in enumerate(all_boundaries):
        end = cuts[i] if i < len(cuts) else "end"
        print(f"  Scene {i + 1:3d} starts at {t:.2f}s")

    if args.no_split:
        return 0

    print(f"\nSplitting video → {output_dir}")
    try:
        created = split_video(input_path, cuts, output_dir, args.show_progress)
    except subprocess.CalledProcessError as exc:
        print(f"FFmpeg error: {exc}", file=sys.stderr)
        return 1

    print(f"\nDone. Created {len(created)} clip(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
