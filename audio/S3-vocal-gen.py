#!/usr/bin/env python3
"""
Generate a foley/vocal audio track from timestamped audio events (output of S1 --output-lipsync).

For each event:
  - type "speech"  → ElevenLabs TTS  (the utterance, e.g. "Help!", "Ouch!")
  - type "sfx"     → ElevenLabs Sound Effects Generation  (e.g. "wooden floorboard creak")

All clips are placed at their timestamps and mixed into a single WAV track.
That track can be layered on top of the S2 music output.

Requirements:
  pip install elevenlabs pydub
  brew install ffmpeg   # or apt-get install ffmpeg  (needed by pydub for MP3 decode)

Usage:
  python S3-vocal-gen.py audio_events.json -o foley.wav --duration 60

  # With a specific ElevenLabs voice for speech:
  python S3-vocal-gen.py audio_events.json -o foley.wav --voice "Rachel"
"""

import argparse
import io
import json
import os
import sys
import tempfile
from pathlib import Path

from pydub import AudioSegment

# ---------------------------------------------------------------------------
# Voice assignment — consistent per character, gendered
# ---------------------------------------------------------------------------

# Pre-made ElevenLabs voice IDs
FEMALE_VOICES = [
    "21m00Tcm4TlvDq8ikWAM",  # Rachel
    "EXAVITQu4vr4xnSDxMaL",  # Bella
    "MF3mGyEYCl7XYWbV9V6O",  # Elli
]
MALE_VOICES = [
    "pNInz6obpgDQGcFmaJgB",  # Adam
    "ErXwobaYiN019PkySvjV",  # Antoni
    "VR6AewLTigWG4xSOukaG",  # Arnold
]

FEMALE_KEYWORDS = {"woman", "female", "girl", "lady", "she", "her", "mrs", "miss", "ms"}
MALE_KEYWORDS   = {"man", "male", "boy", "guy", "he", "him", "mr", "sir", "charlie", "chaplin"}

_char_voice_cache: dict[str, str] = {}
_female_idx = 0
_male_idx = 0

def pick_voice(character: str, gender: str | None = None) -> str:
    """Return a consistent ElevenLabs voice ID for a character.
    Uses explicit gender field if provided, otherwise infers from description keywords."""
    global _female_idx, _male_idx
    key = character.lower().strip()
    if key in _char_voice_cache:
        return _char_voice_cache[key]

    if gender and gender.lower() == "female":
        is_female = True
    elif gender and gender.lower() == "male":
        is_female = False
    else:
        words = set(key.replace(",", " ").replace("-", " ").split())
        is_female = bool(words & FEMALE_KEYWORDS)

    if is_female:
        voice = FEMALE_VOICES[_female_idx % len(FEMALE_VOICES)]
        _female_idx += 1
    else:
        voice = MALE_VOICES[_male_idx % len(MALE_VOICES)]
        _male_idx += 1

    _char_voice_cache[key] = voice
    return voice


# ---------------------------------------------------------------------------
# ElevenLabs helpers
# ---------------------------------------------------------------------------

def _elevenlabs_client(api_key: str):
    try:
        from elevenlabs.client import ElevenLabs
    except ImportError:
        print("Error: elevenlabs package not found. Run: pip install elevenlabs", file=sys.stderr)
        sys.exit(1)
    return ElevenLabs(api_key=api_key)


def generate_speech(client, utterance: str, voice: str) -> bytes:
    """Return MP3 bytes for a spoken utterance via ElevenLabs TTS."""
    audio_iter = client.text_to_speech.convert(
        text=utterance,
        voice_id=voice,
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
    )
    return b"".join(audio_iter)


def generate_sfx(client, description: str, duration_sec: float) -> bytes:
    """Return MP3 bytes for a sound effect via ElevenLabs Sound Generation."""
    response = client.text_to_sound_effects.convert(
        text=description,
        duration_seconds=max(0.5, min(duration_sec, 22.0)),  # API range: 0.5–22s
        prompt_influence=0.4,
    )
    return b"".join(response)


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def mp3_to_segment(mp3_bytes: bytes) -> AudioSegment:
    return AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")


def build_track(events: list[dict], duration_ms: int, voice: str, api_key: str) -> AudioSegment:
    """Generate each event and overlay it at the correct timestamp."""
    client = _elevenlabs_client(api_key)

    # Stereo silent canvas
    track = AudioSegment.silent(duration=duration_ms, frame_rate=44100).set_channels(2)

    speech_events = [e for e in events if e.get("type") == "speech"]
    sfx_events    = [e for e in events if e.get("type") == "sfx"]
    print(f"Events: {len(speech_events)} speech, {len(sfx_events)} sfx")

    for i, event in enumerate(events):
        ts_ms = int(event.get("timestamp_sec", 0) * 1000)
        kind  = event.get("type", "sfx")
        conf  = event.get("confidence", "medium")

        # Skip low-confidence SFX to avoid noise
        # For speech: only skip if the utterance is empty or "..."
        if kind == "sfx" and conf == "low":
            print(f"  [{i+1}/{len(events)}] Skipping low-confidence sfx at {ts_ms/1000:.1f}s")
            continue
        if kind == "speech":
            utterance = event.get("utterance", "").strip().strip(".")
            if not utterance:
                print(f"  [{i+1}/{len(events)}] Skipping empty speech at {ts_ms/1000:.1f}s")
                continue

        try:
            if kind == "speech":
                utterance = event.get("utterance", "")
                char      = event.get("character", "character")
                gender    = event.get("gender")
                char_voice = pick_voice(char, gender)
                print(f"  [{i+1}/{len(events)}] TTS  \"{utterance}\" ({char}, {gender or '?'}) [voice:{char_voice[:8]}] @ {ts_ms/1000:.1f}s ...")
                mp3 = generate_speech(client, utterance, char_voice)
            else:
                desc     = event.get("description", "sound effect")
                dur_hint = event.get("duration_sec", 2.0)
                print(f"  [{i+1}/{len(events)}] SFX  \"{desc}\" @ {ts_ms/1000:.1f}s ...")
                mp3 = generate_sfx(client, desc, dur_hint)

            seg = mp3_to_segment(mp3)

            # Trim to duration_sec if specified (avoids overrun for short sfx)
            max_dur = event.get("duration_sec")
            if max_dur and kind == "sfx":
                seg = seg[: int(max_dur * 1000)]

            # Extend canvas if the event goes past the current end
            needed = ts_ms + len(seg)
            if needed > len(track):
                track = track + AudioSegment.silent(duration=needed - len(track), frame_rate=44100).set_channels(2)

            track = track.overlay(seg, position=ts_ms)

        except Exception as exc:
            print(f"  Warning: failed to generate {kind} event #{i+1}: {exc}", file=sys.stderr)

    return track


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a foley/vocal audio track from S1 audio_events JSON."
    )
    parser.add_argument(
        "events",
        type=Path,
        help="Path to audio_events JSON file (output of S1 --output-lipsync)",
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=Path("foley.wav"),
        help="Output WAV file path (default: foley.wav)",
    )
    parser.add_argument(
        "--duration", "-d", type=float, default=None,
        help="Total track duration in seconds. Defaults to last event timestamp + 5s.",
    )
    parser.add_argument(
        "--voice", default="cgSgspJ2msm6clMCkdW9",
        help="ElevenLabs voice ID or name for speech events (default: Adam)",
    )
    parser.add_argument(
        "--api-key", default=None,
        help="ElevenLabs API key (defaults to ELEVENLABS_API_KEY env var)",
    )
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        print(
            "Error: No ElevenLabs API key. Set ELEVENLABS_API_KEY or pass --api-key.",
            file=sys.stderr,
        )
        return 1

    if not args.events.exists():
        print(f"Error: events file not found: {args.events}", file=sys.stderr)
        return 1

    events = json.loads(args.events.read_text(encoding="utf-8"))
    if not events:
        print("No audio events found in input file.", file=sys.stderr)
        return 1

    # Sort chronologically just in case
    events.sort(key=lambda e: e.get("timestamp_sec", 0))

    # Determine canvas duration
    if args.duration:
        duration_ms = int(args.duration * 1000)
    else:
        last_ts = max(e.get("timestamp_sec", 0) + e.get("duration_sec", 2) for e in events)
        duration_ms = int((last_ts + 5) * 1000)

    print(f"Building foley track — {len(events)} events over {duration_ms/1000:.1f}s ...")

    try:
        track = build_track(events, duration_ms, args.voice, api_key)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Export as WAV
    track.export(str(args.output), format="wav")
    print(f"\nFoley track saved to: {args.output}  ({len(track)/1000:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
