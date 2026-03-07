#!/usr/bin/env python3
"""
Colorize a black-and-white keyframe using Gemini image generation.

Optionally provide a previously-colored reference frame so Gemini can match
the color style, palette, and background consistency.
"""

import argparse
import os
import sys
from pathlib import Path

import google.generativeai as genai
from PIL import Image
import io

MODEL = "gemini-2.0-flash-exp-image-generation"

PROMPT_NO_REF = (
    "Colorize this black and white image. "
    "Produce a realistic, natural colorization that preserves all original detail. "
    "Output only the colorized image."
)

PROMPT_WITH_REF = (
    "The first image is a black and white frame that needs to be colorized. "
    "The second image is an already-colored reference frame from the same scene. "
    "Colorize the black and white image using the reference for style consistency: "
    "match the color palette, skin tones, clothing colors, background colors, lighting mood, "
    "and overall aesthetic of the reference. "
    "Preserve all original detail from the black and white frame. "
    "Output only the colorized image."
)


def load_image_part(path: Path) -> genai.types.Part:
    img = Image.open(path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return {"mime_type": "image/jpeg", "data": buf.getvalue()}


def colorize(bw_path: Path, ref_path: Path | None, model_name: str) -> bytes:
    model = genai.GenerativeModel(model_name=model_name)

    parts = []
    if ref_path:
        parts.append(load_image_part(bw_path))
        parts.append(load_image_part(ref_path))
        parts.append(PROMPT_WITH_REF)
    else:
        parts.append(load_image_part(bw_path))
        parts.append(PROMPT_NO_REF)

    response = model.generate_content(
        parts,
        generation_config=genai.GenerationConfig(response_modalities=["IMAGE", "TEXT"]),
        request_options={"timeout": 120},
    )

    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.mime_type.startswith("image/"):
            return part.inline_data.data

    raise RuntimeError("Gemini did not return an image in the response.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Colorize a B&W keyframe with Gemini (nano banana edition)."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to the black-and-white input image.",
    )
    parser.add_argument(
        "--reference",
        "-r",
        type=Path,
        default=None,
        help="Path to an already-colored reference frame (optional).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Path to write the colorized image (default: <input>_colorized.jpg).",
    )
    parser.add_argument(
        "--model",
        default=MODEL,
        help=f"Gemini model to use (default: {MODEL}).",
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

    genai.configure(api_key=api_key)

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
        image_bytes = colorize(bw_path, ref_path, args.model)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    out_path.write_bytes(image_bytes)
    print(f"Colorized image saved to: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
