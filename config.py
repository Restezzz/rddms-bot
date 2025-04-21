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
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
logger.info(f"Используем URL API: {OPENROUTER_API_URL}")

# Модель
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-4-maverick:free")
logger.info(f"Используем модель: {OPENROUTER_MODEL}") 