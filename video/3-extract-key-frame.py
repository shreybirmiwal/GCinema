#!/usr/bin/env python3
"""
Extract the first frame of a video clip as a PNG screenshot.
"""

import argparse
import sys
import subprocess
from pathlib import Path


def extract_first_frame(input_path: Path, output_path: Path) -> None:
    cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-vframes", "1",
        "-q:v", "2",
        str(output_path),
        "-y",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error:\n{result.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract the first frame of a video clip as a PNG image."
    )
    parser.add_argument("input", type=Path, help="Path to input video file")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Path to output image (default: <input_stem>_frame0.png)",
    )
    args = parser.parse_args()

    input_path = args.input.resolve()
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        return 1

    output_path = args.output or input_path.with_name(f"{input_path.stem}_frame0.png")

    try:
        extract_first_frame(input_path, output_path)
        print(f"Frame saved to: {output_path}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
