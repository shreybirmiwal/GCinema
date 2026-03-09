#!/usr/bin/env python3
"""
Generate a short video clip from a colorized keyframe + scene description.

Backend priority (auto mode):
  1. Google Veo 3.1      — highest quality, content-filtered
  2. Kling v3 Pro        — best image fidelity / minimal hallucination
  3. Wan 2.2 Turbo       — cheapest / fastest fallback
"""

import argparse
import os
import sys
import time
import io
import urllib.request
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

VEO_MODEL      = "veo-3.1-generate-preview"
KLING_MODEL_ID = "fal-ai/kling-video/v3/pro/image-to-video"
WAN_MODEL_ID   = "fal-ai/wan/v2.2-a14b/image-to-video/turbo"
DEFAULT_DURATION = 8


def load_image_for_veo(path: Path) -> types.Image:
    img = Image.open(path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return types.Image(image_bytes=buf.getvalue(), mime_type="image/jpeg")


class ContentFilteredError(Exception):
    """Raised when Veo rejects generation due to content safety filters."""
    pass


def generate_video_veo(
    client: genai.Client,
    image_path: Path,
    description: str,
    duration_seconds: int,
    model_name: str,
) -> bytes:
    image = load_image_for_veo(image_path)

    # Veo requires duration between 4 and 8 seconds inclusive
    # veo_duration = max(4, min(8, duration_seconds))
    veo_duration = 6

    operation = client.models.generate_videos(
        model=model_name,
        source=types.GenerateVideosSource(
            prompt=description,
            image=image,
        ),
        config=types.GenerateVideosConfig(
            duration_seconds=veo_duration,
            person_generation="allow_adult",
        ),
    )

    print("Waiting for Veo to generate video", end="", flush=True)
    while not operation.done:
        time.sleep(10)
        operation = client.operations.get(operation)
        print(".", end="", flush=True)
    print()

    result = operation.result
    if not result:
        raise RuntimeError(
            f"Veo returned no result.\n"
            f"  operation.error = {operation.error}\n"
            f"  operation = {operation}"
        )

    generated_videos = result.generated_videos
    if not generated_videos:
        filtered = getattr(result, "rai_media_filtered_count", 0)
        reasons = getattr(result, "rai_media_filtered_reasons", [])
        if filtered or reasons:
            raise ContentFilteredError(
                f"Veo content filter blocked generation "
                f"(filtered={filtered}): {reasons}"
            )
        raise RuntimeError(f"Veo returned empty videos list.\n  result = {result}")

    video = generated_videos[0].video
    client.files.download(file=video)
    if not video.video_bytes:
        raise RuntimeError("Downloaded Veo video has no bytes.")
    return video.video_bytes


def generate_video_kling(
    image_path: Path,
    description: str,
    duration_seconds: int,
) -> bytes:
    import fal_client

    # Kling v3 Pro only accepts "5" or "10" seconds
    kling_duration = "5" if duration_seconds <= 7 else "10"

    print("Uploading image to fal.ai ...")
    image_url = fal_client.upload_file(str(image_path))

    print(f"Calling Kling v3 Pro image-to-video ({kling_duration}s) ...")

    def on_queue_update(update):
        if isinstance(update, fal_client.InProgress):
            for log in update.logs:
                print(f"  [kling] {log['message']}")

    result = fal_client.subscribe(
        KLING_MODEL_ID,
        arguments={
            "image_url": image_url,
            "prompt": description,
            "duration": kling_duration,
            "aspect_ratio": "16:9",
        },
        with_logs=True,
        on_queue_update=on_queue_update,
    )

    video_url = result["video"]["url"]
    print("Downloading Kling video ...")
    with urllib.request.urlopen(video_url) as resp:
        return resp.read()


def generate_video_wan(
    image_path: Path,
    description: str,
    duration_seconds: int,
) -> bytes:
    import fal_client

    # Wan 2.2 Turbo supports 1–10 seconds; clamp to its valid range
    wan_duration = max(1, min(10, duration_seconds))

    print("Uploading image to fal.ai ...")
    image_url = fal_client.upload_file(str(image_path))

    print(f"Calling Wan 2.2 Turbo image-to-video ({wan_duration}s) ...")

    def on_queue_update(update):
        if isinstance(update, fal_client.InProgress):
            for log in update.logs:
                print(f"  [wan] {log['message']}")

    result = fal_client.subscribe(
        WAN_MODEL_ID,
        arguments={
            "image_url": image_url,
            "prompt": description,
            "resolution": "720p",
            "num_seconds": wan_duration,
            "enable_safety_checker": False,
            "enable_output_safety_checker": False,
        },
        with_logs=True,
        on_queue_update=on_queue_update,
    )

    video_url = result["video"]["url"]
    print("Downloading Wan video ...")
    with urllib.request.urlopen(video_url) as resp:
        return resp.read()


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
        help=f"Duration in seconds (default: {DEFAULT_DURATION}).",
    )
    parser.add_argument(
        "--model", default=VEO_MODEL,
        help=f"Veo model to use (default: {VEO_MODEL}).",
    )
    parser.add_argument(
        "--api-key", default=None,
        help="Google AI API key (defaults to GEMINI_API_KEY env var).",
    )
    parser.add_argument(
        "--backend",
        choices=["veo", "kling", "wan", "auto"],
        default="auto",
        help=(
            "Which backend to use. "
            "'auto' tries Veo → Kling → Wan. "
            "'kling' uses Kling v3 Pro (best image fidelity). "
            "'wan' uses Wan 2.2 Turbo (cheapest). "
            "Default: auto."
        ),
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

    # Audio/voice is handled separately by ElevenLabs — instruct the model to produce no speech or audio.
    description += "\n\nIMPORTANT: Do NOT generate any dialogue, voice, speech, or narration. Produce silent visuals only."

    out_path = args.output or image_path.parent / (image_path.stem + "_generated.mp4")

    print(f"Image:       {image_path}")
    print(f"Description: {desc_path}")
    print(f"Backend:     {args.backend}")
    print(f"Duration:    {args.duration}s")
    print(f"Output:      {out_path}")

    use_veo         = args.backend in ("veo", "auto")
    use_kling       = args.backend in ("kling", "auto")
    use_wan         = args.backend in ("wan",)
    use_wan_as_last = args.backend == "auto"

    video_bytes = None

    # --- Veo ---
    if use_veo:
        api_key = args.api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            if args.backend == "veo":
                print("Error: No API key. Set GEMINI_API_KEY or pass --api-key.", file=sys.stderr)
                return 1
            print("Warning: No GEMINI_API_KEY, skipping Veo.", file=sys.stderr)
        else:
            client = genai.Client(
                api_key=api_key,
                http_options={"api_version": "v1beta"},
            )
            print(f"Generating via Veo ({args.model}) ...")
            try:
                video_bytes = generate_video_veo(
                    client, image_path, description, args.duration, args.model,
                )
            except ContentFilteredError as exc:
                print(f"Warning: {exc}", file=sys.stderr)
                if use_kling or use_wan_as_last:
                    print("Falling back to Kling ...")
                else:
                    print("Error: Veo content-filtered and no fallback enabled.", file=sys.stderr)
                    return 1
            except Exception as exc:
                print(f"Warning (Veo): {exc}", file=sys.stderr)
                if not (use_kling or use_wan_as_last):
                    return 1
                print("Falling back to Kling ...")

    # --- Kling v3 Pro ---
    if video_bytes is None and (use_kling or use_wan_as_last):
        fal_key = os.environ.get("FAL_KEY")
        if not fal_key:
            if args.backend == "kling":
                print("Error: No FAL_KEY set. Required for Kling.", file=sys.stderr)
                return 1
            print("Warning: No FAL_KEY, skipping Kling.", file=sys.stderr)
        elif use_kling or use_wan_as_last:
            try:
                video_bytes = generate_video_kling(image_path, description, args.duration)
            except Exception as exc:
                print(f"Warning (Kling): {exc}", file=sys.stderr)
                if use_wan_as_last:
                    print("Falling back to Wan ...")
                elif args.backend == "kling":
                    print(f"Error (Kling): {exc}", file=sys.stderr)
                    return 1

    # --- Wan 2.2 Turbo (last resort) ---
    if video_bytes is None and (use_wan or use_wan_as_last):
        fal_key = os.environ.get("FAL_KEY")
        if not fal_key:
            print("Error: No FAL_KEY set. Required for Wan.", file=sys.stderr)
            return 1
        try:
            video_bytes = generate_video_wan(image_path, description, args.duration)
        except Exception as exc:
            print(f"Error (Wan): {exc}", file=sys.stderr)
            return 1

    if video_bytes is None:
        print("Error: No video was generated.", file=sys.stderr)
        return 1

    out_path.write_bytes(video_bytes)
    print(f"Video saved to: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
