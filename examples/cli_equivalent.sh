#!/bin/bash

# examples/cli_equivalent.sh
# Shows CLI commands equivalent to the Python examples.
# Assumes you have installed ripzilla (`pip install .` from root)
# and have the test video available.

set -e # Exit on error

VIDEO_URL="https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4"
VIDEO_URL_2="https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerJoyrides.mp4"
LOCAL_VIDEO="../tests/sample_video.mp4"
OUTPUT_DIR="./output"

mkdir -p "$OUTPUT_DIR"

echo "--- Basic Usage Equivalents --- "

echo "[CLI] basic_usage.py - Example 1: URL Default"
ripzilla "$VIDEO_URL" "$OUTPUT_DIR/cli_audio_from_url.aac"

echo "\n[CLI] basic_usage.py - Example 2: Local Default (MP3 output)"
if [ -f "$LOCAL_VIDEO" ]; then
  ripzilla "$LOCAL_VIDEO" "$OUTPUT_DIR/cli_audio_from_local.mp3"
else
  echo "  Skipping local file test, video not found at $LOCAL_VIDEO"
fi

echo "\n--- Custom Settings Equivalents --- "

echo "[CLI] custom_settings.py - Example 1: Low Quality, CPU, Long Timeout"
ripzilla "$VIDEO_URL_2" "$OUTPUT_DIR/cli_audio_low_cpu.opus" --quality low --hwaccel cpu --ffmpeg-timeout 900 -v

echo "\n[CLI] custom_settings.py - Example 2: High Quality, Auto HWAccel (Local)"
if [ -f "$LOCAL_VIDEO" ]; then
  ripzilla "$LOCAL_VIDEO" "$OUTPUT_DIR/cli_audio_high_auto.aac" --quality high --hwaccel auto
else
  echo "  Skipping local file test, video not found at $LOCAL_VIDEO"
fi

echo "\n--- Error Handling Equivalents (Examples) --- "

echo "[CLI] error_handling.py - Example 1: Invalid URL (expect error code 6)"
ripzilla http://invalid.url.that.does.not.exist/video.mp4 "$OUTPUT_DIR/cli_error_invalid_url.aac" || echo "  Expected error code $? for invalid URL"

echo "\n[CLI] error_handling.py - Example 2: Invalid Local Path (expect error code 1)"
ripzilla /non/existent/path/video.mp4 "$OUTPUT_DIR/cli_error_invalid_local.aac" || echo "  Expected error code $? for invalid path"

# Note: Testing no audio, timeout, disk space errors via CLI requires specific setup or files.

echo "\nExamples finished." 