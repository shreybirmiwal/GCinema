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
from google.genai import types

SYSTEM_PROMPT = (
    "You are writing a video description that a video generation AI will use to "
    "recreate this clip. Your output must be extremely long and detailed — aim for "
    "at least 400 words. There is no upper length limit; longer is always better.\n\n"
    "Describe EVERY MOMENT from start to finish. Walk through the clip "
    "chronologically, covering every significant movement and change.\n\n"
    "Cover ALL of the following in depth:\n\n"
    "ACTIONS: Walk through every movement. What does each person or animal do, in "
    "what order? Describe specific body mechanics — ducking, leaning, stumbling, "
    "reaching, flinching, pivoting, etc. Note the speed and urgency of each action "
    "(sprinting vs. jogging, cautious step vs. confident stride).\n\n"
    "SPACE & BLOCKING: Where is each character positioned relative to the environment "
    "and to each other? Which direction do they move (left-to-right, toward camera, "
    "diagonally across the frame)? How does their position change over the clip?\n\n"
    "APPEARANCE: Describe clothing, build, posture, and distinguishing features of "
    "every person and animal. Include approximate age, gender, and demeanor.\n\n"
    "EMOTION & EXPRESSION: Capture facial expressions, body language, and the overall "
    "mood — fear, joy, determination, panic, calm, etc.\n\n"
    "ENVIRONMENT: Describe the setting in detail — the ground surface, structures, "
    "vegetation, objects, weather, time of day, and atmosphere.\n\n"
    "Do NOT mention: camera angles, shot composition, lighting techniques, film "
    "terminology, that it is black and white, or any audio/sound.\n"
    "Do NOT use markdown, headers, or bullet points.\n"
    "Write in flowing, vivid prose paragraphs. Do not stop early — keep writing "
    "until every moment of the clip has been described."
)

USER_PROMPT = (
    "Describe this video clip in exhaustive detail for a video generation AI. "
    "Write at least 400 words. Do not stop early."
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
        contents=[video_file, USER_PROMPT],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=8192,
            temperature=0.7,
        ),
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
