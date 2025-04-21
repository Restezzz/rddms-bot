import requests
import asyncio
import json
import aiohttp
from config import OPENROUTER_API_URLS, OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_HEADERS
import logging
from rddm_info import get_rddm_knowledge
from session_manager import PostSize

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self, api_urls=OPENROUTER_API_URLS, api_key=OPENROUTER_API_KEY, model=OPENROUTER_MODEL, headers=OPENROUTER_HEADERS):
        self.api_urls = api_urls
        self.api_key = api_key
        self.model = model
        self.headers = headers.copy()
        self.headers.update({
            "Content-Type": "application/json",
        })
    
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
        """Асинхронно отправляет запрос к OpenRouter API."""
        # Альтернативные URL для API
        api_urls = self.api_urls
        
        for attempt, current_url in enumerate(api_urls, 1):
            try:
                # Подготовка данных для запроса в формате OpenAI API
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": 1024,
                    "temperature": 0.7
                }
                
                # Обновленный набор заголовков
                headers = self.headers.copy()
                
                logger.info(f"Попытка {attempt}/{len(api_urls)}: Отправка запроса к {current_url} для модели {self.model}")
                
                # Используем aiohttp для асинхронных запросов
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        current_url, 
                        json=payload, 
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=60)  # Увеличенный таймаут
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            logger.error(f"Ошибка API (попытка {attempt}): {response.status}, {error_text}")
                            # Продолжаем к следующему URL, если ошибка авторизации
                            if response.status == 401 and attempt < len(api_urls):
                                logger.info(f"Пробуем альтернативный URL...")
                                continue
                            # Если все URL не сработали или другая ошибка
                            return self._get_fallback_response(user_prompt)
                        
                        result = await response.json()
                        
                        # Извлекаем ответ из структуры OpenAI API
                        if "choices" in result and len(result["choices"]) > 0:
                            message = result["choices"][0]["message"]
                            if message and "content" in message:
                                return message["content"]
                
                # Если дошли сюда, то запрос прошел без ошибок, но формат ответа неожиданный
                logger.error(f"Неожиданный формат ответа (попытка {attempt})")
                
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"Ошибка при обращении к API (попытка {attempt}): {e}")
                # Продолжаем к следующему URL, если не последняя попытка
                if attempt < len(api_urls):
                    logger.info(f"Пробуем альтернативный URL...")
                    continue
        
        # Если все попытки не удались
        logger.error(f"Все попытки запроса к API неудачны. Используем заглушку.")
        return self._get_fallback_response(user_prompt)
    
    def _get_fallback_response(self, user_prompt):
        """Возвращает заглушку при ошибках API."""
        logger.info("Генерация заглушки для демонстрации работы бота")
        
        # Создаем примерный ответ с HTML-форматированием
        if "шаблону" in user_prompt:
            return "👋 Привет от **РДДМ**!\n\nМы рады видеть тебя в нашем сообществе. **Движение первых** - это место, где каждый может проявить себя и стать частью большой дружной команды.\n\n✨ Присоединяйся к нам и открывай новые возможности для саморазвития!\n\nПодробности на сайте [будьвдвижении.рф](https://будьвдвижении.рф) 🚀"
        else:
            return "🎉 **РДДМ** приглашает всех на наше **новое мероприятие**!\n\nБудет интересно, познавательно и весело. Ждем тебя в нашей команде.\n\n📍 Подробности на сайте [будьвдвижении.рф](https://будьвдвижении.рф) ||приходи, будет сюрприз!|| 💫" 