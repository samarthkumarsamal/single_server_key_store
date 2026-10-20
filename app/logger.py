import atexit
import logging
from logging.handlers import (
    QueueHandler,
    QueueListener,
    RotatingFileHandler
)
from pathlib import Path
from queue import SimpleQueue


def configure_operation_logger():
    """
    Configure asynchronous logging for key-value operations.
    """

    # Create the logs directory if it does not exist
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create the operation logger
    logger = logging.getLogger("kv_store.operations")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    # Configure rotating file handler
    file_handler = RotatingFileHandler(
        log_dir / "operations.log",
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8"
    )

    # Configure timestamped log format
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)

    # Create thread-safe logging queue
    log_queue = SimpleQueue()

    # Send log records to the queue
    queue_handler = QueueHandler(log_queue)
    logger.addHandler(queue_handler)

    # Process logs using a background thread
    listener = QueueListener(
        log_queue,
        file_handler
    )
    listener.start()

    # Drain pending logs during normal shutdown
    atexit.register(listener.stop)

    return logger
