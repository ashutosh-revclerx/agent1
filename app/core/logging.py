"""
Logging Configuration
Multi-file logging handler for different log levels
"""
import io
import os
import sys
import logging


class MultiFileHandler(logging.Handler):
    """Custom handler to duplicate logs to multiple destinations based on level"""

    def __init__(self):
        super().__init__()
        os.makedirs("logs", exist_ok=True)
        self.error_handler = logging.FileHandler("logs/error.log", encoding="utf-8")
        self.error_handler.setLevel(logging.ERROR)

        self.debug_handler = logging.FileHandler("logs/debug.log", encoding="utf-8")
        self.debug_handler.setLevel(logging.DEBUG)

        self.info_handler = logging.FileHandler("logs/app.log", encoding="utf-8")
        self.info_handler.setLevel(logging.INFO)

        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        self.error_handler.setFormatter(formatter)
        self.debug_handler.setFormatter(formatter)
        self.info_handler.setFormatter(formatter)

    def emit(self, record):
        self.info_handler.emit(record)
        self.debug_handler.emit(record)
        if record.levelno >= logging.ERROR:
            self.error_handler.emit(record)


def setup_logger():
    """Configure and return application logger"""
    utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            MultiFileHandler(),
            logging.StreamHandler(utf8_stdout),
        ],
    )
    return logging.getLogger(__name__)


logger = setup_logger()
