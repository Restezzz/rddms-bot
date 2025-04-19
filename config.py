import os
from dotenv import load_dotenv

load_dotenv()

# Токен Telegram бота
BOT_TOKEN = os.getenv("BOT_TOKEN", "7994914232:AAFlg-YfYKw9QQHY3jyZ22V14rXPwlGiqyQ")

# Настройки OpenRouter API
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-r1:free") 