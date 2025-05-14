#!/usr/bin/env python
"""
Скрипт для перезапуска бота на Timeweb Cloud.
Использование:
- Через SSH: python restart.py
- Скачать и запустить локально, указав IP-адрес сервера: python restart.py --host=123.45.67.89
"""

import argparse
import requests
import time
import os
import sys
import subprocess

def get_server_ip():
    """Пытается определить IP сервера"""
    try:
        # Если запускается на сервере
        import socket
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        return ip
    except:
        return "localhost"

def restart_bot(host, port=8080):
    """Перезапускает бота, сначала сбрасывая все активные запросы"""
    
    reset_url = f"http://{host}:{port}/reset"
    print(f"Сбрасываем все активные запросы через {reset_url}...")
    
    try:
        response = requests.get(reset_url, timeout=5)
        if response.status_code == 200:
            print("Все активные запросы успешно сброшены")
        else:
            print(f"Ошибка при сбросе запросов: {response.status_code}, {response.text}")
    except requests.RequestException as e:
        print(f"Ошибка при подключении к серверу: {e}")
        return False
    
    # Небольшая пауза для завершения активных процессов
    time.sleep(2)
    
    # Если скрипт запущен на сервере, перезапускаем бота
    if host in ["localhost", "127.0.0.1"] or host == get_server_ip():
        print("Перезапускаем бота локально...")
        
        try:
            # Находим PID процесса Python, запущенного с bot.py
            ps_output = subprocess.check_output(["ps", "-ef"], text=True)
            for line in ps_output.splitlines():
                if "python" in line and "bot.py" in line and "grep" not in line:
                    pid = line.split()[1]
                    print(f"Найден процесс бота с PID {pid}, завершаем...")
                    os.system(f"kill {pid}")
            
            # Даем процессу время на завершение
            time.sleep(3)
            
            # Запускаем бота заново в фоне
            print("Запускаем бота заново...")
            os.system("python bot.py &")
            print("Бот перезапущен!")
            return True
        except Exception as e:
            print(f"Ошибка при перезапуске бота: {e}")
            return False
    else:
        print(f"Скрипт запущен не на сервере ({host}). Для полного перезапуска запустите на сервере.")
        print("Сброс активных запросов выполнен успешно.")
        return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Перезапуск бота RDDM")
    parser.add_argument("--host", default=get_server_ip(), help="IP-адрес сервера")
    parser.add_argument("--port", type=int, default=8080, help="Порт сервера")
    
    args = parser.parse_args()
    
    print(f"Перезапуск бота на {args.host}:{args.port}...")
    restart_bot(args.host, args.port) 