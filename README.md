# ripzilla 🦎✂️

[![PyPI version](https://badge.fury.io/py/ripzilla.svg)](https://badge.fury.io/py/ripzilla) <!-- TODO: Add link once published -->
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) <!-- TODO: Add LICENSE file -->
[![Tests](https://github.com/heyjunin/ripzilla/actions/workflows/test.yml/badge.svg)](https://github.com/heyjunin/ripzilla/actions/workflows/test.yml) <!-- TODO: Setup GitHub Actions -->

**Ripzilla** é uma biblioteca Python robusta e resiliente para extrair áudio de vídeos, sejam eles arquivos locais ou URLs remotas.

## ✨ Funcionalidades

*   Extrai áudio de arquivos de vídeo locais.
*   Extrai áudio diretamente de URLs de vídeo remotas (streaming, quando possível).
*   **Fallback automático:** Se a extração via streaming falhar, baixa o vídeo para um arquivo temporário e extrai localmente.
*   **Resiliente:** Utiliza `tenacity` para tentativas com backoff exponencial em operações de rede e `ffmpeg`.
*   **Presets de Qualidade:** Oferece presets (`raw`, `high`, `medium`, `low`) para diferentes necessidades de qualidade e tamanho de arquivo (incluindo otimização para STT).
*   **Suporte a Hardware Acceleration (macOS):** Detecta e utiliza automaticamente `VideoToolbox` no macOS para acelerar a decodificação (configurável).
*   **Configurável:** Permite ajustar timeouts para `ffmpeg`/`ffprobe` e escolher o modo de aceleração por hardware.
*   **Verificações Prévias:** Checa a existência de `ffmpeg`/`ffprobe`, a presença de stream de áudio no vídeo e espaço em disco (no fallback) antes de iniciar operações custosas.
*   **Interface de Linha de Comando (CLI):** Inclui uma ferramenta CLI (`ripzilla`) para uso direto no terminal.
*   **Resultado Estruturado:** Retorna um objeto `ExtractionResult` com metadados sobre a extração bem-sucedida.

## 🚀 Instalação

**Pré-requisitos:**

*   Python 3.8+
*   `ffmpeg` e `ffprobe` instalados e acessíveis no PATH do sistema.
    *   **macOS:** `brew install ffmpeg`
    *   **Debian/Ubuntu:** `sudo apt update && sudo apt install ffmpeg`
    *   **Windows:** Baixe do site oficial e adicione ao PATH.

**Instalação da Biblioteca:**

```bash
pip install ripzilla
```

Ou instale a partir do código fonte:

```bash
# Clone o repositório
git clone https://github.com/heyjunin/ripzilla.git
cd ripzilla

# Instale
pip install .

# (Opcional) Instale dependências de desenvolvimento para rodar testes
pip install -r requirements-dev.txt
```

## 🛠️ Uso como Biblioteca

Importe a função principal `extract_audio` e as exceções relevantes.

```python
import logging
from ripzilla import (
    extract_audio,
    ExtractionResult,
    ExtractionError,          # Erro genérico da lib
    NoAudioStreamError,       # Vídeo sem áudio
    NetworkError,             # Erro de rede no download
    RipzillaTimeoutError,     # Timeout no ffmpeg/ffprobe
    FFmpegError,              # Erro na execução do ffmpeg
    FFprobeError,             # Erro na execução do ffprobe
    DiskSpaceError,           # Erro de espaço em disco no fallback
    # FileNotFoundError      # Arquivo local não encontrado ou ffmpeg/ffprobe ausente
)

# --- Exemplo Básico --- 
VIDEO_SOURCE = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4"
# VIDEO_SOURCE = "/path/to/local/video.mp4"
OUTPUT_FILE = "extracted_audio.aac"

try:
    print(f"Iniciando extração de: {VIDEO_SOURCE}")
    result: ExtractionResult = extract_audio(VIDEO_SOURCE, OUTPUT_FILE)

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

# --- Tratamento Específico de Erros --- 
except NoAudioStreamError as e:
    print(f"⚠️ Aviso: {e}") # Vídeo de entrada não possui áudio.
except RipzillaTimeoutError as e:
    print(f"❌ Erro: Operação excedeu o timeout. Considere aumentar --ffmpeg-timeout ou --ffprobe-timeout.\n   Detalhes: {e}")
except (FFmpegError, FFprobeError) as e:
    print(f"❌ Erro: Falha na execução do ffmpeg/ffprobe.\n   Detalhes: {e}")
except NetworkError as e:
    print(f"❌ Erro: Falha no download. Verifique a conexão ou a URL.\n   Detalhes: {e}")
except DiskSpaceError as e:
    print(f"❌ Erro: Espaço em disco insuficiente para arquivo temporário (fallback).\n   Detalhes: {e}")
except FileNotFoundError as e:
    # Pode ser o arquivo local de entrada ou o ffmpeg/ffprobe não encontrado no PATH
    print(f"❌ Erro: Arquivo não encontrado: {e}")
except ExtractionError as e:
    # Erro genérico da ripzilla (ex: retries esgotados)
    print(f"❌ Erro de extração: {e}")
except Exception as e:
    # Erros inesperados
    logging.exception(f"❌ Erro inesperado durante a extração!")
    print(f"❌ Erro inesperado: {e}")

```

Veja mais exemplos na pasta `examples/`.

### Parâmetros de `extract_audio`

*   `input_path_or_url` (str): Caminho para o arquivo local ou URL do vídeo.
*   `output_audio_path` (str): Caminho onde o áudio extraído será salvo. A extensão do arquivo geralmente dita o formato (ex: `.aac`, `.mp3`, `.opus`).
*   `ffmpeg_timeout` (int, opcional): Timeout em segundos para comandos `ffmpeg`. Default: 600.
*   `ffprobe_timeout` (int, opcional): Timeout em segundos para comandos `ffprobe`. Default: 120.
*   `hwaccel_mode` (Literal["auto", "gpu", "cpu"], opcional): Modo de aceleração por hardware. Default: `"auto"`.
    *   `"auto"`: Usa a melhor GPU detectada (se houver), senão CPU.
    *   `"gpu"`: Tenta usar a GPU detectada, avisa e usa CPU se não encontrar.
    *   `"cpu"`: Força o uso da CPU.
*   `quality` (str, opcional): Preset de qualidade do áudio. Default: `"raw"`.
    *   `"raw"`: Copia o codec de áudio original (`-acodec copy`).
    *   `"high"`: AAC ~192kbps estéreo.
    *   `"medium"`: AAC ~128kbps estéreo.
    *   `"low"`: Opus ~64kbps mono, 16kHz, filtro high-pass (otimizado para voz).

### Objeto `ExtractionResult`

Em caso de sucesso, `extract_audio` retorna um objeto `dataclass` `ExtractionResult` com os seguintes atributos:

*   `output_path` (str): Caminho do arquivo de áudio gerado.
*   `duration` (float): Tempo total da execução em segundos.
*   `file_size_bytes` (int): Tamanho do arquivo de saída em bytes (-1 se não puder ser obtido).
*   `quality_preset` (str): O preset de qualidade utilizado.
*   `hwaccel_used` (str | None): O método de aceleração por hardware efetivamente utilizado (ex: `'videotoolbox'`) ou `None` se CPU foi usada.
*   `input_source` (str): O caminho/URL de entrada original.
*   `ffmpeg_timeout` (int): O timeout configurado para `ffmpeg`.
*   `ffprobe_timeout` (int): O timeout configurado para `ffprobe`.

## 命令行界面 (CLI)

Use a ferramenta `ripzilla` no terminal:

```bash
ripzilla <input_path_or_url> <output_audio_path> [opções]
```

**Opções:**

*   `-h`, `--help`: Mostra a mensagem de ajuda.
*   `--version`: Mostra a versão do programa.
*   `-v`, `--verbose`: Ativa logs detalhados.
*   `--ffmpeg-timeout SEGUNDOS`: Timeout para comandos `ffmpeg` (padrão: 600).
*   `--ffprobe-timeout SEGUNDOS`: Timeout para comandos `ffprobe` (padrão: 120).
*   `--hwaccel {auto,gpu,cpu}`: Modo de aceleração por hardware (padrão: auto).
*   `--quality {raw,high,medium,low}`: Preset de qualidade do áudio (padrão: raw).

**Exemplo CLI:**

```bash
# Extrair áudio de URL com qualidade baixa, forçando CPU e log verboso
ripzilla https://example.com/lecture.mp4 lecture_audio.opus --quality low --hwaccel cpu -v
```

**Saída em caso de sucesso:**

```
--- Extraction Summary ---
✅ Output: lecture_audio.opus
⏱️ Duration: 25.81s
💾 Size: 2.45 MB (2571158 bytes)
⚙️ Quality: low
🚀 HWAccel Used: CPU
------------------------
```

## 🔊 Presets de Qualidade de Áudio

*   **`raw` (padrão):** Tenta copiar diretamente o stream de áudio existente (`-acodec copy`). Mais rápido, preserva a qualidade original, mas depende do contêiner de saída suportar o codec original.
*   **`high`:** Re-codifica para áudio AAC a ~192 kbps estéreo. Boa qualidade, amplamente compatível.
*   **`medium`:** Re-codifica para áudio AAC a ~128 kbps estéreo. Qualidade padrão, tamanho de arquivo menor.
*   **`low`:** Re-codifica para áudio Opus a ~64 kbps mono, 16kHz de taxa de amostragem, com filtro passa-alta (`highpass`). Otimizado para fala (ex: para STT), menor tamanho de arquivo. Requer `ffmpeg` compilado com suporte a `libopus`.

##  Handling Large Files & Potential Issues

*   **Memória:** Ripzilla é eficiente em termos de memória, evitando carregar vídeos inteiros.
*   **Streaming:** Tenta processar URLs diretamente via streaming.
*   **Fallback & Disco:** Se o streaming falhar, o vídeo *completo* é baixado para um diretório temporário. **Isso requer espaço em disco suficiente.** Uma verificação básica (>1GB livre) é feita, mas arquivos muito grandes exigirão mais.
*   **Timeouts:** Processar arquivos grandes pode demorar. Se ocorrer `RipzillaTimeoutError`, aumente os timeouts via parâmetros da biblioteca ou opções da CLI.
*   **Hardware Acceleration:** `auto` tenta usar a GPU (VideoToolbox no macOS). Se a aceleração falhar ou não for suportada, ele silenciosamente usa a CPU. Use `cpu` para forçar a CPU.
*   **Sem Áudio:** Se o vídeo de entrada não tiver áudio, `NoAudioStreamError` será levantada (ou um aviso será impresso na CLI com código de saída 2).

## ⚠️ Tratamento de Erros

A biblioteca levanta exceções específicas para diferentes problemas:

*   `ExtractionError`: Erro genérico da ripzilla.
*   `MediaToolError`: Base para erros de `ffmpeg`/`ffprobe`.
*   `FFmpegError`: Erro durante execução do `ffmpeg`.
*   `FFprobeError`: Erro durante execução do `ffprobe`.
*   `NoAudioStreamError`: Vídeo de entrada sem stream de áudio.
*   `NetworkError`: Erro de rede durante download (fallback).
*   `RipzillaTimeoutError`: Timeout no `ffmpeg`, `ffprobe` ou conexão de download.
*   `DiskSpaceError`: Espaço em disco insuficiente no diretório temporário para fallback.
*   `FileNotFoundError`: Arquivo de entrada local não existe OU `ffmpeg`/`ffprobe` não encontrado no PATH.
*   `ValueError`: Parâmetro inválido (ex: preset de qualidade inexistente).

Use blocos `try...except` para tratar esses erros na sua aplicação (veja exemplo na seção de Uso).

## 🤝 Contribuição

Contribuições são bem-vindas! Abra uma issue ou envie um pull request.

## 📝 Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo `LICENSE` para detalhes. <!-- TODO: Add LICENSE file -->

## ☑️ TODO

*   Adicionar detecção/suporte para HWAccel CUDA/NVENC/NVDEC em Linux/Windows.
*   Permitir configuração do limite mínimo de espaço em disco.
*   Melhorar a robustez da detecção de ferramentas (`ffmpeg`/`ffprobe`).
*   Adicionar testes unitários mais abrangentes.
*   Publicar no PyPI. 