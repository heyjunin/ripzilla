import argparse
import sys
import logging

# Adjust the path to import from the ripzilla package
# This assumes the CLI is run in a way that the ripzilla package is importable
# (e.g., after installation via pip install .)
try:
    from ripzilla import extract_audio, ExtractionError
    from ripzilla import __version__
except ImportError:
    # Fallback for running script directly during development (not recommended for installed package)
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from ripzilla import extract_audio, ExtractionError
    from ripzilla import __version__

# Import the check function & defaults
from ripzilla.utils import check_media_tools_installed, DEFAULT_FFPROBE_TIMEOUT
from ripzilla.extractors import DEFAULT_FFMPEG_TIMEOUT
# Import specific exceptions for handling
from ripzilla.exceptions import (
    ExtractionError, FFmpegError, FFprobeError, NetworkError,
    RipzillaTimeoutError, NoAudioStreamError, DiskSpaceError
)

def main():
    # --- Add media tools check right at the start for CLI --- 
    try:
        check_media_tools_installed()
    except FileNotFoundError as ff_err:
        # Print a user-friendly message directly to stderr for CLI
        print(f"❌ Error: {ff_err}", file=sys.stderr)
        print("Please ensure the necessary media tools are installed and available in your system's PATH.", file=sys.stderr)
        sys.exit(1)
    # --------------------------------------------------

    parser = argparse.ArgumentParser(
        description=f"Ripzilla v{__version__}: Extract audio from video files or URLs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  ripzilla https://example.com/video.mp4 output.aac\n"
               "  ripzilla /path/to/local/video.mov audio.mp3 -v\n"
               f"  ripzilla --ffmpeg-timeout 1200 --ffprobe-timeout 300 input.mkv output.opus"
    )

    parser.add_argument(
        "input",
        help="Path to the local video file or URL of the remote video."
    )
    parser.add_argument(
        "output",
        help="Path for the output audio file. Extension determines format (e.g., .aac, .mp3)."
    )
    parser.add_argument(
        "--ffmpeg-timeout",
        type=int,
        default=DEFAULT_FFMPEG_TIMEOUT,
        help=f"Timeout in seconds for ffmpeg commands (default: {DEFAULT_FFMPEG_TIMEOUT})."
    )
    parser.add_argument(
        "--ffprobe-timeout",
        type=int,
        default=DEFAULT_FFPROBE_TIMEOUT,
        help=f"Timeout in seconds for ffprobe commands (default: {DEFAULT_FFPROBE_TIMEOUT})."
    )
    parser.add_argument(
        "--hwaccel",
        choices=["auto", "gpu", "cpu"],
        default="auto",
        help="Hardware acceleration mode (default: auto). 'gpu' tries to use detected GPU, 'cpu' forces CPU."
    )
    parser.add_argument(
        "--quality",
        choices=["raw", "high", "medium", "low"],
        default="raw",
        help="Audio quality preset (default: raw). See README for details."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging output."
    )
    parser.add_argument(
        '--version', action='version', version=f'%(prog)s {__version__}'
    )

    args = parser.parse_args()

    # Configure logging level based on verbosity
    log_level = logging.DEBUG if args.verbose else logging.INFO
    # Get the root logger and set its level
    # Note: Basic config might already be set in core.py, this adjusts the level
    logging.getLogger().setLevel(log_level)
    # Ensure handlers are present (basicConfig might not add them if already configured)
    if not logging.getLogger().handlers:
         logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    else:
        # If handlers exist, just set the level for the root logger and existing handlers
        logging.getLogger().setLevel(log_level)
        for handler in logging.getLogger().handlers:
            handler.setLevel(log_level)

    logger = logging.getLogger("ripzilla.cli")
    logger.info(f"Starting Ripzilla CLI with input: {args.input}, output: {args.output}")
    logger.debug(f"FFmpeg timeout: {args.ffmpeg_timeout}s, FFprobe timeout: {args.ffprobe_timeout}s, HWAccel: {args.hwaccel}, Quality: {args.quality}")

    try:
        # Pass timeouts, hwaccel mode, and quality to the core function
        result = extract_audio(
            args.input,
            args.output,
            ffmpeg_timeout=args.ffmpeg_timeout,
            ffprobe_timeout=args.ffprobe_timeout,
            hwaccel_mode=args.hwaccel,
            quality=args.quality
        )
        logger.info(f"Successfully extracted audio to {args.output}")
        # Print result details
        print("--- Extraction Summary ---")
        print(f"✅ Output: {result.output_path}")
        print(f"⏱️ Duration: {result.duration:.2f}s")
        if result.file_size_bytes != -1:
            print(f"💾 Size: {result.file_size_bytes / (1024*1024):.2f} MB ({result.file_size_bytes} bytes)")
        print(f"⚙️ Quality: {result.quality_preset}")
        print(f"🚀 HWAccel Used: {result.hwaccel_used or 'CPU'}")
        print("------------------------")
        sys.exit(0)

    # --- Specific Error Handling for CLI ---
    except NoAudioStreamError as e:
        logger.warning(f"Validation failed: {e}")
        print(f"⚠️  {e}", file=sys.stderr)
        sys.exit(2) # Specific exit code for no audio
    except ValueError as e:
        # Catches invalid quality preset from core.py validation
        logger.error(f"Invalid parameter: {e}")
        print(f"❌ Error: Invalid parameter. {e}", file=sys.stderr)
        sys.exit(1) # Use general error code 1 for bad input
    except RipzillaTimeoutError as e:
        logger.error(f"Operation timed out: {e}")
        print(f"❌ Error: Operation timed out. Consider increasing timeouts (--ffmpeg-timeout, --ffprobe-timeout).\n   Details: {e}", file=sys.stderr)
        sys.exit(3) # Specific exit code for timeout
    except FFmpegError as e:
        logger.error(f"FFmpeg failed: {e}")
        print(f"❌ Error: FFmpeg execution failed.\n   Details: {e}", file=sys.stderr)
        sys.exit(4) # Specific exit code for ffmpeg error
    except FFprobeError as e:
        logger.error(f"FFprobe failed: {e}")
        print(f"❌ Error: FFprobe execution failed.\n   Details: {e}", file=sys.stderr)
        sys.exit(5) # Specific exit code for ffprobe error
    except NetworkError as e:
        logger.error(f"Network error during download: {e}")
        print(f"❌ Error: Download failed. Check network connection or URL.\n   Details: {e}", file=sys.stderr)
        sys.exit(6) # Specific exit code for network error
    except DiskSpaceError as e:
        logger.error(f"Insufficient disk space: {e}")
        print(f"❌ Error: Insufficient disk space for temporary file during fallback.\n   Details: {e}", file=sys.stderr)
        sys.exit(7) # Specific exit code for disk space
    except FileNotFoundError as e:
        # Catches missing input file or missing ffmpeg/ffprobe (from initial check)
        logger.error(f"File not found: {e}")
        print(f"❌ Error: {e}", file=sys.stderr) # Message should be informative enough
        sys.exit(1)
    except ExtractionError as e:
        # Catch-all for other library-specific errors (e.g., fallback exhausted)
        logger.error(f"Audio extraction failed: {e}")
        print(f"❌ Error: Audio extraction failed.\n   Details: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")
        print(f"❌ Error: An unexpected critical error occurred: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main() 