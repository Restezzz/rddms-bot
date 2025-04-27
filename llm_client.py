import requests
import asyncio
import json
import aiohttp
from config import (
    OPENROUTER_API_URLS, OPENROUTER_API_KEY, OPENROUTER_MODEL, 
    OPENROUTER_HEADERS, DEBUG_MODE, DISABLE_SSL_VERIFY, ALTERNATIVE_MODELS
)
import logging
from rddm_info import get_rddm_knowledge
from session_manager import PostSize

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Новый датасет
RDDM_DATASET = {
    "F&Q": [
        "Движение Первых. Экология, #ЭкологияПервых",
        "Движение Первых. Профессия, #ПрофессияПервых",
        "Движение Первых. Путешествия, #ПутешествияПервых",
        "Движение Первых. Добро, #ДоброПервых",
        "Движение Первых. Наука, #НаукаПервых",
        "КВН Первые | Движение Первых, #КВНПервые",
        "Движение Первых. Спорт и ЗОЖ, #СпортЗОЖПервых",
        "Движение Первых. Патриоты, #ПатриотыПервых",
        "Движение Первых. Творчество, #ТворчествоПервых",
        "Движение Первых. Дипломаты, #ДипломатыПервых",
        "Гранты | Движение Первых, #грантыПервых"
    ],
    "HASHTAGS": {
        "Мы - граждане России": {
            "description": "Программа «Мы – граждане России!» реализуется совместно с Министерством внутренних дел РФ",
            "link": "https://vk.com/club26323016",
            "hashtag": "#МыГражданеРоссии"
        },
        "Хранители истории": {
            "hashtag": "#ХранителиИстории"
        },
        "Классные встречи": {
            "hashtag": "#КлассныеВстречи",
            "link": "https://vk.com/klassnye_vstrechi"
        },
        "Первая помощь": {
            "hashtag": "#ПервыеПомогают"
        },
        "Зарница": {
            "hashtag": "#ЗарницаПервых"
        }
    }
}

class LLMClient:
    def __init__(self, api_urls=OPENROUTER_API_URLS, api_key=OPENROUTER_API_KEY, model=OPENROUTER_MODEL, headers=OPENROUTER_HEADERS, debug=DEBUG_MODE, disable_ssl=DISABLE_SSL_VERIFY):
        self.api_urls = api_urls
        self.api_key = api_key
        self.model = model
        self.headers = headers.copy()
        self.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        self.debug = debug
        self.disable_ssl = disable_ssl
        
        if self.debug:
            logger.info(f"LLMClient инициализирован с моделью {model}")
            logger.info(f"SSL проверка: {'отключена' if disable_ssl else 'включена'}")
    
    async def generate_from_template(self, template_post, topic, post_size=PostSize.LARGE, language="ru"):
        """Генерирует пост на основе шаблона и темы."""
        # Определяем размер поста (в символах)
        size_range = self._get_size_range(post_size)
        min_size, max_size = map(int, size_range.split('-'))
        
        # Находим подходящие хэштеги из датасета
        relevant_hashtags = self._get_relevant_hashtags(topic)
        
        system_prompt = """Чат, тебе нужно написать пост для группы в Вконтакте "Движение первых". При составлении поста опирайся на пример поста, который тебе отправил пользоватеь или на информацию, которую в тебя заложили с помощью промта и датасета.

Общая информация про "Движение первых": 
Российское движение детей и молодёжи «Движение первых» — общероссийское общественно-государственное движение, созданное 20 июля 2022 года по инициативе руководства России, для воспитания, организации досуга подростков, и формирования мировоззрения «на основе традиционных российских духовных и нравственных ценностей»."""
        
        user_prompt = f"""Пример поста:
{template_post}

Тема нового поста: {topic}

Датасет:
{json.dumps(RDDM_DATASET, ensure_ascii=False, indent=2)}

Логика составления поста:
1) Если пользователей отправил тебе пример поста, то при генерации нового поста опирайся на него;
2) Если пользователь не прислал информацию по созданию поста, то обрати внимание на то, сколько символов от тебя запросили, после этого посмотри на тематику поста. На основе тематики поста и двух разделов из дата сета: F&Q и # составь пост, обрати внимание, что если речь идёт про выдачу паспорта, то в конце поста обязательно должны быть хештеги данного направления и концовка, которая указана у тебя в датасете. 
3) В конце каждого поста дополнительно указывай данный хэштен - #ДвижениеПервых59

Критерии:
- Обращай внимание на датасет и обязательно указывай в сгенрированных постах ту информацию, которую мы заложили в документе на основе которого, ты будешь составлять пост
- Информацию из датасета подбирай по смыслу, если пользователь указал, что мы показываем выдачу паспортов детям, то и соответствующая информацию из датасета должна быть подтянута
- Не делай слишком формальный текст, но и не уходи в свободу мыслей. Движение - государственная сущность, твоя ЦА люди 14 - 35 лет
- Если в датасете есть ссылки, то они обязательно должны появится и в твоём посте, запомни это
- Ограничение по длине: пост должен содержать от {min_size} до {max_size} символов.

Подходящие для этой темы хештеги: {relevant_hashtags}"""
            
        # Генерируем текст
        generated_text = await self._send_request_async(system_prompt, user_prompt)
        
        # Применяем ограничения по размеру
        return self._enforce_size_limits(generated_text, min_size, max_size)
    
    async def generate_without_template(self, topic, post_size=PostSize.LARGE, language="ru"):
        """Генерирует пост без шаблона, только по теме."""
        # Определяем размер поста (в символах)
        size_range = self._get_size_range(post_size)
        min_size, max_size = map(int, size_range.split('-'))
        
        # Находим подходящие хэштеги из датасета
        relevant_hashtags = self._get_relevant_hashtags(topic)
        
        system_prompt = """Чат, тебе нужно написать пост для группы в Вконтакте "Движение первых". При составлении поста опирайся на пример поста, который тебе отправил пользоватеь или на информацию, которую в тебя заложили с помощью промта и датасета.

Общая информация про "Движение первых": 
Российское движение детей и молодёжи «Движение первых» — общероссийское общественно-государственное движение, созданное 20 июля 2022 года по инициативе руководства России, для воспитания, организации досуга подростков, и формирования мировоззрения «на основе традиционных российских духовных и нравственных ценностей»."""
        
        user_prompt = f"""Тема поста: {topic}

Датасет:
{json.dumps(RDDM_DATASET, ensure_ascii=False, indent=2)}

Логика составления поста:
1) Если пользователей отправил тебе пример поста, то при генерации нового поста опирайся на него;
2) Если пользователь не прислал информацию по созданию поста, то обрати внимание на то, сколько символов от тебя запросили, после этого посмотри на тематику поста. На основе тематики поста и двух разделов из дата сета: F&Q и # составь пост, обрати внимание, что если речь идёт про выдачу паспорта, то в конце поста обязательно должны быть хештеги данного направления и концовка, которая указана у тебя в датасете. 
3) В конце каждого поста дополнительно указывай данный хэштен - #ДвижениеПервых59

Критерии:
- Обращай внимание на датасет и обязательно указывай в сгенрированных постах ту информацию, которую мы заложили в документе на основе которого, ты будешь составлять пост
- Информацию из датасета подбирай по смыслу, если пользователь указал, что мы показываем выдачу паспортов детям, то и соответствующая информацию из датасета должна быть подтянута
- Не делай слишком формальный текст, но и не уходи в свободу мыслей. Движение - государственная сущность, твоя ЦА люди 14 - 35 лет
- Если в датасете есть ссылки, то они обязательно должны появится и в твоём посте, запомни это
- Ограничение по длине: пост должен содержать от {min_size} до {max_size} символов.

Подходящие для этой темы хештеги: {relevant_hashtags}"""
        
        # Генерируем текст
        generated_text = await self._send_request_async(system_prompt, user_prompt)
        
        # Применяем ограничения по размеру
        return self._enforce_size_limits(generated_text, min_size, max_size)
    
    async def modify_post(self, current_post, modification_request, language="ru"):
        """Модифицирует существующий пост согласно запросу."""
        system_prompt = """Чат, тебе нужно отредактировать пост для группы в Вконтакте "Движение первых". При составлении поста опирайся на пример поста, который тебе отправил пользоватеь или на информацию, которую в тебя заложили с помощью промта и датасета.

Общая информация про "Движение первых": 
Российское движение детей и молодёжи «Движение первых» — общероссийское общественно-государственное движение, созданное 20 июля 2022 года по инициативе руководства России, для воспитания, организации досуга подростков, и формирования мировоззрения «на основе традиционных российских духовных и нравственных ценностей»."""
        
        user_prompt = f"""Текущий пост:

{current_post}

Требуемые изменения: {modification_request}

Датасет:
{json.dumps(RDDM_DATASET, ensure_ascii=False, indent=2)}

Критерии:
- Обращай внимание на датасет и обязательно указывай в сгенрированных постах ту информацию, которую мы заложили в документе
- Не делай слишком формальный текст, но и не уходи в свободу мыслей. Движение - государственная сущность, твоя ЦА люди 14 - 35 лет
- Если в датасете есть ссылки, то они обязательно должны появится и в твоём посте
- В конце каждого поста дополнительно указывай хэштег #ДвижениеПервых59"""
            
        # Генерируем текст
        generated_text = await self._send_request_async(system_prompt, user_prompt)
        
        # Сохраняем примерно ту же длину
        current_length = len(current_post)
        return self._enforce_size_limits(generated_text, current_length * 0.8, current_length * 1.2)
    
    def _get_relevant_hashtags(self, topic):
        """Определяет наиболее подходящие хэштеги для темы из датасета."""
        topic_lower = topic.lower()
        hashtags = []
        
        # Проверяем категории F&Q
        for category in RDDM_DATASET["F&Q"]:
            category_name = category.split(",")[0].lower()
            hashtag = category.split(",")[1].strip() if "," in category else ""
            
            # Ищем ключевые слова из категории в теме
            keywords = category_name.replace("движение первых.", "").replace("движение первых", "").split()
            if any(keyword.lower() in topic_lower for keyword in keywords if len(keyword) > 3):
                hashtags.append(hashtag)
        
        # Проверяем специальные хэштеги
        for name, data in RDDM_DATASET["HASHTAGS"].items():
            if name.lower() in topic_lower or any(word.lower() in topic_lower for word in name.lower().split() if len(word) > 3):
                hashtag_info = f"{data['hashtag']}"
                if "link" in data:
                    hashtag_info += f" (ссылка: {data['link']})"
                hashtags.append(hashtag_info)
        
        # Всегда добавляем основной хэштег
        hashtags.append("#ДвижениеПервых59")
        
        if not hashtags:
            # Если не нашли подходящих, возвращаем общий хэштег
            return "#ДвижениеПервых59"
            
        return ", ".join(hashtags)
    
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
            additional_text = "\n\n👋 Присоединяйтесь к нашим мероприятиям и станьте частью Движения первых! #ДвижениеПервых59"
            text += additional_text[:int(min_size - text_length)]
            logger.info(f"Текст был слишком коротким, добавлено завершение. Новая длина: {len(text)}")
        
        # Если текст длиннее максимума, обрезаем до последнего предложения
        if text_length > max_size:
            # Найдем последний знак препинания в пределах лимита
            cutoff_text = text[:int(max_size)]
            last_period = max(cutoff_text.rfind('.'), cutoff_text.rfind('!'), cutoff_text.rfind('?'))
            
            if last_period > 0:
                text = text[:last_period+1]
                logger.info(f"Текст был слишком длинным, обрезан до длины {len(text)}")
                
                # Проверяем, что хэштег #ДвижениеПервых59 присутствует
                if "#ДвижениеПервых59" not in text:
                    text += "\n\n#ДвижениеПервых59"
                    logger.info(f"Добавлен хэштег #ДвижениеПервых59. Новая длина: {len(text)}")
            else:
                text = text[:int(max_size)]
                logger.info(f"Текст был слишком длинным, обрезан до длины {len(text)}")
        
        return text
    
    async def _send_request_async(self, system_prompt, user_prompt):
        """Асинхронно отправляет запрос к OpenRouter API."""
        # Альтернативные URL для API
        api_urls = self.api_urls
        
        # Список моделей для попытки: сначала основная, потом альтернативные
        models_to_try = [self.model] + ALTERNATIVE_MODELS
        
        # Счетчик ошибок для переключения между моделями
        model_errors = 0
        max_model_errors = 3  # После трех ошибок переключаемся на новую модель
        current_model_index = 0
        
        for attempt, current_url in enumerate(api_urls, 1):
            current_model = models_to_try[current_model_index]
            
            try:
                # Подготовка данных для запроса в формате OpenAI API
                payload = {
                    "model": current_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": 1024,
                    "temperature": 0.7
                }
                
                # Обновленный набор заголовков
                headers = self.headers.copy()
                headers["Content-Type"] = "application/json"
                headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                
                logger.info(f"Попытка {attempt}/{len(api_urls)}: Отправка запроса к {current_url} для модели {current_model}")
                
                # Проверяем, нужно ли переключиться на другую модель
                if model_errors >= max_model_errors and current_model_index < len(models_to_try) - 1:
                    current_model_index += 1
                    current_model = models_to_try[current_model_index]
                    logger.info(f"Слишком много ошибок, переключаемся на новую модель: {current_model}")
                    model_errors = 0
                
                # Проверка DNS разрешения перед запросом
                try:
                    import socket
                    host = current_url.split("//")[1].split("/")[0]
                    logger.info(f"Проверка DNS для {host}...")
                    ip = socket.gethostbyname(host)
                    logger.info(f"DNS разрешено: {host} -> {ip}")
                except Exception as dns_err:
                    logger.error(f"Ошибка DNS разрешения для {host}: {dns_err}")
                    if attempt < len(api_urls):
                        logger.info(f"Пробуем альтернативный URL...")
                        continue
                    else:
                        return self._get_fallback_response(user_prompt)
                
                # Отключаем проверку SSL для отладки и решения проблем с сертификатами
                connector = aiohttp.TCPConnector(ssl=False if self.disable_ssl else None, force_close=True)
                timeout = aiohttp.ClientTimeout(total=90, connect=30)
                
                async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                    try:
                        if self.debug:
                            logger.info(f"Заголовки запроса: {headers}")
                            logger.info(f"Payload: {json.dumps(payload)[:200]}...")
                        
                        async with session.post(
                            current_url, 
                            json=payload, 
                            headers=headers
                        ) as response:
                            status = response.status
                            content_type = response.headers.get('Content-Type', 'неизвестно')
                            logger.info(f"Статус ответа: {status}, Content-Type: {content_type}")
                            
                            # Получаем сырой ответ для отладки
                            raw_response = await response.text()
                            logger.info(f"Сырой ответ (первые 200 символов): {raw_response[:200]}...")
                            
                            if status != 200:
                                logger.error(f"Ошибка API (попытка {attempt}): {status}, {raw_response[:500]}")
                                # Продолжаем к следующему URL, если ошибка
                                if attempt < len(api_urls):
                                    logger.info(f"Пробуем альтернативный URL...")
                                    continue
                                # Если все URL не сработали
                                return self._get_fallback_response(user_prompt)
                            
                            # Проверяем формат ответа
                            if not content_type or 'application/json' not in content_type:
                                logger.warning(f"Неверный Content-Type: {content_type}, пробуем распарсить как JSON")
                                model_errors += 1  # Увеличиваем счетчик ошибок модели
                            
                            try:
                                result = json.loads(raw_response)
                                
                                # Извлекаем ответ из структуры OpenAI API
                                if "choices" in result and len(result["choices"]) > 0:
                                    message = result["choices"][0]["message"]
                                    if message and "content" in message:
                                        logger.info("Успешно получен ответ от API")
                                        return message["content"]
                                
                                # Если JSON получен, но не в ожидаемом формате
                                logger.error(f"Неожиданный формат JSON: {json.dumps(result)[:200]}...")
                                model_errors += 1  # Увеличиваем счетчик ошибок модели
                                
                            except json.JSONDecodeError:
                                logger.error(f"Не удалось распарсить JSON из ответа")
                                model_errors += 1  # Увеличиваем счетчик ошибок модели
                                # Продолжаем к следующему URL
                                if attempt < len(api_urls):
                                    logger.info(f"Пробуем альтернативный URL...")
                                    continue
                    except aiohttp.ClientConnectorError as conn_err:
                        logger.error(f"Ошибка соединения (попытка {attempt}): {conn_err}")
                        model_errors += 1  # Увеличиваем счетчик ошибок модели
                        if attempt < len(api_urls):
                            logger.info(f"Пробуем альтернативный URL...")
                            continue
                    except asyncio.TimeoutError:
                        logger.error(f"Таймаут соединения (попытка {attempt})")
                        model_errors += 1  # Увеличиваем счетчик ошибок модели
                        if attempt < len(api_urls):
                            logger.info(f"Пробуем альтернативный URL...")
                            continue
                
                # Если дошли сюда, то запрос прошел без ошибок, но формат ответа неожиданный
                logger.error(f"Неожиданный формат ответа (попытка {attempt})")
                
            except Exception as e:
                logger.error(f"Непредвиденная ошибка при запросе API (попытка {attempt}): {e}")
                # Продолжаем к следующему URL, если не последняя попытка
                if attempt < len(api_urls):
                    logger.info(f"Пробуем альтернативный URL...")
                    continue
        
        # Если все попытки не удались
        logger.error(f"Все попытки запроса к API неудачны. Используем заглушку.")
        return self._get_fallback_response(user_prompt)
    
    def _get_fallback_response(self, user_prompt):
        """Возвращает заглушку при ошибках API."""
        logger.info("Попытка вызова API через библиотеку requests (запасной вариант)")
        
        try:
            # Проверка прямого доступа к https://api.openai.com с ключом OpenRouter
            openai_url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            fallback_system_prompt = """Чат, тебе нужно написать пост для группы в Вконтакте "Движение первых"."""
            
            fallback_user_prompt = """Напиши короткий пост для группы "Движение первых" ВКонтакте. 
            В конце используй хештег #ДвижениеПервых59."""
            
            payload = {
                "model": "gpt-3.5-turbo",  # Используем стандартную модель OpenAI
                "messages": [
                    {"role": "system", "content": fallback_system_prompt},
                    {"role": "user", "content": fallback_user_prompt}
                ],
                "max_tokens": 256,
                "temperature": 0.7
            }
            
            logger.info(f"Отправка запасного запроса напрямую к OpenAI API")
            response = requests.post(
                openai_url, 
                headers=headers, 
                json=payload, 
                timeout=30, 
                verify=not self.disable_ssl
            )
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    if "choices" in result and len(result["choices"]) > 0:
                        message = result["choices"][0]["message"]
                        if message and "content" in message:
                            logger.info("Успешно получен ответ через запасной вариант OpenAI API")
                            return message["content"]
                except Exception as json_err:
                    logger.error(f"Ошибка при обработке JSON в запасном варианте OpenAI: {json_err}")
            else:
                logger.error(f"Ошибка запасного запроса OpenAI: {response.status_code}, {response.text[:200]}")
            
            # Стандартный fallback, если все остальное не работает
            # Используем requests для синхронного запроса как последнюю надежду
            url = self.api_urls[0]  # Используем первый URL из списка
            headers = self.headers.copy()
            headers["Content-Type"] = "application/json"
            headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": fallback_system_prompt},
                    {"role": "user", "content": fallback_user_prompt}
                ],
                "max_tokens": 256,
                "temperature": 0.7
            }
            
            logger.info(f"Отправка запасного запроса через requests к {url}")
            response = requests.post(
                url, 
                headers=headers, 
                json=payload, 
                timeout=30, 
                verify=not self.disable_ssl
            )
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    if "choices" in result and len(result["choices"]) > 0:
                        message = result["choices"][0]["message"]
                        if message and "content" in message:
                            logger.info("Успешно получен ответ через запасной вариант requests")
                            return message["content"]
                except Exception as json_err:
                    logger.error(f"Ошибка при обработке JSON в запасном варианте: {json_err}")
            else:
                logger.error(f"Ошибка запасного запроса: {response.status_code}, {response.text[:200]}")
                
        except Exception as e:
            logger.error(f"Ошибка при выполнении запасного запроса: {e}")
        
        logger.info("Генерация заглушки для демонстрации работы бота")
        
        # Создаем примерный ответ для демонстрации если все запросы не сработали
        if "шаблону" in user_prompt:
            return "👋 Привет от Движения первых!\n\nМы рады видеть вас в нашем сообществе. Движение первых - это место, где каждый может проявить себя и стать частью большой дружной команды.\n\n✨ Присоединяйтесь к нам и открывайте новые возможности для саморазвития!\n\n#ДвижениеПервых59"
        elif "паспорт" in user_prompt.lower():
            return "🇷🇺 Сегодня в торжественной обстановке наши ребята получили свои первые паспорта гражданина России!\n\nЭто важный и ответственный момент для каждого молодого человека. Теперь у них есть не только права, но и обязанности перед страной.\n\nПоздравляем наших новых полноправных граждан!\n\n#МыГражданеРоссии #ДвижениеПервых59"
        else:
            return "🎉 Движение первых приглашает всех на наше новое мероприятие!\n\nБудет интересно, познавательно и весело. Ждем вас в нашей команде.\n\n#ДвижениеПервых59" 