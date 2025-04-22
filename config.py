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
BOT_TOKEN = os.getenv("BOT_TOKEN", "7782469339:AAEEpEHAkB6DN3SAD6LPbAL1D_rg6EdfZV4")
logger.info(f"Загружен токен бота: {BOT_TOKEN[:13]}...")

# Настройки OpenRouter API
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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")
# Проверяем, что ключ не пустой и имеет правильный формат
if not OPENROUTER_API_KEY or not OPENROUTER_API_KEY.startswith("sk-or-"):
    logger.error(f"Неверный формат API ключа OpenRouter: {OPENROUTER_API_KEY[:13]}...")
else:
    logger.info(f"Загружен API ключ OpenRouter: {OPENROUTER_API_KEY[:13]}...")

# URL API может меняться
OPENROUTER_API_URLS = [
    "https://api.openrouter.ai/api/v1/chat/completions",  # Сначала другой поддомен
    "https://openrouter.ai/api/v1/chat/completions", 
    "https://openrouter.ai/v1/chat/completions",
    "https://openrouter.ai/api/chat/completions",
    "https://api.openai.com/v1/chat/completions",  # Последняя надежда - обычное API OpenAI
]
logger.info(f"Основной URL API: {OPENROUTER_API_URLS[0]}")

# Заголовки для OpenRouter API
OPENROUTER_HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Referer": "https://railway.app",
    "X-Title": "RDDM Bot"
}

# Модель
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-4-maverick:free")
logger.info(f"Используем модель: {OPENROUTER_MODEL}")

# Альтернативные модели (если основная не работает)
ALTERNATIVE_MODELS = [
    "anthropic/claude-3-sonnet:beta",
    "anthropic/claude-3-haiku:beta",
    "openai/gpt-3.5-turbo",
    "google/gemini-1.5-pro"
]
logger.info(f"Доступно {len(ALTERNATIVE_MODELS)} альтернативных моделей")

# Настройки отладки и безопасности
DEBUG_MODE = True  # Режим отладки для дополнительной информации
DISABLE_SSL_VERIFY = True  # Отключение проверки SSL сертификатов
logger.info(f"Режим отладки: {DEBUG_MODE}, Проверка SSL: {not DISABLE_SSL_VERIFY}") 