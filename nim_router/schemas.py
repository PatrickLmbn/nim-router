from typing import Optional, Union
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
    tool_choice: Optional[Union[str, dict]] = None


class ResponsesRequest(BaseModel):
    model: str
    input: Optional[Union[str, list[dict]]] = None
    instructions: Optional[str] = None
    max_output_tokens: Optional[int] = None
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 1.0
    stream: Optional[bool] = False
    stop: Optional[list[str]] = None
    tools: Optional[list[dict]] = None
    tool_choice: Optional[str] = "auto"
    store: Optional[bool] = False
