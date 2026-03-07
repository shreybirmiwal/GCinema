#!/usr/bin/env python3
"""
Generate a master color guide by having Gemini watch the ENTIRE film.

Uploads the full video to the Gemini Files API and prompts the model to
produce a detailed, character- and object-specific color guide that will
anchor every colorization call in the pipeline.
"""

import argparse
import os
import sys
import time
from pathlib import Path

from google import genai

MODEL = "gemini-3.1"

COLOR_GUIDE_PROMPT = (
    "Watch this entire black-and-white film and produce a master color guide "
    "that will be used to consistently colorize every scene.\n\n"
    "For every recurring character, object, animal, and environment you can identify, "
    "specify exact, actionable colors. Examples of the level of detail expected:\n"
    "  - 'Main character (man in suit): charcoal grey pinstripe suit, white dress shirt, "
    "burgundy tie, warm olive complexion, dark brown hair'\n"
    "  - 'Lion: tawny orange-gold fur, pale cream belly, amber eyes'\n"
    "  - 'Young woman: dusty rose blouse, navy skirt, fair rosy complexion, auburn hair'\n"
    "  - 'Interior parlor: cream walls, mahogany furniture, Persian rug in deep reds and golds'\n"
    "  - 'Exterior street: grey cobblestones, brown brick buildings, overcast cool daylight'\n\n"
    "Also note the overall lighting mood for day/night/interior scenes and any "
    "consistent color temperature (e.g. warm golden afternoons, cool blue nights).\n\n"
    "Be specific — 'dusty rose' not 'pink', 'tawny orange-gold' not 'yellow'. "
    "Return only the color guide as plain descriptive text, no markdown headers."
)


def upload_video(client: genai.Client, path: Path):
    print(f"Uploading film: {path} ...")
    video_file = client.files.upload(file=str(path))

    while video_file.state.name == "PROCESSING":
        print("  Waiting for Gemini to process video ...", end="\r")
        time.sleep(5)
        video_file = client.files.get(name=video_file.name)

    if video_file.state.name != "ACTIVE":
        raise RuntimeError(f"File processing failed with state: {video_file.state.name}")

    print(f"\nUpload complete: {video_file.uri}")
    return video_file


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a master color guide by analyzing the entire film video."
    )
    parser.add_argument("input", type=Path, help="Path to the film video (MP4)")
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Path to write the color guide text (default: color_guide.txt next to input)",
    )
    parser.add_argument(
        "--model", default=MODEL,
        help=f"Gemini model to use (default: {MODEL})",
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

    input_path = args.input.resolve()
    if not input_path.is_file():
        print(f"Error: Input video not found: {input_path}", file=sys.stderr)
        return 1

    out_path = args.output or input_path.parent / "color_guide.txt"

    client = genai.Client(api_key=api_key)

    try:
        video_file = upload_video(client, input_path)
        print(f"Generating master color guide with {args.model} ...")
        response = client.models.generate_content(
            model=args.model,
            contents=[video_file, COLOR_GUIDE_PROMPT],
        )
        guide = response.text.strip()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    out_path.write_text(guide, encoding="utf-8")
    print(f"Color guide saved to: {out_path}")
    print(f"\n--- Color Guide Preview ---\n{guide[:500]}{'...' if len(guide) > 500 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
