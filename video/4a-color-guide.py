#!/usr/bin/env python3
"""
Generate a master color guide for a film by analyzing its first frame.

Sends the first keyframe to Gemini and asks it to produce a detailed,
specific color description that will be used to keep colorization
consistent across all scenes in the pipeline.
"""

import argparse
import os
import sys
import io
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

MODEL = "gemini-2.0-flash"

COLOR_GUIDE_PROMPT = (
    "Analyze this black and white film frame and create a master color guide "
    "that will be used to consistently colorize every scene in this film.\n\n"
    "For each thing you can identify, specify exact, actionable colors:\n"
    "- Characters: skin tone, hair color, eye color, clothing colors and fabrics\n"
    "- Environment: wall/floor colors, furniture, props, sky, outdoor elements\n"
    "- Lighting: warm or cool, color temperature (e.g. golden afternoon, harsh white noon, soft blue dusk)\n"
    "- Overall palette mood: e.g. desaturated and gritty, warm and nostalgic, high-contrast dramatic\n\n"
    "Be specific — say 'dusty rose blouse' not 'pink shirt', 'warm olive complexion' not 'tan skin'. "
    "This guide will anchor every colorization call so colors stay consistent across cuts and scenes. "
    "Return only the color guide as plain descriptive text, no bullet headers or markdown."
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a master color guide from a film's first keyframe."
    )
    parser.add_argument("input", type=Path, help="Path to the keyframe image (PNG/JPG)")
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Path to write the color guide text (default: <input>_color_guide.txt)",
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
        print(f"Error: Input image not found: {input_path}", file=sys.stderr)
        return 1

    out_path = args.output or input_path.parent / (input_path.stem + "_color_guide.txt")

    client = genai.Client(api_key=api_key)

    img = Image.open(input_path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    image_part = types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")

    print(f"Generating master color guide from: {input_path}")
    try:
        response = client.models.generate_content(
            model=args.model,
            contents=[image_part, COLOR_GUIDE_PROMPT],
        )
        guide = response.text.strip()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    out_path.write_text(guide, encoding="utf-8")
    print(f"Color guide saved to: {out_path}")
    print(f"\n--- Color Guide Preview ---\n{guide[:300]}{'...' if len(guide) > 300 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
