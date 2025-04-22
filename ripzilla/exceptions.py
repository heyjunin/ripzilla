class ExtractionError(Exception):
    """Base exception for errors during the audio extraction process."""
    pass

class MediaToolError(ExtractionError):
    """Base exception for errors related to external tools (ffmpeg, ffprobe)."""
    pass

class FFmpegError(MediaToolError):
    """Exception raised for errors during ffmpeg execution."""
    pass

class FFprobeError(MediaToolError):
    """Exception raised for errors during ffprobe execution."""
    pass

class NoAudioStreamError(ExtractionError, ValueError):
    """Exception raised when the input media does not contain an audio stream."""
    pass

class NetworkError(ExtractionError):
    """Exception raised for network-related errors during download."""
    # Often wraps requests.exceptions.RequestException
    pass

class RipzillaTimeoutError(ExtractionError, TimeoutError):
    """Exception raised when a timeout occurs during processing (ffmpeg, ffprobe, download)."""
    pass

class DiskSpaceError(ExtractionError, OSError):
    """Exception raised when there is insufficient disk space for temporary files."""
    pass 