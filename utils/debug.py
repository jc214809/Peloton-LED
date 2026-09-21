import logging
import os
from logging.handlers import RotatingFileHandler

logger = logging.getLogger("peloton-led")

# Determine the base directory path dynamically
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Logs live next to the code by default (local dev), but PELOTON_LOG_DIR lets
# a managed install (e.g. systemd with ProtectSystem=strict, where the code
# directory is read-only) point this at a writable path instead.
LOG_DIR = os.environ.get('PELOTON_LOG_DIR') or os.path.join(BASE_DIR, 'logs')

# Create handlers for both console and file
console_handler = logging.StreamHandler()  # For console output
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(module)s:%(lineno)d - %(funcName)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

try:
    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, 'app.log'),
        maxBytes=5 * 1024 * 1024,
        backupCount=10
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except OSError as exc:
    # A read-only or missing log directory must not prevent the app from
    # running — console output (captured by journalctl under systemd) is
    # still available even without a log file.
    logger.warning('Could not set up file logging in %s: %s', LOG_DIR, exc)

logger.propagate = False

info = logger.info

warning = logger.warning

error = logger.error

log = logger.debug

exception = logger.exception
