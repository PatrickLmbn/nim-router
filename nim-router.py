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
    try:
        if len(sys.argv) > 1:
            cmd = sys.argv[1].lower()
            if cmd in ("models", "list", "select"):
                from nim_router.cli import select_primary_model
                select_primary_model()
            elif cmd in ("probe", "scan"):
                from nim_router.cli import probe_active_models
                probe_active_models()
            elif cmd in ("connect", "keys", "key", "config"):
                from nim_router.cli import connect_api_keys
                connect_api_keys()
            elif cmd in ("restart", "reload"):
                from nim_router.cli import restart_server
                restart_server()
            elif cmd in ("stop", "kill", "down"):
                from nim_router.cli import stop_server
                stop_server()
            elif cmd in ("logs", "log"):
                from nim_router.cli import show_logs
                show_logs()
            elif cmd in ("help", "-h", "--help"):
                from nim_router.cli import show_help
                show_help()
            elif cmd in ("server", "start", "run"):
                port = int(os.getenv("PORT", 11435))
                uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
            else:
                print(f"\033[1;33m[!] Unknown command: '{sys.argv[1]}'\033[0m\n")
                from nim_router.cli import show_help
                show_help()
                sys.exit(1)
        else:
            port = int(os.getenv("PORT", 11435))
            uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)