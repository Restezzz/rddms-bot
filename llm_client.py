import requests
import asyncio
import json
import aiohttp
import time
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

class RateLimiter:
    """Класс для ограничения частоты запросов к API"""
    def __init__(self, requests_per_minute=12):  # По умолчанию - 1 запрос в 5 секунд
        self.requests_per_minute = requests_per_minute
        self.interval = 60 / requests_per_minute  # Интервал между запросами в секундах
        self.last_request_time = 0
        self.lock = asyncio.Lock()
    
    async def acquire(self):
        """Ожидает, пока можно выполнить следующий запрос"""
        async with self.lock:
            current_time = time.time()
            time_since_last = current_time - self.last_request_time
            
            if time_since_last < self.interval:
                # Если прошло недостаточно времени, ждем
                wait_time = self.interval - time_since_last
                await asyncio.sleep(wait_time)
            
            # Обновляем время последнего запроса
            self.last_request_time = time.time()

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
        self.disable_ssl = True  # Всегда отключаем SSL-проверку
        
        # Семафор для ограничения одновременных запросов
        self.request_semaphore = asyncio.Semaphore(3)  # Максимум 3 одновременных запроса
        
        # Rate limiter для ограничения частоты запросов
        self.rate_limiter = RateLimiter(requests_per_minute=15)  # 15 запросов в минуту
        
        # Отслеживание активных запросов
        self.active_requests = set()
        self.request_lock = asyncio.Lock()
        
        if self.debug:
            logger.info(f"LLMClient инициализирован с моделью {model}")
            logger.info(f"SSL проверка: {'отключена' if disable_ssl else 'включена'}")
            logger.info(f"Семафор: максимум 3 одновременных запроса")
            logger.info(f"Rate limiter: максимум 15 запросов в минуту")
    
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
- Не делай слишком формальный текст, но и не уходи в свободу мыслей. Движение - государственная сущность, твоя целевая аудитория - люди 14-35 лет
- Если в датасете есть ссылки, то они обязательно должны появиться и в твоём посте, запомни это
- Ограничение по длине: пост должен содержать от {min_size} до {max_size} символов.
- Не обрезай ссылки, они обязательно должны быть полные, а не частичные.
- Пиши пост без "", я планирую сразу скопировать и опубликовать пост
- Также не пиши в конечном результате что-то типа "вот пример поста на вашу тему", нужно писать только сам пост.

Подходящие для этой темы хештеги: {relevant_hashtags}"""
            
        # Генерируем текст с установленным тайм-аутом
        try:
            generated_text = await asyncio.wait_for(
                self._send_request_async(system_prompt, user_prompt),
                timeout=30  # Жесткий тайм-аут 30 секунд на весь запрос
            )
            
            # Применяем ограничения по размеру
            return self._enforce_size_limits(generated_text, min_size, max_size)
            
        except asyncio.TimeoutError:
            logger.error(f"Тайм-аут при генерации поста из шаблона по теме '{topic}'")
            return f"Извините, время ожидания истекло. Попробуйте ещё раз или выберите другую тему.\n\n#ДвижениеПервых59"
        except Exception as e:
            logger.error(f"Ошибка при генерации поста: {e}")
            return f"Произошла ошибка при генерации поста. Пожалуйста, попробуйте позже.\n\n#ДвижениеПервых59"
    
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
- Не делай слишком формальный текст, но и не уходи в свободу мыслей. Движение - государственная сущность, твоя целевая аудитория - люди 14-35 лет
- Если в датасете есть ссылки, то они обязательно должны появиться и в твоём посте, запомни это
- Ограничение по длине: пост должен содержать от {min_size} до {max_size} символов.
- Не обрезай ссылки, они обязательно должны быть полные, а не частичные.
- Пиши пост без "", я планирую сразу скопировать и опубликовать пост
- Также не пиши в конечном результате что-то типа "вот пример поста на вашу тему", нужно писать только сам пост.

Подходящие для этой темы хештеги: {relevant_hashtags}"""
        
        # Генерируем текст с тайм-аутом
        try:
            generated_text = await asyncio.wait_for(
                self._send_request_async(system_prompt, user_prompt),
                timeout=30  # Жесткий тайм-аут 30 секунд на весь запрос
            )
            
            # Применяем ограничения по размеру
            return self._enforce_size_limits(generated_text, min_size, max_size)
            
        except asyncio.TimeoutError:
            logger.error(f"Тайм-аут при генерации поста без шаблона по теме '{topic}'")
            return f"Извините, время ожидания истекло. Попробуйте ещё раз или выберите другую тему.\n\n#ДвижениеПервых59"
        except Exception as e:
            logger.error(f"Ошибка при генерации поста: {e}")
            return f"Произошла ошибка при генерации поста. Пожалуйста, попробуйте позже.\n\n#ДвижениеПервых59"
    
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
- Не делай слишком формальный текст, но и не уходи в свободу мыслей. Движение - государственная сущность, твоя целевая аудитория - люди 14-35 лет
- Если в датасете есть ссылки, то они обязательно должны появиться и в твоём посте
- Не обрезай ссылки, они обязательно должны быть полные, а не частичные.
- Пиши пост без "", я планирую сразу скопировать и опубликовать пост
- Также не пиши в конечном результате что-то типа "вот отредактированный пост", нужно писать только сам пост.
- В конце каждого поста дополнительно указывай хэштег #ДвижениеПервых59"""
            
        # Генерируем текст с тайм-аутом
        try:
            generated_text = await asyncio.wait_for(
                self._send_request_async(system_prompt, user_prompt),
                timeout=30  # Жесткий тайм-аут 30 секунд на весь запрос
            )
            
            # Сохраняем примерно ту же длину
            current_length = len(current_post)
            return self._enforce_size_limits(generated_text, current_length * 0.8, current_length * 1.2)
            
        except asyncio.TimeoutError:
            logger.error(f"Тайм-аут при модификации поста")
            return f"Извините, время ожидания истекло. Попробуйте ещё раз с другим запросом на изменение.\n\n{current_post}"
        except Exception as e:
            logger.error(f"Ошибка при модификации поста: {e}")
            return f"Произошла ошибка при модификации поста. Пожалуйста, попробуйте позже.\n\n{current_post}"
    
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
            
            for keyword in keywords:
                if len(keyword) > 3 and keyword.lower() in topic_lower:
                    if hashtag:
                        hashtags.append(hashtag)
                    break
        
        # Проверяем хэштеги
        for name, data in RDDM_DATASET["HASHTAGS"].items():
            name_lower = name.lower()
            # Если название категории содержится в теме
            if name_lower in topic_lower:
                hashtags.append(data["hashtag"])
        
        # Всегда добавляем основной хэштег
        if "#ДвижениеПервых" not in hashtags:
            hashtags.append("#ДвижениеПервых")
        
        # Возвращаем список уникальных хэштегов
        return ", ".join(set(hashtags)) if hashtags else "#ДвижениеПервых"
    
    def _get_size_range(self, post_size):
        """Возвращает диапазон размеров поста в зависимости от выбранного размера."""
        if post_size == PostSize.SMALL:
            return "200-400"
        elif post_size == PostSize.MEDIUM:
            return "400-800"
        else:  # PostSize.LARGE по умолчанию
            return "800-1200"
    
    def _enforce_size_limits(self, text, min_size, max_size):
        """Приводит текст к нужному размеру."""
        if not text:
            return f"Произошла ошибка при генерации поста. Пожалуйста, попробуйте позже.\n\n#ДвижениеПервых59"
            
        # Если текст слишком короткий
        if len(text) < min_size:
            # Просто возвращаем "как есть", возможно, это результат ошибки
            logger.warning(f"Текст слишком короткий: {len(text)} символов (минимум {min_size})")
            return text
            
        # Если текст слишком длинный
        if len(text) > max_size:
            logger.warning(f"Текст слишком длинный: {len(text)} символов (максимум {max_size})")
            
            # Ищем конец абзаца перед ограничением
            truncated = text[:max_size]
            last_paragraph = truncated.rfind("\n\n")
            
            if last_paragraph > min_size:
                truncated = text[:last_paragraph]
            else:
                # Если не можем найти конец абзаца, ищем конец предложения
                last_sentence = max([
                    truncated.rfind(". "),
                    truncated.rfind("! "),
                    truncated.rfind("? ")
                ])
                
                if last_sentence > min_size:
                    truncated = text[:last_sentence+1]  # +1 чтобы включить символ окончания
                else:
                    # Если не можем найти конец предложения, обрезаем по максимуму
                    truncated = text[:max_size]
            
            # Убедимся, что основные хэштеги не потеряны
            if "#ДвижениеПервых59" not in truncated:
                truncated = truncated + "\n\n#ДвижениеПервых59"
                
            return truncated
            
        # Если текст в пределах нормы
        return text
    
    async def _send_request_async(self, system_prompt, user_prompt):
        """Асинхронно отправляет запрос к OpenRouter API с ограничением одновременных запросов."""
        # Ограничиваем частоту запросов
        await self.rate_limiter.acquire()
        
        # Ограничиваем количество одновременных запросов
        async with self.request_semaphore:
            # Создаем уникальный идентификатор для этого запроса
            request_id = id(user_prompt)
            
            # Регистрируем запрос как активный
            async with self.request_lock:
                self.active_requests.add(request_id)
            
            try:
                # Задаем таймаут для всего процесса запроса
                return await asyncio.wait_for(
                    self._execute_request(system_prompt, user_prompt, request_id),
                    timeout=25  # Общий таймаут немного меньше, чем у вызывающих методов
                )
            except asyncio.TimeoutError:
                logger.error(f"Таймаут для запроса {request_id}")
                raise
            except Exception as e:
                logger.error(f"Ошибка при запросе {request_id}: {e}")
                raise
            finally:
                # Удаляем запрос из списка активных
                async with self.request_lock:
                    self.active_requests.discard(request_id)
    
    async def _execute_request(self, system_prompt, user_prompt, request_id):
        """Выполняет фактический запрос к API с обработкой ошибок и сменой моделей/URL."""
        # Используем все доступные URL для большей вероятности успеха
        api_urls = self.api_urls.copy()
        
        # Список моделей для попытки
        models_to_try = [self.model] + ALTERNATIVE_MODELS[:1]  # Берем только первую альтернативную модель
        
        for attempt, current_url in enumerate(api_urls, 1):
            current_model = models_to_try[0]  # Текущая модель для этой попытки
            
            try:
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
                
                headers = self.headers.copy()
                logger.info(f"Запрос {request_id}: попытка {attempt}/{len(api_urls)} к {current_url}, модель {current_model}")
                
                # Отключаем проверку SSL для отладки и решения проблем с сертификатами
                connector = aiohttp.TCPConnector(ssl=False, force_close=True)
                
                # Настраиваем более жесткие тайм-ауты для разных этапов запроса
                timeout = aiohttp.ClientTimeout(total=20, connect=5, sock_read=15)
                
                async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                    async with session.post(
                        current_url, 
                        json=payload, 
                        headers=headers
                    ) as response:
                        status = response.status
                        raw_response = await asyncio.wait_for(response.text(), timeout=10)
                        
                        if status != 200:
                            logger.error(f"Ошибка API (запрос {request_id}): статус {status}")
                            # Переходим к следующей попытке
                            raise Exception(f"API вернул статус {status}")
                        
                        # Если дошли сюда, то статус 200
                        try:
                            result = json.loads(raw_response)
                            
                            # Проверяем наличие ответа в ожидаемом формате
                            if "choices" in result and len(result["choices"]) > 0:
                                message = result["choices"][0]["message"]
                                if message and "content" in message:
                                    logger.info(f"Запрос {request_id}: успешно получен ответ")
                                    return message["content"]
                            
                            # Если дошли сюда - формат ответа неожиданный
                            logger.error(f"Запрос {request_id}: неожиданный формат JSON")
                            raise Exception("Неожиданный формат ответа")
                            
                        except json.JSONDecodeError:
                            logger.error(f"Запрос {request_id}: ошибка декодирования JSON")
                            raise
            
            except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
                logger.error(f"Запрос {request_id}: ошибка соединения: {e}")
            
            except Exception as e:
                logger.error(f"Запрос {request_id}: ошибка: {e}")
            
            # Если попытка не удалась, пробуем другую модель и/или URL
            if len(models_to_try) > 1:
                # Меняем модель
                models_to_try = models_to_try[1:] + models_to_try[:1]
            elif attempt < len(api_urls):
                # Переключаемся на следующий URL и сбрасываем модели
                models_to_try = [self.model] + ALTERNATIVE_MODELS[:1]
        
        # Если все попытки не удались
        logger.error(f"Запрос {request_id}: все попытки запроса к API неудачны")
        return self._get_fallback_response(user_prompt)
    
    def _get_fallback_response(self, user_prompt):
        """Возвращает заглушку при ошибках API."""
        logger.info("Использование заглушки из-за ошибок API")
        
        user_prompt_lower = user_prompt.lower()
        
        # Проверяем различные ключевые слова для выбора подходящей заглушки
        if "паспорт" in user_prompt_lower:
            return """Сегодня состоялось торжественное вручение паспортов юным гражданам России! 

В этот важный день ребята присоединились к программе «Мы – граждане России!», которая реализуется совместно с Министерством внутренних дел РФ.

Получение паспорта - это первый серьёзный шаг во взрослую жизнь, новые права и обязанности. Искренне поздравляем ребят с этим значимым событием!

Подробнее о программе: https://vk.com/club26323016

#МыГражданеРоссии #ПатриотыПервых #ДвижениеПервых59"""
        
        elif "экология" in user_prompt_lower:
            return """Друзья! Движение Первых приглашает всех на экологическую акцию по уборке городского парка!

Вместе мы сделаем наш город чище и покажем, что забота о природе начинается с малого - с бережного отношения к окружающей среде вокруг нас.

Приходите в эту субботу в 12:00, с собой можно взять перчатки и хорошее настроение!

#ЭкологияПервых #ДвижениеПервых59"""
        
        elif "спорт" in user_prompt_lower:
            return """Активный образ жизни - путь к успеху! 

Сегодня участники "Движения Первых" провели открытую тренировку на свежем воздухе. Утренняя зарядка, пробежка и спортивные игры - отличный заряд энергии на весь день!

Присоединяйтесь к нашим регулярным тренировкам каждую субботу в 10:00 в городском парке.

#СпортЗОЖПервых #ДвижениеПервых59"""
            
        elif "коров" in user_prompt_lower:
            return """Сегодня в рамках образовательной программы "Движения Первых" ребята посетили современную молочную ферму и узнали о новейших технологиях в сельском хозяйстве!

Самое яркое впечатление произвели автоматические доильные аппараты, где коровы самостоятельно заходят в доильные боксы, когда чувствуют необходимость. Датчики и роботизированная система делают процесс доения комфортным как для животных, так и для фермеров.

Такие экскурсии не только расширяют кругозор, но и знакомят молодежь с инновациями в традиционных отраслях.

#НаукаПервых #ТехнологииБудущего #ДвижениеПервых59"""
        
        else:
            return """Друзья! "Движение Первых" - это наша общая история, которую мы пишем вместе.

Приглашаем вас принять участие в наших мероприятиях, раскрыть свои таланты и найти единомышленников.

Следите за обновлениями группы, чтобы не пропустить интересные события и возможности для саморазвития!

#ДвижениеПервых59"""
            
    async def cancel_all_requests(self):
        """Отменяет все активные запросы"""
        logger.warning(f"Отмена всех активных запросов ({len(self.active_requests)})")
        # В текущей реализации запросы отменяются через тайм-ауты 