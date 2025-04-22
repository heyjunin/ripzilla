import requests
import logging
import shutil
import subprocess
import tempfile
import os
import sys
import functools

# Import new exceptions
from .exceptions import FFprobeError, NetworkError, RipzillaTimeoutError, NoAudioStreamError, DiskSpaceError

logger = logging.getLogger(__name__)

DEFAULT_FFPROBE_TIMEOUT = 120 # Default 2 minutes
DEFAULT_DOWNLOAD_TIMEOUT = 60 # Default 1 minute for connection/initial response


def check_media_tools_installed():
    """Checks if ffmpeg and ffprobe are installed and accessible in the system PATH."""
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")

    if not ffmpeg_path:
        logger.error("ffmpeg not found. Please ensure ffmpeg is installed and in your system's PATH.")
        raise FileNotFoundError("ffmpeg executable not found in PATH. Ripzilla requires ffmpeg.")
    if not ffprobe_path:
        logger.error("ffprobe not found. Please ensure ffprobe is installed and in your system's PATH (usually comes with ffmpeg).")
        raise FileNotFoundError("ffprobe executable not found in PATH. Ripzilla requires ffprobe to check for audio streams.")

    logger.debug(f"ffmpeg found at: {ffmpeg_path}")
    logger.debug(f"ffprobe found at: {ffprobe_path}")
    return True


def has_audio_stream(input_path_or_url: str, timeout: int = DEFAULT_FFPROBE_TIMEOUT) -> bool:
    """Checks if the input video source has at least one audio stream using ffprobe."""
    logger.info(f"Checking for audio streams in: {input_path_or_url} (timeout={timeout}s)")
    cmd = [
        "ffprobe",
        "-v", "error",        # Only show errors
        "-select_streams", "a", # Select only audio streams
        "-show_entries", "stream=codec_type", # Show the stream type (should be 'audio')
        "-of", "csv=p=0",      # Output format: CSV, no printing of section header
        input_path_or_url
    ]
    try:
        # Use the provided timeout
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)

        # ffprobe returns non-zero if the file is invalid or no streams are found.
        if result.returncode == 0 and 'audio' in result.stdout.lower():
            logger.debug(f"Audio stream detected in {input_path_or_url}")
            return True
        else:
            # Use specific exception for clarity
            if result.returncode != 0:
                 logger.warning(f"ffprobe command failed (code {result.returncode}) checking for audio streams in {input_path_or_url}.")
                 logger.debug(f"ffprobe stderr: {result.stderr}")
                 # Raise specific error for ffprobe failure
                 raise FFprobeError(f"ffprobe failed (code {result.returncode}): {result.stderr or 'No stderr output'}")
            else:
                # Return code was 0 but no 'audio' found in output
                 logger.warning(f"No audio stream detected in {input_path_or_url}.")
                 return False # No specific exception, just return False

    except subprocess.TimeoutExpired:
        error_message = f"ffprobe command timed out after {timeout} seconds checking for audio streams in {input_path_or_url}"
        logger.error(error_message)
        raise RipzillaTimeoutError(error_message)
    except Exception as e:
        error_message = f"An unexpected error occurred while running ffprobe: {e}"
        logger.error(error_message, exc_info=True)
        # Wrap in FFprobeError
        raise FFprobeError(error_message) from e


@functools.lru_cache(maxsize=1)
def detect_best_hwaccel() -> str | None:
    """
    Detects the best available ffmpeg hardware acceleration method for the current platform.
    Currently checks for VideoToolbox on macOS. TODO: Add checks for CUDA/NVENC/NVDEC on Linux/Windows.
    Caches the result.
    Returns the name of the hwaccel method (e.g., 'videotoolbox') or None.
    """
    if sys.platform != 'darwin':
        logger.debug("Hardware acceleration check skipped: Not on macOS.")
        return None

    logger.debug("Checking for supported ffmpeg hardware acceleration on macOS...")
    cmd = ["ffmpeg", "-hwaccels"]
    try:
        # Short timeout for this check
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=15)
        available_hwaccels = result.stdout.strip().split('\n')[1:] # Skip header line
        logger.debug(f"Available ffmpeg hwaccels: {available_hwaccels}")
        if "videotoolbox" in available_hwaccels:
            logger.info("VideoToolbox hardware acceleration detected.")
            return "videotoolbox"
        else:
            logger.info("VideoToolbox not found in ffmpeg hardware accelerators.")
            return None
    except FileNotFoundError:
        logger.warning("Cannot check for hardware acceleration: ffmpeg not found.")
        return None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.warning(f"Failed to check ffmpeg hwaccels: {e}")
        if hasattr(e, 'stderr'):
            logger.debug(f"ffmpeg -hwaccels stderr: {e.stderr}")
        return None
    except Exception as e:
        logger.warning(f"An unexpected error occurred checking ffmpeg hwaccels: {e}")
        return None


def _check_disk_space(check_path: str, min_required_gb: float = 1.0):
    """Checks if the specified path has at least min_required_gb free space."""
    try:
        usage = shutil.disk_usage(check_path)
        free_gb = usage.free / (1024**3)
        logger.debug(f"Checking disk space for {check_path}. Free: {free_gb:.2f} GB")
        if free_gb < min_required_gb:
            error_message = f"Insufficient disk space in {check_path}. Required: >{min_required_gb} GB, Available: {free_gb:.2f} GB"
            logger.error(error_message)
            raise DiskSpaceError(error_message)
        return True
    except FileNotFoundError:
        logger.warning(f"Could not check disk space: Path not found {check_path}")
        # If we can't check the path, maybe proceed cautiously?
        # For now, let's assume it's okay if the path doesn't exist yet.
        return True
    except DiskSpaceError as dse:
        # Explicitly re-raise DiskSpaceError if it was raised by the check
        raise dse
    except Exception as e:
        logger.warning(f"Could not check disk space for {check_path}: {e}")
        # If any other error occurs during check, log warning but proceed
        return True


def download_video(url: str, output_path: str, timeout: int = DEFAULT_DOWNLOAD_TIMEOUT):
    """Downloads a video from a URL to a local path."""
    logger.info(f"Attempting to download video from {url} to {output_path} (conn timeout={timeout}s)")
    try:
        # Timeout applies to establishing connection and first byte, not total download time
        with requests.get(url, stream=True, timeout=timeout) as r:
            r.raise_for_status()  # Raise an exception for bad status codes (HTTPError)
            with open(output_path, "wb") as f:
                # TODO: Consider adding a total download timeout? More complex.
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        logger.info(f"Successfully downloaded video to {output_path}")
    except requests.exceptions.Timeout as e:
        error_message = f"Connection timed out after {timeout} seconds while trying to download {url}"
        logger.error(error_message)
        # Raise our specific timeout error, wrapping the original
        raise RipzillaTimeoutError(error_message) from e
    except requests.exceptions.RequestException as e:
        error_message = f"Failed to download video from {url}: {e}"
        logger.error(error_message)
        # Wrap requests exceptions in our NetworkError
        raise NetworkError(error_message) from e 