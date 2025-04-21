import os
import logging
from dotenv import load_dotenv, find_dotenv

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Пытаемся найти .env файл
env_path = find_dotenv()
if env_path:
    logger.info(f"Найден .env файл: {env_path}")
    load_dotenv(env_path)
else:
    logger.warning("Файл .env не найден, используем значения по умолчанию")
    load_dotenv()

# Токен Telegram бота
BOT_TOKEN = os.getenv("BOT_TOKEN", "7994914232:AAFlg-YfYKw9QQHY3jyZ22V14rXPwlGiqyQ")
logger.info(f"Загружен токен бота: {BOT_TOKEN[:10]}...")

# Настройки OpenRouter API
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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")
# Проверяем, что ключ не пустой и имеет правильный формат
if not OPENROUTER_API_KEY or not OPENROUTER_API_KEY.startswith("sk-or-"):
    logger.error(f"Неверный формат API ключа OpenRouter: {OPENROUTER_API_KEY[:10]}...")
else:
    logger.info(f"Загружен API ключ OpenRouter: {OPENROUTER_API_KEY[:10]}...")

# URL API может меняться
OPENROUTER_API_URLS = [
    "https://openrouter.ai/api/v1/chat/completions",
    "https://api.openrouter.ai/api/v1/chat/completions", 
    "https://openrouter.ai/v1/chat/completions"
]
logger.info(f"Основной URL API: {OPENROUTER_API_URLS[0]}")

# Заголовки для OpenRouter API
OPENROUTER_HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "HTTP-Referer": "https://railway.app",
    "X-Title": "RDDM Bot"
}

# Модель
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-4-maverick:free")
logger.info(f"Используем модель: {OPENROUTER_MODEL}") 