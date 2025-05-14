#!/usr/bin/env python
"""
Скрипт запуска для Timeweb Cloud
Гарантирует корректный запуск сервера и обработку ошибок
"""
import os
import sys
import subprocess
import time
import logging
import signal

logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("run")

# Функция для обработки сигналов завершения
def signal_handler(sig, frame):
    logger.info(f"Получен сигнал {sig}, завершаем работу")
    sys.exit(0)

# Регистрируем обработчики сигналов
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def main():
    logger.info("===== Запуск приложения на Timeweb Cloud =====")
    
    # Устанавливаем переменную окружения PORT для правильного определения порта
    os.environ["PORT"] = "8080"
    
    # Проверяем наличие delete_webhook.py
    if os.path.exists("delete_webhook.py"):
        logger.info("Выполняем удаление webhook...")
        try:
            # Запускаем delete_webhook.py и дожидаемся завершения
            result = subprocess.run(["python", "delete_webhook.py"], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE, 
                                   text=True,
                                   check=False)
            logger.info(f"Скрипт delete_webhook.py завершен с кодом {result.returncode}")
            if result.stdout:
                logger.info(f"Вывод: {result.stdout}")
            if result.stderr:
                logger.error(f"Ошибки: {result.stderr}")
        except Exception as e:
            logger.error(f"Ошибка при удалении webhook: {e}")
    
    # Небольшая пауза перед запуском бота
    time.sleep(1)
    
    # Проверяем наличие psutil и устанавливаем при необходимости
    try:
        import psutil
        logger.info("Библиотека psutil уже установлена")
    except ImportError:
        logger.info("Устанавливаем psutil для мониторинга...")
        try:
            result = subprocess.run([sys.executable, "-m", "pip", "install", "psutil"],
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              text=True)
            if result.returncode == 0:
                logger.info("psutil успешно установлен")
            else:
                logger.error(f"Ошибка установки psutil: {result.stderr}")
        except Exception as e:
            logger.error(f"Не удалось установить psutil: {e}")
    
    # Запускаем простой сервер вместо бота
    if os.path.exists("simple_server.py"):
        logger.info("Запуск простого HTTP-сервера...")
        try:
            server_process = subprocess.Popen(
                ["python", "simple_server.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            # Функция для чтения вывода из потока
            def read_stream(stream, prefix):
                while True:
                    line = stream.readline()
                    if not line:
                        break
                    logger.info(f"{prefix}: {line.rstrip()}")
            
            # Запускаем отдельные потоки для чтения stdout и stderr
            import threading
            stdout_thread = threading.Thread(target=read_stream, args=(server_process.stdout, "SERVER"))
            stderr_thread = threading.Thread(target=read_stream, args=(server_process.stderr, "SERVER_ERR"))
            stdout_thread.daemon = True
            stderr_thread.daemon = True
            stdout_thread.start()
            stderr_thread.start()
            
            # Проверяем состояние процесса каждые 2 секунды
            while True:
                # Если процесс завершился, запускаем аварийный сервер
                if server_process.poll() is not None:
                    exit_code = server_process.returncode
                    logger.error(f"Сервер неожиданно завершился с кодом {exit_code}")
                    
                    # Запускаем аварийный HTTP-сервер
                    logger.info("Запускаем аварийный HTTP-сервер после сбоя...")
                    if os.path.exists("emergency_server.py"):
                        os.execv(sys.executable, [sys.executable, "emergency_server.py"])
                    else:
                        # Используем встроенный аварийный сервер
                        from http.server import HTTPServer, BaseHTTPRequestHandler
                        
                        class SimpleHandler(BaseHTTPRequestHandler):
                            def do_GET(self):
                                self.send_response(200)
                                self.send_header('Content-type', 'application/json')
                                self.end_headers()
                                response = f'{{"status":"error","message":"Server crashed with exit code {exit_code}"}}'
                                self.wfile.write(response.encode())
                        
                        server = HTTPServer(('0.0.0.0', 8080), SimpleHandler)
                        logger.info("Встроенный аварийный HTTP-сервер запущен на порту 8080")
                        server.serve_forever()
                
                # Если процесс работает, ждем 2 секунды
                time.sleep(2)
            
        except Exception as e:
            logger.error(f"Ошибка при запуске простого сервера: {e}")
            # Пробуем запустить аварийный сервер
            if os.path.exists("emergency_server.py"):
                os.execv(sys.executable, [sys.executable, "emergency_server.py"])
            else:
                # Запускаем встроенный аварийный сервер
                from http.server import HTTPServer, BaseHTTPRequestHandler
                
                class SimpleHandler(BaseHTTPRequestHandler):
                    def do_GET(self):
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        response = f'{{"status":"error","message":"Failed to start server: {str(e)}"}}'
                        self.wfile.write(response.encode())
                
                server = HTTPServer(('0.0.0.0', 8080), SimpleHandler)
                logger.info("Встроенный аварийный HTTP-сервер запущен на порту 8080")
                server.serve_forever()
                
    # Если simple_server.py отсутствует, запускаем бота напрямую
    else:
        # Запускаем бота
        logger.info("Запуск бота...")
        try:
            # Запускаем бота как подпроцесс
            bot_process = subprocess.Popen(["python", "bot.py"], 
                                        stdout=subprocess.PIPE, 
                                        stderr=subprocess.PIPE, 
                                        text=True)
            
            # Даем боту время для запуска
            time.sleep(5)
            
            # Проверяем, запустился ли процесс
            if bot_process.poll() is not None:
                # Процесс завершился сразу, это ошибка
                stdout, stderr = bot_process.communicate()
                logger.error(f"Ошибка при запуске бота, код выхода: {bot_process.returncode}")
                if stdout:
                    logger.info(f"Вывод бота: {stdout}")
                if stderr:
                    logger.error(f"Ошибки бота: {stderr}")
                
                # Запускаем аварийный HTTP-сервер
                logger.info("Запускаем аварийный HTTP-сервер...")
                if os.path.exists("emergency_server.py"):
                    os.execv(sys.executable, [sys.executable, "emergency_server.py"])
                else:
                    logger.error("Файл emergency_server.py не найден!")
                    # Используем встроенный аварийный сервер
                    from http.server import HTTPServer, BaseHTTPRequestHandler
                    
                    class SimpleHandler(BaseHTTPRequestHandler):
                        def do_GET(self):
                            self.send_response(200)
                            self.send_header('Content-type', 'application/json')
                            self.end_headers()
                            response = '{"status":"error","message":"Bot failed to start, check logs"}'
                            self.wfile.write(response.encode())
                
                    server = HTTPServer(('0.0.0.0', 8080), SimpleHandler)
                    logger.info("Встроенный аварийный HTTP-сервер запущен на порту 8080")
                    server.serve_forever()
            
            # Если процесс запустился, начинаем читать его вывод
            logger.info("Бот успешно запущен, начинаем читать вывод")
            
            # Функция для чтения вывода из потока
            def read_stream(stream, prefix):
                while True:
                    line = stream.readline()
                    if not line:
                        break
                    print(f"{prefix}: {line.rstrip()}")
            
            # Запускаем отдельные потоки для чтения stdout и stderr
            import threading
            stdout_thread = threading.Thread(target=read_stream, args=(bot_process.stdout, "STDOUT"))
            stderr_thread = threading.Thread(target=read_stream, args=(bot_process.stderr, "STDERR"))
            stdout_thread.daemon = True
            stderr_thread.daemon = True
            stdout_thread.start()
            stderr_thread.start()
            
            # Проверяем состояние процесса каждые 2 секунды
            while True:
                # Если процесс завершился, запускаем аварийный сервер
                if bot_process.poll() is not None:
                    exit_code = bot_process.returncode
                    logger.error(f"Бот неожиданно завершился с кодом {exit_code}")
                    
                    # Запускаем аварийный HTTP-сервер
                    logger.info("Запускаем аварийный HTTP-сервер после сбоя...")
                    if os.path.exists("emergency_server.py"):
                        os.execv(sys.executable, [sys.executable, "emergency_server.py"])
                    else:
                        # Используем встроенный аварийный сервер
                        from http.server import HTTPServer, BaseHTTPRequestHandler
                        
                        class SimpleHandler(BaseHTTPRequestHandler):
                            def do_GET(self):
                                self.send_response(200)
                                self.send_header('Content-type', 'application/json')
                                self.end_headers()
                                response = f'{{"status":"error","message":"Bot crashed with exit code {exit_code}"}}'
                                self.wfile.write(response.encode())
                        
                        server = HTTPServer(('0.0.0.0', 8080), SimpleHandler)
                        logger.info("Встроенный аварийный HTTP-сервер запущен на порту 8080")
                        server.serve_forever()
                
                # Если процесс работает, ждем 2 секунды
                time.sleep(2)
        
        except Exception as e:
            logger.error(f"Ошибка при запуске бота: {e}")
            # Запускаем аварийный HTTP-сервер
            logger.info("Запускаем аварийный HTTP-сервер из-за исключения...")
            if os.path.exists("emergency_server.py"):
                os.execv(sys.executable, [sys.executable, "emergency_server.py"])
            else:
                # Используем встроенный аварийный сервер
                from http.server import HTTPServer, BaseHTTPRequestHandler
                
                class SimpleHandler(BaseHTTPRequestHandler):
                    def do_GET(self):
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        response = f'{{"status":"error","message":"Exception: {str(e)}"}}'
                        self.wfile.write(response.encode())
                
                server = HTTPServer(('0.0.0.0', 8080), SimpleHandler)
                logger.info("Встроенный аварийный HTTP-сервер запущен на порту 8080")
                server.serve_forever()

if __name__ == "__main__":
    main() 