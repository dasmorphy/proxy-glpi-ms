from timeit import default_timer

import connexion
from flask import g
from flask.views import MethodView
from flask import request
from loguru import logger

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.uses_cases.proxy_use_case import ProxyUseCase
from swagger_server.utils.transactions.transaction import generate_internal_transaction_id


class GlpiProxyView(MethodView):
    def __init__(self):
        self.proxy_use_case = ProxyUseCase()

    def _proxy(self, method, endpoint):
        """Guarda la bitacora de ingreso en la base de datos.

        Guardado de bitacora de ingreso # noqa: E501

        :param body: 
        :type body: dict | bytes

        :rtype: ResponsePostLogbookEntry
        """
        internal_process = (None, None)
        response = {}
        status_code = 500
        try:
            # body = request.get_json() 
            start_time = default_timer()
            internal_transaction_id = str(generate_internal_transaction_id())

            external_transaction_id = request.headers.get('externalTransactionId')
            internal_process = (internal_transaction_id, external_transaction_id)
            response["internal_transaction_id"] = internal_transaction_id
            response["external_transaction_id"] = external_transaction_id
            message = f"start request: {method}, channel: {request.headers.get('channel')}"
            logger.info(message, internal=internal_transaction_id, external=external_transaction_id)
            api = self.proxy_use_case.proxy(
                method=method,
                endpoint=endpoint,
                incoming_request=connexion.request,
                internal=getattr(g, "internal", None),
                external=getattr(g, "external", None),
            )
            response["error_code"] = 0
            response["data"] = api.get_json()
            response["message"] = "Datos obtenidos correctamente"
            end_time = default_timer()
            logger.info(f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                        internal=internal_transaction_id, external=request.headers.get('externalTransactionId'))
            status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(ex, method, internal_process)
            
        return response, status_code

    def delete_glpi(self, endpoint, **kwargs):
        return self._proxy("DELETE", endpoint)

    def get_glpi(self, endpoint, **kwargs):
        return self._proxy("GET", endpoint)

    def post_glpi(self, endpoint, body=None, **kwargs):
        # El proxy usa los bytes originales para preservar JSON, formularios,
        # multipart y cualquier otro tipo de contenido.
        return self._proxy("POST", endpoint)
