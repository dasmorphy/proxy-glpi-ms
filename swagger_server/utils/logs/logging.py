import logging
from logging.handlers import RotatingFileHandler
import datetime
import os


def log():
    now = datetime.datetime.now()
    format_logger = now.strftime('%Y-%m-%d')

    log_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'logs')
    os.makedirs(log_dir, exist_ok=True)

    rthandler = RotatingFileHandler(
        os.path.join(log_dir, f'proxy-glpi-api-{format_logger}.log'),
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
    )

    logging.basicConfig(
        handlers=[rthandler],
        level=logging.INFO,
        format="[%(asctime)s] - [%(filename)s:%(lineno)d %(funcName)20s()] - [%(levelname)s] -  [%(message)s]",
        datefmt='%Y-%m-%dT%H:%M:%S',
    )