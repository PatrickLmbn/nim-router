#!/usr/bin/env python3
import os
from fastapi import HTTPException
import uvicorn

from nim_router.schemas import ChatCompletionRequest
from nim_router.engine import ModelRouter
from nim_router.server import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 11435))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")