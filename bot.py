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
import json
import time
import aiohttp

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

# Создаем отдельный маршрутизатор для отладочных команд (с меньшим приоритетом)
debug_router = Router(name="debug_router")

# Важно: включаем router в диспетчер ПЕРЕД регистрацией других обработчиков
dp.include_router(router)  # Основной маршрутизатор с приоритетом по умолчанию

# Добавляем явный обработчик команды /start для отладки
@debug_router.message(Command("start"))
async def cmd_start_debug(message: Message):
    logger.info(f"DEBUG: Получена команда /start от {message.from_user.id}")
    try:
        await message.answer("Привет! Я бот и я работаю в режиме отладки.")
        logger.info(f"DEBUG: Отправлен ответ на команду /start пользователю {message.from_user.id}")
    except Exception as e:
        logger.error(f"DEBUG: Ошибка при отправке ответа на /start: {e}")

# Добавляем обработчик команды /debug
@debug_router.message(Command("debug"))
async def cmd_debug(message: Message):
    logger.info(f"DEBUG: Получена команда /debug от {message.from_user.id}")
    try:
        debug_info = "Диагностическая информация:\n"
        debug_info += f"- Бот запущен и работает\n"
        debug_info += f"- Telegram ID: {message.from_user.id}\n"
        debug_info += f"- Имя пользователя: {message.from_user.username}\n"
        debug_info += f"- Диспетчер: обработчиков сообщений: {len(dp.message.handlers)}\n"
        debug_info += f"- Router включен: {router in dp.routers}\n"
        
        await message.answer(debug_info)
        logger.info(f"DEBUG: Отправлена отладочная информация пользователю {message.from_user.id}")
    except Exception as e:
        logger.error(f"DEBUG: Ошибка при отправке отладочной информации: {e}")

# Добавляем отладочный маршрутизатор ПОСЛЕДНИМ, чтобы он имел самый низкий приоритет
dp.include_router(debug_router)

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

# Глобальный флаг для предотвращения двойной отправки
POST_ALREADY_SENT = {}

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
        
        # Устанавливаем флаг, что сообщение ещё не отправлялось
        POST_ALREADY_SENT[user_id] = False
        
        try:
            # Попытка отправить с HTML форматированием
            html_text = format_to_html(generated_post)
            sent_message = await callback_query.message.answer(html_text, parse_mode="HTML")
            # Запоминаем ID сообщения с постом
            session_manager.update_session(user_id, current_post_message_id=sent_message.message_id)
            # Помечаем что сообщение отправлено
            POST_ALREADY_SENT[user_id] = True
        except Exception as e:
            # Только если HTML отправка не удалась, пробуем обычный текст
            logger.error(f"Ошибка при отправке HTML: {e}")
            if not POST_ALREADY_SENT.get(user_id, False):
                sent_message = await callback_query.message.answer(generated_post)
                session_manager.update_session(user_id, current_post_message_id=sent_message.message_id)
        
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
    
    # Устанавливаем флаг, что сообщение ещё не отправлялось
    POST_ALREADY_SENT[user_id] = False
    
    # Показываем текущий пост и запрашиваем изменения
    try:
        html_text = format_to_html(session.current_post)
        post_message = await message.answer(f"Текущий пост:\n\n{html_text}", parse_mode="HTML")
        # Сохраняем ID сообщения с текущим постом
        session_manager.update_session(user_id, current_post_message_id=post_message.message_id)
        # Помечаем что сообщение отправлено
        POST_ALREADY_SENT[user_id] = True
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения с HTML: {e}")
        # Только если HTML отправка не удалась, пробуем обычный текст
        if not POST_ALREADY_SENT.get(user_id, False):
            post_message = await message.answer(f"Текущий пост:\n\n{session.current_post}")
            # Сохраняем ID сообщения с текущим постом
            session_manager.update_session(user_id, current_post_message_id=post_message.message_id)
    
    await message.answer("Пожалуйста, укажите, какие изменения нужно внести.")

@router.message()
async def process_message(message: Message):
    """Обрабатывает все текстовые сообщения."""
    user_id = message.from_user.id
    
    # Получаем текущую сессию пользователя, если есть
    user_state = session_manager.get_session(user_id)
    
    # Если нет активной сессии, не обрабатываем сообщение
    if not user_state:
        logger.info(f"Получено сообщение вне сессии от {user_id}")
        # Отправляем сообщение о начале новой сессии
        await message.answer(
            "Чтобы начать работу, нажмите на кнопку или введите команду /start", 
            reply_markup=main_keyboard
        )
        return
    
    # Проверяем текущий этап сессии
    if user_state.stage == "wait_for_topic":
        try:
            topic = message.text.strip()
            
            # Создаем клавиатуру для действий с постом
            post_actions = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Подтвердить ✅", callback_data="action:confirm")],
                [InlineKeyboardButton(text="Изменить ✏️", callback_data="action:edit")],
                [InlineKeyboardButton(text="Новый пост 🔄", callback_data="action:new")]
            ])
            
            # Отправляем сообщение о генерации
            processing_msg = await message.answer("⏳ Генерирую пост по вашей теме... Это может занять до 30 секунд.")
            
            # Определяем, какой режим генерации использовать
            try:
                if user_state.post_text and user_state.mode == GenerationMode.TEMPLATE:
                    # Используем текущий пост как шаблон для нового
                    logger.info(f"Генерация поста по шаблону для пользователя {user_id}")
                    
                    # Устанавливаем таймаут для запроса
                    try:
                        post_text = await asyncio.wait_for(
                            llm_client.generate_from_template(
                                template_post=user_state.post_text, 
                                topic=topic,
                                post_size=user_state.post_size
                            ),
                            timeout=45  # 45 секунд на всю генерацию
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"Таймаут при генерации поста по шаблону для {user_id}")
                        await processing_msg.delete()
                        await message.answer("⌛ Время ожидания истекло. Пожалуйста, попробуйте еще раз или выберите другую тему.")
                        return
                else:
                    # Генерируем без шаблона
                    logger.info(f"Генерация поста без шаблона для пользователя {user_id}")
                    
                    # Устанавливаем таймаут для запроса
                    try:
                        post_text = await asyncio.wait_for(
                            llm_client.generate_without_template(
                                topic=topic,
                                post_size=user_state.post_size
                            ),
                            timeout=45  # 45 секунд на всю генерацию
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"Таймаут при генерации поста без шаблона для {user_id}")
                        await processing_msg.delete()
                        await message.answer("⌛ Время ожидания истекло. Пожалуйста, попробуйте еще раз или выберите другую тему.")
                        return
                
                # Сохраняем сгенерированный пост в состоянии пользователя
                user_state.post_text = post_text
                user_state.last_topic = topic
                session_manager.update_session(user_id, user_state)
                
                # Удаляем сообщение о генерации
                await processing_msg.delete()
                
                # Отправляем сгенерированный пост
                await message.answer(
                    f"✅ Вот ваш пост на тему: {topic}\n\n{post_text}", 
                    reply_markup=post_actions,
                    parse_mode='HTML'
                )
                logger.info(f"Пост успешно сгенерирован для пользователя {user_id}")
                
            except Exception as e:
                logger.error(f"Ошибка при генерации поста: {e}")
                await processing_msg.delete()
                await message.answer(
                    f"❌ Произошла ошибка при генерации поста: {str(e)}. Пожалуйста, попробуйте еще раз.",
                    reply_markup=main_keyboard
                )
                # Сбрасываем сессию при ошибке
                session_manager.reset_session(user_id)
                
        except Exception as e:
            logger.error(f"Ошибка при обработке темы: {e}")
            await message.answer(
                "❌ Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте еще раз.",
                reply_markup=main_keyboard
            )
            session_manager.reset_session(user_id)
            
    elif user_state.stage == "wait_for_edit":
        try:
            edit_request = message.text.strip()
            
            # Создаем клавиатуру для действий с отредактированным постом
            post_actions = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Подтвердить ✅", callback_data="action:confirm")],
                [InlineKeyboardButton(text="Изменить ✏️", callback_data="action:edit")],
                [InlineKeyboardButton(text="Новый пост 🔄", callback_data="action:new")]
            ])
            
            # Отправляем сообщение о редактировании
            processing_msg = await message.answer("⏳ Редактирую пост согласно вашим пожеланиям... Это может занять до 30 секунд.")
            
            try:
                # Вызываем редактирование с таймаутом
                try:
                    edited_text = await asyncio.wait_for(
                        llm_client.modify_post(
                            current_post=user_state.post_text,
                            modification_request=edit_request
                        ),
                        timeout=45  # 45 секунд на всё редактирование
                    )
                except asyncio.TimeoutError:
                    logger.error(f"Таймаут при редактировании поста для {user_id}")
                    await processing_msg.delete()
                    await message.answer("⌛ Время ожидания истекло. Пожалуйста, попробуйте еще раз с более простым запросом.")
                    return
                    
                # Сохраняем отредактированный пост
                user_state.post_text = edited_text
                session_manager.update_session(user_id, user_state)
                
                # Удаляем сообщение о редактировании
                await processing_msg.delete()
                
                # Отправляем отредактированный пост
                await message.answer(
                    f"✅ Вот ваш отредактированный пост:\n\n{edited_text}", 
                    reply_markup=post_actions,
                    parse_mode='HTML'
                )
                logger.info(f"Пост успешно отредактирован для пользователя {user_id}")
                
            except Exception as e:
                logger.error(f"Ошибка при редактировании поста: {e}")
                await processing_msg.delete()
                await message.answer(
                    f"❌ Произошла ошибка при редактировании поста: {str(e)}. Пожалуйста, попробуйте еще раз.",
                    reply_markup=post_actions
                )
        except Exception as e:
            logger.error(f"Ошибка при обработке запроса на редактирование: {e}")
            await message.answer(
                "❌ Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте еще раз.",
                reply_markup=main_keyboard
            )
    else:
        # Если не ожидаем ни темы, ни редактирования, то просто игнорируем сообщение
        logger.info(f"Получено неожиданное сообщение от {user_id} в состоянии {user_state.stage}")
        await message.answer(
            "Пожалуйста, выберите действие из меню ниже:",
            reply_markup=main_keyboard
        )

# Функция для отмены всех активных запросов при перезапуске
async def cancel_active_requests():
    try:
        logger.info("Отмена всех активных запросов API перед перезапуском")
        await llm_client.cancel_all_requests()
    except Exception as e:
        logger.error(f"Ошибка при отмене запросов: {e}")

# Функция проверки работоспособности API
async def test_api_connection():
    """Проверяет доступность API методом отправки тестового запроса."""
    logger.info("Проверка подключения к API...")
    try:
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

if __name__ == "__main__":
    # Устанавливаем уровень логирования, чтобы видеть все сообщения
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("===== Запуск бота =====")
    
    # Логируем параметры окружения
    is_railway = os.environ.get("RAILWAY_ENVIRONMENT") is not None
    is_timeweb = "TWC_" in os.environ.get("HOSTNAME", "") or any("TIMEWEB" in key for key in os.environ.keys())
    
    if is_timeweb:
        logger.info("Обнаружена среда Timeweb Cloud!")
    
    logger.info(f"Запуск на Railway: {is_railway}")
    logger.info(f"Запуск на Timeweb: {is_timeweb}")
    
    # Логируем окружение для отладки
    logger.info("=== Переменные окружения ===")
    for key, value in sorted(os.environ.items()):
        # Скрываем токены и ключи
        if any(secret in key.lower() for secret in ["token", "key", "secret", "password", "auth"]):
            value = value[:10] + "..." if value and len(value) > 10 else value
        logger.info(f"{key}: {value}")
    logger.info("===================================")
    
    # Все запускаем в одном асинхронном цикле
    import asyncio
    
    async def run_all():
        # Проверяем и удаляем webhook с помощью прямых запросов к API
        logger.info("Проверяем статус webhook...")
        try:
            # Получаем информацию о текущем webhook
            webhook_info = await bot.get_webhook_info()
            if webhook_info.url:
                logger.warning(f"Обнаружен активный webhook: {webhook_info.url}")
                
                # Удаляем webhook через API бота
                logger.info("Удаляю webhook через API...")
                await bot.delete_webhook(drop_pending_updates=True)
                
                # Повторно проверяем статус webhook
                webhook_info = await bot.get_webhook_info()
                if webhook_info.url:
                    logger.error(f"Webhook всё ещё активен после попытки удаления: {webhook_info.url}")
                    logger.warning("Пробую альтернативный метод удаления webhook...")
                    
                    # Используем альтернативный метод - прямой HTTP запрос
                    import aiohttp
                    delete_url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=true"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(delete_url) as response:
                            response_json = await response.json()
                            if response.status == 200 and response_json.get('ok'):
                                logger.info("Webhook успешно удален через прямой HTTP запрос!")
                            else:
                                logger.error(f"Не удалось удалить webhook: {response_json}")
                else:
                    logger.info("Webhook успешно удален!")
            else:
                logger.info("Webhook не активен, продолжаем работу в режиме polling.")
        except Exception as e:
            logger.error(f"Ошибка при проверке/удалении webhook: {e}")
        
        # Проверяем API
        try:
            api_status = await test_api_connection()
            if api_status:
                logger.info("API доступен и работает")
            else:
                logger.warning("API недоступен, бот будет работать с заглушками")
        except Exception as e:
            logger.error(f"Ошибка при проверке API: {e}")
        
        # Запускаем HTTP сервер для healthcheck и для Timeweb Cloud
        # Используем стандартный порт 8080, который нужен для Timeweb
        import aiohttp
        from aiohttp import web
        
        # Создаем простой HTTP-сервер для ответа на healthcheck
        app = web.Application()
        
        # Middleware для логирования запросов
        @web.middleware
        async def logging_middleware(request, handler):
            start_time = asyncio.get_event_loop().time()
            try:
                response = await handler(request)
                end_time = asyncio.get_event_loop().time()
                duration = end_time - start_time
                # Логируем только запросы к корню
                if request.path == "/":
                    logger.info(f"HTTP Request: {request.method} {request.path} - {response.status} ({duration:.4f}s)")
                return response
            except Exception as e:
                logger.error(f"HTTP Error: {request.method} {request.path} - {e}")
                raise
        
        # Применяем middleware
        app.middlewares.append(logging_middleware)
        
        # Глобальная переменная для отслеживания состояния бота
        bot_started_at = time.time()
        polling_active = True
        
        # Обработчик для принудительного завершения или перезапуска зависших запросов
        async def reset_handler(request):
            # Отменяем все активные запросы
            await cancel_active_requests()
            session_manager.reset_all_sessions()
            return web.json_response({
                "status": "ok", 
                "message": "Все активные запросы отменены, сессии сброшены"
            })
        
        async def health_handler(request):
            uptime = int(time.time() - bot_started_at)
            # Отслеживаем количество активных запросов
            active_requests = len(llm_client.active_requests) if hasattr(llm_client, 'active_requests') else 0
            
            return web.json_response({
                "status": "ok", 
                "mode": "polling", 
                "timestamp": int(time.time()),
                "uptime": uptime,
                "polling_active": polling_active,
                "handlers_count": len(dp.message.handlers),
                "active_sessions": len(session_manager.sessions),
                "active_requests": active_requests
            })
        
        app.router.add_get('/', health_handler)
        app.router.add_get('/reset', reset_handler)  # Новый эндпоинт для сброса зависших запросов
        
        # Получаем порт из переменной окружения
        # Важно: на Timeweb Cloud порт должен быть 8080
        port = int(os.environ.get("PORT", 8080))
        logger.info(f"HTTP сервер будет запущен на порту {port}")
        
        # Запускаем HTTP сервер в асинхронном режиме без блокировки
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        logger.info(f"HTTP сервер запущен на порту {port}")
        
        # Запускаем бота
        logger.info("Запуск бота в режиме polling...")
        
        # Выводим информацию о зарегистрированных обработчиках
        router_info = "Зарегистрированные обработчики:\n"
        for r in dp.message.handlers:
            router_info += f"- Обработчик сообщений: {r}\n"
        logger.info(router_info)
        
        # Настраиваем обработку ошибок для диспетчера
        @dp.errors()
        async def error_handler(exception):
            logger.error(f"Ошибка при обработке обновления: {exception}")
            return True  # Продолжаем обработку других обновлений
        
        try:
            # Запускаем с автоматическим перезапуском при ошибках сети
            while True:
                try:
                    # Проверяем еще раз, что webhook точно удален
                    webhook_info = await bot.get_webhook_info()
                    if webhook_info.url:
                        logger.error(f"Webhook всё ещё активен перед запуском polling: {webhook_info.url}")
                        logger.info("Еще одна попытка удаления webhook...")
                        await bot.delete_webhook(drop_pending_updates=True)
                        
                        # Если и это не помогло - используем прямой HTTP запрос
                        webhook_info = await bot.get_webhook_info()
                        if webhook_info.url:
                            delete_url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=true"
                            async with aiohttp.ClientSession() as session:
                                async with session.get(delete_url) as response:
                                    response_json = await response.json()
                                    logger.info(f"Результат принудительного удаления webhook: {response_json}")
                    
                    logger.info("Запуск polling...")
                    # Мониторинг активных запросов каждые 5 минут
                    async def monitor_active_requests():
                        while True:
                            try:
                                await asyncio.sleep(300)  # Проверка каждые 5 минут
                                active_requests = len(llm_client.active_requests) if hasattr(llm_client, 'active_requests') else 0
                                logger.info(f"Мониторинг: {active_requests} активных API запросов")
                                if active_requests > 10:
                                    logger.warning(f"Большое количество активных запросов: {active_requests}. Отмена...")
                                    await cancel_active_requests()
                            except Exception as e:
                                logger.error(f"Ошибка в мониторинге активных запросов: {e}")
                    
                    # Запускаем мониторинг в отдельной задаче
                    asyncio.create_task(monitor_active_requests())
                    
                    # Запускаем polling
                    await dp.start_polling(bot)
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.error(f"Сетевая ошибка при polling: {e}, перезапуск через 5 секунд...")
                    await asyncio.sleep(5)
                except Exception as e:
                    logger.error(f"Критическая ошибка при polling: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    break  # Выходим из цикла при критических ошибках
        except Exception as e:
            logger.error(f"Ошибка при запуске polling: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    # Запускаем все в одном цикле
    asyncio.run(run_all()) 