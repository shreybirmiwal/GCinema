#!/usr/bin/env python3
"""
Match the duration of a colorized video clip to an original clip by
speeding up or slowing down the colorized clip using ffmpeg.
"""

import argparse
import subprocess
import sys
from pathlib import Path


def get_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def match_length(original: Path, colorized: Path, output: Path) -> None:
    orig_dur = get_duration(original)
    col_dur = get_duration(colorized)

    speed = col_dur / orig_dur  # >1 means colorized is longer (slow down), <1 means speed up
    print(f"Original duration:   {orig_dur:.3f}s")
    print(f"Colorized duration:  {col_dur:.3f}s")
    print(f"Speed factor:        {speed:.4f}x")

    # setpts adjusts video timing; atempo handles audio (limited to 0.5-2.0 range)
    vf = f"setpts={speed:.6f}*PTS"

    # Build audio filter chain: atempo is limited to [0.5, 2.0] so chain multiple if needed
    remaining = speed
    atempo_filters = []
    while remaining > 2.0:
        atempo_filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        atempo_filters.append("atempo=0.5")
        remaining /= 0.5
    atempo_filters.append(f"atempo={remaining:.6f}")
    af = ",".join(atempo_filters)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(colorized),
        "-vf", vf,
        "-af", af,
        str(output),
    ]

    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print(f"Output saved to: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Match colorized video length to original by adjusting playback speed."
    )
    parser.add_argument("original", type=Path, help="Original (reference) video clip.")
    parser.add_argument("colorized", type=Path, help="Colorized video clip to adjust.")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output path (default: <colorized>_matched<ext>).",
    )
    args = parser.parse_args()

    original = args.original.resolve()
    colorized = args.colorized.resolve()

    for p in (original, colorized):
        if not p.is_file():
            print(f"Error: File not found: {p}", file=sys.stderr)
            return 1

    output = args.output or colorized.parent / (colorized.stem + "_matched" + colorized.suffix)

    try:
        match_length(original, colorized, output)
    except subprocess.CalledProcessError as e:
        print(f"Error: ffmpeg/ffprobe failed: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
