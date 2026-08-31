#!/usr/bin/env python3
import os
import sys
from fastapi import HTTPException
import uvicorn

from nim_router.schemas import ChatCompletionRequest
from nim_router.engine import ModelRouter
from nim_router.server import create_app

app = create_app()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("models", "list", "select"):
        from nim_router.cli import main as cli_main
        cli_main()
    else:
        port = int(os.getenv("PORT", 11435))
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")