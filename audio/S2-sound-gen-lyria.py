#!/usr/bin/env python3
"""
Generate background music for a video clip using Gemini Lyria RealTime.

Takes a text prompt (e.g. from S1-sound-gen-prompt.py --output-music) and produces
a WAV audio file via the lyria-realtime-exp model.

Requirements:
  pip install google-genai

Usage:
  # From a prompt file (output of S1):
  python S2-sound-gen-lyria.py music_prompt.txt -o score.wav

  # Inline prompt:
  python S2-sound-gen-lyria.py "Lively ragtime piano, upbeat 120 BPM, comedic silent-film style" -o score.wav

  # Control duration and BPM:
  python S2-sound-gen-lyria.py music_prompt.txt -o score.wav --duration 30 --bpm 110
"""

import argparse
import asyncio
import os
import struct
import sys
import wave
from pathlib import Path

from google import genai
from google.genai import types

# Lyria outputs 48 kHz stereo 16-bit PCM
SAMPLE_RATE = 48_000
CHANNELS = 2
SAMPLE_WIDTH = 2  # bytes (16-bit)


def write_wav(path: Path, pcm_data: bytes) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_data)


async def generate_music(
    prompt: str,
    api_key: str,
    duration_sec: int,
    bpm: int | None,
    output_path: Path,
) -> None:
    client = genai.Client(
        api_key=api_key,
        http_options={"api_version": "v1alpha"},
    )

    print(f"Connecting to lyria-realtime-exp ...")
    print(f"Prompt: {prompt[:120]}{'...' if len(prompt) > 120 else ''}")
    if bpm:
        print(f"BPM: {bpm}")
    print(f"Duration: {duration_sec}s")

    frames_needed = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH * duration_sec
    collected = bytearray()

    async with client.aio.live.music.connect(model="lyria-realtime-exp") as session:
        await session.set_weighted_prompts([types.WeightedPrompt(text=prompt, weight=1.0)])
        if bpm:
            await session.set_music_generation_config(types.LiveMusicGenerationConfig(bpm=bpm))
        await session.play()

        print("Connected. Receiving audio...", end="", flush=True)

        async for response in session.receive():
            if response.server_content and response.server_content.audio_chunks:
                for chunk in response.server_content.audio_chunks:
                    if chunk.data:
                        collected.extend(chunk.data)

            pct = min(100, int(len(collected) / frames_needed * 100))
            print(f"\r  Buffering audio ... {pct:3d}%  ({len(collected)//1024} KB)", end="", flush=True)

            if len(collected) >= frames_needed:
                break

    print()  # newline after progress

    if not collected:
        raise RuntimeError("No audio data received from Lyria. Check your API key and quota.")

    # Trim to requested duration if we got more
    collected = bytes(collected[:frames_needed])

    write_wav(output_path, collected)
    duration_actual = len(collected) / (SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH)
    print(f"Saved {duration_actual:.1f}s of audio to: {output_path}")


def resolve_prompt(prompt_arg: str) -> str:
    """If prompt_arg looks like a file path that exists, read it; otherwise use as-is."""
    p = Path(prompt_arg)
    if p.exists() and p.is_file():
        text = p.read_text(encoding="utf-8").strip()
        print(f"Loaded prompt from: {p}")
        return text
    return prompt_arg.strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate music from a text prompt using Gemini Lyria RealTime."
    )
    parser.add_argument(
        "prompt",
        help="Music generation prompt as a string, or path to a text file (e.g. output of S1 --output-music)",
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=Path("music.wav"),
        help="Path for the output WAV file (default: music.wav)",
    )
    parser.add_argument(
        "--duration", "-d", type=int, default=30,
        help="Desired audio duration in seconds (default: 30)",
    )
    parser.add_argument(
        "--bpm", type=int, default=None,
        help="Optional BPM hint to pass to Lyria",
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

    prompt = resolve_prompt(args.prompt)
    if not prompt:
        print("Error: Empty prompt.", file=sys.stderr)
        return 1

    try:
        asyncio.run(generate_music(prompt, api_key, args.duration, args.bpm, args.output))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
