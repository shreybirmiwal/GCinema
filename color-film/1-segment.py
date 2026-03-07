#!/usr/bin/env python3
"""
Segment an MP4 video into clips at scene boundaries.

Splits the video where the camera has moved to a different scene (not character/object
movement within the same scene). Uses PySceneDetect's AdaptiveDetector to reduce false
positives from camera motion (pan, tilt, zoom) within a single scene.
"""

import argparse
import sys
from pathlib import Path

from scenedetect import detect, AdaptiveDetector
from scenedetect.video_splitter import split_video_ffmpeg, is_ffmpeg_available


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Segment an MP4 video into clips at scene boundaries (camera moves to different scene)."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to input MP4 video",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=None,
        help="Directory for output clips (default: same as input)",
    )
    parser.add_argument(
        "--min-scene-len",
        type=int,
        default=15,
        metavar="FRAMES",
        help="Minimum scene length in frames (default: 15)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=3.0,
        metavar="FLOAT",
        help="Adaptive threshold for scene cuts; higher = fewer cuts (default: 3.0)",
    )
    parser.add_argument(
        "--min-content-val",
        type=float,
        default=15.0,
        metavar="FLOAT",
        help="Minimum content change to register a cut (default: 15.0)",
    )
    parser.add_argument(
        "--no-split",
        action="store_true",
        help="Only detect and list scenes, do not split video",
    )
    parser.add_argument(
        "--show-progress",
        action="store_true",
        help="Show progress bar during detection",
    )
    args = parser.parse_args()

    input_path = args.input.resolve()
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        return 1
    if not input_path.is_file():
        print(f"Error: Input path is not a file: {input_path}", file=sys.stderr)
        return 1

    output_dir = args.output_dir.resolve() if args.output_dir else input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    detector = AdaptiveDetector(
        adaptive_threshold=args.threshold,
        min_scene_len=args.min_scene_len,
        min_content_val=args.min_content_val,
    )

    print(f"Detecting scenes in: {input_path}")
    scene_list = detect(
        str(input_path),
        detector,
        show_progress=args.show_progress,
        start_in_scene=True,
    )

    if not scene_list:
        print("No scenes detected. Video may be empty or unreadable.", file=sys.stderr)
        return 1

    print(f"\nDetected {len(scene_list)} scene(s):")
    for i, (start, end) in enumerate(scene_list, 1):
        print(f"  Scene {i:3d}: {start.get_timecode()} - {end.get_timecode()}")

    if args.no_split:
        return 0

    if not is_ffmpeg_available():
        print(
            "\nError: FFmpeg is required for splitting but was not found. "
            "Install FFmpeg and ensure it is in your PATH.",
            file=sys.stderr,
        )
        return 1

    print(f"\nSplitting video into clips in: {output_dir}")
    result = split_video_ffmpeg(
        str(input_path),
        scene_list,
        output_dir=str(output_dir),
        output_file_template="$VIDEO_NAME-Scene-$SCENE_NUMBER.mp4",
        show_progress=args.show_progress,
    )

    if result != 0:
        print("Error: FFmpeg split failed.", file=sys.stderr)
        return 1

    video_name = input_path.stem
    print(f"\nDone. Created {len(scene_list)} clip(s):")
    for i in range(1, len(scene_list) + 1):
        print(f"  {video_name}-Scene-{i:03d}.mp4")

    return 0


if __name__ == "__main__":
    sys.exit(main())
