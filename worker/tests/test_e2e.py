#!/usr/bin/env python3
import os
import sys
import json
import time
import uuid
import pika
import signal
from datetime import datetime
from dotenv import load_dotenv

# Carregando variáveis de ambiente
load_dotenv()

# Configurações do teste
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")

TEST_VIDEO_URL = os.getenv("TEST_VIDEO_URL", "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4")
TASK_QUEUE = os.getenv("TASK_QUEUE", "jobs.audio.extract")
REPLY_QUEUE = os.getenv("REPLY_QUEUE", "jobs.audio.extract.response")
OUTPUT_FORMAT = os.getenv("OUTPUT_FORMAT", "mp3")
TEST_TIMEOUT_SECONDS = int(os.getenv("TEST_TIMEOUT_SECONDS", "180"))

# Configuração de timeout para evitar que o teste fique preso
def timeout_handler(signum, frame):
    print("❌ FALHA: Timeout do teste atingido. O worker não respondeu no tempo esperado.")
    sys.exit(1)

# Definir temporizador de timeout
signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(TEST_TIMEOUT_SECONDS)

print(f"🚀 Iniciando teste E2E do worker de extração de áudio")
print(f"🔄 Tentando conexão com RabbitMQ em {RABBITMQ_HOST}:{RABBITMQ_PORT}")

# Variáveis para armazenar a resposta
response_received = False
audio_url = None

try:
    # Estabelecer conexão com RabbitMQ
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials,
        connection_attempts=5,
        retry_delay=5
    )
    
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    
    print(f"✅ Conexão com RabbitMQ estabelecida")
    
    # Declarar a fila de resposta
    result = channel.queue_declare(queue=REPLY_QUEUE, durable=True)
    
    # Gerar ID de correlação único para rastrear a mensagem
    correlation_id = str(uuid.uuid4())
    print(f"🔑 ID de correlação: {correlation_id}")
    
    # Criar mensagem de teste
    message = {
        "video_url": TEST_VIDEO_URL,
        "output_format": OUTPUT_FORMAT,
        "correlation_id": correlation_id,
        "reply_to": REPLY_QUEUE,
        "quality": "medium",
        "hwaccel_mode": "auto"
    }
    
    # Publicar mensagem na fila
    channel.basic_publish(
        exchange="",
        routing_key=TASK_QUEUE,
        properties=pika.BasicProperties(
            delivery_mode=2,  # persistente
            correlation_id=correlation_id,
            reply_to=REPLY_QUEUE,
            content_type="application/json"
        ),
        body=json.dumps(message)
    )
    
    print(f"📤 Mensagem enviada para fila {TASK_QUEUE}")
    print(f"📝 Conteúdo: {json.dumps(message, indent=2)}")
    
    print(f"⏳ Aguardando resposta na fila {REPLY_QUEUE}...")
    start_time = time.time()
    
    # Callback para processar mensagens da fila de resposta
    def callback(ch, method, properties, body):
        global response_received, audio_url
        
        if properties.correlation_id == correlation_id:
            response_received = True
            response_data = json.loads(body)
            
            print(f"📥 Resposta recebida em {round(time.time() - start_time, 2)}s")
            print(f"📝 Conteúdo da resposta: {json.dumps(response_data, indent=2)}")
            
            # Verificar se a resposta é válida
            if 'result' in response_data:
                result = response_data['result']
                
                if result.get('status') == 'success':
                    print(f"✅ SUCESSO: Extração concluída com êxito!")
                    audio_url = result.get('audio_url') or result.get('audio_path')
                    
                    # Exibir informações da extração
                    if 'extraction_info' in result:
                        info = result['extraction_info']
                        print(f"ℹ️ Duração do processamento: {info.get('duration_seconds', 'N/A')}s")
                        print(f"ℹ️ Tamanho do arquivo: {info.get('file_size_mb', 'N/A')} MB")
                        print(f"ℹ️ Preset de qualidade: {info.get('quality_preset', 'N/A')}")
                        print(f"ℹ️ Aceleração de hardware: {info.get('hwaccel_used', 'cpu')}")
                else:
                    print(f"❌ FALHA: {result.get('error_type', 'erro desconhecido')} - {result.get('message', 'Sem mensagem de erro')}")
            else:
                print(f"❌ FALHA: Formato de resposta inválido")
            
            # Parar consumo após receber a resposta
            ch.stop_consuming()
    
    # Consumir mensagens da fila de resposta
    channel.basic_consume(
        queue=REPLY_QUEUE,
        on_message_callback=callback,
        auto_ack=True
    )
    
    # Iniciar consumo (bloqueante até receber resposta)
    channel.start_consuming()
    
    # Verificar se a resposta foi recebida e validar
    if response_received:
        if audio_url:
            print(f"🎉 TESTE E2E CONCLUÍDO COM SUCESSO!")
            print(f"🔊 URL do áudio: {audio_url}")
            sys.exit(0)
        else:
            print(f"❌ TESTE E2E FALHOU: Áudio não gerado corretamente")
            sys.exit(1)
    else:
        print(f"❌ TESTE E2E FALHOU: Não recebeu resposta")
        sys.exit(1)
        
except pika.exceptions.AMQPConnectionError as e:
    print(f"❌ FALHA: Erro ao conectar ao RabbitMQ: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ FALHA: Erro durante teste E2E: {e}")
    sys.exit(1)
finally:
    # Cancelar o timeout
    signal.alarm(0)
    
    # Fechar conexão se estiver aberta
    if 'connection' in locals() and connection.is_open:
        connection.close()
        print("🔌 Conexão com RabbitMQ fechada") 