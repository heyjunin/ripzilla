"""
examples/error_handling.py

Demonstrates how to catch specific exceptions raised by ripzilla.
"""

import sys
import os
import logging

# Adjust path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ripzilla import (
    extract_audio,
    # ExtractionResult, # Imported from core
    ExtractionError,       # Base error
)
# Import specific exceptions
from ripzilla.exceptions import (
    NoAudioStreamError,    # Video has no audio
    NetworkError,          # Download failure
    RipzillaTimeoutError,  # ffmpeg/ffprobe/download timeout
    FFmpegError,           # ffmpeg execution error
    FFprobeError,          # ffprobe execution error
    DiskSpaceError         # Not enough disk space for fallback temp file
)
# Need to import from core for ExtractionResult
from ripzilla.core import ExtractionResult


# Configure logging
logging.basicConfig(level=logging.WARNING) # Set to WARNING to reduce noise unless verbose

# --- Constants --- 
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Test Cases --- 
# 1. Invalid URL (will likely cause NetworkError or maybe DNS error wrapped in it)
INVALID_URL = "http://invalid.url.that.does.not.exist/video.mp4"
# 2. Video known to have no audio stream (requires creating one - use the test fixture logic)
#    Let's skip creating one here and just show the error handling logic.
# 3. Non-existent local file
INVALID_LOCAL = "/non/existent/path/video.mp4"

def run_extraction(input_src, output_name):
    output_file = os.path.join(OUTPUT_DIR, output_name)
    print(f"\n--- Tentando extrair: {input_src} -> {output_file} ---")
    try:
        result = extract_audio(input_src, output_file, quality="medium") # Use medium to force ffmpeg action
        print(f"✅ Sucesso! Saída em {result.output_path}")
        # print_result(result) # Can use helper from other examples if needed
        return True

    except NoAudioStreamError as e:
        print(f" Caught: {type(e).__name__} - Vídeo não contém áudio: {e}")
    except RipzillaTimeoutError as e:
        print(f" Caught: {type(e).__name__} - Operação excedeu timeout: {e}")
    except (FFmpegError, FFprobeError) as e:
        print(f" Caught: {type(e).__name__} - Erro no FFmpeg/FFprobe: {e}")
    except NetworkError as e:
        print(f" Caught: {type(e).__name__} - Erro de rede no download: {e}")
    except DiskSpaceError as e:
        print(f" Caught: {type(e).__name__} - Falta de espaço em disco: {e}")
    except FileNotFoundError as e:
        print(f" Caught: {type(e).__name__} - Arquivo não encontrado (input ou ffmpeg/ffprobe): {e}")
    except ValueError as e:
         # e.g., Invalid quality preset
        print(f" Caught: {type(e).__name__} - Parâmetro inválido: {e}")
    except ExtractionError as e:
        # Catch-all for other ripzilla errors
        print(f" Caught: {type(e).__name__} - Erro genérico de extração: {e}")
    except Exception as e:
        # Unexpected errors
        logging.exception(f"Erro inesperado não tratado pela ripzilla!")
        print(f" Caught: {type(e).__name__} - Erro inesperado: {e}")
    return False

def main():
    print("Demonstrando tratamento de erros específicos:")
    
    # Test Case 1: Invalid URL
    run_extraction(INVALID_URL, "error_invalid_url.aac")
    
    # Test Case 2: Invalid Local Path
    run_extraction(INVALID_LOCAL, "error_invalid_local.aac")
    
    # TODO: Add a test case for NoAudioStreamError - requires generating a file
    print("\n(Nota: Para testar NoAudioStreamError, gere um vídeo sem áudio)")
    # TODO: Add a test case for DiskSpaceError - requires mocking or filling disk
    print("(Nota: Para testar DiskSpaceError, é necessário mockar ou encher o disco)")
    # TODO: Add a test case for Timeout - requires long video or low timeout
    print("(Nota: Para testar Timeout, use um vídeo longo ou timeouts curtos)")

if __name__ == "__main__":
    main() 