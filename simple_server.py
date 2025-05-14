#!/usr/bin/env python
"""
Простейший HTTP-сервер для Timeweb Cloud
Гарантированно работает на порту 8080
"""
import http.server
import socketserver
import json
import time
import os
import sys
import threading
import logging
import subprocess

# Настройка логирования в файл и консоль
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("server.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("simple_server")

# Импортируем мониторинг ресурсов
try:
    from resource_monitor import monitor, add_monitor_routes
    MONITOR_AVAILABLE = True
    logger.info("Мониторинг ресурсов успешно импортирован")
except ImportError as e:
    logger.warning(f"Не удалось импортировать мониторинг ресурсов: {e}")
    MONITOR_AVAILABLE = False

# Порт для сервера
PORT = int(os.environ.get("PORT", 8080))

# Статус бота
BOT_STATUS = {
    "status": "starting",
    "start_time": time.time(),
    "bot_process": None,
    "last_error": None
}

class SimpleHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    """Простой обработчик HTTP-запросов"""
    
    def log_message(self, format, *args):
        """Переопределяем логирование запросов"""
        logger.info(f"{self.address_string()} - {format % args}")
    
    def do_GET(self):
        """Обработка GET-запросов"""
        # Отвечаем на любой запрос успешным статусом
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        # Базовый ответ со статусом
        response = {
            "status": BOT_STATUS["status"],
            "uptime": int(time.time() - BOT_STATUS["start_time"]),
            "timestamp": int(time.time())
        }
        
        # Добавляем дополнительную информацию в зависимости от запроса
        if self.path == "/reset":
            response["message"] = "Resetting bot process..."
            threading.Thread(target=restart_bot).start()
        elif self.path == "/start_bot":
            response["message"] = "Starting bot process..."
            threading.Thread(target=start_bot_process).start()
        elif self.path == "/status":
            # Добавляем расширенную информацию о статусе
            if BOT_STATUS["bot_process"] is not None:
                response["bot_running"] = BOT_STATUS["bot_process"].poll() is None
                response["bot_pid"] = BOT_STATUS["bot_process"].pid if BOT_STATUS["bot_process"].poll() is None else None
            if BOT_STATUS["last_error"]:
                response["last_error"] = BOT_STATUS["last_error"]
            
            # Добавляем информацию о ресурсах, если доступен мониторинг
            if MONITOR_AVAILABLE:
                try:
                    import psutil
                    response["system"] = {
                        "cpu_percent": psutil.cpu_percent(interval=0.5),
                        "memory_percent": psutil.virtual_memory().percent,
                        "memory_available_mb": round(psutil.virtual_memory().available / (1024 * 1024), 2)
                    }
                except ImportError:
                    pass
        elif self.path == "/monitor" and MONITOR_AVAILABLE:
            # Если запрос к /monitor и мониторинг доступен, передаем запрос монитору
            self.wfile.write(monitor.get_status().encode())
            return
        
        # Отправляем ответ
        self.wfile.write(json.dumps(response, indent=2).encode())

def start_bot_process():
    """Запускает бота в отдельном процессе"""
    global BOT_STATUS
    
    # Если процесс уже запущен, сначала останавливаем его
    if BOT_STATUS["bot_process"] is not None and BOT_STATUS["bot_process"].poll() is None:
        logger.info("Останавливаем существующий процесс бота...")
        try:
            BOT_STATUS["bot_process"].terminate()
            # Даем процессу время на завершение
            for _ in range(5):
                if BOT_STATUS["bot_process"].poll() is not None:
                    break
                time.sleep(1)
            # Если процесс не завершился, убиваем его
            if BOT_STATUS["bot_process"].poll() is None:
                BOT_STATUS["bot_process"].kill()
        except Exception as e:
            logger.error(f"Ошибка при остановке процесса бота: {e}")
    
    # Запускаем бота
    logger.info("Запуск процесса бота...")
    BOT_STATUS["status"] = "starting_bot"
    
    try:
        # Пробуем запустить бота
        bot_process = subprocess.Popen(
            ["python", "bot.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Построчная буферизация
            env=os.environ.copy()  # Передаем все переменные окружения
        )
        
        BOT_STATUS["bot_process"] = bot_process
        BOT_STATUS["status"] = "bot_running"
        
        # Запускаем потоки для чтения вывода бота
        def reader(stream, prefix):
            for line in stream:
                logger.info(f"{prefix}: {line.rstrip()}")
        
        threading.Thread(target=reader, args=(bot_process.stdout, "BOT_OUT"), daemon=True).start()
        threading.Thread(target=reader, args=(bot_process.stderr, "BOT_ERR"), daemon=True).start()
        
        # Запускаем поток для мониторинга состояния бота
        def monitor():
            while True:
                # Проверяем, работает ли бот
                if bot_process.poll() is not None:
                    exit_code = bot_process.poll()
                    logger.error(f"Процесс бота завершился с кодом {exit_code}")
                    BOT_STATUS["status"] = "bot_crashed"
                    BOT_STATUS["last_error"] = f"Bot exited with code {exit_code}"
                    break
                time.sleep(5)
        
        threading.Thread(target=monitor, daemon=True).start()
        
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        BOT_STATUS["status"] = "bot_start_failed"
        BOT_STATUS["last_error"] = str(e)
        
def restart_bot():
    """Перезапускает бота"""
    logger.info("Перезапуск бота...")
    start_bot_process()

def run_server():
    """Запускает HTTP-сервер"""
    try:
        # Ставим SO_REUSEADDR для предотвращения ошибки "Address already in use"
        socketserver.TCPServer.allow_reuse_address = True
        
        # Создаем класс обработчика
        handler_class = SimpleHTTPRequestHandler
        
        # Если доступен мониторинг, добавляем его маршруты
        if MONITOR_AVAILABLE:
            handler_class = add_monitor_routes(handler_class)
        
        with socketserver.TCPServer(("", PORT), handler_class) as httpd:
            logger.info(f"Сервер запущен на порту {PORT}")
            httpd.serve_forever()
    except Exception as e:
        logger.error(f"Ошибка при запуске сервера: {e}")
        sys.exit(1)

if __name__ == "__main__":
    logger.info("===== Запуск простого HTTP-сервера =====")
    
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
        logger.info("Мониторинг ресурсов запущен")
    
    # Запускаем поток для бота
    threading.Thread(target=start_bot_process, daemon=True).start()
    
    # Запускаем HTTP-сервер в основном потоке
    run_server() 