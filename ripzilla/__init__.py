from .core import extract_audio, ExtractionResult
from .exceptions import (
    ExtractionError,
    NoAudioStreamError,
    NetworkError,
    RipzillaTimeoutError,
    FFmpegError,
    FFprobeError,
    DiskSpaceError
)

__all__ = [
    "extract_audio", 
    "ExtractionResult",
    "ExtractionError",
    "NoAudioStreamError",
    "NetworkError",
    "RipzillaTimeoutError",
    "FFmpegError",
    "FFprobeError",
    "DiskSpaceError"
]

# Define package version (consider moving to a central place like pyproject.toml later)
__version__ = "0.1.1" 