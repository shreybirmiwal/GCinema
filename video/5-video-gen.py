#!/usr/bin/env python3
"""
Generate a short video clip from a colorized keyframe + scene description using Veo3.

Takes a colorized image (from step 4) and a description text file (from step 2)
and produces an MP4 video via Google's Veo3 image-to-video model.
"""

import argparse
import os
import sys
import time
from pathlib import Path
import io

from google import genai
from google.genai import types
from PIL import Image

MODEL = "veo-3.0-generate-preview"
DEFAULT_DURATION = 5  # seconds


def load_image(path: Path) -> types.Image:
    img = Image.open(path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return types.Image(image_bytes=buf.getvalue(), mime_type="image/jpeg")


def generate_video(
    client: genai.Client,
    image_path: Path,
    description: str,
    duration_seconds: int,
    model_name: str,
) -> bytes:
    image = load_image(image_path)

    operation = client.models.generate_video(
        model=model_name,
        prompt=description,
        image=image,
        config=types.GenerateVideoConfig(
            duration_seconds=duration_seconds,
            enhance_prompt=True,
        ),
    )

    print("Waiting for Veo3 to generate video", end="", flush=True)
    while not operation.done:
        time.sleep(5)
        operation = client.operations.get(operation)
        print(".", end="", flush=True)
    print()

    if operation.error:
        raise RuntimeError(f"Video generation failed: {operation.error}")

    video = operation.response.generated_videos[0]
    return client.files.download(file=video.video)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a video from a colorized keyframe + scene description using Veo3."
    )
    parser.add_argument(
        "image",
        type=Path,
        help="Path to the colorized keyframe image (e.g. frame0_colorized.jpg).",
    )
    parser.add_argument(
        "description",
        type=Path,
        help="Path to the scene description text file (e.g. description.txt).",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Path to write the output video (default: <image_stem>_generated.mp4).",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_DURATION,
        help=f"Duration of generated video in seconds (default: {DEFAULT_DURATION}).",
    )
    parser.add_argument(
        "--model",
        default=MODEL,
        help=f"Veo model to use (default: {MODEL}).",
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

    image_path = args.image.resolve()
    if not image_path.is_file():
        print(f"Error: Image not found: {image_path}", file=sys.stderr)
        return 1

    desc_path = args.description.resolve()
    if not desc_path.is_file():
        print(f"Error: Description file not found: {desc_path}", file=sys.stderr)
        return 1

    description = desc_path.read_text(encoding="utf-8").strip()
    if not description:
        print("Error: Description file is empty.", file=sys.stderr)
        return 1

    out_path = args.output or image_path.parent / (image_path.stem + "_generated.mp4")

    client = genai.Client(api_key=api_key)

    print(f"Image:       {image_path}")
    print(f"Description: {desc_path}")
    print(f"Model:       {args.model}")
    print(f"Duration:    {args.duration}s")
    print(f"Output:      {out_path}")
    print("Generating ...")

    try:
        video_bytes = generate_video(client, image_path, description, args.duration, args.model)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    out_path.write_bytes(video_bytes)
    print(f"Video saved to: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
