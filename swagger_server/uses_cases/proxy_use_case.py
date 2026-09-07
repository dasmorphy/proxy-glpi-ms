from urllib.parse import urlsplit

import requests
from flask import Response
from loguru import logger

from swagger_server.config.access import access
from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.repository.proxy_repository import ProxyRepository


class ProxyUseCase:
    ALLOWED_METHODS = {"GET", "POST", "DELETE"}
    REQUEST_HEADERS_TO_SKIP = {
        "accept-encoding",
        "app-token",
        "connection",
        "content-length",
        "host",
        "session-token",
        "transfer-encoding",
    }
    RESPONSE_HEADERS_TO_SKIP = {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }

    def __init__(self, repository=None, http_client=None, settings=None):
        glpi_settings = settings if settings is not None else access()["GLPI"]
        self.repository = repository or ProxyRepository()
        self.http_client = http_client or requests.Session()
        self.api_glpi = (glpi_settings.get("API") or "").rstrip("/")
        self.app_token = glpi_settings.get("APP_TOKEN")
        self.user_token_session = glpi_settings.get("USER_TOKEN_SESSION")
        self.timeout = glpi_settings.get("TIMEOUT", 30)

    def proxy(self, method, endpoint, incoming_request, internal=None, external=None):
        method = method.upper()
        if method not in self.ALLOWED_METHODS:
            raise CustomAPIException("Metodo HTTP no soportado", 405)

        self._validate_proxy_configuration()
        url = self._build_url(endpoint)
        session_token = self.repository.get_glpi_token_cache(internal, external)
        if not session_token:
            session_token = self._refresh_session(internal, external)

        response = self._send_request(
            method,
            url,
            incoming_request,
            session_token,
            internal,
            external,
        )

        # El token puede haber expirado antes de su TTL en Redis. Se renueva y
        # se repite la operacion una sola vez para evitar ciclos infinitos.
        if response.status_code == 401:
            self._close_upstream_response(response)
            session_token = self._refresh_session(internal, external)
            response = self._send_request(
                method,
                url,
                incoming_request,
                session_token,
                internal,
                external,
            )

        return self._to_flask_response(response)

    def _validate_proxy_configuration(self):
        missing = []
        if not self.api_glpi:
            missing.append("API_GLPI")
        if not self.app_token:
            missing.append("APP_TOKEN")
        if not self.user_token_session:
            missing.append("USER_TOKEN_SESSION")
        if missing:
            raise CustomAPIException(
                "Faltan variables de entorno requeridas: {}".format(", ".join(missing)),
                500,
            )

    def _build_url(self, endpoint):
        endpoint = (endpoint or "").strip()
        parsed_endpoint = urlsplit(endpoint)
        if not endpoint or parsed_endpoint.scheme or parsed_endpoint.netloc:
            raise CustomAPIException("El endpoint de GLPI no es valido", 400)
        if parsed_endpoint.fragment:
            raise CustomAPIException("El endpoint de GLPI no debe contener fragmentos", 400)
        return "{}/{}".format(self.api_glpi, endpoint.lstrip("/"))

    def _refresh_session(self, internal=None, external=None):
        headers = {
            "App-Token": self.app_token,
            "Authorization": "user_token {}".format(self.user_token_session),
        }
        try:
            response = self.http_client.request(
                method="GET",
                url="{}/initSession".format(self.api_glpi),
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exception:
            logger.error(
                "Error al iniciar sesion en GLPI: {}",
                str(exception),
                internal=internal,
                external=external,
            )
            raise CustomAPIException("No fue posible iniciar sesion en GLPI", 502)

        if not 200 <= response.status_code < 300:
            raise CustomAPIException(
                "GLPI rechazo el inicio de sesion con codigo {}".format(
                    response.status_code
                ),
                502,
            )

        try:
            session_token = response.json().get("session_token")
        except (TypeError, ValueError, AttributeError):
            session_token = None
        if not session_token:
            raise CustomAPIException(
                "GLPI no devolvio un session_token valido",
                502,
            )

        self.repository.save_glpi_token_cache(
            session_token,
            internal=internal,
            external=external,
        )
        return session_token

    def _send_request(
        self,
        method,
        url,
        incoming_request,
        session_token,
        internal=None,
        external=None,
    ):
        headers = {
            name: value
            for name, value in incoming_request.headers.items()
            if name.lower() not in self.REQUEST_HEADERS_TO_SKIP
        }
        headers["App-Token"] = self.app_token
        headers["Session-Token"] = session_token

        query_params = []
        for name, values in incoming_request.args.lists():
            if name != "endpoint":
                query_params.extend((name, value) for value in values)

        body = incoming_request.get_data(cache=True)
        try:
            return self.http_client.request(
                method=method,
                url=url,
                headers=headers,
                params=query_params,
                data=body if body else None,
                timeout=self.timeout,
                stream=True,
            )
        except requests.RequestException as exception:
            logger.error(
                "Error al consumir GLPI: {}",
                str(exception),
                internal=internal,
                external=external,
            )
            raise CustomAPIException("No fue posible consumir el endpoint de GLPI", 502)

    def _to_flask_response(self, upstream_response):
        raw_response = getattr(upstream_response, "raw", None)
        if raw_response is not None:
            body = raw_response.read(decode_content=False)
        else:
            body = upstream_response.content

        response = Response(
            body,
            status=upstream_response.status_code,
        )

        for name, values in self._response_header_values(upstream_response):
            if name.lower() not in self.RESPONSE_HEADERS_TO_SKIP:
                response.headers.pop(name, None)
                for value in values:
                    response.headers.add(name, value)

        self._close_upstream_response(upstream_response)
        return response

    @staticmethod
    def _response_header_values(upstream_response):
        """Obtiene todos los valores, incluidos headers repetidos."""
        raw_headers = getattr(getattr(upstream_response, "raw", None), "headers", None)
        if raw_headers is not None and hasattr(raw_headers, "getlist"):
            return [(name, raw_headers.getlist(name)) for name in raw_headers.keys()]
        return [(name, [value]) for name, value in upstream_response.headers.items()]

    @staticmethod
    def _close_upstream_response(upstream_response):
        close = getattr(upstream_response, "close", None)
        if callable(close):
            close()
