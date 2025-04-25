#!/usr/bin/env python3
import json
import pika
import uuid
import sys
import os
import time
from datetime import datetime

# Configurações
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "15673"))  # Porta mapeada no docker-compose
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
QUEUE_NAME = os.getenv("QUEUE_NAME", "jobs.audio.extract")
REPLY_QUEUE = os.getenv("REPLY_QUEUE", "jobs.audio.extract.response")

# Amostra de vídeo para teste
DEFAULT_VIDEO_URL = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4"

def send_message(video_url):
    """Envia uma mensagem para o worker processar o vídeo"""
    try:
        print(f"Conectando ao RabbitMQ em {RABBITMQ_HOST}:{RABBITMQ_PORT}...")
        
        # Estabelecer conexão
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
        parameters = pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            virtual_host="/",
            credentials=credentials
        )
        
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        
        # Criar fila de respostas
        channel.queue_declare(queue=REPLY_QUEUE, durable=True)
        
        # Configurar consumo da fila de respostas
        channel.basic_consume(
            queue=REPLY_QUEUE,
            on_message_callback=on_response,
            auto_ack=True
        )
        
        # Gerar ID de correlação
        correlation_id = str(uuid.uuid4())
        
        # Preparar mensagem
        message = {
            "video_url": video_url,
            "output_format": "aac",
            "quality": "medium",
            "hwaccel_mode": "auto",
            "reply_to": REPLY_QUEUE,
            "correlation_id": correlation_id,
        }
        
        print(f"Enviando mensagem para a fila {QUEUE_NAME}...")
        
        # Publicar mensagem
        channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            properties=pika.BasicProperties(
                delivery_mode=2,  # Persistente
                correlation_id=correlation_id,
                reply_to=REPLY_QUEUE,
                content_type="application/json"
            ),
            body=json.dumps(message)
        )
        
        print(f"Mensagem enviada com ID de correlação: {correlation_id}")
        print("Aguardando resposta (pressione Ctrl+C para sair)...")
        
        # Iniciar timer
        start_time = time.time()
        
        try:
            # Aguardar resposta
            channel.start_consuming()
        except KeyboardInterrupt:
            print("\nOperação cancelada pelo usuário.")
        finally:
            # Fechar conexão
            if connection.is_open:
                connection.close()
            
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")
        sys.exit(1)

def on_response(ch, method, properties, body):
    """Callback quando uma resposta é recebida"""
    try:
        # Calcular tempo de processamento
        processing_time = time.time() - start_time
        
        # Analisar resposta
        response = json.loads(body)
        
        print("\n--- Resposta recebida ---")
        print(f"⏱️ Tempo total: {processing_time:.2f}s")
        
        # Verificar status
        result = response.get("result", {})
        status = result.get("status", "unknown")
        
        if status == "success":
            # Exibir dados da extração bem-sucedida
            info = result.get("extraction_info", {})
            print(f"✅ Status: {status}")
            print(f"🎵 Arquivo: {result.get('audio_path')}")
            print(f"🔗 URL: {result.get('audio_url') or 'N/A'}")
            print(f"⏱️ Duração: {info.get('duration_seconds', 0):.2f}s")
            print(f"💾 Tamanho: {info.get('file_size_mb', 0):.2f} MB ({info.get('file_size_bytes', 0)} bytes)")
            print(f"⚙️ Preset: {info.get('quality_preset', 'N/A')}")
            print(f"🚀 HWAccel: {info.get('hwaccel_used', 'N/A')}")
        else:
            # Exibir dados de falha
            print(f"❌ Status: {status}")
            print(f"🛑 Tipo de erro: {result.get('error_type', 'unknown')}")
            print(f"🛑 Mensagem: {result.get('message', 'Sem detalhes')}")
        
        print("------------------------")
        
        # Parar consumo
        ch.stop_consuming()
        
    except json.JSONDecodeError:
        print("❌ Erro ao decodificar resposta JSON")
    except Exception as e:
        print(f"❌ Erro ao processar resposta: {e}")
    finally:
        # Parar consumo em qualquer caso
        ch.stop_consuming()

if __name__ == "__main__":
    # Usar URL fornecida como argumento ou usar a padrão
    video_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VIDEO_URL
    
    print(f"Iniciando teste de extração de áudio com Ripzilla Worker")
    print(f"URL do vídeo: {video_url}")
    
    # Iniciar timer global
    start_time = time.time()
    
    # Enviar mensagem
    send_message(video_url) 