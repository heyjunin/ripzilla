#!/usr/bin/env python3
import os
import sys
import json
import time
import pika
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
from loguru import logger
from dotenv import load_dotenv

# Importando a biblioteca ripzilla para extração de áudio
from ripzilla import (
    extract_audio,
    ExtractionError,
    NoAudioStreamError,
    NetworkError,
    RipzillaTimeoutError,
    FFmpegError,
    FFprobeError,
    DiskSpaceError
)

# Carregando variáveis de ambiente
load_dotenv()

# Configuração de logs
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=os.getenv("LOG_LEVEL", "INFO")
)

class AudioExtractionWorker:
    """Worker para extração de áudio usando ripzilla"""
    
    def __init__(self):
        # Configurações do RabbitMQ
        self.rabbitmq_host = os.getenv("RABBITMQ_HOST", "localhost")
        self.rabbitmq_port = int(os.getenv("RABBITMQ_PORT", "5672"))
        self.rabbitmq_user = os.getenv("RABBITMQ_USER", "guest")
        self.rabbitmq_pass = os.getenv("RABBITMQ_PASS", "guest")
        self.rabbitmq_vhost = os.getenv("RABBITMQ_VHOST", "/")
        
        # Configurações da fila
        self.queue_name = os.getenv("QUEUE_NAME", "jobs.audio.extract")
        self.dlq_name = os.getenv("DLQ_NAME", "jobs.audio.extract.dlq")
        self.max_attempts = int(os.getenv("MAX_ATTEMPTS", "3"))
        self.message_ttl = int(os.getenv("MESSAGE_TTL", "1800000"))  # 30 minutos em ms
        
        # Configurações de extração
        self.temp_dir = os.getenv("TEMP_DIR", "/tmp/ripzilla")
        self.storage_base_url = os.getenv("STORAGE_BASE_URL", "")
        self.ffmpeg_timeout = int(os.getenv("FFMPEG_TIMEOUT", "600"))
        self.ffprobe_timeout = int(os.getenv("FFPROBE_TIMEOUT", "120"))
        
        # Criar diretório temporário se não existir
        Path(self.temp_dir).mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Worker iniciado - Queue: {self.queue_name} | DLQ: {self.dlq_name} | Max Attempts: {self.max_attempts}")
    
    def connect(self):
        """Estabelece conexão com o RabbitMQ e configura as filas"""
        try:
            # Estabelecer conexão
            credentials = pika.PlainCredentials(self.rabbitmq_user, self.rabbitmq_pass)
            parameters = pika.ConnectionParameters(
                host=self.rabbitmq_host,
                port=self.rabbitmq_port,
                virtual_host=self.rabbitmq_vhost,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )
            
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            # Declarar exchange para DLQ
            self.channel.exchange_declare(
                exchange="dlx",
                exchange_type="direct",
                durable=True
            )
            
            # Configurar DLQ
            self.channel.queue_declare(
                queue=self.dlq_name,
                durable=True,
                arguments={
                    "x-message-ttl": 7 * 24 * 60 * 60 * 1000,  # 7 dias em ms
                    "x-queue-mode": "lazy"
                }
            )
            
            self.channel.queue_bind(
                exchange="dlx",
                queue=self.dlq_name,
                routing_key=self.queue_name
            )
            
            # Configurar fila principal com deadletter
            self.channel.queue_declare(
                queue=self.queue_name,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": "dlx",
                    "x-dead-letter-routing-key": self.queue_name,
                    "x-message-ttl": self.message_ttl,
                    "x-max-priority": 10
                }
            )
            
            logger.info("Conexão com RabbitMQ estabelecida")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao conectar ao RabbitMQ: {e}")
            return False
    
    def start_consuming(self):
        """Inicia o consumo de mensagens da fila"""
        try:
            self.channel.basic_qos(prefetch_count=1)
            self.channel.basic_consume(
                queue=self.queue_name,
                on_message_callback=self.process_message
            )
            
            logger.info(f"Iniciando consumo da fila {self.queue_name}")
            self.channel.start_consuming()
            
        except KeyboardInterrupt:
            logger.info("Recebido sinal de interrupção. Encerrando worker...")
            self.channel.stop_consuming()
            self.connection.close()
        except Exception as e:
            logger.error(f"Erro durante o consumo de mensagens: {e}")
            self.reconnect()
    
    def reconnect(self, retry_delay=5):
        """Reconecta ao RabbitMQ em caso de falha"""
        logger.warning(f"Tentando reconectar em {retry_delay} segundos...")
        time.sleep(retry_delay)
        
        if self.connect():
            self.start_consuming()
        else:
            self.reconnect(min(retry_delay * 2, 60))  # Backoff exponencial com máximo de 60 segundos
    
    def process_message(self, ch, method, properties, body):
        """Processa uma mensagem da fila"""
        start_time = time.time()
        message_id = properties.message_id or "unknown"
        correlation_id = properties.correlation_id or "unknown"
        
        try:
            logger.info(f"Iniciando processamento da mensagem {message_id} [correlation_id: {correlation_id}]")
            
            # Analisar o corpo da mensagem
            message_data = json.loads(body)
            logger.debug(f"Conteúdo da mensagem: {message_data}")
            
            # Verificar campos obrigatórios
            if "video_url" not in message_data:
                raise ValueError("Campo 'video_url' não encontrado na mensagem")
            
            # Extrair informações da mensagem
            video_url = message_data["video_url"]
            output_format = message_data.get("output_format", "mp3")
            reply_to = message_data.get("reply_to", "jobs.audio.extract.response")
            correlation_id = message_data.get("correlation_id", correlation_id)
            
            # Configurações opcionais de extração
            quality = message_data.get("quality", "medium")
            hwaccel_mode = message_data.get("hwaccel_mode", "auto")
            
            # Gerar caminho de saída temporário
            filename = f"{correlation_id}_{int(time.time())}.{output_format}"
            output_path = os.path.join(self.temp_dir, filename)
            
            # Extrair áudio com ripzilla
            result = self.extract_audio(
                video_url=video_url,
                output_path=output_path,
                quality=quality,
                hwaccel_mode=hwaccel_mode
            )
            
            # Enviar resposta
            self.send_response(
                reply_to=reply_to,
                correlation_id=correlation_id,
                result=result,
                message_data=message_data
            )
            
            # Acknowledge da mensagem
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
            # Registrar tempo de execução
            execution_time = round(time.time() - start_time, 2)
            logger.info(f"Processamento concluído em {execution_time}s [correlation_id: {correlation_id}]")
            
        except json.JSONDecodeError as e:
            logger.error(f"Erro ao decodificar JSON da mensagem: {e}")
            # Mensagem inválida, enviar para DLQ imediatamente
            ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
            
        except ValueError as e:
            logger.error(f"Erro de validação da mensagem: {e}")
            # Mensagem inválida, enviar para DLQ imediatamente
            ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
            
        except Exception as e:
            # Verificar se deve tentar novamente ou enviar para DLQ
            current_retries = self.get_message_retry_count(properties.headers)
            
            if current_retries >= self.max_attempts - 1:
                logger.critical(
                    f"Falha no processamento após {current_retries + 1} tentativas. "
                    f"Enviando para DLQ: {e} [correlation_id: {correlation_id}]"
                )
                ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
            else:
                logger.error(
                    f"Falha no processamento. Tentativa {current_retries + 1}/{self.max_attempts}. "
                    f"Erro: {e} [correlation_id: {correlation_id}]"
                )
                ch.basic_reject(delivery_tag=method.delivery_tag, requeue=True)
    
    def get_message_retry_count(self, headers) -> int:
        """Obtém o número de tentativas de uma mensagem"""
        if not headers or 'x-death' not in headers:
            return 0
            
        x_death = headers['x-death']
        if not x_death or not isinstance(x_death, list):
            return 0
            
        # Somar todas as contagens de morte para a fila atual
        return sum(
            death.get('count', 0) 
            for death in x_death 
            if death.get('queue') == self.queue_name
        )
    
    def extract_audio(self, video_url, output_path, quality, hwaccel_mode) -> Dict[str, Any]:
        """Extrai áudio do vídeo usando a biblioteca ripzilla"""
        try:
            logger.info(f"Iniciando extração de áudio de {video_url}")
            
            result = extract_audio(
                input_path_or_url=video_url,
                output_audio_path=output_path,
                ffmpeg_timeout=self.ffmpeg_timeout,
                ffprobe_timeout=self.ffprobe_timeout,
                hwaccel_mode=hwaccel_mode,
                quality=quality
            )
            
            # Calcular tamanho do arquivo em MB
            file_size_mb = round(result.file_size_bytes / (1024 * 1024), 2) if result.file_size_bytes > 0 else 0
            
            # Construir URL do arquivo final
            audio_url = None
            if self.storage_base_url:
                audio_url = f"{self.storage_base_url}/{os.path.basename(output_path)}"
            
            response = {
                "status": "success",
                "audio_path": output_path,
                "audio_url": audio_url,
                "extraction_info": {
                    "duration_seconds": result.duration,
                    "file_size_bytes": result.file_size_bytes,
                    "file_size_mb": file_size_mb,
                    "quality_preset": result.quality_preset,
                    "hwaccel_used": result.hwaccel_used or "cpu",
                    "input_source": result.input_source,
                    "ffmpeg_timeout": result.ffmpeg_timeout,
                    "ffprobe_timeout": result.ffprobe_timeout,
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            logger.info(f"Extração concluída. Tamanho: {file_size_mb} MB")
            return response
            
        except NoAudioStreamError as e:
            logger.warning(f"Vídeo não possui stream de áudio: {e}")
            return {
                "status": "error", 
                "error_type": "no_audio_stream",
                "message": str(e)
            }
            
        except (FFmpegError, FFprobeError) as e:
            logger.error(f"Erro no processamento de mídia: {e}")
            return {
                "status": "error", 
                "error_type": "media_processing_error",
                "message": str(e)
            }
            
        except NetworkError as e:
            logger.error(f"Erro de rede: {e}")
            return {
                "status": "error", 
                "error_type": "network_error",
                "message": str(e)
            }
            
        except RipzillaTimeoutError as e:
            logger.error(f"Timeout durante o processamento: {e}")
            return {
                "status": "error", 
                "error_type": "timeout",
                "message": str(e)
            }
            
        except DiskSpaceError as e:
            logger.error(f"Erro de espaço em disco: {e}")
            return {
                "status": "error", 
                "error_type": "disk_space_error",
                "message": str(e)
            }
            
        except ExtractionError as e:
            logger.error(f"Erro de extração genérico: {e}")
            return {
                "status": "error", 
                "error_type": "extraction_error",
                "message": str(e)
            }
            
        except Exception as e:
            logger.exception(f"Erro inesperado durante extração: {e}")
            return {
                "status": "error", 
                "error_type": "unknown_error",
                "message": str(e)
            }
    
    def send_response(self, reply_to, correlation_id, result, message_data):
        """Envia resposta para a fila de respostas"""
        if not reply_to:
            logger.warning("Campo 'reply_to' não fornecido, resposta não será enviada")
            return
            
        try:
            response_data = {
                "original_request": {
                    "video_url": message_data.get("video_url"),
                    "output_format": message_data.get("output_format"),
                    "correlation_id": correlation_id
                },
                "result": result,
                "processed_at": datetime.now().isoformat()
            }
            
            # Garantir que a fila de resposta existe
            self.channel.queue_declare(queue=reply_to, durable=True)
            
            # Publicar resposta
            self.channel.basic_publish(
                exchange="",
                routing_key=reply_to,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # persistente
                    correlation_id=correlation_id,
                    content_type="application/json"
                ),
                body=json.dumps(response_data)
            )
            
            logger.info(f"Resposta enviada para fila {reply_to} [correlation_id: {correlation_id}]")
            
        except Exception as e:
            logger.error(f"Erro ao enviar resposta: {e}")


if __name__ == "__main__":
    worker = AudioExtractionWorker()
    
    if worker.connect():
        worker.start_consuming()
    else:
        logger.critical("Falha ao conectar ao RabbitMQ. Encerrando...")
        sys.exit(1) 