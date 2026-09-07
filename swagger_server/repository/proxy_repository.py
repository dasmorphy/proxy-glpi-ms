from loguru import logger

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.resources.databases.redis import RedisClient


class ProxyRepository:
    SESSION_TOKEN_KEY = "glpi:session-token"

    def __init__(self):
        # Este microservicio solo necesita Redis. Crear una conexion PostgreSQL
        # aqui hacia que el proxy dependiera de una base que nunca utiliza.
        self.redis_client = RedisClient()

    def get_glpi_token_cache(self, internal=None, external=None):
        try:
            return self.redis_client.client.get(self.SESSION_TOKEN_KEY)
        except Exception as exception:
            logger.error("Error al obtener el token de GLPI: {}", str(exception), internal=internal, external=external)
            raise CustomAPIException("Error al obtener el token de GLPI", 503)

    def save_glpi_token_cache(
        self,
        token: str,
        usr_id=None,
        internal=None,
        external=None,
    ):
        """Guarda el token bajo una clave estable para poder recuperarlo.

        ``usr_id`` se conserva como argumento opcional por compatibilidad con
        llamadas anteriores de este repositorio.
        """
        try:
            if not token:
                raise ValueError("El token de sesion esta vacio")

            self.redis_client.client.set(
                self.SESSION_TOKEN_KEY,
                token
            )
            return token
        except Exception as exception:
            logger.error(
                "Error al guardar el token de GLPI: {}",
                str(exception),
                internal=internal,
                external=external,
            )
            raise CustomAPIException("Error al guardar el token de GLPI", 500)
