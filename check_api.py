import os
import sys
import logging
import asyncio
from llm_client import LLMClient
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

async def main():
    """Проверяет работу LLM клиента с OpenRouter API."""
    logger.info("Запуск проверки подключения к OpenRouter через LLMClient...")
    
    # Создаем экземпляр клиента
    client = LLMClient()
    
    # Простой запрос для теста
    system_prompt = "Ты помощник для тестирования API."
    user_prompt = "Напиши одно предложение для проверки API подключения."
    
    try:
        # Пробуем выполнить запрос
        logger.info("Отправляем тестовый запрос...")
        start_time = asyncio.get_event_loop().time()
        
        response = await client._send_request_async(system_prompt, user_prompt)
        
        elapsed = asyncio.get_event_loop().time() - start_time
        logger.info(f"Запрос выполнен за {elapsed:.2f} секунд")
        
        # Проверяем результат
        if response:
            logger.info(f"✅ API работает! Получен ответ: {response[:100]}..." if len(response) > 100 else response)
            return True
        else:
            logger.error("❌ Получен пустой ответ от API")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке API: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        logger.info("Проверка прервана пользователем")
        sys.exit(1) 