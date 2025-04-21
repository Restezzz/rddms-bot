import os
import sys
import logging
import asyncio
from llm_client import LLMClient
from dotenv import load_dotenv
import json

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
    
    # Выводим настройки
    logger.info(f"Используются следующие настройки:")
    logger.info(f"API URLs: {client.api_urls}")
    logger.info(f"Прямые IP URLs: {client.direct_ip_urls}")
    logger.info(f"Основная модель: {client.model}")
    logger.info(f"Резервные модели: {client.backup_models}")
    logger.info(f"Прокси HTTP: {client.http_proxy}")
    logger.info(f"Прокси HTTPS: {client.https_proxy}")
    logger.info(f"Таймаут: {client.request_timeout}с")
    logger.info(f"Максимальное количество попыток: {client.max_retries}")
    
    # Простой запрос для теста
    system_prompt = "Ты помощник для тестирования API."
    user_prompt = "Напиши одно предложение для проверки API подключения. Ответ должен быть максимально коротким."
    
    try:
        # Пробуем выполнить запрос
        logger.info("Отправляем тестовый запрос...")
        start_time = asyncio.get_event_loop().time()
        
        response = await client._send_request_async(system_prompt, user_prompt)
        
        elapsed = asyncio.get_event_loop().time() - start_time
        logger.info(f"Запрос выполнен за {elapsed:.2f} секунд")
        
        # Проверяем результат
        if response:
            logger.info(f"✅ API работает! Получен ответ: {response[:200]}..." if len(response) > 200 else response)
            
            # Проверяем, это заглушка или реальный ответ
            if "от РДДМ" in response or "Движение первых" in response:
                logger.warning("⚠️ Получена заглушка, а не реальный ответ от API")
                return False
            
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
        
        if result:
            logger.info("✅ Проверка успешна! API работает корректно.")
            sys.exit(0)
        else:
            logger.error("❌ Проверка не удалась. API не работает корректно.")
            
            # Рекомендации по решению проблемы
            logger.info("\nРекомендации по устранению проблемы:")
            logger.info("1. Проверьте API ключ в .env файле")
            logger.info("2. Попробуйте добавить IP-адреса из hosts.txt в системный файл hosts:")
            logger.info("   Windows: C:\\Windows\\System32\\drivers\\etc\\hosts")
            logger.info("   Linux: /etc/hosts")
            logger.info("3. Проверьте работу прокси или VPN, если используются")
            logger.info("4. Запустите скрипт check_dns.py для диагностики сетевых проблем")
            
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("Проверка прервана пользователем")
        sys.exit(1) 