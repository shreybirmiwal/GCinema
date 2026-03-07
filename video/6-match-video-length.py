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


def has_audio_stream(path: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def match_length(original: Path, colorized: Path, output: Path) -> None:
    orig_dur = get_duration(original)
    col_dur = get_duration(colorized)

    # setpts < 1 speeds up video, setpts > 1 slows it down
    pts_factor = orig_dur / col_dur
    print(f"Original duration:   {orig_dur:.3f}s")
    print(f"Colorized duration:  {col_dur:.3f}s")
    print(f"PTS factor:          {pts_factor:.4f}x  (target: {orig_dur:.3f}s)")

    vf = f"setpts={pts_factor:.6f}*PTS"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(colorized),
        "-vf", vf,
    ]

    if has_audio_stream(colorized):
        # atempo > 1 speeds up audio, atempo < 1 slows it down (inverse of setpts)
        atempo_speed = col_dur / orig_dur
        remaining = atempo_speed
        atempo_filters = []
        while remaining > 2.0:
            atempo_filters.append("atempo=2.0")
            remaining /= 2.0
        while remaining < 0.5:
            atempo_filters.append("atempo=0.5")
            remaining *= 2.0
        atempo_filters.append(f"atempo={remaining:.6f}")
        af = ",".join(atempo_filters)
        cmd += ["-af", af]
    else:
        cmd += ["-an"]

    cmd.append(str(output))

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
