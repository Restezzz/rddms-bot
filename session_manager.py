from enum import Enum
from typing import Dict, Optional
from pydantic import BaseModel

class GenerationMode(str, Enum):
    TEMPLATE = "template"
    NO_TEMPLATE = "no_template"

class PostSize(str, Enum):
    SMALL = "small"  # 200-400 символов
    MEDIUM = "medium"  # 400-800 символов
    LARGE = "large"  # 800-1200 символов

class UserState(str, Enum):
    WAITING_FOR_MODE = "waiting_for_mode"
    WAITING_FOR_TEMPLATE = "waiting_for_template"
    WAITING_FOR_TOPIC = "waiting_for_topic" 
    WAITING_FOR_POST_SIZE = "waiting_for_post_size"
    WAITING_FOR_CHANGES = "waiting_for_changes"
    IDLE = "idle"

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
    def __init__(self):
        self.sessions: Dict[int, UserSession] = {}
    
    def get_session(self, user_id: int) -> UserSession:
        """Получает или создает сессию для пользователя"""
        if user_id not in self.sessions:
            self.sessions[user_id] = UserSession(user_id=user_id)
        return self.sessions[user_id]
    
    def update_session(self, user_id: int, **kwargs) -> UserSession:
        """Обновляет параметры сессии пользователя"""
        session = self.get_session(user_id)
        
        for key, value in kwargs.items():
            if hasattr(session, key):
                setattr(session, key, value)
                
        return session
    
    def reset_session(self, user_id: int) -> UserSession:
        """Сбрасывает сессию пользователя до начального состояния"""
        chat_id = None
        if user_id in self.sessions:
            chat_id = self.sessions[user_id].chat_id
            
        self.sessions[user_id] = UserSession(user_id=user_id)
        
        if chat_id:
            self.sessions[user_id].chat_id = chat_id
            
        return self.sessions[user_id] 