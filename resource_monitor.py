#!/usr/bin/env python
"""
Модуль мониторинга системных ресурсов
Отслеживает использование CPU и памяти, отправляет уведомления
"""
import os
import asyncio
import logging
import time
import json
from datetime import datetime
import threading

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("monitor.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("resource_monitor")

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    logger.warning("psutil не установлен, мониторинг ресурсов будет ограничен")
    PSUTIL_AVAILABLE = False

class ResourceMonitor:
    def __init__(self, 
                 admin_chat_id=None, 
                 check_interval=60, 
                 cpu_threshold=90, 
                 memory_threshold=90,
                 history_size=100):
        """
        Инициализация монитора ресурсов
        
        :param admin_chat_id: ID чата администратора для уведомлений
        :param check_interval: Интервал проверки в секундах
        :param cpu_threshold: Порог загрузки CPU (%)
        :param memory_threshold: Порог использования памяти (%)
        :param history_size: Количество точек истории для хранения
        """
        self.admin_chat_id = admin_chat_id
        self.check_interval = check_interval
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self.history_size = history_size
        
        # Данные мониторинга
        self.monitoring_data = {
            "last_update": time.time(),
            "current": {
                "cpu": 0,
                "memory": 0,
                "uptime": 0
            },
            "history": [],
            "alerts": []
        }
        
        # Флаг работы мониторинга
        self.is_running = False
        
        # Время запуска
        self.start_time = time.time()
        
        # Блокировка для многопоточного доступа
        self.lock = threading.Lock()
        
        logger.info(f"Монитор ресурсов инициализирован (CPU: {cpu_threshold}%, RAM: {memory_threshold}%)")
    
    def start(self):
        """Запуск мониторинга в отдельном потоке"""
        if self.is_running:
            logger.warning("Монитор ресурсов уже запущен")
            return
        
        self.is_running = True
        threading.Thread(target=self._monitoring_loop, daemon=True).start()
        logger.info("Мониторинг ресурсов запущен")
    
    def stop(self):
        """Остановка мониторинга"""
        self.is_running = False
        logger.info("Мониторинг ресурсов остановлен")
    
    def _monitoring_loop(self):
        """Основной цикл мониторинга"""
        last_alert_time = 0
        
        while self.is_running:
            try:
                # Получаем данные о ресурсах
                cpu_percent, memory_percent = self._get_resource_usage()
                uptime = int(time.time() - self.start_time)
                
                # Обновляем данные мониторинга
                with self.lock:
                    self.monitoring_data["last_update"] = time.time()
                    self.monitoring_data["current"]["cpu"] = cpu_percent
                    self.monitoring_data["current"]["memory"] = memory_percent
                    self.monitoring_data["current"]["uptime"] = uptime
                    
                    # Добавляем точку в историю
                    history_point = {
                        "timestamp": time.time(),
                        "cpu": cpu_percent,
                        "memory": memory_percent
                    }
                    self.monitoring_data["history"].append(history_point)
                    
                    # Ограничиваем размер истории
                    if len(self.monitoring_data["history"]) > self.history_size:
                        self.monitoring_data["history"] = self.monitoring_data["history"][-self.history_size:]
                
                # Логируем текущее состояние
                if cpu_percent > 50 or memory_percent > 50:
                    logger.info(f"Ресурсы: CPU {cpu_percent:.1f}%, RAM {memory_percent:.1f}%")
                else:
                    logger.debug(f"Ресурсы: CPU {cpu_percent:.1f}%, RAM {memory_percent:.1f}%")
                
                # Проверяем превышение порогов
                current_time = time.time()
                alert_cooldown = 300  # Минимум 5 минут между алертами
                
                if (cpu_percent > self.cpu_threshold or memory_percent > self.memory_threshold) and \
                   (current_time - last_alert_time > alert_cooldown):
                    alert_message = self._generate_alert(cpu_percent, memory_percent)
                    self._send_alert(alert_message)
                    last_alert_time = current_time
                    
                    # Сохраняем алерт в историю
                    with self.lock:
                        self.monitoring_data["alerts"].append({
                            "timestamp": current_time,
                            "cpu": cpu_percent,
                            "memory": memory_percent,
                            "message": alert_message
                        })
                        
                        # Ограничиваем количество алертов в истории
                        if len(self.monitoring_data["alerts"]) > 20:
                            self.monitoring_data["alerts"] = self.monitoring_data["alerts"][-20:]
            
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
            
            # Пауза между проверками
            time.sleep(self.check_interval)
    
    def _get_resource_usage(self):
        """Получение данных о загрузке CPU и памяти"""
        if not PSUTIL_AVAILABLE:
            # Если psutil не доступен, используем упрощенный способ
            try:
                # В Windows можно использовать wmic
                if os.name == 'nt':
                    import subprocess
                    cpu = float(subprocess.check_output('wmic cpu get loadpercentage', shell=True).decode().strip().split('\n')[1])
                    mem = float(subprocess.check_output('wmic OS get FreePhysicalMemory,TotalVisibleMemorySize', shell=True).decode().strip().split('\n')[1].split())
                    memory_percent = 100 - (float(mem[0]) / float(mem[1]) * 100)
                    return cpu, memory_percent
                else:
                    # Для Linux используем /proc
                    with open('/proc/stat', 'r') as f:
                        cpu_lines = f.readlines()
                    cpu_line = cpu_lines[0].split()
                    cpu_idle = float(cpu_line[4])
                    cpu_total = sum(float(x) for x in cpu_line[1:])
                    cpu_percent = 100 - (cpu_idle / cpu_total * 100)
                    
                    with open('/proc/meminfo', 'r') as f:
                        mem_lines = f.readlines()
                    total = int(mem_lines[0].split()[1])
                    free = int(mem_lines[1].split()[1])
                    memory_percent = 100 - (free / total * 100)
                    
                    return cpu_percent, memory_percent
            except Exception as e:
                logger.error(f"Ошибка при получении данных о ресурсах: {e}")
                return 0, 0
        else:
            # Используем psutil если доступен
            cpu_percent = psutil.cpu_percent(interval=1)
            memory_percent = psutil.virtual_memory().percent
            return cpu_percent, memory_percent
    
    def _generate_alert(self, cpu_percent, memory_percent):
        """Генерация текста уведомления"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"⚠️ ВНИМАНИЕ! Высокая нагрузка ({timestamp}):\n"
        message += f"CPU: {cpu_percent:.1f}% (порог: {self.cpu_threshold}%)\n"
        message += f"RAM: {memory_percent:.1f}% (порог: {self.memory_threshold}%)\n"
        
        # Добавляем информацию о процессах, если psutil доступен
        if PSUTIL_AVAILABLE:
            try:
                # Получаем топ-5 процессов по CPU
                processes = []
                for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                    processes.append(proc.info)
                
                # Сортируем по CPU
                top_cpu = sorted(processes, key=lambda x: x['cpu_percent'], reverse=True)[:3]
                
                if top_cpu:
                    message += "\nТоп процессы по CPU:\n"
                    for proc in top_cpu:
                        message += f"- {proc['name']} (PID: {proc['pid']}): CPU {proc['cpu_percent']:.1f}%, RAM {proc['memory_percent']:.1f}%\n"
            except Exception as e:
                logger.error(f"Ошибка при получении информации о процессах: {e}")
        
        return message
    
    def _send_alert(self, message):
        """Отправка уведомления"""
        logger.warning(f"АЛЕРТ: {message}")
        
        # Если настроен ID чата администратора, отправляем через Telegram
        if self.admin_chat_id:
            try:
                # Импортируем только при необходимости
                from telegram import Bot
                from config import BOT_TOKEN
                
                async def send_telegram_message():
                    bot = Bot(token=BOT_TOKEN)
                    await bot.send_message(chat_id=self.admin_chat_id, text=message, parse_mode='HTML')
                
                # Запускаем asyncio задачу
                asyncio.run(send_telegram_message())
                logger.info(f"Уведомление отправлено в Telegram (chat_id: {self.admin_chat_id})")
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления в Telegram: {e}")
    
    def get_status(self):
        """Получение текущего статуса для API"""
        with self.lock:
            return json.dumps(self.monitoring_data)

# Создаем глобальный экземпляр монитора
monitor = ResourceMonitor()

# Функция для интеграции с HTTP-сервером
def add_monitor_routes(server_handler_class):
    """
    Добавляет обработку путей мониторинга в HTTP-сервер
    
    :param server_handler_class: Класс обработчика HTTP-запросов
    :return: Обновленный класс с поддержкой мониторинга
    """
    original_do_get = server_handler_class.do_GET
    
    def enhanced_do_get(self):
        if self.path == "/monitor" or self.path == "/monitor/":
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(monitor.get_status().encode())
        else:
            original_do_get(self)
    
    server_handler_class.do_GET = enhanced_do_get
    return server_handler_class

if __name__ == "__main__":
    # Тест мониторинга
    test_monitor = ResourceMonitor(check_interval=5)
    test_monitor.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        test_monitor.stop()
        print("Мониторинг остановлен") 