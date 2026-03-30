from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: str
    use_ingredients: bool = False


class ChatMessageResponse(BaseModel):
    role: str
    content: str
    timestamp: datetime

    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    response: str
    session_id: str


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessageResponse]
    session_id: str
