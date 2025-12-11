import logging
import os
import sys
from datetime import datetime

def setup_logger(name):
    """
    Sets up a logger that matches the user's requirement:
    - Writes to a log file in logs/ directory (one file per run).
    - Writes to console.
    """
    # Determine log directory (copilot_agent/logs)
    # This assumes lib/logger.py is in copilot_agent/lib/
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_dir = os.path.join(base_dir, 'logs')
    os.makedirs(log_dir, exist_ok=True)

    # Use environment variable for unified log file if set, otherwise generate timestamped name
    log_file_path = os.getenv('COPILOT_AGENT_LOG_FILE')
    if not log_file_path:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"agent-{timestamp}.log"
        log_file_path = os.path.join(log_dir, filename)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Prevent adding duplicate handlers if setup_logger is called multiple times for same name
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # 1. File Handler
    try:
        file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to setup file logging: {e}")

    # 2. Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
