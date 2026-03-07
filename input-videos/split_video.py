#!/usr/bin/env python3
"""
split_video.py - Split an MP4 into chunks based on timestamps.

Usage:
    python split_video.py <input.mp4> <start1>-<end1> <start2>-<end2> ...

Timestamps can be in seconds (e.g. 30) or MM:SS or HH:MM:SS format.

Examples:
    python split_video.py movie.mp4 0-1:30 1:30-3:00 3:00-5:45
    python split_video.py movie.mp4 0-90 90-180 180-345
    python split_video.py movie.mp4 0:00:00-0:01:30 0:01:30-0:03:00
"""

import sys
import os
import subprocess


def parse_timestamp(ts: str) -> float:
    """Convert timestamp string to seconds (float)."""
    ts = ts.strip()
    parts = ts.split(":")
    if len(parts) == 1:
        return float(parts[0])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    else:
        raise ValueError(f"Invalid timestamp format: {ts}")


def seconds_to_ffmpeg(secs: float) -> str:
    """Convert seconds to HH:MM:SS.mmm for ffmpeg."""
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = secs % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def split_video(input_path: str, segments: list[tuple[float, float]]):
    if not os.path.isfile(input_path):
        print(f"Error: file not found: {input_path}")
        sys.exit(1)

    base = os.path.splitext(os.path.basename(input_path))[0]
    out_dir = os.path.dirname(os.path.abspath(input_path))

    print(f"Splitting '{input_path}' into {len(segments)} chunk(s)...\n")

    for i, (start, end) in enumerate(segments, 1):
        duration = end - start
        if duration <= 0:
            print(f"  [chunk {i}] Skipping — end ({end}s) is not after start ({start}s)")
            continue

        out_name = f"{base}_chunk{i:02d}_{seconds_to_ffmpeg(start).replace(':', '-')}.mp4"
        out_path = os.path.join(out_dir, out_name)

        cmd = [
            "ffmpeg", "-y",
            "-ss", seconds_to_ffmpeg(start),
            "-i", input_path,
            "-t", str(duration),
            "-c", "copy",
            out_path
        ]

        print(f"  [chunk {i}] {seconds_to_ffmpeg(start)} -> {seconds_to_ffmpeg(end)}  =>  {out_name}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"    ffmpeg error:\n{result.stderr}")
        else:
            print(f"    Done.")

    print("\nAll chunks complete.")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    input_path = sys.argv[1]
    raw_segments = sys.argv[2:]

    segments = []
    for seg in raw_segments:
        if "-" not in seg:
            print(f"Error: segment '{seg}' must be in 'start-end' format (e.g. 0-1:30)")
            sys.exit(1)
        # Split on the last occurrence isn't needed; split on first '-' that separates timestamps
        # Timestamps won't have '-' in them, so split on '-' is fine — but MM:SS has ':' not '-'
        # Edge case: negative numbers not supported (timestamps are always positive)
        dash_idx = seg.index("-")
        start_str = seg[:dash_idx]
        end_str = seg[dash_idx + 1:]
        try:
            start = parse_timestamp(start_str)
            end = parse_timestamp(end_str)
        except ValueError as e:
            print(f"Error parsing segment '{seg}': {e}")
            sys.exit(1)
        segments.append((start, end))

    split_video(input_path, segments)


if __name__ == "__main__":
    main()
