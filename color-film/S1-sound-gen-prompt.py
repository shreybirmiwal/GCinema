#!/usr/bin/env python3
"""
Send a video clip to Gemini and generate:
  1. A music/audio composition prompt describing what the soundtrack would likely sound like.
  2. A lip-sync / dialogue transcript with timestamps for any spoken words, exclamations, etc.

Output is printed to stdout or written to a JSON file.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import google.generativeai as genai

SYSTEM_PROMPT = """\
You are an expert film sound designer and music composer analyzing a silent or archival video clip.

Analyze the video carefully and return a JSON object with exactly two keys:

1. "music_prompt": A detailed text prompt (2-5 sentences) describing the ideal background music or
   audio composition for this clip. Include:
   - Genre / style (e.g. orchestral, jazz, ragtime, suspense, comedic)
   - Tempo and energy level
   - Key instruments
   - Mood and emotional arc across the clip
   - Any sound effects that should accompany the music (foley, ambience, etc.)

2. "lip_sync": A list of objects, each representing a moment where a character appears to speak,
   shout, react, or make a vocal sound. Each object must have:
   - "timestamp_sec": approximate time in seconds (float) from the start of the clip
   - "character": brief description of who is speaking (e.g. "man in hat", "woman on left")
   - "utterance": the most likely word(s), exclamation, or phonetic approximation
     (e.g. "Help!", "Ouch!", "What?", "No no no", "Ha ha ha")
   - "confidence": "high", "medium", or "low" based on how clear the lip movement is

Return ONLY the raw JSON object with no markdown fencing or extra commentary.
"""


def upload_video(path: Path) -> genai.types.File:
    print(f"Uploading {path} ...")
    video_file = genai.upload_file(path=str(path))

    while video_file.state.name == "PROCESSING":
        print("  Waiting for Gemini to process video ...", end="\r")
        time.sleep(5)
        video_file = genai.get_file(video_file.name)

    if video_file.state.name != "ACTIVE":
        raise RuntimeError(f"File processing failed with state: {video_file.state.name}")

    print(f"\nUpload complete: {video_file.uri}")
    return video_file


def analyze_video(video_file: genai.types.File, model_name: str) -> dict:
    model = genai.GenerativeModel(model_name=model_name)
    response = model.generate_content(
        [video_file, SYSTEM_PROMPT],
        request_options={"timeout": 300},
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

    print("\n=== LIP SYNC & DIALOGUE TIMESTAMPS ===\n")
    lip_sync = data.get("lip_sync", [])
    if not lip_sync:
        print("No lip-sync moments detected.")
        return

    for entry in lip_sync:
        ts = entry.get("timestamp_sec", "?")
        char = entry.get("character", "unknown")
        utt = entry.get("utterance", "")
        conf = entry.get("confidence", "")
        print(f"  [{ts:>6.2f}s]  {char:<25}  \"{utt}\"  ({conf} confidence)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a music composition prompt and lip-sync transcript from a video clip."
    )
    parser.add_argument("input", type=Path, help="Path to input video file (e.g. MP4)")
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Path to write JSON output (default: prints to stdout)",
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

    genai.configure(api_key=api_key)

    input_path = args.input.resolve()
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        return 1

    try:
        video_file = upload_video(input_path)
        print(f"Analyzing with {args.model} ...")
        data = analyze_video(video_file, args.model)
    except json.JSONDecodeError as exc:
        print(f"Error: Gemini returned non-JSON output: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.output:
        args.output.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"Results written to: {args.output}")
    else:
        pretty_print(data)

    return 0


if __name__ == "__main__":
    sys.exit(main())
