#!/bin/bash

# Criar ambiente virtual se não existir
if [ ! -d "venv" ]; then
  echo "Criando ambiente virtual..."
  python3 -m venv venv
fi

# Ativar ambiente virtual
echo "Ativando ambiente virtual..."
source venv/bin/activate

# Instalar dependências
echo "Instalando dependências..."
pip install -r requirements.txt
pip install pytest pytest-mock

# Baixar vídeo de amostra para o diretório de testes
echo "Baixando vídeo de amostra..."
mkdir -p tests
wget -O tests/sample_video.mp4 https://download.samplelib.com/mp4/sample-5s.mp4

# Executar testes
echo "Executando testes..."
python -m pytest tests

# Desativar ambiente virtual
deactivate

echo "Processo concluído!" 