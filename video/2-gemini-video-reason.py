#!/usr/bin/env python3
"""
Send a video clip to Gemini and get a comprehensive scene description.

Uploads the video to the Gemini Files API, then prompts the model to produce
a detailed description suitable for recreating the scene from text alone.
"""

import argparse
import os
import sys
import time
from pathlib import Path

from google import genai

SYSTEM_PROMPT = (
    "Describe what HAPPENS in this clip in 2-4 plain sentences. "
    "Focus only on the people, animals, objects, and their actions — who does what, "
    "where they are, what they interact with.\n\n"
    "Do NOT mention: camera angles, shot composition, lighting, film techniques, "
    "that it is black and white, or any audio/sound. "
    "Do NOT use markdown, headers, or bullet points. "
    "Just write plain sentences describing the scene action."
)


def upload_video(client: genai.Client, path: Path):
    """Upload the video file and wait until processing is complete."""
    print(f"Uploading {path} ...")
    video_file = client.files.upload(file=str(path))

    # The Files API processes uploads asynchronously; poll until ready.
    while video_file.state.name == "PROCESSING":
        print("  Waiting for Gemini to process video ...", end="\r")
        time.sleep(5)
        video_file = client.files.get(name=video_file.name)

    if video_file.state.name != "ACTIVE":
        raise RuntimeError(
            f"File processing failed with state: {video_file.state.name}"
        )

    print(f"\nUpload complete: {video_file.uri}")
    return video_file


def describe_video(client: genai.Client, video_file, model_name: str) -> str:
    response = client.models.generate_content(
        model=model_name,
        contents=[video_file, SYSTEM_PROMPT],
    )
    return response.text


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Use Gemini to produce a comprehensive description of a video clip."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to input video file (e.g. MP4)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Path to write the description text (default: prints to stdout)",
    )
    parser.add_argument(
        "--model",
        default="gemini-3.1-pro-preview",
        help="Gemini model to use (default: gemini-3.1-pro-preview)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Google AI API key (defaults to GEMINI_API_KEY env var)",
    )
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(
            "Error: No API key provided. Set GEMINI_API_KEY or pass --api-key.",
            file=sys.stderr,
        )
        return 1

    client = genai.Client(api_key=api_key)

    input_path = args.input.resolve()
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        return 1
    if not input_path.is_file():
        print(f"Error: Input path is not a file: {input_path}", file=sys.stderr)
        return 1

    try:
        video_file = upload_video(client, input_path)
        print(f"Generating description with {args.model} ...")
        description = describe_video(client, video_file, args.model)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.output:
        args.output.write_text(description, encoding="utf-8")
        print(f"Description written to: {args.output}")
    else:
        print("\n--- Scene Description ---\n")
        print(description)

    return 0


if __name__ == "__main__":
    sys.exit(main())
