import asyncio
import logging
from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramNetworkError, TelegramBadRequest
import re
import os
import socket

from config import BOT_TOKEN
from session_manager import SessionManager, UserState, GenerationMode, PostSize
from llm_client import LLMClient

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)

# Инициализация диспетчера и хранилища состояний
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# Добавляем глобальный обработчик для всех сообщений
@dp.message()
async def debug_echo(message: Message):
    logger.info(f"DEBUG: Получено сообщение от {message.from_user.id}: {message.text if message.text else 'без текста'}")
    try:
        await message.answer("Я получил ваше сообщение и работаю! Это тестовый ответ.")
        logger.info(f"DEBUG: Отправлен ответ пользователю {message.from_user.id}")
    except Exception as e:
        logger.error(f"DEBUG: Ошибка при отправке ответа: {e}")

# Инициализация менеджера сессий и клиента LLM
session_manager = SessionManager()
llm_client = LLMClient()

# Главное меню с кнопками команд
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚀 Новый пост"), KeyboardButton(text="✏️ Изменить")],
    ],
    resize_keyboard=True
)

# Клавиатура выбора режима
mode_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Генерация по шаблону", callback_data="mode:template")],
    [InlineKeyboardButton(text="Генерация без шаблона", callback_data="mode:no_template")]
])

# Клавиатура выбора размера поста
size_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Короткий пост (200-400 символов)", callback_data="size:small")],
    [InlineKeyboardButton(text="Средний пост (400-800 символов)", callback_data="size:medium")],
    [InlineKeyboardButton(text="Длинный пост (800-1200 символов)", callback_data="size:large")]
])

# Список специальных символов, которые нужно экранировать в MarkdownV2
SPECIAL_CHARS = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']

def escape_markdown(text):
    """Экранирует специальные символы для MarkdownV2, но сохраняет форматирование md-разметки"""
    # Сначала защищаем существующую разметку
    # Защищаем **жирный**
    bold_pattern = r'(\*\*)(.*?)(\*\*)'
    protected_text = re.sub(bold_pattern, lambda m: f"BOLD_START{m.group(2)}BOLD_END", text)
    
    # Защищаем `код`
    code_pattern = r'(`)(.*?)(`)'
    protected_text = re.sub(code_pattern, lambda m: f"CODE_START{m.group(2)}CODE_END", protected_text)
    
    # Защищаем ```блок кода```
    code_block_pattern = r'(```)(.*?)(```)'
    protected_text = re.sub(code_block_pattern, lambda m: f"CODE_BLOCK_START{m.group(2)}CODE_BLOCK_END", protected_text)
    
    # Защищаем ~~зачеркнутый~~
    strike_pattern = r'(~~)(.*?)(~~)'
    protected_text = re.sub(strike_pattern, lambda m: f"STRIKE_START{m.group(2)}STRIKE_END", protected_text)
    
    # Защищаем ||скрытый текст||
    spoiler_pattern = r'(\|\|)(.*?)(\|\|)'
    protected_text = re.sub(spoiler_pattern, lambda m: f"SPOILER_START{m.group(2)}SPOILER_END", protected_text)
    
    # Защищаем [ссылка](URL)
    link_pattern = r'(\[)(.*?)(\])(\()(.*?)(\))'
    protected_text = re.sub(link_pattern, lambda m: f"LINK_TEXT_START{m.group(2)}LINK_TEXT_END{m.group(4)}LINK_URL{m.group(6)}", protected_text)
    
    # Экранируем все специальные символы
    for char in SPECIAL_CHARS:
        protected_text = protected_text.replace(char, f'\\{char}')
    
    # Восстанавливаем защищенную разметку
    result = protected_text.replace("BOLD_START", "**").replace("BOLD_END", "**")
    result = result.replace("CODE_START", "`").replace("CODE_END", "`")
    result = result.replace("CODE_BLOCK_START", "```").replace("CODE_BLOCK_END", "```")
    result = result.replace("STRIKE_START", "~~").replace("STRIKE_END", "~~")
    result = result.replace("SPOILER_START", "||").replace("SPOILER_END", "||")
    result = result.replace("LINK_TEXT_START", "[").replace("LINK_TEXT_END", "]")
    result = result.replace("LINK_URL", "(").replace("(LINK_URL", "(")
    
    return result

def format_message_text(text):
    """Подготавливает текст с учетом ограничений Markdown в Telegram"""
    # Преобразование блоков кода и скрытого текста в HTML, так как они не поддерживаются в MarkdownV2
    
    # Преобразование ```блок кода``` в <pre>блок кода</pre>
    code_block_pattern = r'```(.*?)```'
    html_with_code_blocks = re.sub(code_block_pattern, r'<pre>\1</pre>', text, flags=re.DOTALL)
    
    # Преобразование ||скрытый текст|| в <tg-spoiler>скрытый текст</tg-spoiler>
    spoiler_pattern = r'\|\|(.*?)\|\|'
    html_text = re.sub(spoiler_pattern, r'<tg-spoiler>\1</tg-spoiler>', html_with_code_blocks)
    
    # Остальная Markdown-разметка поддерживается в MarkdownV2
    # Экранируем специальные символы для MarkdownV2
    markdown_types = ['**', '`', '~~', '[', ']', '(', ')']
    
    for md_type in markdown_types:
        html_text = html_text.replace(md_type, f'\\{md_type}')
    
    # Экранируем другие специальные символы
    for char in ['.', '!', '+', '-', '=', '>', '#', '|', '{', '}']:
        html_text = html_text.replace(char, f'\\{char}')
    
    # Восстанавливаем Markdown-разметку
    html_text = html_text.replace('\\*\\*', '**')
    html_text = html_text.replace('\\`', '`')
    html_text = html_text.replace('\\~\\~', '~~')
    
    # Восстанавливаем ссылки
    link_pattern = r'\\\[\s*(.*?)\s*\\\]\\\(\s*(.*?)\s*\\\)'
    html_text = re.sub(link_pattern, r'[\1](\2)', html_text)
    
    return html_text

def format_to_html(text):
    """Конвертирует Markdown-разметку в HTML для использования в Telegram"""
    # Сначала экранируем специальные HTML-символы
    html_text = text.replace('&', '&amp;')
    html_text = html_text.replace('<', '&lt;').replace('>', '&gt;')
    
    # Сохраняем плейсхолдеры для разметки, чтобы избежать проблем с вложенными тегами
    placeholders = {}
    
    # Функция для создания уникальных плейсхолдеров
    def placeholder(match, prefix):
        nonlocal placeholders
        content = match.group(1)
        placeholder_id = f"__{prefix}_{len(placeholders)}__"
        placeholders[placeholder_id] = content
        return placeholder_id
    
    # Заменяем Markdown на плейсхолдеры
    # **жирный** -> __bold_0__
    bold_pattern = r'\*\*(.*?)\*\*'
    html_text = re.sub(bold_pattern, lambda m: placeholder(m, "bold"), html_text)
    
    # `код` -> __code_0__
    code_pattern = r'`(.*?)`'
    html_text = re.sub(code_pattern, lambda m: placeholder(m, "code"), html_text)
    
    # ```блок кода``` -> __codeblock_0__
    code_block_pattern = r'```(.*?)```'
    html_text = re.sub(code_block_pattern, lambda m: placeholder(m, "codeblock"), html_text, flags=re.DOTALL)
    
    # ~~зачеркнутый~~ -> __strike_0__
    strike_pattern = r'~~(.*?)~~'
    html_text = re.sub(strike_pattern, lambda m: placeholder(m, "strike"), html_text)
    
    # ||скрытый текст|| -> __spoiler_0__
    spoiler_pattern = r'\|\|(.*?)\|\|'
    html_text = re.sub(spoiler_pattern, lambda m: placeholder(m, "spoiler"), html_text)
    
    # [ссылка](URL) -> __link_0__
    link_pattern = r'\[(.*?)\]\((.*?)\)'
    
    def link_placeholder(match):
        text = match.group(1)
        url = match.group(2)
        placeholder_id = f"__link_{len(placeholders)}__"
        placeholders[placeholder_id] = (text, url)
        return placeholder_id
    
    html_text = re.sub(link_pattern, link_placeholder, html_text)
    
    # Заменяем плейсхолдеры на HTML-теги
    for placeholder_id, content in placeholders.items():
        if placeholder_id.startswith("__bold_"):
            html_text = html_text.replace(placeholder_id, f"<b>{content}</b>")
        elif placeholder_id.startswith("__code_"):
            html_text = html_text.replace(placeholder_id, f"<code>{content}</code>")
        elif placeholder_id.startswith("__codeblock_"):
            html_text = html_text.replace(placeholder_id, f"<pre>{content}</pre>")
        elif placeholder_id.startswith("__strike_"):
            html_text = html_text.replace(placeholder_id, f"<s>{content}</s>")
        elif placeholder_id.startswith("__spoiler_"):
            html_text = html_text.replace(placeholder_id, f"<tg-spoiler>{content}</tg-spoiler>")
        elif placeholder_id.startswith("__link_"):
            text, url = content
            html_text = html_text.replace(placeholder_id, f'<a href="{url}">{text}</a>')
    
    return html_text

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start - начало новой сессии"""
    await start_session(message)

@router.message(lambda msg: msg.text == "🚀 Новый пост")
async def btn_start(message: Message):
    """Обработчик кнопки 'Новый пост'"""
    await start_session(message)

async def start_session(message: Message):
    """Начинает новую сессию создания поста"""
    user_id = message.from_user.id
    session_manager.reset_session(user_id)
    
    await message.answer(
        "Привет! Я AI SMM Помощник, и я создаю контент для социальных сетей. Специализируюсь на создании постов, связанных с новостями от РДДМ.",
        reply_markup=main_keyboard
    )
    
    await message.answer(
        "Выберите режим создания поста:",
        reply_markup=mode_keyboard
    )

@router.callback_query(lambda c: c.data.startswith("mode:"))
async def process_mode_selection(callback_query: CallbackQuery):
    """Обработчик выбора режима генерации"""
    user_id = callback_query.from_user.id
    selected_mode = callback_query.data.split(":")[1]
    
    if selected_mode == "template":
        mode = GenerationMode.TEMPLATE
        session_manager.update_session(
            user_id, 
            mode=mode,
            state=UserState.WAITING_FOR_TEMPLATE
        )
        
        # Редактируем сообщение вместо отправки нового
        await callback_query.message.edit_text(
            "Вы выбрали режим генерации по шаблону. Пожалуйста, отправьте пример поста."
        )
    else:
        mode = GenerationMode.NO_TEMPLATE
        session_manager.update_session(
            user_id, 
            mode=mode,
            state=UserState.WAITING_FOR_TOPIC
        )
        
        # Редактируем сообщение вместо отправки нового
        await callback_query.message.edit_text(
            "Вы выбрали режим генерации без шаблона. Пожалуйста, укажите тему или событие для генерации поста."
        )
    
    # Отвечаем на callback до начала генерации
    await callback_query.answer()

@router.callback_query(lambda c: c.data.startswith("size:"))
async def process_size_selection(callback_query: CallbackQuery):
    """Обработчик выбора размера поста"""
    user_id = callback_query.from_user.id
    selected_size = callback_query.data.split(":")[1]
    
    # Определение размера поста
    if selected_size == "small":
        post_size = PostSize.SMALL
    elif selected_size == "medium":
        post_size = PostSize.MEDIUM
    else:
        post_size = PostSize.LARGE
    
    session = session_manager.get_session(user_id)
    
    # Логируем выбранный размер для отладки
    logger.info(f"Выбран размер поста: {post_size} для пользователя {user_id}")
    
    session_manager.update_session(
        user_id,
        post_size=post_size,
        state=UserState.IDLE
    )
    
    # Важно: отвечаем на callback сразу, до начала генерации
    await callback_query.answer()
    
    # Редактируем сообщение с информацией о начале генерации
    status_message = await callback_query.message.edit_text("Понял! Генерирую ваш пост...")
    
    try:
        # Использование разных методов в зависимости от режима
        if session.mode == GenerationMode.TEMPLATE:
            generated_post = await llm_client.generate_from_template(
                template_post=session.template_post, 
                topic=session.topic,
                post_size=post_size,
                language=session.language
            )
        else:
            generated_post = await llm_client.generate_without_template(
                topic=session.topic,
                post_size=post_size,
                language=session.language
            )
        
        # Сохраняем сгенерированный пост
        session_manager.update_session(user_id, current_post=generated_post)
        
        # Отправляем результат
        await status_message.edit_text("✅ Генерация завершена!")
        try:
            html_text = format_to_html(generated_post)
            await callback_query.message.answer(html_text, parse_mode="HTML")
        except TelegramBadRequest as e:
            logger.error(f"Ошибка при отправке сообщения с HTML: {e}")
            # Если возникла ошибка, отправляем без форматирования
            await callback_query.message.answer(generated_post)
        
        # Создаем инлайн-кнопки для действий с постом
        actions_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить пост", callback_data="action:edit")],
            [InlineKeyboardButton(text="🚀 Создать новый пост", callback_data="action:new")]
        ])
        
        await callback_query.message.answer(
            "Что делаем дальше?",
            reply_markup=actions_keyboard
        )
        
    except Exception as e:
        logger.error(f"Ошибка при генерации поста: {e}")
        await status_message.edit_text(
            "❌ Произошла ошибка при генерации поста. Возможно, сервер нейросети перегружен. "
            "Пожалуйста, попробуйте еще раз или выберите другой размер поста."
        )

@router.callback_query(lambda c: c.data.startswith("action:"))
async def process_post_action(callback_query: CallbackQuery):
    """Обработчик действий с постом"""
    action = callback_query.data.split(":")[1]
    
    if action == "edit":
        await cmd_change(callback_query.message, callback_query.from_user.id)
    elif action == "new":
        await start_session(callback_query.message)
    
    await callback_query.answer()

@router.message(Command("change"))
async def cmd_change_command(message: Message):
    """Обработчик команды /change"""
    await cmd_change(message, message.from_user.id)

@router.message(lambda msg: msg.text == "✏️ Изменить")
async def btn_change(message: Message):
    """Обработчик кнопки 'Изменить'"""
    await cmd_change(message, message.from_user.id)

async def cmd_change(message: Message, user_id: int):
    """Обработчик изменения поста"""
    session = session_manager.get_session(user_id)
    
    if not session.current_post:
        await message.answer(
            "У вас нет активного поста для изменения. Пожалуйста, сначала создайте пост.",
            reply_markup=main_keyboard
        )
        return
    
    session_manager.update_session(user_id, state=UserState.WAITING_FOR_CHANGES)
    
    session_manager.update_session(user_id, chat_id=message.chat.id)
    
    # Показываем текущий пост и запрашиваем изменения
    try:
        html_text = format_to_html(session.current_post)
        post_message = await message.answer(f"Текущий пост:\n\n{html_text}", parse_mode="HTML")
    except TelegramBadRequest as e:
        logger.error(f"Ошибка при отправке сообщения с HTML: {e}")
        post_message = await message.answer(f"Текущий пост:\n\n{session.current_post}")
    
    # Сохраняем ID сообщения с текущим постом
    session_manager.update_session(user_id, current_post_message_id=post_message.message_id)
    
    await message.answer("Пожалуйста, укажите, какие изменения нужно внести.")

@router.message()
async def process_message(message: Message):
    """Обработчик текстовых сообщений от пользователя"""
    user_id = message.from_user.id
    session = session_manager.get_session(user_id)
    
    if session.state == UserState.WAITING_FOR_TEMPLATE:
        # Получен шаблон, теперь ждем тему
        session_manager.update_session(
            user_id,
            template_post=message.text,
            state=UserState.WAITING_FOR_TOPIC
        )
        
        await message.answer(
            "✅ Шаблон принят! Теперь, пожалуйста, укажите тему для генерации поста."
        )
    
    elif session.state == UserState.WAITING_FOR_TOPIC:
        # Получена тема, запрашиваем размер поста
        session_manager.update_session(
            user_id,
            topic=message.text,
            state=UserState.WAITING_FOR_POST_SIZE
        )
        
        await message.answer(
            "✅ Тема принята! Теперь выберите предпочтительный размер поста:",
            reply_markup=size_keyboard
        )
    
    elif session.state == UserState.WAITING_FOR_CHANGES:
        if session.current_post_message_id and session.chat_id:
            try:
                await bot.delete_message(
                    chat_id=session.chat_id,
                    message_id=session.current_post_message_id
                )
                # Сбрасываем ID сообщения
                session_manager.update_session(user_id, current_post_message_id=None)
            except Exception as e:
                logger.error(f"Не удалось удалить сообщение: {e}")
        
        status_message = await message.answer("⏳ Вношу изменения в пост...")
        
        try:
            modified_post = await llm_client.modify_post(
                session.current_post,
                message.text,
                language=session.language
            )
            
            # Обновляем текущий пост
            session_manager.update_session(
                user_id,
                current_post=modified_post,
                state=UserState.IDLE
            )
            
            # Сообщаем об успешном изменении и показываем результат
            await status_message.edit_text("✅ Пост успешно изменен!")
            try:
                html_text = format_to_html(modified_post)
                await message.answer(html_text, parse_mode="HTML")
            except TelegramBadRequest as e:
                logger.error(f"Ошибка при отправке сообщения с HTML: {e}")
                await message.answer(modified_post)
            
            # Создаем инлайн-кнопки для дальнейших действий
            actions_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✏️ Изменить еще раз", callback_data="action:edit")],
                [InlineKeyboardButton(text="🚀 Создать новый пост", callback_data="action:new")]
            ])
            
            await message.answer(
                "Что делаем дальше?",
                reply_markup=actions_keyboard
            )
        except Exception as e:
            logger.error(f"Ошибка при изменении поста: {e}")
            await status_message.edit_text(
                "❌ Произошла ошибка при внесении изменений. Возможно, сервер нейросети перегружен. "
                "Пожалуйста, попробуйте еще раз с более кратким описанием изменений."
            )

async def test_api_connection():
    """Проверяет подключение к API при запуске"""
    try:
        logger.info("Диагностика API подключения...")
        
        # Используем asyncio.wait_for для ограничения времени ожидания
        import asyncio
        try:
            # Простой запрос для проверки соединения с таймаутом 10 секунд
            await asyncio.wait_for(
                llm_client.generate_without_template(
                    topic="тестовый запрос",
                    post_size=PostSize.SMALL
                ), 
                timeout=10.0
            )
            
            logger.info("Тестовый запрос к API выполнен успешно!")
            return True
        except asyncio.TimeoutError:
            logger.error("Тестовый запрос к API превысил таймаут (10 секунд)")
            return False
    except Exception as e:
        logger.error(f"Тестовый запрос к API не удался: {e}")
        return False

# Глобальные переменные для webhook режима
webhook_path = None
app = None

async def setup():
    """Инициализация бота и настройка webhook"""
    try:
        # Определяем, запущены ли мы на Railway
        is_railway = os.environ.get("RAILWAY_ENVIRONMENT") is not None
        
        # Проверяем, зарегистрированы ли обработчики
        handlers_count = len(dp.handlers.values())
        logger.info(f"Зарегистрировано обработчиков в диспетчере: {handlers_count}")
        
        # Логирование всех зарегистрированных обработчиков
        for router_key, router in dp.routers.items():
            router_handlers = len(router.handlers) if hasattr(router, "handlers") else 0
            logger.info(f"Роутер {router_key}: {router_handlers} обработчиков")
        
        # Добавляем тестовый обработчик для проверки
        @dp.message()
        async def echo_handler(message: Message):
            logger.info(f"Получено сообщение: {message.text}")
            try:
                await message.answer("Тестовый ответ на сообщение")
                logger.info("Отправлен тестовый ответ")
            except Exception as e:
                logger.error(f"Ошибка при отправке ответа: {e}")
        
        # Принудительно удаляем webhook перед запуском
        logger.info("Удаляем webhook...")
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            
            # Делаем двойную проверку, что webhook точно удален
            webhook_info = await bot.get_webhook_info()
            if webhook_info.url:
                logger.warning(f"Webhook всё ещё активен: {webhook_info.url}. Пробуем удалить снова...")
                await bot.delete_webhook(drop_pending_updates=True)
        except Exception as e:
            logger.error(f"Ошибка при удалении webhook: {e}")
        
        # Проверяем соединение с API
        try:
            api_status = await test_api_connection()
            if not api_status:
                logger.warning("API недоступен, бот будет работать с заглушками")
        except Exception as e:
            logger.error(f"Ошибка при проверке API: {e}")
        
        if is_railway:
            # На Railway запускаем бота в режиме webhook
            logger.info("Запуск на Railway, используем webhook...")
            
            try:
                # Получаем URL для webhook
                # Проверяем все возможные источники домена Railway
                railway_domain_vars = [
                    "RAILWAY_PUBLIC_DOMAIN",
                    "RAILWAY_STATIC_URL",
                    "RAILWAY_DOMAIN",
                    "RAILWAY_SERVICE_NAME"
                ]
                
                webhook_host = None
                
                # Проверяем переменные среды Railway
                for var in railway_domain_vars:
                    if os.environ.get(var):
                        value = os.environ.get(var)
                        # Если это просто имя сервиса без домена, добавляем домен Railway
                        if not value.startswith("http") and "." not in value:
                            value = f"{value}.up.railway.app"
                        
                        webhook_host = value if value.startswith("http") else f"https://{value}"
                        logger.info(f"Использую {var} для webhook: {webhook_host}")
                        break
                
                # Используем имя сервиса для создания стандартного URL Railway
                if not webhook_host and os.environ.get("RAILWAY_SERVICE_NAME"):
                    service_name = os.environ.get("RAILWAY_SERVICE_NAME")
                    # Шаблон URL для Railway: https://имя-сервиса.up.railway.app
                    webhook_host = f"https://{service_name}.up.railway.app"
                    logger.info(f"Использую стандартный шаблон Railway по имени сервиса: {webhook_host}")
                
                # Используем проектное имя для создания стандартного URL Railway
                if not webhook_host and os.environ.get("RAILWAY_PROJECT_NAME"):
                    project_name = os.environ.get("RAILWAY_PROJECT_NAME")
                    # Шаблон URL для Railway по имени проекта
                    webhook_host = f"https://{project_name}.up.railway.app"
                    logger.info(f"Использую стандартный шаблон Railway по имени проекта: {webhook_host}")
                
                # Смотрим статические переменные Railway PUBLIC_URL
                if not webhook_host and os.environ.get("PUBLIC_URL"):
                    webhook_host = os.environ.get("PUBLIC_URL")
                    logger.info(f"Использую PUBLIC_URL: {webhook_host}")
                
                # Если всё еще нет URL, используем имя хоста плюс порт
                if not webhook_host:
                    import socket
                    try:
                        hostname = socket.gethostname()
                        # Не добавляем порт в webhook URL, так как Telegram принимает только порты 80, 88, 443 или 8443
                        webhook_host = f"https://{hostname}"
                        logger.info(f"Использую hostname: {webhook_host}")
                    except Exception as e:
                        logger.error(f"Ошибка при получении hostname: {e}")
                        # Последний вариант - использовать фиксированный URL
                        webhook_host = "https://rddm-bot.up.railway.app"
                        logger.warning(f"Использую фиксированный URL: {webhook_host}")
                
                # Убедимся, что URL не содержит нестандартный порт
                if ":" in webhook_host and any(p in webhook_host for p in ["8080", "8000", "3000"]):
                    # Удаляем порт из URL
                    webhook_host = webhook_host.split(":")[0] + ("" if webhook_host.startswith("https") else ":443")
                    logger.info(f"Удален нестандартный порт из URL: {webhook_host}")
                
                # Проверяем, начинается ли URL с протокола
                if not webhook_host.startswith("http"):
                    webhook_host = "https://" + webhook_host
                    logger.info(f"Добавлен протокол в URL: {webhook_host}")
                
                global webhook_path
                webhook_path = f"/webhook/{BOT_TOKEN}"
                webhook_url = f"{webhook_host}{webhook_path}"
                
                # Настраиваем webhook
                logger.info(f"Устанавливаю webhook на {webhook_url}")
                
                # Сначала проверим, доступен ли домен
                try:
                    import socket
                    # Извлекаем домен из URL
                    domain = webhook_host.replace("https://", "").replace("http://", "").split("/")[0]
                    logger.info(f"Проверяю доступность домена {domain}...")
                    
                    # Пытаемся разрешить домен
                    socket.gethostbyname(domain)
                    logger.info(f"Домен {domain} успешно разрешен!")
                except Exception as e:
                    logger.error(f"Домен {domain} не разрешается: {e}")
                    # Если домен не разрешается, пробуем альтернативные варианты
                    webhook_host = "https://refreshing-commitment.up.railway.app"
                    webhook_url = f"{webhook_host}{webhook_path}"
                    logger.warning(f"Использую хардкодированный URL Railway из проектного имени: {webhook_host}")
                
                try:
                    await bot.set_webhook(url=webhook_url)
                    logger.info("Webhook успешно установлен!")
                except Exception as e:
                    # Не останавливаем работу бота, если webhook не установился
                    logger.error(f"Ошибка при установке webhook: {e}")
                    logger.warning("Продолжаем работу бота без webhook. Это может повлиять на работу с Telegram, но сервер будет работать.")
            except Exception as e:
                logger.error(f"Ошибка при установке webhook: {e}")
            
            # Возвращаем True для webhook режима
            return True
        
        # Для локального режима - False
        return False
    except Exception as e:
        logger.error(f"Общая ошибка в setup(): {e}")
        # Даже при ошибке возвращаем True, чтобы не блокировать запуск
        return True

async def main():
    """Точка входа для запуска бота в режиме polling"""
    # Удаляем webhook перед запуском
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем бота
    logger.info("Запуск в режиме polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Устанавливаем уровень логирования, чтобы видеть все сообщения
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("===== Запуск бота =====")
    
    # Логируем параметры окружения
    is_railway = os.environ.get("RAILWAY_ENVIRONMENT") is not None
    logger.info(f"Запуск на Railway: {is_railway}")
    
    # Логируем все переменные окружения, связанные с Railway
    logger.info("=== Railway переменные окружения ===")
    for key, value in sorted(os.environ.items()):
        if "RAILWAY" in key or "URL" in key or "DOMAIN" in key or "HOST" in key:
            # Скрываем токены и ключи
            if any(secret in key.lower() for secret in ["token", "key", "secret", "password", "auth"]):
                value = value[:10] + "..." if value and len(value) > 10 else value
            logger.info(f"{key}: {value}")
    logger.info("===================================")
    
    # Проверяем переменную окружения для выбора режима
    force_polling = os.environ.get("FORCE_POLLING", "false").lower() == "true"
    if force_polling:
        logger.info("Режим FORCE_POLLING активирован! Запуск в режиме polling вместо webhook.")
        asyncio.run(main())
    elif is_railway:
        # Используем FastAPI для запуска в webhook режиме
        logger.info("Инициализация FastAPI для webhook режима")
        from fastapi import FastAPI, Request, Response
        from fastapi.middleware.cors import CORSMiddleware
        import uvicorn
        
        app = FastAPI()
        
        # Настройка CORS
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Объявляем healthcheck эндпоинт первым делом
        @app.get("/")
        async def root():
            return {"status": "ok", "mode": "webhook"}
        
        @app.post("/webhook/{token}")
        async def bot_webhook(request: Request, token: str):
            logger.info(f"Получен webhook запрос, токен: {token[:5]}...")
            
            if token == BOT_TOKEN:
                try:
                    # Логируем тело запроса
                    request_body = await request.json()
                    logger.info(f"Webhook данные: {request_body}")
                    
                    # Отправляем данные в диспетчер
                    await dp.feed_update(bot, request_body)
                    logger.info("Данные успешно переданы в диспетчер")
                    
                    return Response(status_code=200)
                except Exception as e:
                    logger.error(f"Ошибка при обработке webhook запроса: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    return Response(status_code=500)
            else:
                logger.warning(f"Получен запрос с неверным токеном: {token[:5]}...")
                return Response(status_code=403)
        
        # Выносим настройку webhook в отдельный процесс
        @app.on_event("startup")
        async def on_startup():
            # Запускаем настройку webhook в фоне
            import asyncio
            asyncio.create_task(setup())
            logger.info("Сервер запущен и готов обрабатывать запросы")
        
        # Запускаем сервер FastAPI
        port = int(os.environ.get("PORT", 8000))
        logger.info(f"Запуск FastAPI сервера на порту {port}")
        
        try:
            logger.info("Запуск uvicorn...")
            uvicorn.run(app, host="0.0.0.0", port=port)
        except Exception as e:
            logger.critical(f"Критическая ошибка при запуске сервера: {e}")
            import traceback
            logger.critical(f"Трейсбек: {traceback.format_exc()}")
    else:
        # Локально используем asyncio для запуска в режиме polling
        asyncio.run(main()) 