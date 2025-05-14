from enum import Enum
from typing import Dict, Optional
from pydantic import BaseModel
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class GenerationMode(str, Enum):
    TEMPLATE = "template"
    NO_TEMPLATE = "no_template"

class PostSize(str, Enum):
    SMALL = "small"  # 200-400 символов
    MEDIUM = "medium"  # 400-800 символов
    LARGE = "large"  # 800-1200 символов

class UserState:
    """Класс для хранения состояния пользовательской сессии"""
    
    def __init__(self):
        # Базовая информация сессии
        self.user_id = None
        self.stage = "init"  # Текущий этап сессии
        self.post_text = None  # Текущий текст поста
        self.last_activity = datetime.now()
        self.last_topic = None  # Последняя тема, использованная для генерации
        
        # Режим генерации
        self.mode = GenerationMode.NO_TEMPLATE
        
        # Размер поста
        self.post_size = PostSize.MEDIUM
        
    def update(self, **kwargs):
        """Обновляет поля объекта по словарю с аргументами"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        
        # Обновляем время активности при любом обновлении
        self.last_activity = datetime.now()

class UserSession(BaseModel):
    user_id: int
    state: UserState = UserState.WAITING_FOR_MODE
    mode: Optional[GenerationMode] = None
    template_post: Optional[str] = None
    topic: Optional[str] = None
    current_post: Optional[str] = None
    post_size: Optional[PostSize] = None
    language: str = "ru"
    current_post_message_id: Optional[int] = None
    chat_id: Optional[int] = None

class SessionManager:
    """Управление пользовательскими сессиями"""
    
    def __init__(self, session_timeout_minutes=30):
        self.sessions = {}  # Словарь {user_id: UserState}
        self.session_timeout = timedelta(minutes=session_timeout_minutes)
        logger.info(f"SessionManager инициализирован с таймаутом сессии {session_timeout_minutes} минут")
    
    def create_session(self, user_id):
        """Создает новую сессию для пользователя"""
        session = UserState()
        session.user_id = user_id
        self.sessions[user_id] = session
        logger.info(f"Создана новая сессия для пользователя {user_id}")
        return session
    
    def get_session(self, user_id):
        """Возвращает текущую сессию пользователя или создает новую"""
        # Проверяем существующую сессию
        if user_id in self.sessions:
            session = self.sessions[user_id]
            # Проверяем, не истекла ли сессия
            if datetime.now() - session.last_activity > self.session_timeout:
                logger.info(f"Сессия пользователя {user_id} истекла, создаем новую")
                return self.create_session(user_id)
            return session
        
        # Если сессии нет, возвращаем None
        return None
    
    def update_session(self, user_id, user_state=None, **kwargs):
        """Обновляет параметры сессии пользователя"""
        session = self.get_session(user_id)
        
        if not session:
            # Если сессии нет, создаем новую
            session = self.create_session(user_id)
        
        if user_state:
            # Если передан объект UserState, заменяем существующую сессию
            user_state.last_activity = datetime.now()
            self.sessions[user_id] = user_state
            logger.info(f"Сессия пользователя {user_id} полностью обновлена")
        else:
            # Иначе обновляем только переданные параметры
            session.update(**kwargs)
            logger.info(f"Параметры сессии пользователя {user_id} обновлены: {kwargs}")
        
        return session
    
    def reset_session(self, user_id):
        """Сбрасывает сессию пользователя"""
        if user_id in self.sessions:
            logger.info(f"Сброс сессии пользователя {user_id}")
            del self.sessions[user_id]
    
    def reset_all_sessions(self):
        """Сбрасывает все активные сессии"""
        session_count = len(self.sessions)
        self.sessions.clear()
        logger.info(f"Сброшены все активные сессии ({session_count})")
    
    def clean_expired_sessions(self):
        """Удаляет все истекшие сессии"""
        now = datetime.now()
        expired_user_ids = [
            user_id for user_id, session in self.sessions.items()
            if now - session.last_activity > self.session_timeout
        ]
        
        for user_id in expired_user_ids:
            logger.info(f"Удаление истекшей сессии пользователя {user_id}")
            del self.sessions[user_id]
        
        if expired_user_ids:
            logger.info(f"Удалено {len(expired_user_ids)} истекших сессий")
        
        return len(expired_user_ids) 