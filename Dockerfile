FROM python:3.11-slim

# Instalar ffmpeg e dependências
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Diretório de trabalho
WORKDIR /app

# Copiar arquivo de requisitos e instalar dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar a biblioteca ripzilla diretamente para o PYTHONPATH
COPY ripzilla /app/ripzilla/
COPY setup.py /app/setup.py

# Copiar código fonte do worker
COPY src/worker.py /app/src/worker.py

# Criar diretório temporário para arquivos de áudio
RUN mkdir -p /tmp/ripzilla && chmod 777 /tmp/ripzilla

# Define PYTHONPATH para incluir o diretório atual
ENV PYTHONPATH=/app

# Executar worker
CMD ["python", "src/worker.py"] 