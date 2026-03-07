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

MODEL = "gemini-3.1-flash-image-preview"

PROMPT_NO_REF_ONE = (
    "Add natural, realistic color to this black and white image. "
    "Keep it subtle and grounded — do not over-saturate."
)

PROMPT_NO_REF_TWO = (
    "You are given two black-and-white frames (A and B) from the same scene. "
    "Choose whichever frame is clearer, more informative, or better represents the scene, "
    "and colorize it with natural, realistic colors. Keep it subtle and grounded — do not over-saturate."
)

PROMPT_WITH_REF_ONE = (
    "Add natural, realistic color to the first image (black and white). "
    "Use the second image as a reference for color style, palette, "
    "skin tones, clothing, and background consistency."
)

PROMPT_WITH_REF_TWO = (
    "You are given two black-and-white frames (A and B) from the same scene, "
    "followed by a previously colorized reference image. "
    "Choose whichever B&W frame is clearer, more informative, or better represents the scene, "
    "and colorize it. Use the reference image to maintain consistent color palette, "
    "skin tones, and clothing across scenes. Keep colors natural and grounded — do not over-saturate."
)


def load_image_part(path: Path) -> types.Part:
    img = Image.open(path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")


def colorize(
    client: genai.Client,
    bw_path: Path,
    bw_path2: Path | None,
    ref_path: Path | None,
    model_name: str,
) -> bytes:
    contents = [load_image_part(bw_path)]
    if bw_path2:
        contents.append(load_image_part(bw_path2))
    if ref_path:
        contents.append(load_image_part(ref_path))
        contents.append(PROMPT_WITH_REF_TWO if bw_path2 else PROMPT_WITH_REF_ONE)
    else:
        contents.append(PROMPT_NO_REF_TWO if bw_path2 else PROMPT_NO_REF_ONE)

    response = client.models.generate_content(
        model=model_name,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        ),
    )

    if not response.candidates:
        raise RuntimeError(
            f"Model returned no candidates.\n"
            f"Prompt feedback: {getattr(response, 'prompt_feedback', 'N/A')}\n"
            f"Raw response: {response}"
        )

    candidate = response.candidates[0]
    if not candidate.content or not candidate.content.parts:
        raise RuntimeError(
            f"Model returned empty content.\n"
            f"Finish reason: {getattr(candidate, 'finish_reason', 'N/A')}\n"
            f"Safety ratings: {getattr(candidate, 'safety_ratings', 'N/A')}"
        )

    for part in candidate.content.parts:
        if part.inline_data and part.inline_data.mime_type.startswith("image/"):
            return part.inline_data.data

    text_parts = [p.text for p in candidate.content.parts if hasattr(p, "text") and p.text]
    raise RuntimeError(
        f"Model did not return an image.\n"
        f"Text response: {' '.join(text_parts) if text_parts else '(none)'}"
    )


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
        "--input2", "-i2",
        type=Path,
        default=None,
        help="Path to a second black-and-white frame from the same scene (e.g. at 0.9s offset).",
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

    bw_path2 = None
    if args.input2:
        bw_path2 = args.input2.resolve()
        if not bw_path2.is_file():
            print(f"Warning: Second B&W frame not found, skipping: {bw_path2}", file=sys.stderr)
            bw_path2 = None

    ref_path = None
    if args.reference:
        ref_path = args.reference.resolve()
        if not ref_path.is_file():
            print(f"Error: Reference image not found: {ref_path}", file=sys.stderr)
            return 1

    out_path = args.output or bw_path.parent / (bw_path.stem + "_colorized.jpg")

    print(f"Input:     {bw_path}")
    print(f"Input2:    {bw_path2 or '(none)'}")
    print(f"Reference: {ref_path or '(none)'}")
    print(f"Model:     {args.model}")
    print("Colorizing ...")

    try:
        image_bytes = colorize(client, bw_path, bw_path2, ref_path, args.model)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    out_path.write_bytes(image_bytes)
    print(f"Colorized image saved to: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
