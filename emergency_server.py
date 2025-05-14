#!/usr/bin/env python
"""
Аварийный HTTP-сервер для Timeweb Cloud
Запускается если основное приложение не может работать
"""
import sys
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
import time
import signal

logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("emergency_server")

# Импортируем мониторинг ресурсов, если доступен
try:
    from resource_monitor import monitor
    MONITOR_AVAILABLE = True
    logger.info("Мониторинг ресурсов успешно импортирован")
except ImportError:
    MONITOR_AVAILABLE = False
    logger.warning("Мониторинг ресурсов недоступен")

# Порт для сервера
PORT = int(os.environ.get("PORT", 8080))

class EmergencyHandler(BaseHTTPRequestHandler):
    """Простой обработчик HTTP-запросов для аварийного режима"""
    
    def log_message(self, format, *args):
        """Переопределяем логирование запросов"""
        logger.info(f"{self.address_string()} - {format % args}")
    
    def do_GET(self):
        """Обработка GET-запросов"""
        # Если запрос к мониторингу и мониторинг доступен
        if self.path == "/monitor" and MONITOR_AVAILABLE:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(monitor.get_status().encode())
            return
            
        # Отвечаем на запрос к корневому пути
        if self.path == "/" or self.path == "/health":
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            # Формируем ответ в зависимости от пути
            response_data = {
                "status": "error",
                "mode": "emergency",
                "timestamp": int(time.time()),
                "message": "Бот находится в аварийном режиме. Пожалуйста, проверьте логи."
            }
            
            # Добавляем информацию о системе, если возможно
            try:
                import psutil
                response_data["system"] = {
                    "cpu_percent": psutil.cpu_percent(interval=0.5),
                    "memory_percent": psutil.virtual_memory().percent,
                    "memory_available_mb": round(psutil.virtual_memory().available / (1024 * 1024), 2)
                }
            except ImportError:
                pass
            
            # Если запрос к /reset, добавляем информацию о сбросе
            if self.path == "/reset":
                response_data["message"] = "Команда сброса получена, но бот в аварийном режиме."
                logger.info("Получена команда сброса в аварийном режиме")
            
            # Отправляем JSON-ответ
            self.wfile.write(json.dumps(response_data).encode())
        else:
            # Для всех других путей отправляем 404
            self.send_response(404)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {"status": "error", "message": f"Путь {self.path} не найден"}
            self.wfile.write(json.dumps(response).encode())

def run_emergency_server(port=PORT):
    """Запускает аварийный HTTP-сервер"""
    try:
        # Запускаем мониторинг ресурсов, если доступен
        if MONITOR_AVAILABLE:
            # Настраиваем ID чата администратора из переменной окружения или config
            admin_chat_id = os.environ.get("ADMIN_CHAT_ID")
            if not admin_chat_id:
                try:
                    from config import ADMIN_CHAT_ID
                    admin_chat_id = ADMIN_CHAT_ID
                except (ImportError, AttributeError):
                    admin_chat_id = None
            
            # Запускаем мониторинг
            if admin_chat_id:
                monitor.admin_chat_id = admin_chat_id
                logger.info(f"Настроены уведомления для администратора: {admin_chat_id}")
            
            monitor.start()
            logger.info("Мониторинг ресурсов запущен в аварийном режиме")
            
            # Отправляем уведомление о переходе в аварийный режим
            if admin_chat_id:
                try:
                    import asyncio
                    from telegram import Bot
                    from config import BOT_TOKEN
                    
                    async def send_emergency_notification():
                        bot = Bot(token=BOT_TOKEN)
                        message = "🚨 ВНИМАНИЕ! Бот перешел в аварийный режим!\n"
                        message += f"Время: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                        message += "Проверьте логи и перезапустите приложение."
                        await bot.send_message(chat_id=admin_chat_id, text=message)
                    
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(send_emergency_notification())
                    loop.close()
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление об аварийном режиме: {e}")
        
        server = HTTPServer(('0.0.0.0', port), EmergencyHandler)
        logger.info(f"Аварийный HTTP-сервер запущен на порту {port}")
        
        # Регистрируем обработчик сигналов для корректного завершения
        def signal_handler(sig, frame):
            logger.info(f"Получен сигнал {sig}, завершаем работу")
            server.server_close()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Запускаем сервер
        server.serve_forever()
    except Exception as e:
        logger.error(f"Ошибка при запуске аварийного сервера: {e}")
        sys.exit(1)

if __name__ == "__main__":
    logger.info("===== Запуск аварийного HTTP-сервера =====")
    run_emergency_server() 