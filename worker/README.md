# Worker de Extração de Áudio com Ripzilla

Este worker é um microserviço independente que utiliza a biblioteca `ripzilla` para extrair áudio de vídeos. Ele funciona como um processador de tarefas que consome mensagens de uma fila RabbitMQ e retorna o resultado para outra fila.

## Características

- ✅ **Independente**: Não tem acoplamento com a aplicação principal
- 🔄 **Resiliente**: Tentativas automáticas com backoff exponencial
- 📊 **Observável**: Logs detalhados com loguru
- 🐇 **Dead Letter Queue**: Mensagens que falham são movidas para uma DLQ
- 🎛️ **Configurável**: Variáveis de ambiente para todos os parâmetros
- 🐳 **Dockerizado**: Pronto para deployment em containers

## Sobre a Biblioteca Ripzilla

Este worker utiliza a biblioteca Ripzilla que está disponível localmente neste repositório. A configuração do Docker Compose está preparada para montar o diretório da biblioteca e instalá-la automaticamente durante a inicialização dos containers.

## Formato das Mensagens

### Entrada (Consumo)

```json
{
  "video_url": "https://example.com/video.mp4",
  "output_format": "mp3",
  "correlation_id": "abc123",
  "reply_to": "jobs.audio.extract.response",
  "quality": "medium",
  "hwaccel_mode": "auto"
}
```

### Saída (Produção)

```json
{
  "original_request": {
    "video_url": "https://example.com/video.mp4",
    "output_format": "mp3",
    "correlation_id": "abc123"
  },
  "result": {
    "status": "success",
    "audio_path": "/tmp/ripzilla/abc123_1620000000.mp3",
    "audio_url": "http://localhost:8080/audio/abc123_1620000000.mp3",
    "extraction_info": {
      "duration_seconds": 25.81,
      "file_size_bytes": 2571158,
      "file_size_mb": 2.45,
      "quality_preset": "medium",
      "hwaccel_used": "cpu",
      "input_source": "https://example.com/video.mp4",
      "ffmpeg_timeout": 600,
      "ffprobe_timeout": 120,
      "timestamp": "2023-06-01T12:00:00.000000"
    }
  },
  "processed_at": "2023-06-01T12:00:00.000000"
}
```

## Executando com Docker Compose

### Pré-requisitos

- Docker e Docker Compose instalados
- FFmpeg (já incluído na imagem Docker)
- Biblioteca ripzilla local (já configurada para ser montada como volume)

### Passos

1. Clone o repositório e navegue até a pasta do worker:

```bash
cd worker
```

2. Execute o Docker Compose:

```bash
docker-compose up
```

Para executar em background:

```bash
docker-compose up -d
```

3. Acessar interface do RabbitMQ:

Acesse http://localhost:15672 (usuário: `guest`, senha: `guest`)

### Teste E2E Automatizado

O Docker Compose inclui um serviço de teste E2E que:

1. Publica uma mensagem de teste na fila
2. Aguarda a resposta na fila reply_to
3. Valida o resultado

Para executar apenas o teste:

```bash
docker-compose run e2e-test
```

## Variáveis de Ambiente

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `RABBITMQ_HOST` | Host do RabbitMQ | `rabbitmq` |
| `RABBITMQ_PORT` | Porta do RabbitMQ | `5672` |
| `RABBITMQ_USER` | Usuário do RabbitMQ | `guest` |
| `RABBITMQ_PASS` | Senha do RabbitMQ | `guest` |
| `QUEUE_NAME` | Nome da fila principal | `jobs.audio.extract` |
| `DLQ_NAME` | Nome da DLQ | `jobs.audio.extract.dlq` |
| `MAX_ATTEMPTS` | Máximo de tentativas | `3` |
| `MESSAGE_TTL` | TTL das mensagens (ms) | `1800000` (30min) |
| `TEMP_DIR` | Diretório temporário | `/tmp/ripzilla` |
| `STORAGE_BASE_URL` | URL base para arquivos | `http://localhost:8080/audio` |
| `FFMPEG_TIMEOUT` | Timeout do FFmpeg (s) | `600` |
| `FFPROBE_TIMEOUT` | Timeout do FFprobe (s) | `120` |
| `LOG_LEVEL` | Nível de log | `INFO` |

## Escalabilidade Horizontal

Este worker foi projetado para permitir escalabilidade horizontal:

- Pode ser distribuído em múltiplos nós/containers
- RabbitMQ garante que cada mensagem seja processada por apenas um worker
- Não mantém estado entre processamentos
- Baixo acoplamento facilita escala independente

Para escalar, basta aumentar o número de réplicas:

```bash
docker-compose up --scale worker=3
```

## Implantação em Produção

Para implantação em produção, você tem duas opções para lidar com a biblioteca `ripzilla`:

1. **Repositório Privado do GitHub**: Configure acesso ao repositório privado durante o build da imagem Docker:
   ```dockerfile
   # No Dockerfile de produção
   ARG GITHUB_TOKEN
   RUN pip install git+https://${GITHUB_TOKEN}@github.com/heyjunin/ripzilla.git
   ```

2. **Empacotar a Biblioteca**: Adicione a biblioteca como parte da imagem Docker:
   ```dockerfile
   # No Dockerfile de produção
   COPY ripzilla /app/ripzilla
   COPY setup.py /app/
   RUN pip install -e /app/
   ```

## Operações e Monitoramento

- **Logs**: Todos os logs são enviados para stdout (capturáveis pelo Docker)
- **Mensagens Falhas**: Verificar a DLQ (`jobs.audio.extract.dlq`) para mensagens problemáticas
- **Métricas**: Monitorar filas através da UI do RabbitMQ

## Exemplo de Integração

```python
import pika
import json
import uuid

# Conexão com RabbitMQ
connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()

# Declarar fila de resposta
result = channel.queue_declare(queue='my_app.responses', durable=True)
callback_queue = result.method.queue

# Gerar ID de correlação
correlation_id = str(uuid.uuid4())

# Publicar mensagem
channel.basic_publish(
    exchange='',
    routing_key='jobs.audio.extract',
    properties=pika.BasicProperties(
        delivery_mode=2,  # persistente
        correlation_id=correlation_id,
        reply_to=callback_queue
    ),
    body=json.dumps({
        'video_url': 'https://example.com/video.mp4',
        'output_format': 'mp3',
        'correlation_id': correlation_id,
        'reply_to': callback_queue
    })
)

print(f"Mensagem enviada com correlation_id: {correlation_id}")
``` 