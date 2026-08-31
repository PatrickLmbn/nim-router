from typing import Optional
from pydantic import BaseModel

class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[dict]
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 1.0
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    stop: Optional[list[str]] = None
    tools: Optional[list[dict]] = None
