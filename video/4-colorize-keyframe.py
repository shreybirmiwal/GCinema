#!/usr/bin/env python3
"""
Colorize a black-and-white keyframe using NanoBanana image generation.

Keeps the prompt minimal to avoid over-saturation and hallucination.
Primary signal is the previous colorized reference frame (if available).
"""

import argparse
import os
import sys
from pathlib import Path
import io

from google import genai
from google.genai import types
from PIL import Image

MODEL = "nanobanana-2"

PROMPT_NO_REF = (
    "Add natural, realistic color to this black and white image. "
    "Keep it subtle and grounded — do not over-saturate."
)

PROMPT_WITH_REF = (
    "Add natural, realistic color to the first image (black and white). "
    "Use the second image as a reference for color style, palette, "
    "skin tones, clothing, and background consistency."
)


def load_image_part(path: Path) -> types.Part:
    img = Image.open(path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")


def colorize(
    client: genai.Client,
    bw_path: Path,
    ref_path: Path | None,
    model_name: str,
) -> bytes:
    contents = [load_image_part(bw_path)]
    if ref_path:
        contents.append(load_image_part(ref_path))
        contents.append(PROMPT_WITH_REF)
    else:
        contents.append(PROMPT_NO_REF)

    response = client.models.generate_content(
        model=model_name,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        ),
    )

    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.mime_type.startswith("image/"):
            return part.inline_data.data

    raise RuntimeError("Model did not return an image in the response.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Colorize a B&W keyframe with NanoBanana."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to the black-and-white input image.",
    )
    parser.add_argument(
        "--reference", "-r",
        type=Path,
        default=None,
        help="Path to a single already-colorized reference frame from the previous scene.",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Path to write the colorized image (default: <input>_colorized.jpg).",
    )
    parser.add_argument(
        "--model",
        default=MODEL,
        help=f"Model to use (default: {MODEL}).",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Google AI API key (defaults to GEMINI_API_KEY env var).",
    )
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: No API key provided. Set GEMINI_API_KEY or pass --api-key.", file=sys.stderr)
        return 1

    client = genai.Client(api_key=api_key)

    bw_path = args.input.resolve()
    if not bw_path.is_file():
        print(f"Error: Input image not found: {bw_path}", file=sys.stderr)
        return 1

    ref_path = None
    if args.reference:
        ref_path = args.reference.resolve()
        if not ref_path.is_file():
            print(f"Error: Reference image not found: {ref_path}", file=sys.stderr)
            return 1

    out_path = args.output or bw_path.parent / (bw_path.stem + "_colorized.jpg")

    print(f"Input:     {bw_path}")
    print(f"Reference: {ref_path or '(none)'}")
    print(f"Model:     {args.model}")
    print("Colorizing ...")

    try:
        image_bytes = colorize(client, bw_path, ref_path, args.model)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    out_path.write_bytes(image_bytes)
    print(f"Colorized image saved to: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
