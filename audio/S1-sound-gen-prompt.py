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

CHARACTER_PROMPT = """\
You are analyzing a silent film clip. First, identify every character who appears.

For each character return a JSON array where each object has:
- "id": a short snake_case identifier (e.g. "charlie", "woman_in_hat")
- "description": what they look like (e.g. "man in bowler hat and baggy trousers")
- "gender": "male" or "female"
- "role": one sentence on their role in this scene
- "approximate_age": "child", "young_adult", "adult", or "elderly"

Return ONLY the raw JSON array, no markdown fencing.
"""

AUDIO_PROMPT_TEMPLATE = """\
You are an expert silent-film sound designer and dialogue writer restoring a classic silent film.
This is a SILENT film — there is no audio. Your job is to INVENT the full soundscape AND dialogue
that would bring this film to life, exactly as a 1920s sound restoration team would.

The following characters appear in this clip:
{character_list}

LANGUAGE REQUIREMENT: All dialogue and speech utterances MUST be written in {language}.
Every "utterance" field for speech events must contain natural, expressive {language} words or phrases.
Do NOT write utterances in any other language.

Analyze the video carefully and return a JSON object with exactly two keys:

1. "music_prompt": A detailed text prompt (2-5 sentences) describing the ideal background music or
   audio composition for this clip. Include:
   - Genre / style (e.g. orchestral, jazz, ragtime, suspense, comedic)
   - Tempo and energy level
   - Key instruments
   - Mood and emotional arc across the clip

2. "audio_events": A chronologically-sorted list of every discrete sound moment in the clip.
   Include BOTH invented dialogue AND sound effects. Aim for 20+ events total.

   Each object must have:
   - "timestamp_sec": time in seconds (float) from the start of the clip
   - "duration_sec": estimated duration of the sound in seconds (float, minimum 0.5)
   - "type": either "speech" (character vocal) or "sfx" (sound effect / foley)

   For type "speech":
       - "character_id": the character's id from the list above (e.g. "charlie", "woman_in_hat")
       - "character": human-readable description (e.g. "Charlie", "Woman in hat")
       - "gender": "male" or "female" (copy from the character list above — this is critical)
       - "utterance": INVENT a natural, expressive line of dialogue that fits the scene and
         emotion — based on facial expressions, body language, and context. This is a silent
         film restoration: you MUST write actual words, never use "..." or leave it blank.
         Examples: "Watch out!", "Oh my goodness!", "Ha! Take that!", "Are you alright?",
         "I did it!", "Help me!", "That was incredible!"
       - "confidence": always "high" or "medium" — never "low" for speech with real utterances

   For type "sfx":
       - "description": concise plain-English description for a sound effects generator
         (e.g. "wooden floorboard creak", "door slam", "crowd cheering", "horse whinny")
       - "confidence": "high", "medium", or "low"

   IMPORTANT for speech:
   - Use the character list above to correctly assign gender — this determines the voice used
   - Watch every moment a character opens their mouth or shows strong emotion
   - Invent dialogue that matches their expression — excited, scared, funny, dramatic
   - Include exclamations, reactions, short sentences — keep each utterance under 10 words
   - Mark ALL invented speech as "high" or "medium" confidence

   Be thorough — include footsteps, impacts, ambient sounds, crowd reactions,
   object interactions, character exclamations, and full invented dialogue exchanges.

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


def _parse_json(raw: str):
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(raw)


def identify_characters(video_file, client: genai.Client, model_name: str) -> list:
    print("Pass 1: identifying characters...")
    response = client.models.generate_content(
        model=model_name,
        contents=[video_file, CHARACTER_PROMPT],
    )
    characters = _parse_json(response.text)
    for c in characters:
        print(f"  [{c.get('gender','?')}] {c.get('id')} — {c.get('description')}")
    return characters


def analyze_video(video_file, client: genai.Client, model_name: str, characters: list, language: str = "English") -> dict:
    char_list = "\n".join(
        f"- {c['id']} ({c['gender']}, {c.get('approximate_age','adult')}): {c['description']} — {c.get('role','')}"
        for c in characters
    )
    prompt = AUDIO_PROMPT_TEMPLATE.format(character_list=char_list, language=language)
    print("Pass 2: generating music prompt + audio events...")
    response = client.models.generate_content(
        model=model_name,
        contents=[video_file, prompt],
    )
    return _parse_json(response.text)


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
        "--language", default="English",
        help="Language for dialogue utterances (e.g. English, Spanish, French, Japanese). Default: English",
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
        characters = identify_characters(video_file, client, args.model)
        data = analyze_video(video_file, client, args.model, characters, language=args.language)
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
