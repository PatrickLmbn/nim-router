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

log_handler = logging.StreamHandler(sys.stdout)
log_handler.setFormatter(ColoredFormatter())
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("nim-router")
logger.setLevel(logging.INFO)
logger.handlers = [log_handler]
logger.propagate = False
