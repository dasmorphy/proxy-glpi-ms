from timeit import default_timer

import connexion
from flask import g
from flask.views import MethodView
from flask import request
from loguru import logger
from werkzeug.datastructures import Headers

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.uses_cases.internal_management_use_case import InternalManagementUseCase
from swagger_server.uses_cases.proxy_use_case import ProxyUseCase
from swagger_server.utils.transactions.transaction import generate_internal_transaction_id


class GlpiProxyView(MethodView):
    WRAPPED_BODY_HEADERS_TO_SKIP = {
        "connection",
        "content-encoding",
        "content-length",
        "content-type",
        "transfer-encoding",
    }

    def __init__(self):
        self.proxy_use_case = ProxyUseCase()
        self.internal_management_use_case = InternalManagementUseCase()

    def _proxy(self, method, endpoint):
        """Ejecuta el proxy y conserva sus headers en la respuesta estandar."""
        internal_process = (None, None)
        response = {}
        status_code = 500
        try:
            start_time = default_timer()
            internal_transaction_id = str(generate_internal_transaction_id())

            external_transaction_id = request.headers.get('externalTransactionId')
            internal_process = (internal_transaction_id, external_transaction_id)
            response["internal_transaction_id"] = internal_transaction_id
            response["external_transaction_id"] = external_transaction_id
            message = f"start request: {method}, channel: {request.headers.get('channel')}"
            logger.info(message, internal=internal_transaction_id, external=external_transaction_id)
            upstream_response = self.proxy_use_case.proxy(
                method=method,
                endpoint=endpoint,
                incoming_request=connexion.request,
                internal=getattr(g, "internal", None),
                external=getattr(g, "external", None),
            )
            response_headers = self._copy_upstream_headers(upstream_response)
            response["error_code"] = 0
            response["data"] = upstream_response.get_json()
            response["message"] = "Datos obtenidos correctamente"
            end_time = default_timer()
            logger.info(f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                        internal=internal_transaction_id, external=request.headers.get('externalTransactionId'))
            status_code = 200
            return response, status_code, response_headers
        except Exception as ex:
            return CustomAPIException.check_exception(ex, method, internal_process)

    def _copy_upstream_headers(self, upstream_response):
        """Copia headers GLPI compatibles con el nuevo cuerpo JSON."""
        headers = Headers()
        for name, value in upstream_response.headers.to_wsgi_list():
            if name.lower() not in self.WRAPPED_BODY_HEADERS_TO_SKIP:
                headers.add(name, value)
        return headers

    def delete_glpi(self, endpoint, **kwargs):
        return self._proxy("DELETE", endpoint)

    def get_glpi(self, endpoint, **kwargs):
        return self._proxy("GET", endpoint)

    def post_glpi(self, endpoint, body=None, **kwargs):
        # El proxy usa los bytes originales para preservar JSON, formularios,
        # multipart y cualquier otro tipo de contenido.
        return self._proxy("POST", endpoint)

    def post_ticket_technical(self, body=None):
        """Guarda el ticket del area tecnica en la base de datos.

        Guardado de ticket # noqa: E501

        :param body: 
        :type body: dict | bytes

        :rtype: ResponseGeneric
        """
        internal_process = (None, None)
        function_name = "post_ticket_technical"
        response = {}
        status_code = 500
        try:
            if connexion.request.is_json:
                body = connexion.request.get_json()  # noqa: E501
                start_time = default_timer()
                internal_transaction_id = str(generate_internal_transaction_id())
                external_transaction_id = body.get("externalTransactionId")
                internal_process = (internal_transaction_id, external_transaction_id)
                response["internal_transaction_id"] = internal_transaction_id
                response["external_transaction_id"] = external_transaction_id
                message = f"start request: {function_name}, channel: {body.get('channel')}"
                logger.info(message, internal=internal_transaction_id, external=external_transaction_id)
                self.internal_management_use_case.post_ticket_technical(body.get('data'), internal_transaction_id, external_transaction_id)
                response["error_code"] = 0
                response["message"] = "Registro creado correctamente"
                end_time = default_timer()
                logger.info(f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                    internal=internal_transaction_id, external=external_transaction_id)
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(ex, function_name, internal_process)
            
        return response, status_code
