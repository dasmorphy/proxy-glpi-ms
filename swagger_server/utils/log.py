from timeit import default_timer
from loguru import logger
from datetime import datetime, timedelta, time

# VARIABLES (CAMBIAR EN EL CASO QUE SEA NECESARIO)
MS_NAME: str = 'proxy-glpi-ms'  # NOMBRE DEL MS, CAMBIAR CON EL NOMBRE DE CADA MS
LOG_SIZE: int = 2          # CANTIDAD EN MB Ejemplo: (20 = 20MB), debe ser mayor a 1, número entero sin decimales
LOG_MAX_DAYS: int = 60     # CANTIDAD DE ARCHIVOS DE LOG EN DIAS (MAX DIAS GUARDAR)


# CONSTANTES
FOLDER_LOG: str = 'logs'
LOG_ENCODING: str = 'utf-8'
LOG_EXTENSION: str = 'log'


class Rotator:

    def __init__(self, size, at):
        self._size = size
        now = datetime.now()
        today_at_time = now.replace(hour=at.hour, minute=at.minute, second=at.second)
        if now >= today_at_time:
            # the current time is already past the target time so it would rotate already
            # add one day to prevent an immediate rotation
            self._next_rotate = today_at_time + timedelta(days=1)
        else:
            self._next_rotate = today_at_time

    def should_rotate(self, message, file):
        file.seek(0, 2)
        if file.tell() + len(message) > self._size:
            return True
        if message.record["time"].timestamp() > self._next_rotate.timestamp():
            self._next_rotate += timedelta(days=1)
            return True
        return False


def configure_logger():
    rotator = Rotator(LOG_SIZE * 1024 * 1024, time(0, 0, 0))
    rotator.should_rotate
    logger.remove()  # Eliminar cualquier configuración de registro existente

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<magenta>ITID: {extra[internal]}</magenta> | "
        "<magenta>ETID: {extra[external]}</magenta> | "
        "<cyan>PACKAGE: {name}</cyan> | MODULE: <cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>MESSAGE: {message}</level>"
    )

    logger.add(
        f"{FOLDER_LOG}/{MS_NAME}-{{time:YYYY-MM-DD}}.{LOG_EXTENSION}",  # Ruta donde se guardarán los archivos con la fecha del día actual
        rotation=rotator.should_rotate,               # Rotar los archivos cuando alcanzan 1 MB
        retention=f"{str(LOG_MAX_DAYS)} days",                # Mantener un máximo de 5 archivos (por la rotación y el nuevo día)
        level="DEBUG",                 # Nivel de registro (puedes ajustar esto)
        format=log_format,
        enqueue=True,                  # Enqueue logs to be processed in the background
    )


def start_request(channel: str, function_name: str, internal_process: tuple, system: str = None, log: bool = True):
    if log:
        try:
            internal, external = internal_process
            message = f'{function_name} - Channel: {channel} - System: {system}'
            logger.info(message, internal=internal, external=external)
        except:
            pass


def execute_duration(start_time, function_name: str, internal_process: tuple, log: bool = True):
    if log:
        try:
            internal, external = internal_process
            end_time = default_timer()
            message = f"{function_name} end in {round((end_time - start_time) * 1000)} ms"
            logger.info(message, internal=internal, external=external)
        except:
            pass
