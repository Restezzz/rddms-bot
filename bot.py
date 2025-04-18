import asyncio
import logging
from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramNetworkError, TelegramBadRequest

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

async def main():
    # Удаляем webhook перед запуском
    await bot.delete_webhook(drop_pending_updates=True)
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main()) 