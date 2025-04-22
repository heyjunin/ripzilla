from .core import extract_audio
from .exceptions import ExtractionError

__all__ = ["extract_audio", "ExtractionError"]

# Define package version (consider moving to a central place like pyproject.toml later)
__version__ = "0.1.0" 