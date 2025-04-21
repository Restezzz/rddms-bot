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
BOT_TOKEN = os.getenv("BOT_TOKEN", "7937225313:AAHjFkasjVqVnR-W4y3vKU81ysFQ7ZBKkCo")
logger.info(f"Загружен токен бота: {BOT_TOKEN[:10]}...")

# Настройки OpenRouter API
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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")
# Проверяем, что ключ не пустой и имеет правильный формат
if not OPENROUTER_API_KEY or not OPENROUTER_API_KEY.startswith("sk-or-"):
    logger.error(f"Неверный формат API ключа OpenRouter: {OPENROUTER_API_KEY[:10]}...")
else:
    logger.info(f"Загружен API ключ OpenRouter: {OPENROUTER_API_KEY[:10]}...")

# Расширенный список URL API для резервного подключения
OPENROUTER_API_URLS = [
    "https://openrouter.ai/api/v1/chat/completions",
    "https://api.openrouter.ai/api/v1/chat/completions", 
    "https://openrouter.ai/v1/chat/completions",
    "https://openrouterme.org/api/v1/chat/completions",
    "https://openrouterme.org/v1/chat/completions"
]
logger.info(f"Загружено {len(OPENROUTER_API_URLS)} URL для API")

# Список разрешенных рефереров
ALLOWED_REFERERS = [
    "https://timeweb.cloud",
    "https://railway.app",
    "https://localhost",
    "https://rddm-bot.ru"
]

# Заголовки для OpenRouter API
OPENROUTER_HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "HTTP-Referer": ALLOWED_REFERERS[0],
    "X-Title": "RDDM Bot"
}

# Настройки прокси из переменных окружения
HTTP_PROXY = os.getenv("HTTP_PROXY")
HTTPS_PROXY = os.getenv("HTTPS_PROXY")

if HTTP_PROXY or HTTPS_PROXY:
    logger.info(f"Найдены настройки прокси: HTTP={HTTP_PROXY}, HTTPS={HTTPS_PROXY}")
    # Устанавливаем прокси для requests
    os.environ["REQUESTS_CA_BUNDLE"] = os.getenv("REQUESTS_CA_BUNDLE", "")

# Модель
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-4-maverick:free")
# Альтернативные модели для бэкапа, если основная недоступна
BACKUP_MODELS = [
    "anthropic/claude-3-haiku",
    "openai/gpt-3.5-turbo",
    "google/gemini-pro"
]
logger.info(f"Основная модель: {OPENROUTER_MODEL}")

# Таймауты для запросов
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "60"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
logger.info(f"Таймаут запросов: {REQUEST_TIMEOUT}с, макс. попыток: {MAX_RETRIES}") 