#!/usr/bin/env python3
"""
Generate a short video clip from a colorized keyframe + scene description.

Uses xAI's Grok Imagine Video API (image-to-video).
"""

import argparse
import base64
import os
import sys
import time
import urllib.request
from pathlib import Path

import requests

GROK_MODEL = "grok-imagine-video"
DEFAULT_DURATION = 8
POLL_INTERVAL = 5
POLL_TIMEOUT = 600

API_BASE = "https://api.x.ai/v1"


def encode_image_as_data_uri(path: Path) -> str:
    data = path.read_bytes()
    suffix = path.suffix.lower()
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(suffix, "image/jpeg")
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def generate_video(
    api_key: str,
    image_path: Path,
    description: str,
    duration_seconds: int,
) -> bytes:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    image_data_uri = encode_image_as_data_uri(image_path)
    clamped_duration = max(1, min(15, duration_seconds))

    print(f"Submitting image-to-video request ({clamped_duration}s, 720p) ...")

    resp = requests.post(
        f"{API_BASE}/videos/generations",
        headers=headers,
        json={
            "model": GROK_MODEL,
            "prompt": description,
            "image_url": image_data_uri,
            "duration": clamped_duration,
            "aspect_ratio": "16:9",
            "resolution": "720p",
        },
        timeout=60,
    )

    if resp.status_code != 200:
        raise RuntimeError(
            f"Grok Imagine API error {resp.status_code}: {resp.text}"
        )

    request_id = resp.json().get("request_id")
    if not request_id:
        raise RuntimeError(f"No request_id in response: {resp.json()}")

    print(f"Request ID: {request_id}")
    print("Waiting for video generation", end="", flush=True)

    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        print(".", end="", flush=True)

        poll_resp = requests.get(
            f"{API_BASE}/videos/{request_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )

        if poll_resp.status_code != 200:
            print()
            raise RuntimeError(
                f"Poll error {poll_resp.status_code}: {poll_resp.text}"
            )

        data = poll_resp.json()
        status = data.get("status")

        if status == "done":
            print()
            video_url = data["video"]["url"]
            actual_dur = data["video"].get("duration", "?")
            moderation = data["video"].get("respect_moderation", True)
            print(f"Video ready — duration: {actual_dur}s, moderation_ok: {moderation}")

            if not moderation:
                raise RuntimeError("Video was filtered by content moderation.")

            print("Downloading video ...")
            with urllib.request.urlopen(video_url) as r:
                return r.read()

        elif status == "expired":
            print()
            raise RuntimeError("Video generation request expired.")

    print()
    raise TimeoutError(
        f"Video generation did not complete within {POLL_TIMEOUT}s."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a video from a colorized keyframe + scene description."
    )
    parser.add_argument(
        "image", type=Path,
        help="Path to the colorized keyframe image (e.g. frame0_colorized.jpg).",
    )
    parser.add_argument(
        "description", type=Path,
        help="Path to the scene description text file (e.g. description.txt).",
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Path to write the output video (default: <image_stem>_generated.mp4).",
    )
    parser.add_argument(
        "--duration", type=int, default=DEFAULT_DURATION,
        help=f"Duration in seconds, 1-15 (default: {DEFAULT_DURATION}).",
    )
    parser.add_argument(
        "--api-key", default=None,
        help="xAI API key (defaults to XAI_API_KEY env var).",
    )
    args = parser.parse_args()

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

    description += "\n\nIMPORTANT: Do NOT generate any dialogue, voice, speech, or narration. Produce silent visuals only."

    out_path = args.output or image_path.parent / (image_path.stem + "_generated.mp4")

    api_key = args.api_key or os.environ.get("XAI_API_KEY")
    if not api_key:
        print(
            "Error: No API key. Set XAI_API_KEY env var or pass --api-key.",
            file=sys.stderr,
        )
        return 1

    print(f"Image:       {image_path}")
    print(f"Description: {desc_path}")
    print(f"Model:       {GROK_MODEL}")
    print(f"Duration:    {args.duration}s")
    print(f"Output:      {out_path}")

    try:
        video_bytes = generate_video(api_key, image_path, description, args.duration)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    out_path.write_bytes(video_bytes)
    print(f"Video saved to: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
