"""
examples/basic_usage.py

Demonstrates basic audio extraction from a URL and a local file (if available).
"""

import sys
import os
import logging

# Adjust path to find ripzilla if not installed
script_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(script_dir, '..'))
sys.path.insert(0, project_root)

from ripzilla import extract_audio, ExtractionError
from ripzilla.core import ExtractionResult # Import from core

# Configure logging for more details (optional)
logging.basicConfig(level=logging.INFO)

# --- Constants --- 
# Public test video URL
VIDEO_URL = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4"
# Path to a local video file (replace with your own or use the one from tests/)
LOCAL_VIDEO_PATH = os.path.join(project_root, "tests", "sample_video.mp4") 

OUTPUT_DIR = os.path.join(script_dir, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def print_result(result: ExtractionResult):
    """Helper to print result details."""
    print("\n--- Resumo da Extração ---")
    print(f"✅ Saída: {result.output_path}")
    print(f"⏱️ Duração: {result.duration:.2f}s")
    if result.file_size_bytes != -1:
        print(f"💾 Tamanho: {result.file_size_bytes / (1024*1024):.2f} MB ({result.file_size_bytes} bytes)")
    else:
        print("💾 Tamanho: Não foi possível obter")
    print(f"⚙️ Preset Qualidade: {result.quality_preset}")
    print(f"🚀 HWAccel Usado: {result.hwaccel_used or 'CPU'}")
    print("------------------------")


def main():
    # --- Example 1: Extract from URL (default settings) --- 
    print("--- Exemplo 1: Extraindo de URL (padrão) ---")
    output_url_file = os.path.join(OUTPUT_DIR, "audio_from_url.aac")
    try:
        result_url = extract_audio(VIDEO_URL, output_url_file)
        print_result(result_url)
    except ExtractionError as e:
        print(f"❌ Falha ao extrair da URL: {e}")
    except Exception as e:
        logging.exception("Erro inesperado na extração da URL")
        print(f"❌ Erro inesperado: {e}")

    print("\n========================================\n")

    # --- Example 2: Extract from Local File (default settings) --- 
    print("--- Exemplo 2: Extraindo de Arquivo Local (padrão) ---")
    if not os.path.exists(LOCAL_VIDEO_PATH):
        print(f"⚠️ Aviso: Arquivo de vídeo local não encontrado em {LOCAL_VIDEO_PATH}. Pulando exemplo local.")
        print("    (Você pode copiar o vídeo de tests/sample_video.mp4 ou usar seu próprio vídeo)")
        return
        
    output_local_file = os.path.join(OUTPUT_DIR, "audio_from_local.mp3") # Output as mp3
    try:
        result_local = extract_audio(LOCAL_VIDEO_PATH, output_local_file)
        print_result(result_local)
    except ExtractionError as e:
        print(f"❌ Falha ao extrair do arquivo local: {e}")
    except Exception as e:
        logging.exception("Erro inesperado na extração local")
        print(f"❌ Erro inesperado: {e}")


if __name__ == "__main__":
    main() 