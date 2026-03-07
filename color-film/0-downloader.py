#!/usr/bin/env python3
"""
Download a YouTube video (video-only, no audio) and save it in the color-film folder.
"""

import argparse
import sys
from pathlib import Path

import yt_dlp


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download a YouTube video (video-only, no audio) to the color-film folder."
    )
    parser.add_argument(
        "url",
        help="YouTube video URL",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=None,
        help="Output directory (default: color-film folder)",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    output_dir = args.output_dir.resolve() if args.output_dir else script_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "format": "bestvideo[ext=mp4]/bestvideo",
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
        "quiet": False,
        "no_warnings": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([args.url])
    except yt_dlp.utils.DownloadError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
