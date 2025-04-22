import logging
from tenacity import RetryError
import os
from typing import Literal
from dataclasses import dataclass, field
import time

from .extractors import try_stream_extract, try_local_extract, fallback_download_extract, DEFAULT_FFMPEG_TIMEOUT, AUDIO_PRESETS
from .exceptions import (
    ExtractionError, FFmpegError, FFprobeError, NetworkError, RipzillaTimeoutError, NoAudioStreamError, DiskSpaceError
)
from .utils import check_media_tools_installed, has_audio_stream, DEFAULT_FFPROBE_TIMEOUT, detect_best_hwaccel

logger = logging.getLogger(__name__)

# Configure basic logging for the library
# Users of the library can configure this further if needed
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

@dataclass
class ExtractionResult:
    """Holds metadata about a successful audio extraction."""
    output_path: str
    duration: float # Execution time in seconds
    file_size_bytes: int
    quality_preset: str
    hwaccel_used: str | None # e.g., 'videotoolbox' or None for CPU
    input_source: str # Original input path or URL
    ffmpeg_timeout: int
    ffprobe_timeout: int
    # Add more fields if needed, e.g., original file info, ffmpeg logs?

def extract_audio(
    input_path_or_url: str,
    output_audio_path: str,
    ffmpeg_timeout: int = DEFAULT_FFMPEG_TIMEOUT,
    ffprobe_timeout: int = DEFAULT_FFPROBE_TIMEOUT,
    hwaccel_mode: Literal["auto", "gpu", "cpu"] = "auto",
    quality: str = "raw"
) -> ExtractionResult:
    """
    Extracts audio from a video file (local path or URL) to a specified output path.

    Attempts direct streaming extraction for URLs first. If that fails, it falls back
    to downloading the video to a temporary location and extracting locally.
    Uses retries with exponential backoff for robustness during extraction attempts.

    Args:
        input_path_or_url: Path to the local video file or URL of the video.
        output_audio_path: Path where the extracted audio file will be saved.
        ffmpeg_timeout (int): Timeout in seconds for individual ffmpeg commands (default: 600).
                              Increase for very large/complex files.
        ffprobe_timeout (int): Timeout in seconds for ffprobe commands (default: 120).
        hwaccel_mode (Literal["auto", "gpu", "cpu"]): Hardware acceleration mode (default: "auto").
            "auto": Use best detected GPU acceleration (e.g., VideoToolbox on macOS) if available, else CPU.
            "gpu": Try to use detected GPU acceleration; warn and use CPU if none detected.
            "cpu": Force CPU decoding, do not attempt GPU acceleration.
        quality (str): Audio quality preset (default: "raw").
                     Options: "raw" (copy codec), "high" (AAC ~192k), "medium" (AAC ~128k),
                     "low" (Opus ~64k, mono, 16kHz, filtered for voice).

    Raises:
        ExtractionError: Generic error if extraction fails after all attempts (e.g., retry exhaustion).
        FileNotFoundError: If a local input file does not exist OR if ffmpeg/ffprobe executable is not found in PATH.
        NetworkError: If downloading the video fails due to network issues (wraps requests exceptions).
        NoAudioStreamError: If the input video does not contain a detectable audio stream.
        RipzillaTimeoutError: If ffprobe or ffmpeg commands exceed their respective timeouts.
        FFprobeError: If ffprobe fails for reasons other than timeout or no audio stream.
        FFmpegError: If ffmpeg fails during execution (e.g., invalid format, codec issues).
        DiskSpaceError: If there is insufficient disk space in the system's temporary directory
                        during the fallback download process.
        OSError: For other underlying OS / file system errors.
        ValueError: If an invalid quality preset is provided.

    Returns:
        ExtractionResult: An object containing metadata about the successful extraction.
    """
    start_time = time.monotonic()
    hwaccel_actually_used = None # Track what was actually used

    # --- Prerequisite Checks ---
    is_url = input_path_or_url.lower().startswith(("http://", "https://"))
    try:
        check_media_tools_installed() # Check for ffmpeg and ffprobe

        # --- Check file existence FIRST if it's a local path --- 
        if not is_url and not os.path.exists(input_path_or_url):
            raise FileNotFoundError(f"Input file not found: {input_path_or_url}")
        # ---------------------------------------------------------

        # Now check for audio stream using ffprobe with timeout
        if not has_audio_stream(input_path_or_url, timeout=ffprobe_timeout):
            message = f"Input does not contain an audio stream: {input_path_or_url}"
            logger.warning(message)
            raise NoAudioStreamError(message)

        # --- Validate quality preset early ---
        if quality not in AUDIO_PRESETS:
             raise ValueError(f"Invalid quality preset: {quality}. Valid: {list(AUDIO_PRESETS.keys())}")
        # ----------------------------------

        # Determine potential hwaccel based on mode *before* extraction starts
        # This is for the result object, the extractors re-check
        if hwaccel_mode != "cpu":
             detected = detect_best_hwaccel()
             if detected:
                 hwaccel_actually_used = detected # Assume it will be used if mode is auto/gpu and detected
             elif hwaccel_mode == "gpu":
                 logger.warning("GPU mode requested, but no compatible HWAccel detected. Will use CPU.")
                 # hwaccel_actually_used remains None
        # If mode is cpu, hwaccel_actually_used remains None

    except FileNotFoundError as ff_err:
        # Catches missing tools OR missing local file
        logger.critical(f"Prerequisite check failed: {ff_err}")
        raise # Reraise the specific FileNotFoundError
    except RipzillaTimeoutError as probe_timeout:
        logger.error(f"Failed to check for audio streams: {probe_timeout}")
        raise # Reraise the specific TimeoutError from ffprobe
    except NoAudioStreamError as no_audio_err:
        # Specifically catch the NoAudioStreamError we raised
        raise no_audio_err
    except FFprobeError as probe_err:
         # Catch other ffprobe errors
        logger.error(f"Audio stream check failed: {probe_err}")
        raise probe_err # Reraise the original FFprobeError
    except ValueError as val_err:
        # Catches NoAudioStreamError OR invalid quality preset
        logger.error(f"Input validation failed: {val_err}")
        raise val_err
    # ----------------------------------------

    logger.info(f"Proceeding with audio extraction for {'URL' if is_url else 'local file'}: {input_path_or_url} (Quality: {quality}, HWAccel Mode: {hwaccel_mode})")

    try:
        if is_url:
            logger.info("Attempting direct stream extraction...")
            try:
                # First attempt: Stream directly, pass timeout and hwaccel_mode
                try_stream_extract(
                    input_path_or_url,
                    output_audio_path,
                    ffmpeg_timeout=ffmpeg_timeout,
                    hwaccel_mode=hwaccel_mode,
                    quality=quality
                )
                logger.info(f"Stream extraction successful for {input_path_or_url}")
                # --- Create result and return early for stream success --- 
                end_time = time.monotonic()
                duration = round(end_time - start_time, 3)
                try:
                    file_size = os.path.getsize(output_audio_path)
                except OSError as e:
                    logger.warning(f"Could not get file size for {output_audio_path}: {e}")
                    file_size = -1
                result = ExtractionResult(
                    output_path=output_audio_path,
                    duration=duration,
                    file_size_bytes=file_size,
                    quality_preset=quality,
                    hwaccel_used=hwaccel_actually_used,
                    input_source=input_path_or_url,
                    ffmpeg_timeout=ffmpeg_timeout,
                    ffprobe_timeout=ffprobe_timeout
                )
                return result
                # ----------------------------------------------------------
            except RetryError as stream_retry_err:
                # This catches failures after all retries for stream extraction
                # Access the actual exception from the last attempt
                last_exception = stream_retry_err.last_attempt.exception()
                logger.warning(f"Stream extraction failed after retries for {input_path_or_url}: {last_exception}")
                # Proceed to fallback
                pass
            except (FFmpegError, RipzillaTimeoutError) as stream_err:
                 # Catch specific errors during streaming attempt
                 logger.warning(f"Direct stream extraction attempt failed for {input_path_or_url}: {stream_err}")
                 # Proceed to fallback
                 pass
            except Exception as stream_err:
                # Catch unexpected errors during streaming attempt
                logger.warning(f"Unexpected error during stream extraction attempt for {input_path_or_url}: {stream_err}", exc_info=True)
                # Proceed to fallback
                pass

            # Fallback: Download then extract
            logger.info(f"Attempting fallback: Download and extract for {input_path_or_url}")
            # Pass timeout to fallback function
            fallback_download_extract(
                input_path_or_url,
                output_audio_path,
                ffmpeg_timeout=ffmpeg_timeout,
                hwaccel_mode=hwaccel_mode,
                quality=quality
            )
            logger.info(f"Fallback extraction successful for {input_path_or_url}")

        else:
            # Local file: Try local extraction directly, pass timeout
            logger.info("Attempting local file extraction...")
            try_local_extract(
                input_path_or_url,
                output_audio_path,
                ffmpeg_timeout=ffmpeg_timeout,
                hwaccel_mode=hwaccel_mode,
                quality=quality
            )
            logger.info(f"Local extraction successful for {input_path_or_url}")

    # --- Specific Error Handling for Extraction Phase ---
    except RetryError as e:
        # This catches final failure after retries for local extract (direct or via fallback)
        last_exception = e.last_attempt.exception()
        logger.critical(f"Extraction failed after retries for {input_path_or_url}: {last_exception}")
        # Reraise specific known errors directly, wrap others
        if isinstance(last_exception, (FFmpegError, RipzillaTimeoutError, NetworkError, DiskSpaceError)):
            raise last_exception
        else:
            raise ExtractionError(f"Extraction failed for {input_path_or_url} after multiple attempts.") from last_exception
    except (FFmpegError, RipzillaTimeoutError, NetworkError, DiskSpaceError) as specific_err:
        # Catch specific errors raised directly from extractors or utils
        # Added DiskSpaceError here as it can be raised from fallback_download_extract
        logger.critical(f"Extraction failed for {input_path_or_url}: {specific_err}")
        raise # Reraise the specific error
    except Exception as e:
        # Catch any other unexpected errors during the main extraction logic
        logger.exception(f"An unexpected error occurred during audio extraction logic for {input_path_or_url}")
        raise ExtractionError(f"An unexpected error occurred during extraction from {input_path_or_url}.") from e

    # --- Success Path: Create and return result (now only for non-stream or fallback) --- 
    end_time = time.monotonic()
    duration = round(end_time - start_time, 3)

    try:
        file_size = os.path.getsize(output_audio_path)
    except OSError as e:
        logger.warning(f"Could not get file size for {output_audio_path}: {e}")
        file_size = -1 # Indicate failure to get size

    logger.info(f"Audio extraction process completed for {input_path_or_url}. Output: {output_audio_path} (Duration: {duration}s, Size: {file_size} bytes)")

    result = ExtractionResult(
        output_path=output_audio_path,
        duration=duration,
        file_size_bytes=file_size,
        quality_preset=quality,
        hwaccel_used=hwaccel_actually_used,
        input_source=input_path_or_url,
        ffmpeg_timeout=ffmpeg_timeout,
        ffprobe_timeout=ffprobe_timeout
    )
    return result 