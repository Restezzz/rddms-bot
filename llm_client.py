import requests
import asyncio
import json
import aiohttp
from config import (
    OPENROUTER_API_URLS, OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_HEADERS,
    BACKUP_MODELS, REQUEST_TIMEOUT, MAX_RETRIES, ALLOWED_REFERERS, HTTP_PROXY, HTTPS_PROXY,
    DIRECT_IP_URLS
)
import logging
from rddm_info import get_rddm_knowledge
from session_manager import PostSize
import os
from urllib3.exceptions import InsecureRequestWarning
import urllib3
import time
import random
from urllib.parse import urlparse

# Отключаем предупреждения SSL для отладки
urllib3.disable_warnings(InsecureRequestWarning)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self, api_urls=OPENROUTER_API_URLS, api_key=OPENROUTER_API_KEY, model=OPENROUTER_MODEL, headers=OPENROUTER_HEADERS):
        self.api_urls = api_urls
        self.api_key = api_key
        self.model = model
        self.backup_models = BACKUP_MODELS
        self.headers = headers.copy()
        self.headers.update({
            "Content-Type": "application/json",
        })
        
        # Прямые IP URL для обхода блокировки DNS
        self.direct_ip_urls = DIRECT_IP_URLS
        
        # Настройки прокси из конфига или переменных окружения
        self.http_proxy = HTTP_PROXY or os.environ.get('HTTP_PROXY')
        self.https_proxy = HTTPS_PROXY or os.environ.get('HTTPS_PROXY')
        
        # Таймауты и количество попыток
        self.request_timeout = REQUEST_TIMEOUT
        self.max_retries = MAX_RETRIES
        
        # Список разрешенных реферреров
        self.referers = ALLOWED_REFERERS
    
    async def generate_from_template(self, template_post, topic, post_size=PostSize.LARGE, language="ru"):
        """Генерирует пост на основе шаблона и темы."""
        # Получаем только релевантную информацию о РДДМ
        rddm_info = get_rddm_knowledge(topic)
        
        # Определяем размер поста (в символах)
        size_range = self._get_size_range(post_size)
        min_size, max_size = map(int, size_range.split('-'))
        
        system_prompt = """Ты специалист SMM, создающий посты для социальных сетей от имени Российского движения детей и молодёжи "Движение первых" (РДДМ). 
        Пиши искренним, дружелюбным, но не фамильярным языком. Избегай официальных фраз и канцеляризмов."""
        
        user_prompt = f"""На основе примера поста:

{template_post}

Сгенерируй новый пост на тему: {topic}

Краткая справка о РДДМ:
{rddm_info}

ВАЖНОЕ ОГРАНИЧЕНИЕ ПО ДЛИНЕ! 
Пост должен содержать от {min_size} до {max_size} символов. Тщательно проверь длину текста!

ВАЖНЫЕ ТРЕБОВАНИЯ:
1. Используй следующие типы форматирования текста для Telegram (будет преобразовано в HTML): 
   **жирный текст** - для выделения важных фраз
   `код` - для технических терминов
   ```блок кода``` - для примеров кода или цитат
   ~~зачеркнутый текст~~ - для перечёркивания
   ||скрытый текст|| - для скрытия спойлеров
   [текст ссылки](URL) - для добавления ссылок
2. Пиши простым, современным языком без канцеляризмов
3. Не используй фразы "и так далее", "и прочее", перечисляй конкретно
4. Пиши от имени РДДМ в дружелюбном, но не фамильярном тоне
5. Избегай официоза, пиши как человек для человека
6. Не перечисляй все ценности РДДМ, упоминай только 2-3 уместные к теме
7. Текст должен быть на русском языке
8. Разделяй текст на абзацы для удобного чтения
9. Используй эмодзи (смайлики), если они уместны в контексте поста"""
        
        # Если нужен другой язык
        if language.lower() != "ru":
            user_prompt += f"\nНесмотря на предыдущие требования, пост должен быть написан на {language} языке."
            
        # Генерируем текст
        generated_text = await self._send_request_async(system_prompt, user_prompt)
        
        # Применяем ограничения по размеру
        return self._enforce_size_limits(generated_text, min_size, max_size)
    
    async def generate_without_template(self, topic, post_size=PostSize.LARGE, language="ru"):
        """Генерирует пост без шаблона, только по теме."""
        # Получаем только релевантную информацию о РДДМ
        rddm_info = get_rddm_knowledge(topic)
        
        # Определяем размер поста (в символах)
        size_range = self._get_size_range(post_size)
        min_size, max_size = map(int, size_range.split('-'))
        
        system_prompt = """Ты специалист SMM, создающий посты для социальных сетей от имени Российского движения детей и молодёжи "Движение первых" (РДДМ).
        Пиши искренним, дружелюбным, но не фамильярным языком. Избегай официальных фраз и канцеляризмов."""
        
        user_prompt = f"""Создай интересный пост для социальных сетей на тему: {topic}
        
Краткая справка о РДДМ:
{rddm_info}

ВАЖНОЕ ОГРАНИЧЕНИЕ ПО ДЛИНЕ! 
Пост должен содержать от {min_size} до {max_size} символов. Тщательно проверь длину текста!

ВАЖНЫЕ ТРЕБОВАНИЯ:
1. Используй следующие типы форматирования текста для Telegram (будет преобразовано в HTML): 
   **жирный текст** - для выделения важных фраз
   `код` - для технических терминов
   ```блок кода``` - для примеров кода или цитат
   ~~зачеркнутый текст~~ - для перечёркивания
   ||скрытый текст|| - для скрытия спойлеров
   [текст ссылки](URL) - для добавления ссылок
2. Пиши простым, современным языком без канцеляризмов
3. Не используй фразы "и так далее", "и прочее", перечисляй конкретно
4. Пиши от имени РДДМ в дружелюбном, но не фамильярном тоне 
5. Избегай официоза, пиши как человек для человека
6. Не перечисляй все ценности РДДМ, упоминай только 2-3 уместные к теме
7. Пост должен иметь вступление, основную часть и призыв к действию
8. Текст должен быть на русском языке
9. Разделяй текст на абзацы для удобного чтения
10. Используй эмодзи (смайлики), если они уместны в контексте поста"""
        
        # Если нужен другой язык
        if language.lower() != "ru":
            user_prompt += f"\nНесмотря на предыдущие требования, пост должен быть написан на {language} языке."
            
        # Генерируем текст
        generated_text = await self._send_request_async(system_prompt, user_prompt)
        
        # Применяем ограничения по размеру
        return self._enforce_size_limits(generated_text, min_size, max_size)
    
    async def modify_post(self, current_post, modification_request, language="ru"):
        """Модифицирует существующий пост согласно запросу."""
        system_prompt = """Ты специалист SMM, создающий и редактирующий посты для социальных сетей от имени Российского движения детей и молодёжи "Движение первых" (РДДМ).
        Пиши искренним, дружелюбным, но не фамильярным языком. Избегай официальных фраз и канцеляризмов."""
        
        user_prompt = f"""Вот текущий пост:

{current_post}

Внеси следующие изменения: {modification_request}

ВАЖНЫЕ ТРЕБОВАНИЯ:
1. Сохрани примерно ту же длину что и у исходного поста
2. Используй следующие типы форматирования текста для Telegram (будет преобразовано в HTML): 
   **жирный текст** - для выделения важных фраз
   `код` - для технических терминов
   ```блок кода``` - для примеров кода или цитат
   ~~зачеркнутый текст~~ - для перечёркивания
   ||скрытый текст|| - для скрытия спойлеров
   [текст ссылки](URL) - для добавления ссылок
3. Пиши простым, современным языком без канцеляризмов
4. Не используй фразы "и так далее", "и прочее", перечисляй конкретно
5. Пиши от имени РДДМ в дружелюбном, но не фамильярном тоне
6. Избегай официоза, пиши как человек для человека
7. Текст должен быть на русском языке
8. Разделяй текст на абзацы для удобного чтения
9. Используй эмодзи (смайлики), если они уместны в контексте поста"""
        
        # Если нужен другой язык
        if language.lower() != "ru":
            user_prompt += f"\nНесмотря на предыдущие требования, пост должен быть написан на {language} языке."
            
        # Генерируем текст
        generated_text = await self._send_request_async(system_prompt, user_prompt)
        
        # Сохраняем примерно ту же длину
        current_length = len(current_post)
        return self._enforce_size_limits(generated_text, current_length * 0.8, current_length * 1.2)
    
    def _get_size_range(self, post_size):
        """Возвращает диапазон символов для размера поста."""
        if post_size == PostSize.SMALL:
            return "200-400"
        elif post_size == PostSize.MEDIUM:
            return "400-800"
        else:  # PostSize.LARGE
            return "800-1200"
    
    def _enforce_size_limits(self, text, min_size, max_size):
        """Обеспечивает соответствие текста заданным лимитам по размеру."""
        # Убираем лишние пробелы и переносы строк, сохраняя абзацы
        paragraphs = text.split('\n\n')
        text = '\n\n'.join([' '.join(p.split()) for p in paragraphs])
        
        text_length = len(text)
        logger.info(f"Длина сгенерированного текста: {text_length} символов (лимит: {min_size}-{max_size})")
        
        # Если текст короче минимума, добавляем стандартное завершение
        if text_length < min_size:
            additional_text = "\n\n👋 Присоединяйтесь к нашим мероприятиям и станьте частью **Движения первых**! Подробности на сайте [будьвдвижении.рф](https://будьвдвижении.рф) и в наших социальных сетях."
            text += additional_text[:int(min_size - text_length)]
            logger.info(f"Текст был слишком коротким, добавлено завершение. Новая длина: {len(text)}")
        
        # Если текст длиннее максимума, обрезаем до последнего предложения
        if text_length > max_size:
            # Найдем последний знак препинания в пределах лимита
            cutoff_text = text[:int(max_size)]
            last_period = max(cutoff_text.rfind('.'), cutoff_text.rfind('!'), cutoff_text.rfind('?'))
            
            if last_period > 0:
                # Проверяем, не разрывает ли обрезка Markdown-разметку
                text_to_check = text[:last_period + 1]
                
                # Проверяем парные символы Markdown (двойные звездочки для жирного)
                if text_to_check.count('**') % 2 != 0:
                    # Ищем последний открывающий символ
                    last_bold = text_to_check.rfind('**')
                    if last_bold > 0:
                        text_to_check = text_to_check[:last_bold] + text_to_check[last_bold+2:]
                
                # Проверяем одиночные бэктики для кода
                if text_to_check.count('`') % 2 != 0:
                    last_backtick = text_to_check.rfind('`')
                    if last_backtick > 0:
                        text_to_check = text_to_check[:last_backtick] + text_to_check[last_backtick+1:]
                
                # Проверяем тройные бэктики для блока кода
                triple_backticks = text_to_check.count('```')
                if triple_backticks % 2 != 0:
                    last_triple = text_to_check.rfind('```')
                    if last_triple > 0:
                        text_to_check = text_to_check[:last_triple] + text_to_check[last_triple+3:]
                
                # Проверяем двойные тильды для зачеркнутого текста
                if text_to_check.count('~~') % 2 != 0:
                    last_strikethrough = text_to_check.rfind('~~')
                    if last_strikethrough > 0:
                        text_to_check = text_to_check[:last_strikethrough] + text_to_check[last_strikethrough+2:]
                
                # Проверяем двойные вертикальные черты для скрытого текста
                if text_to_check.count('||') % 2 != 0:
                    last_spoiler = text_to_check.rfind('||')
                    if last_spoiler > 0:
                        text_to_check = text_to_check[:last_spoiler] + text_to_check[last_spoiler+2:]
                
                # Проверяем, не разрывается ли ссылка
                if text_to_check.count('[') != text_to_check.count(']') or text_to_check.count('(') != text_to_check.count(')'):
                    # Ищем последнюю полную ссылку
                    last_complete_link_end = text_to_check.rfind(')')
                    if last_complete_link_end > 0:
                        # Находим соответствующую открывающую скобку
                        for i in range(last_complete_link_end - 1, -1, -1):
                            if text_to_check[i] == '(':
                                # Находим соответствующую закрывающую квадратную скобку
                                for j in range(i - 1, -1, -1):
                                    if text_to_check[j] == '[':
                                        # Теперь у нас есть полная ссылка от j до last_complete_link_end
                                        text_to_check = text_to_check[:last_complete_link_end + 1]
                                        break
                                break
                
                text = text_to_check
                logger.info(f"Текст был слишком длинным, обрезан до {len(text)} символов")
            else:
                # Если нет знаков препинания, просто обрезаем
                text = cutoff_text + "..."
                logger.info(f"Текст обрезан без учета структуры предложений: {len(text)} символов")
        
        return text
    
    async def _send_request_async(self, system_prompt, user_prompt):
        """Асинхронно отправляет запрос к OpenRouter API с улучшенной обработкой ошибок и прокси."""
        # Все возможные URL для API
        api_urls = self.api_urls.copy() if self.api_urls else []
        
        # Правильные URL API для OpenRouter (обновленные)
        all_urls = api_urls.copy()
        
        # Добавляем прямые IP URL из конфига
        if hasattr(self, 'direct_ip_urls') and self.direct_ip_urls:
            all_urls.extend(self.direct_ip_urls)
        else:
            # Используем IP-адреса напрямую (обход DNS-блокировки)
            direct_ips = [
                # Формат: https://IP/правильный_путь_к_API
                "https://13.226.158.10/api/v1/chat/completions",  # IP для openrouter.ai
                "https://13.226.158.23/api/v1/chat/completions"   # Альтернативный IP
            ]
            all_urls.extend(direct_ips)
        
        # Удаляем дубликаты, сохраняя порядок
        all_urls = list(dict.fromkeys(all_urls))
        
        # Прокси настройки из переменных окружения или None
        proxy_settings = None
        if self.http_proxy or self.https_proxy:
            proxy_settings = {
                "http": self.http_proxy,
                "https": self.https_proxy or self.http_proxy  # Если https нет, используем http
            }
            logger.info(f"Используем прокси: {proxy_settings}")
        
        # Создаем список моделей для последовательного перебора, начиная с основной
        models_to_try = [self.model] + [m for m in self.backup_models if m != self.model]
        logger.info(f"Модели для проверки: {models_to_try}")
        
        # Полный набор заголовков с вариациями рефереров
        headers_variations = []
        for referer in self.referers:
            headers_variations.append({
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": referer,
                "X-Title": "RDDM Bot"
            })
        
        # Перебираем все модели
        for current_model in models_to_try:
            logger.info(f"Пробуем модель: {current_model}")
            
            # Подготовка данных для запроса
            payload = {
                "model": current_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": 1024,
                "temperature": 0.7
            }
            
            # Перемешиваем URL и заголовки для равномерного распределения нагрузки
            random.shuffle(all_urls)
            random.shuffle(headers_variations)
            
            # Проверка всех комбинаций
            for attempt_num, (url, headers) in enumerate([(u, h) for u in all_urls for h in headers_variations], 1):
                # Ограничиваем количество попыток для каждой модели
                if attempt_num > self.max_retries * len(all_urls):
                    logger.warning(f"Превышено максимальное число попыток для модели {current_model}")
                    break
                    
                try:
                    # Извлекаем домен из URL для DNS проверки
                    domain = urlparse(url).netloc
                    logger.info(f"Попытка {attempt_num} с моделью {current_model}: URL={url}, домен={domain}")
                    
                    # Проверяем, IP это или домен
                    is_ip = all(c.isdigit() or c == '.' for c in domain.split(':')[0])
                    
                    # Если IP адрес, используем правильный Host заголовок
                    if is_ip:
                        logger.info(f"Обнаружен IP адрес: {domain}, будет использован Host заголовок")
                    
                    # Таймаут больше для первых попыток, меньше для последующих
                    timeout_seconds = self.request_timeout if attempt_num <= 3 else self.request_timeout // 2
                    
                    # Измеряем время выполнения запроса
                    start_time = time.time()
                    
                    # Пробуем с SSL и без
                    for ssl_verify in [False, True]:
                        try:
                            # TCP-соединение, необходимое для использования с некоторыми прокси
                            tcp_connector = aiohttp.TCPConnector(
                                ssl=ssl_verify,
                                force_close=True,  # Закрывать соединение после использования
                                ttl_dns_cache=300  # Кэширование DNS на 5 минут
                            )
                            
                            # Дополнительные заголовки для работы с прокси и IP
                            headers_with_host = headers.copy()
                            if is_ip:
                                # Если используем IP, явно указываем Host заголовок
                                headers_with_host["Host"] = "openrouter.ai"
                            
                            async with aiohttp.ClientSession(connector=tcp_connector) as session:
                                async with session.post(
                                    url, 
                                    json=payload, 
                                    headers=headers_with_host,
                                    proxy=self.https_proxy,  # Используем прокси напрямую в aiohttp
                                    timeout=aiohttp.ClientTimeout(total=timeout_seconds, connect=timeout_seconds//2),
                                    ssl=ssl_verify
                                ) as response:
                                    elapsed_time = time.time() - start_time
                                    logger.info(f"Ответ: статус={response.status}, время={elapsed_time:.2f}с, SSL={ssl_verify}")
                                    
                                    # Проверяем статус ответа перед чтением тела
                                    if response.status == 200:
                                        try:
                                            # Проверяем content-type
                                            content_type = response.headers.get('Content-Type', '')
                                            logger.info(f"Получен Content-Type: {content_type}")
                                            
                                            # Читаем текст ответа
                                            text = await response.text()
                                            
                                            # Пытаемся распарсить JSON
                                            try:
                                                if 'application/json' in content_type:
                                                    result = json.loads(text)
                                                else:
                                                    logger.warning(f"Неожиданный Content-Type: {content_type}, пробуем вручную декодировать JSON")
                                                    if text.strip().startswith('{') and '"choices"' in text:
                                                        result = json.loads(text)
                                                    else:
                                                        logger.error(f"Ответ не похож на JSON: {text[:200]}...")
                                                        continue
                                                
                                                if "choices" in result and len(result["choices"]) > 0:
                                                    message = result["choices"][0]["message"]
                                                    if message and "content" in message:
                                                        logger.info(f"Успешный ответ от {url} с моделью {current_model}")
                                                        return message["content"]
                                                    else:
                                                        logger.warning("API вернул пустое содержимое")
                                                else:
                                                    logger.warning("В ответе API отсутствуют choices")
                                                    logger.debug(f"Содержимое ответа: {str(result)[:200]}...")
                                            except json.JSONDecodeError as e:
                                                logger.error(f"Ошибка парсинга JSON: {e}")
                                                logger.debug(f"Проблемный текст: {text[:200]}...")
                                        except Exception as e:
                                            logger.error(f"Ошибка при обработке ответа: {type(e).__name__}: {str(e)}")
                                    
                                    # Логируем текст ответа при ошибке
                                    if response.status != 200:
                                        text = await response.text()
                                        logger.warning(f"Неудачный статус {response.status}: {text[:200]}...")
                                    
                                    # Если 401, проблема с API ключом - пропускаем все дальнейшие попытки
                                    if response.status == 401:
                                        logger.error("Неверный API ключ. Пропускаем все дальнейшие попытки с этим ключом.")
                                        return self._get_fallback_response(user_prompt)
                            
                            # Если дошли сюда без ошибок, но успешного ответа не получили - идем дальше
                            break
                            
                        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                            logger.warning(f"Ошибка {type(e).__name__} при SSL={ssl_verify}: {str(e)}")
                            # Специфические ошибки для более точной диагностики
                            if isinstance(e, aiohttp.ClientConnectorError):
                                logger.error(f"Не удалось подключиться к {domain}. Проверьте сетевое соединение или прокси.")
                            elif isinstance(e, aiohttp.ServerDisconnectedError):
                                logger.error(f"Сервер {domain} разорвал соединение.")
                            elif isinstance(e, aiohttp.ClientResponseError):
                                logger.error(f"Ошибка HTTP: {e.status}, {e.message}")
                            elif isinstance(e, aiohttp.ClientPayloadError):
                                logger.error(f"Ошибка чтения ответа от {domain}")
                            elif isinstance(e, aiohttp.ClientOSError):
                                logger.error(f"Системная ошибка ввода/вывода: {str(e)}")
                            # Продолжаем со следующим ssl_verify или переходим к следующей комбинации
                    
                    # Небольшая задержка между попытками
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Неожиданная ошибка: {type(e).__name__}: {str(e)}")
                    # Продолжаем следующую попытку
                    await asyncio.sleep(1)
        
        # Если все попытки через aiohttp не удались, пробуем через обычный requests
        logger.info("Все попытки через aiohttp не удались. Пробуем синхронный requests...")
        
        # Берем последнюю использованную модель и пробуем ее еще раз через requests
        last_model = models_to_try[-1]
        payload["model"] = last_model
        
        # Список URL для синхронного запроса - только проверенные URL
        sync_urls = [
            "https://openrouter.ai/api/v1/chat/completions",
            "https://api.openrouter.ai/api/v1/chat/completions",
            "https://13.226.158.10/api/v1/chat/completions"
        ]
        
        for url in sync_urls:
            for headers in headers_variations[:2]:  # Только первые две вариации заголовков
                logger.info(f"Синхронный запрос к {url} с моделью {last_model}")
                try:
                    # Проверяем, IP это или домен
                    domain = urlparse(url).netloc
                    is_ip = all(c.isdigit() or c == '.' for c in domain.split(':')[0])
                    
                    # Если IP адрес, добавляем Host заголовок
                    if is_ip:
                        headers["Host"] = "openrouter.ai"
                    
                    # Пробуем запрос с большим таймаутом
                    response = requests.post(
                        url,
                        json=payload,
                        headers=headers,
                        proxies=proxy_settings,
                        timeout=self.request_timeout,  # Большой таймаут для синхронного запроса
                        verify=False  # Отключаем проверку SSL
                    )
                    
                    logger.info(f"Синхронный ответ: статус {response.status_code}")
                    
                    if response.status_code == 200:
                        try:
                            # Проверка Content-Type
                            content_type = response.headers.get('Content-Type', '')
                            logger.info(f"Получен Content-Type: {content_type}")
                            
                            # Читаем текст ответа
                            text = response.text
                            
                            # Пытаемся распарсить JSON
                            try:
                                if 'application/json' in content_type:
                                    result = json.loads(text)
                                else:
                                    if text.strip().startswith('{') and '"choices"' in text:
                                        result = json.loads(text)
                                        logger.warning(f"Декодирован JSON с неожиданным Content-Type: {content_type}")
                                    else:
                                        logger.error(f"Ответ не похож на JSON: {text[:200]}...")
                                        continue
                                
                                if result and "choices" in result and len(result["choices"]) > 0:
                                    message = result["choices"][0]["message"]
                                    if message and "content" in message:
                                        logger.info(f"Успешный синхронный ответ с моделью {last_model}")
                                        return message["content"]
                                    else:
                                        logger.warning("API вернул пустое содержимое")
                            except json.JSONDecodeError as e:
                                logger.error(f"Ошибка парсинга JSON: {e}")
                                logger.debug(f"Проблемный текст: {text[:200]}...")
                        except Exception as e:
                            logger.error(f"Ошибка при обработке синхронного ответа: {e}")
                except Exception as e:
                    logger.error(f"Ошибка при синхронном запросе к {url}: {e}")
        
        # Если все попытки неудачны
        logger.error("Все попытки отправки запроса к API неудачны. Возвращаем заглушку.")
        return self._get_fallback_response(user_prompt)
    
    def _get_fallback_response(self, user_prompt):
        """Возвращает заглушку при ошибках API."""
        logger.info("Генерация заглушки для демонстрации работы бота")
        
        # Создаем примерный ответ с HTML-форматированием
        if "шаблону" in user_prompt:
            return "👋 Привет от **РДДМ**!\n\nМы рады видеть тебя в нашем сообществе. **Движение первых** - это место, где каждый может проявить себя и стать частью большой дружной команды.\n\n✨ Присоединяйся к нам и открывай новые возможности для саморазвития!\n\nПодробности на сайте [будьвдвижении.рф](https://будьвдвижении.рф) 🚀"
        else:
            return "🎉 **РДДМ** приглашает всех на наше **новое мероприятие**!\n\nБудет интересно, познавательно и весело. Ждем тебя в нашей команде.\n\n📍 Подробности на сайте [будьвдвижении.рф](https://будьвдвижении.рф) ||приходи, будет сюрприз!|| 💫" 