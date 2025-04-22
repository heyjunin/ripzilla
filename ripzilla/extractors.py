from tenacity import retry, stop_after_attempt, wait_exponential, RetryError
import subprocess
import os
import tempfile
import logging
from typing import Literal, Dict, List
from .utils import download_video, _check_disk_space, detect_best_hwaccel
from .exceptions import ExtractionError, FFmpegError, RipzillaTimeoutError, NetworkError, DiskSpaceError

logger = logging.getLogger(__name__)

# --- Constants ---
DEFAULT_FFMPEG_TIMEOUT = 600 # Default 10 minutes

# Base FFMPEG command parts (to be assembled)
# Note: -i {input} and {output} are added dynamically
# Note: -vn is crucial for audio-only extraction
BASE_FFMPEG_PARTS = ["ffmpeg", "-y"]
INPUT_FLAG = ["-i", "{input}"]
VIDEO_DISABLE_FLAGS = ["-vn"]
OUTPUT_PATH = ["{output}"]

# Preset definitions (ffmpeg flags)
# Raw: Direct copy
# High: AAC ~192k (good balance)
# Medium: AAC ~128k (standard)
# Low: Opus ~64k, mono, 16kHz sample rate, high-pass filter (optimized for voice/STT)
#      Opus is generally better than AAC/MP3 at lower bitrates.
#      `-af highpass=f=200`: Removes very low frequencies (rumble)
#      `-ar 16000`: Reduces sample rate (saves space, enough for voice)
AUDIO_PRESETS: Dict[str, List[str]] = {
    "raw": ["-acodec", "copy"],
    "high": ["-acodec", "aac", "-b:a", "192k"],
    "medium": ["-acodec", "aac", "-b:a", "128k"],
    "low": ["-acodec", "libopus", "-b:a", "64k", "-ar", "16000", "-ac", "1", "-af", "highpass=f=200"]
}

# Helper function to build the command
def _build_ffmpeg_cmd(
    input_path: str,
    output_path: str,
    quality: str,
    hwaccel: str | None
) -> List[str]:
    """Builds the full ffmpeg command list based on inputs and presets."""
    if quality not in AUDIO_PRESETS:
        raise ValueError(f"Invalid audio quality preset: {quality}. Valid presets: {list(AUDIO_PRESETS.keys())}")

    cmd_parts = BASE_FFMPEG_PARTS.copy()

    # Add HWAccel flags before input if specified
    if hwaccel:
        logger.info(f"Using {hwaccel} hardware acceleration.")
        cmd_parts.extend(["-hwaccel", hwaccel])
    else:
         logger.info("Using CPU for extraction (no HWAccel detected or mode is cpu).")

    # Add input flag and path
    cmd_parts.extend([flag.format(input=input_path) for flag in INPUT_FLAG])

    # Add video disable and audio preset flags
    cmd_parts.extend(VIDEO_DISABLE_FLAGS)
    cmd_parts.extend(AUDIO_PRESETS[quality])

    # Add output path
    cmd_parts.append(output_path) # Output path doesn't need formatting

    return cmd_parts

def _run_ffmpeg(cmd: list[str], output_path: str, timeout: int = DEFAULT_FFMPEG_TIMEOUT):
    """Runs an ffmpeg command and checks for errors."""
    logger.info(f"Running ffmpeg command (timeout={timeout}s): {' '.join(cmd)}")
    try:
        # Using PIPE for stdout/stderr to capture ffmpeg's output for logging/debugging
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, text=True, timeout=timeout)

        # Check if ffmpeg command executed successfully
        if result.returncode != 0:
            error_message = f"FFmpeg command failed with code {result.returncode}: {' '.join(cmd)}\nStderr: {result.stderr}"
            logger.error(error_message)
            # Attempt to delete potentially incomplete output file
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                    logger.info(f"Removed incomplete output file: {output_path}")
                except OSError as remove_err:
                    logger.warning(f"Could not remove incomplete file {output_path}: {remove_err}")
            raise FFmpegError(error_message)

        # Even if return code is 0, double-check if the output file was actually created and is not empty
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            error_message = f"FFmpeg command seemed successful, but output file {output_path} is missing or empty.\nStderr: {result.stderr}"
            logger.error(error_message)
            logger.error(f"FFmpeg stdout: {result.stdout}") # Log stdout only on this specific error
            raise FFmpegError(error_message)

        logger.info(f"FFmpeg command successful. Output created at: {output_path}")

    except subprocess.TimeoutExpired:
        error_message = f"FFmpeg command timed out after {timeout} seconds: {' '.join(cmd)}"
        logger.error(error_message)
        raise RipzillaTimeoutError(error_message)
    except Exception as e:
        # Catch-all for other unexpected errors during subprocess execution
        logger.error(f"An unexpected error occurred while running FFmpeg: {e}", exc_info=True)
        # Wrap in FFmpegError for consistency?
        raise FFmpegError(f"An unexpected error occurred while running FFmpeg: {e}") from e


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
def try_stream_extract(
    url: str,
    output_path: str,
    ffmpeg_timeout: int = DEFAULT_FFMPEG_TIMEOUT,
    hwaccel_mode: Literal["auto", "gpu", "cpu"] = "auto",
    quality: str = "raw" # Add quality parameter
):
    """Attempts to extract audio directly from a URL stream using ffmpeg."""
    logger.info(f"Attempting streaming extraction for {url} -> {output_path} (Quality: {quality}, HWAccel: {hwaccel_mode})")

    # Determine hwaccel to use based on mode
    hwaccel_to_use = None
    if hwaccel_mode != "cpu":
        detected_hwaccel = detect_best_hwaccel()
        if hwaccel_mode == "auto" and detected_hwaccel:
            hwaccel_to_use = detected_hwaccel
        elif hwaccel_mode == "gpu":
            if detected_hwaccel:
                hwaccel_to_use = detected_hwaccel
            else:
                logger.warning("GPU acceleration requested, but no compatible method detected. Using CPU.")

    # Build command using helper
    try:
        cmd = _build_ffmpeg_cmd(url, output_path, quality, hwaccel_to_use)
    except ValueError as e:
        logger.error(f"Failed to build command: {e}")
        raise e # Re-raise configuration error immediately

    # Run ffmpeg
    try:
        _run_ffmpeg(cmd, output_path, timeout=ffmpeg_timeout)
        logger.info(f"Streaming extraction successful for {url}")
    except (FFmpegError, RipzillaTimeoutError) as e:
        logger.warning(f"Streaming extraction attempt failed for {url}: {e}")
        raise


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
def try_local_extract(
    local_path: str,
    output_path: str,
    ffmpeg_timeout: int = DEFAULT_FFMPEG_TIMEOUT,
    hwaccel_mode: Literal["auto", "gpu", "cpu"] = "auto",
    quality: str = "raw" # Add quality parameter
):
    """Attempts to extract audio from a local file using ffmpeg."""
    logger.info(f"Attempting local extraction for {local_path} -> {output_path} (Quality: {quality}, HWAccel: {hwaccel_mode})")
    if not os.path.exists(local_path):
         logger.error(f"Input file not found: {local_path}")
         raise FileNotFoundError(f"Input file not found: {local_path}")

    # Determine hwaccel to use
    hwaccel_to_use = None
    if hwaccel_mode != "cpu":
        detected_hwaccel = detect_best_hwaccel()
        if hwaccel_mode == "auto" and detected_hwaccel:
            hwaccel_to_use = detected_hwaccel
        elif hwaccel_mode == "gpu":
            if detected_hwaccel:
                hwaccel_to_use = detected_hwaccel
            else:
                logger.warning("GPU acceleration requested, but no compatible method detected. Using CPU.")

    # Build command
    try:
        cmd = _build_ffmpeg_cmd(local_path, output_path, quality, hwaccel_to_use)
    except ValueError as e:
        logger.error(f"Failed to build command: {e}")
        raise e

    # Run ffmpeg
    try:
        _run_ffmpeg(cmd, output_path, timeout=ffmpeg_timeout)
        logger.info(f"Local extraction successful for {local_path}")
    except (FFmpegError, RipzillaTimeoutError) as e:
        logger.warning(f"Local extraction attempt failed for {local_path}: {e}")
        raise


def fallback_download_extract(
    url: str,
    output_path: str,
    ffmpeg_timeout: int = DEFAULT_FFMPEG_TIMEOUT,
    hwaccel_mode: Literal["auto", "gpu", "cpu"] = "auto",
    quality: str = "raw" # Pass quality through
):
    """Downloads the video and then extracts audio locally as a fallback."""
    # Quality and HWAccel mode are passed down to try_local_extract
    logger.warning(f"Streaming failed for {url}. Falling back to download and extract.")
    temp_video_file = None
    try:
        # --- Check disk space in temp dir BEFORE creating file --- 
        temp_dir = tempfile.gettempdir()
        _check_disk_space(temp_dir) # Use default check (1GB free in temp dir)
        # ---------------------------------------------------------

        # Now create the temp file and download
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, dir=temp_dir) as tmp:
            temp_video_file = tmp.name
            logger.info(f"Downloading to temporary file: {temp_video_file}")
            download_video(url, temp_video_file) # Raises NetworkError on failure

        # Now try extracting from the downloaded file
        logger.info(f"Download complete. Attempting local extraction from {temp_video_file}")
        # Pass the timeout, hwaccel_mode AND quality to the local extraction attempt
        try_local_extract(
            temp_video_file,
            output_path,
            ffmpeg_timeout=ffmpeg_timeout,
            hwaccel_mode=hwaccel_mode,
            quality=quality # Pass quality
        )
        logger.info(f"Fallback extraction successful for {url}")

    # Catch specific errors including DiskSpaceError
    except (DiskSpaceError, NetworkError, FileNotFoundError, FFmpegError, RipzillaTimeoutError, RetryError) as e:
        logger.error(f"Fallback download/extract failed for {url}: {e}")
        # Re-raise specific errors or wrap others
        if isinstance(e, (DiskSpaceError, NetworkError, FFmpegError, RipzillaTimeoutError)):
             raise
        else: # Wrap RetryError, FileNotFoundError etc.
            raise ExtractionError(f"Fallback extraction failed for {url}") from e
    finally:
        # Ensure the temporary file is always deleted
        if temp_video_file and os.path.exists(temp_video_file):
            try:
                os.unlink(temp_video_file)
                logger.info(f"Cleaned up temporary file: {temp_video_file}")
            except OSError as e:
                logger.error(f"Error deleting temporary file {temp_video_file}: {e}") 