#!/usr/bin/env python3
"""
Mix a background music track (score.wav) and a foley/vocal track (foley.wav)
into a single MP3 that matches an exact target duration.

Usage:
  python S4-mix-audio.py score.wav foley.wav --duration 45.3 -o final_audio.mp3
  python S4-mix-audio.py score.wav foley.wav --duration 45.3 -o final_audio.mp3 --music-volume -6
"""

import argparse
import sys
from pathlib import Path

from pydub import AudioSegment


def load_and_normalize(path: Path) -> AudioSegment:
    fmt = path.suffix.lstrip(".").lower() or "wav"
    seg = AudioSegment.from_file(str(path), format=fmt)
    # Normalize to stereo 44100
    if seg.channels == 1:
        seg = seg.set_channels(2)
    return seg.set_frame_rate(44100)


def fit_to_duration(seg: AudioSegment, target_ms: int) -> AudioSegment:
    """Trim or pad with silence to exactly target_ms milliseconds."""
    if len(seg) > target_ms:
        return seg[:target_ms]
    if len(seg) < target_ms:
        pad = AudioSegment.silent(duration=target_ms - len(seg), frame_rate=44100).set_channels(2)
        return seg + pad
    return seg


def mix(
    score_path: Path,
    foley_path: Path,
    target_sec: float,
    output_path: Path,
    music_volume_db: float,
) -> None:
    target_ms = int(round(target_sec * 1000))

    print(f"Loading score:  {score_path}")
    score = load_and_normalize(score_path)

    print(f"Loading foley:  {foley_path}")
    foley = load_and_normalize(foley_path)

    # Loop music if shorter than target
    if len(score) < target_ms:
        loops_needed = (target_ms // len(score)) + 1
        score = score * loops_needed

    score = fit_to_duration(score, target_ms)
    foley = fit_to_duration(foley, target_ms)

    if music_volume_db != 0:
        score = score + music_volume_db

    mixed = score.overlay(foley)
    mixed = fit_to_duration(mixed, target_ms)  # safety trim after overlay

    output_path.parent.mkdir(parents=True, exist_ok=True)
    mixed.export(str(output_path), format="mp3", bitrate="192k")
    actual_sec = len(mixed) / 1000
    print(f"Mixed audio saved to: {output_path}  ({actual_sec:.3f}s, target={target_sec:.3f}s)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mix score.wav + foley.wav into a final MP3 at an exact target duration."
    )
    parser.add_argument("score", type=Path, help="Background music WAV (output of S2)")
    parser.add_argument("foley", type=Path, help="Foley/vocal WAV (output of S3)")
    parser.add_argument(
        "--duration", "-d", type=float, required=True,
        help="Exact target duration in seconds (must match video length)",
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=Path("final_audio.mp3"),
        help="Output MP3 file path (default: final_audio.mp3)",
    )
    parser.add_argument(
        "--music-volume", type=float, default=-6.0, metavar="DB",
        help="Adjust background music volume in dB before mixing (default: -6 dB)",
    )
    args = parser.parse_args()

    for p in (args.score, args.foley):
        if not p.exists():
            print(f"Error: file not found: {p}", file=sys.stderr)
            return 1

    try:
        mix(args.score, args.foley, args.duration, args.output, args.music_volume)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
