#!/usr/bin/env python3
"""
Download a YouTube video (video-only, no audio) and save it in the color-film folder.

YouTube may only expose combined video+audio streams (m3u8/HLS). In that case the
script downloads the best available mp4 and strips the audio track with ffmpeg.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import yt_dlp


def strip_audio(path: Path) -> None:
    """Replace file with an audio-stripped copy using ffmpeg."""
    tmp = path.with_suffix(".noaudio.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(path), "-an", "-c:v", "copy", str(tmp)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    tmp.replace(path)
    print(f"Audio stripped: {path.name}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download a YouTube video (video-only, no audio) to the color-film folder."
    )
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=None,
        help="Output directory (default: color-film folder)",
    )
    parser.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        default=None,
        help="Use cookies from a browser (e.g. safari, chrome, firefox) to bypass bot detection",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    output_dir = args.output_dir.resolve() if args.output_dir else script_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded_files: list[Path] = []

    class TrackDownload(yt_dlp.YoutubeDL):
        def process_info(self, info_dict):
            result = super().process_info(info_dict)
            filepath = info_dict.get("filepath") or info_dict.get("_filename")
            if filepath:
                downloaded_files.append(Path(filepath))
            return result

    ydl_opts = {
        # Prefer video-only streams; fall back to combined stream (m3u8/https)
        "format": "bestvideo[ext=mp4]/bestvideo/best[ext=mp4]/best",
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
        "quiet": False,
        "no_warnings": False,
    }
    if args.cookies_from_browser:
        ydl_opts["cookiesfrombrowser"] = (args.cookies_from_browser,)

    try:
        with TrackDownload(ydl_opts) as ydl:
            info = ydl.extract_info(args.url, download=True)
            # Resolve final filepath from info dict
            filepath = ydl.prepare_filename(info)
            downloaded_files.append(Path(filepath))
    except yt_dlp.utils.DownloadError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Strip audio from every downloaded file (in case a combined stream was used)
    for fp in set(downloaded_files):
        if fp.exists() and fp.suffix in {".mp4", ".webm", ".mkv"}:
            has_audio = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "a",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(fp)],
                capture_output=True, text=True,
            ).stdout.strip()
            if has_audio:
                strip_audio(fp)
            else:
                print(f"No audio track found, skipping strip: {fp.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
