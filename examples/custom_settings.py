"""
examples/custom_settings.py

Demonstrates using custom settings like quality presets, timeouts, and HWAccel modes.
"""

import sys
import os
import logging

# Adjust path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ripzilla import extract_audio, ExtractionError
from ripzilla.core import ExtractionResult # Import from core

# Configure logging
logging.basicConfig(level=logging.INFO)

# --- Constants --- 
VIDEO_URL = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerJoyrides.mp4" # Different video
LOCAL_VIDEO_PATH = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')), "tests", "sample_video.mp4") 

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def print_result(result: ExtractionResult):
    # ... (same helper function as in basic_usage.py) ...
    print("\n--- Resumo da Extração ---")
    print(f"✅ Saída: {result.output_path}")
    print(f"⏱️ Duração: {result.duration:.2f}s")
    if result.file_size_bytes != -1:
        print(f"💾 Tamanho: {result.file_size_bytes / (1024*1024):.2f} MB ({result.file_size_bytes} bytes)")
    else:
        print("💾 Tamanho: Não foi possível obter")
    print(f"⚙️ Preset Qualidade: {result.quality_preset}")
    print(f"🚀 HWAccel Usado: {result.hwaccel_used or 'CPU'}")
    print(f"🔧 Timeout FFmpeg: {result.ffmpeg_timeout}s")
    print(f"🔧 Timeout FFprobe: {result.ffprobe_timeout}s")
    print("------------------------")

def main():
    # --- Example 1: Low quality for STT, force CPU, longer timeout --- 
    print("--- Exemplo 1: Qualidade baixa, forçando CPU, timeout longo ---")
    output_low_cpu = os.path.join(OUTPUT_DIR, "audio_low_cpu.opus") # Opus extension for low preset
    try:
        result_low = extract_audio(
            VIDEO_URL,
            output_low_cpu,
            quality="low",
            hwaccel_mode="cpu",
            ffmpeg_timeout=900 # 15 minutes
        )
        print_result(result_low)
    except ExtractionError as e:
        print(f"❌ Falha na extração (low/cpu): {e}")
    except Exception as e:
        logging.exception("Erro inesperado")
        print(f"❌ Erro inesperado: {e}")

    print("\n========================================\n")

    # --- Example 2: High quality, auto HWAccel (default), default timeouts --- 
    print("--- Exemplo 2: Qualidade alta, HWAccel auto (padrão) ---")
    if not os.path.exists(LOCAL_VIDEO_PATH):
        print(f"⚠️ Aviso: Arquivo local {LOCAL_VIDEO_PATH} não encontrado. Pulando exemplo.")
        return
        
    output_high_auto = os.path.join(OUTPUT_DIR, "audio_high_auto.aac")
    try:
        result_high = extract_audio(
            LOCAL_VIDEO_PATH,
            output_high_auto,
            quality="high",
            hwaccel_mode="auto" # Default, but explicit here
        )
        print_result(result_high)
    except ExtractionError as e:
        print(f"❌ Falha na extração (high/auto): {e}")
    except Exception as e:
        logging.exception("Erro inesperado")
        print(f"❌ Erro inesperado: {e}")

if __name__ == "__main__":
    main() 