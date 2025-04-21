#!/usr/bin/env python
"""
Скрипт для принудительного удаления webhook у бота.
Запустите его один раз перед запуском основного бота.
"""

import requests
import os
import sys
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Получаем токен бота из переменных окружения или аргументов
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN and len(sys.argv) > 1:
    BOT_TOKEN = sys.argv[1]

if not BOT_TOKEN:
    print("Ошибка: Не указан BOT_TOKEN. Укажите его в .env файле или передайте как аргумент командной строки.")
    sys.exit(1)

# URL для удаления webhook
delete_webhook_url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=true"

# URL для получения информации о webhook
get_webhook_info_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"

# Запрашиваем информацию о текущем webhook
print("Получаю информацию о текущем webhook...")
response = requests.get(get_webhook_info_url)
webhook_info = response.json()

if response.status_code == 200 and webhook_info.get("ok"):
    webhook_url = webhook_info.get("result", {}).get("url", "Не установлен")
    print(f"Текущий webhook URL: {webhook_url}")
else:
    print(f"Ошибка при получении информации о webhook: {response.text}")
    sys.exit(1)

# Удаляем webhook
print("Удаляю webhook...")
response = requests.get(delete_webhook_url)
if response.status_code == 200 and response.json().get("ok"):
    print("Webhook успешно удален!")
else:
    print(f"Ошибка при удалении webhook: {response.text}")
    sys.exit(1)

# Проверяем, что webhook действительно удален
print("Проверяю информацию о webhook после удаления...")
response = requests.get(get_webhook_info_url)
webhook_info = response.json()

if response.status_code == 200 and webhook_info.get("ok"):
    webhook_url = webhook_info.get("result", {}).get("url", "Не установлен")
    if not webhook_url or webhook_url == "":
        print("Webhook успешно удален и больше не активен!")
    else:
        print(f"Внимание! Webhook всё ещё активен: {webhook_url}")
        sys.exit(1)
else:
    print(f"Ошибка при получении информации о webhook: {response.text}")
    sys.exit(1)

print("Готово! Теперь вы можете запустить бота в режиме polling.") 