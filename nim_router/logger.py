import logging
import sys

SUCCESS_LEVEL = 25
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")

def log_success(self, message, *args, **kws):
    if self.isEnabledFor(SUCCESS_LEVEL):
        self._log(SUCCESS_LEVEL, message, args, **kws)

logging.Logger.success = log_success

class ColoredFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: "\033[90m",
        logging.INFO: "\033[94m",
        SUCCESS_LEVEL: "\033[92m",
        logging.WARNING: "\033[93m",
        logging.ERROR: "\033[91m",
        logging.CRITICAL: "\033[1;91m",
    }

    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, "")
        reset = "\033[0m"
        asctime = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        levelname = record.levelname
        msg = record.getMessage()
        return f"{asctime} - {color}{levelname}{reset} - {color}{msg}{reset}"

import asyncio
from collections import deque
import time

log_buffer = deque(maxlen=300)
_log_subscribers: set[asyncio.Queue] = set()

class BufferAndBroadcastHandler(logging.Handler):
    def emit(self, record):
        try:
            entry = {
                "timestamp": time.strftime("%H:%M:%S", time.localtime(record.created)),
                "level": record.levelname,
                "message": record.getMessage(),
            }
            log_buffer.append(entry)
            for q in list(_log_subscribers):
                try:
                    q.put_nowait(entry)
                except Exception:
                    pass
        except Exception:
            pass

def register_log_subscriber() -> asyncio.Queue:
    q = asyncio.Queue(maxsize=100)
    _log_subscribers.add(q)
    return q

def unregister_log_subscriber(q: asyncio.Queue):
    _log_subscribers.discard(q)

def get_recent_logs() -> list[dict]:
    return list(log_buffer)

log_handler = logging.StreamHandler(sys.stdout)
log_handler.setFormatter(ColoredFormatter())
broadcast_handler = BufferAndBroadcastHandler()

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("nim-router")
logger.setLevel(logging.INFO)
logger.handlers = [log_handler, broadcast_handler]
logger.propagate = False

