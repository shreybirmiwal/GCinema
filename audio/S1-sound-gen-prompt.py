#!/usr/bin/env python3
"""
Send a video clip to Gemini and generate:
  1. A music/audio composition prompt describing what the soundtrack would likely sound like.
  2. A unified list of timestamped audio events: vocal sounds (speech/exclamations) AND
     sound effects (foley, ambience, impacts, etc.) — feed into S3-vocal-gen.py.

Outputs:
  --output-music    plain-text music/audio prompt  (feed into S2-sound-gen-lyria.py)
  --output-lipsync  JSON array of all timestamped audio events (speech + sfx)  (feed into S3)
  --output          combined JSON with both fields (legacy / default when no flags given)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from google import genai

SYSTEM_PROMPT = """\
You are an expert silent-film sound designer analyzing a video clip to recreate its full
soundscape. The clip has no audio — your job is to infer every sound that would realistically
accompany what you see on screen.

Analyze the video carefully and return a JSON object with exactly two keys:

1. "music_prompt": A detailed text prompt (2-5 sentences) describing the ideal background music or
   audio composition for this clip. Include:
   - Genre / style (e.g. orchestral, jazz, ragtime, suspense, comedic)
   - Tempo and energy level
   - Key instruments
   - Mood and emotional arc across the clip

2. "audio_events": A chronologically-sorted list of every discrete sound moment in the clip.
   Include BOTH character vocal sounds AND environmental/foley sound effects.
   Each object must have:
   - "timestamp_sec": time in seconds (float) from the start of the clip
   - "duration_sec": estimated duration of the sound in seconds (float)
   - "type": either "speech" (character vocal) or "sfx" (sound effect / foley)
   - For type "speech":
       - "character": brief description (e.g. "man in hat", "woman on left")
       - "utterance": most likely word(s) or exclamation (e.g. "Help!", "Ouch!", "Ha ha ha!")
       - "confidence": "high", "medium", or "low" based on lip movement clarity
   - For type "sfx":
       - "description": concise plain-English description of the sound suitable for a sound
         effects generator (e.g. "wooden floorboard creak", "door slam", "glass shattering",
         "horse hooves on cobblestone", "crowd gasp", "cartoon boing", "ticking clock")
       - "confidence": "high", "medium", or "low"

   Be thorough — include footsteps, impacts, ambient sounds, object interactions, reactions,
   doors, vehicles, weather, crowd noise, etc. A good sound design pass has many events.

Return ONLY the raw JSON object with no markdown fencing or extra commentary.
"""


def upload_video(path: Path, client: genai.Client):
    print(f"Uploading {path} ...")
    video_file = client.files.upload(file=str(path))

    while video_file.state.name == "PROCESSING":
        print("  Waiting for Gemini to process video ...", end="\r")
        time.sleep(5)
        video_file = client.files.get(name=video_file.name)

    if video_file.state.name != "ACTIVE":
        raise RuntimeError(f"File processing failed with state: {video_file.state.name}")

    print(f"\nUpload complete: {video_file.uri}")
    return video_file


def analyze_video(video_file, client: genai.Client, model_name: str) -> dict:
    response = client.models.generate_content(
        model=model_name,
        contents=[video_file, SYSTEM_PROMPT],
    )
    raw = response.text.strip()

    # Strip markdown fences if the model added them anyway
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    return json.loads(raw)


def pretty_print(data: dict) -> None:
    print("\n=== MUSIC / AUDIO COMPOSITION PROMPT ===\n")
    print(data.get("music_prompt", "(none)"))

    print("\n=== AUDIO EVENTS (speech + sfx) ===\n")
    events = data.get("audio_events", [])
    if not events:
        print("No audio events detected.")
        return

    for e in events:
        ts = e.get("timestamp_sec", 0)
        dur = e.get("duration_sec", 0)
        kind = e.get("type", "?")
        conf = e.get("confidence", "")
        if kind == "speech":
            char = e.get("character", "unknown")
            utt = e.get("utterance", "")
            print(f"  [{ts:>6.2f}s +{dur:.1f}s]  SPEECH  {char:<22}  \"{utt}\"  ({conf})")
        else:
            desc = e.get("description", "")
            print(f"  [{ts:>6.2f}s +{dur:.1f}s]  SFX     {desc}  ({conf})")


def write_outputs(data: dict, output_music: Path | None, output_lipsync: Path | None, output: Path | None) -> None:
    """Write results to the requested output paths."""
    if output_music:
        output_music.write_text(data.get("music_prompt", ""), encoding="utf-8")
        print(f"Music prompt written to:  {output_music}")

    if output_lipsync:
        output_lipsync.write_text(
            json.dumps(data.get("audio_events", []), indent=2), encoding="utf-8"
        )
        print(f"Audio events JSON written to: {output_lipsync}")

    if output:
        output.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"Combined JSON written to: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a music composition prompt and lip-sync transcript from a video clip."
    )
    parser.add_argument("input", type=Path, help="Path to input video file (e.g. MP4)")
    parser.add_argument(
        "--output-music", "-om", type=Path, default=None, metavar="PATH",
        help="Write the music/audio composition prompt as plain text to this file",
    )
    parser.add_argument(
        "--output-lipsync", "-ol", type=Path, default=None, metavar="PATH",
        help="Write the timestamped lip-sync array as JSON to this file",
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Write the full combined JSON (music_prompt + lip_sync) to this file",
    )
    parser.add_argument(
        "--model", default="gemini-2.0-flash",
        help="Gemini model to use (default: gemini-2.0-flash)",
    )
    parser.add_argument(
        "--api-key", default=None,
        help="Google AI API key (defaults to GEMINI_API_KEY env var)",
    )
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: No API key provided. Set GEMINI_API_KEY or pass --api-key.", file=sys.stderr)
        return 1

    client = genai.Client(api_key=api_key)

    input_path = args.input.resolve()
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        return 1

    try:
        video_file = upload_video(input_path, client)
        print(f"Analyzing with {args.model} ...")
        data = analyze_video(video_file, client, args.model)
    except json.JSONDecodeError as exc:
        print(f"Error: Gemini returned non-JSON output: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    any_file_output = args.output_music or args.output_lipsync or args.output
    if any_file_output:
        write_outputs(data, args.output_music, args.output_lipsync, args.output)
    else:
        pretty_print(data)

    return 0


if __name__ == "__main__":
    sys.exit(main())
