from timeit import default_timer
import re
from urllib.parse import parse_qsl, urlsplit

import connexion
from flask import Response, g
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
            response_data = upstream_response.get_json()
            # if method.upper() == "GET" and self._is_ticket_collection_endpoint(endpoint):
                # response_data = self.internal_management_use_case.add_management_area_to_tickets(
                #     response_data,
                #     internal_transaction_id,
                #     external_transaction_id,
                # )
            response["data"] = []
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

    @staticmethod
    def _is_ticket_collection_endpoint(endpoint):
        path = urlsplit(endpoint or "").path.strip("/")
        return path.casefold() == "ticket"

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

    def _update_ticket_management(self, function_name, update_method):
        internal_process = (None, None)
        response = {}
        status_code = 500
        try:
            if connexion.request.is_json:
                body = connexion.request.get_json()
                start_time = default_timer()
                internal_transaction_id = str(generate_internal_transaction_id())
                external_transaction_id = body.get("externalTransactionId")
                internal_process = (internal_transaction_id, external_transaction_id)
                response["internal_transaction_id"] = internal_transaction_id
                response["external_transaction_id"] = external_transaction_id
                logger.info(
                    f"start request: {function_name}, channel: {body.get('channel')}",
                    internal=internal_transaction_id,
                    external=external_transaction_id,
                )
                update_method(
                    body.get("data"),
                    internal_transaction_id,
                    external_transaction_id,
                )
                response["error_code"] = 0
                response["message"] = "Registro actualizado correctamente"
                logger.info(
                    f"Fin de la transacción, procesada en : {default_timer() - start_time} milisegundos",
                    internal=internal_transaction_id,
                    external=external_transaction_id,
                )
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(
                ex,
                function_name,
                internal_process,
            )

        return response, status_code

    def put_ticket_technical(self, body=None):
        return self._update_ticket_management(
            "put_ticket_technical",
            self.internal_management_use_case.update_ticket_technical,
        )

    def get_ticket_technical(self):
        internal_process = (None, None)
        function_name = "get_ticket_technical"
        response = {}
        status_code = 500
        try:
            if connexion.request.headers:
                start_time = default_timer()
                internal_transaction_id = str(generate_internal_transaction_id())
                external_transaction_id = request.headers.get('externalTransactionId')
                internal_process = (internal_transaction_id, external_transaction_id)
                response["internal_transaction_id"] = internal_transaction_id
                response["external_transaction_id"] = external_transaction_id
                message = f"start request: {function_name}, channel: {request.headers.get('channel')}"
                logger.info(message, internal=internal_transaction_id, external=external_transaction_id)
                headers = {k.lower(): v for k, v in request.headers.items()}
                results = self.internal_management_use_case.get_ticket_technical(headers, request.args, internal_transaction_id, external_transaction_id)
                response["error_code"] = 0
                response["message"] = "Datos obtenidos correctamente"
                response["data"] = results
                end_time = default_timer()
                logger.info(f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                            internal=internal_transaction_id, external=external_transaction_id)
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(ex, function_name, internal_process)

        return response, status_code


    def post_ticket_commercial(self, body=None):
        """Guarda el ticket del area comercial en la base de datos."""
        internal_process = (None, None)
        function_name = "post_ticket_commercial"
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
                logger.info(
                    message,
                    internal=internal_transaction_id,
                    external=external_transaction_id,
                )
                self.internal_management_use_case.post_ticket_commercial(
                    body.get('data'),
                    internal_transaction_id,
                    external_transaction_id,
                )
                response["error_code"] = 0
                response["message"] = "Registro creado correctamente"
                end_time = default_timer()
                logger.info(
                    f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                    internal=internal_transaction_id,
                    external=external_transaction_id,
                )
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(
                ex,
                function_name,
                internal_process,
            )

        return response, status_code

    def put_ticket_commercial(self, body=None):
        return self._update_ticket_management(
            "put_ticket_commercial",
            self.internal_management_use_case.update_ticket_commercial,
        )

    def get_ticket_commercial(self):
        internal_process = (None, None)
        function_name = "get_ticket_commercial"
        response = {}
        status_code = 500
        try:
            if connexion.request.headers:
                start_time = default_timer()
                internal_transaction_id = str(generate_internal_transaction_id())
                external_transaction_id = request.headers.get(
                    'externalTransactionId'
                )
                internal_process = (
                    internal_transaction_id,
                    external_transaction_id,
                )
                response["internal_transaction_id"] = internal_transaction_id
                response["external_transaction_id"] = external_transaction_id
                message = (
                    f"start request: {function_name}, "
                    f"channel: {request.headers.get('channel')}"
                )
                logger.info(
                    message,
                    internal=internal_transaction_id,
                    external=external_transaction_id,
                )
                headers = {k.lower(): v for k, v in request.headers.items()}
                results = self.internal_management_use_case.get_ticket_commercial(
                    headers,
                    request.args,
                    internal_transaction_id,
                    external_transaction_id,
                )
                response["error_code"] = 0
                response["message"] = "Datos obtenidos correctamente"
                response["data"] = results
                end_time = default_timer()
                logger.info(
                    f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                    internal=internal_transaction_id,
                    external=external_transaction_id,
                )
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(
                ex,
                function_name,
                internal_process,
            )

        return response, status_code


    def get_type_solution(self):
        internal_process = (None, None)
        function_name = "get_type_solution"
        response = {}
        status_code = 500
        try:
            if connexion.request.headers:
                start_time = default_timer()
                internal_transaction_id = str(generate_internal_transaction_id())
                external_transaction_id = request.headers.get('externalTransactionId')
                internal_process = (internal_transaction_id, external_transaction_id)
                response["internal_transaction_id"] = internal_transaction_id
                response["external_transaction_id"] = external_transaction_id
                message = f"start request: {function_name}, channel: {request.headers.get('channel')}"
                logger.info(message, internal=internal_transaction_id, external=external_transaction_id)
                results = self.internal_management_use_case.get_type_solution(internal_transaction_id, external_transaction_id)
                response["error_code"] = 0
                response["message"] = "Datos obtenidos correctamente"
                response["data"] = results
                end_time = default_timer()
                logger.info(f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                            internal=internal_transaction_id, external=external_transaction_id)
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(ex, function_name, internal_process)

        return response, status_code


    def get_providers(self):
        internal_process = (None, None)
        function_name = "get_providers"
        response = {}
        status_code = 500
        try:
            if connexion.request.headers:
                start_time = default_timer()
                internal_transaction_id = str(generate_internal_transaction_id())
                external_transaction_id = request.headers.get('externalTransactionId')
                internal_process = (internal_transaction_id, external_transaction_id)
                response["internal_transaction_id"] = internal_transaction_id
                response["external_transaction_id"] = external_transaction_id
                message = f"start request: {function_name}, channel: {request.headers.get('channel')}"
                logger.info(message, internal=internal_transaction_id, external=external_transaction_id)
                results = self.internal_management_use_case.get_providers(internal_transaction_id, external_transaction_id)
                response["error_code"] = 0
                response["message"] = "Datos obtenidos correctamente"
                response["data"] = results
                end_time = default_timer()
                logger.info(f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                            internal=internal_transaction_id, external=external_transaction_id)
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(ex, function_name, internal_process)

        return response, status_code


    def get_commercial_ticket_status(self):
        internal_process = (None, None)
        function_name = "get_commercial_ticket_status"
        response = {}
        status_code = 500
        try:
            if connexion.request.headers:
                start_time = default_timer()
                internal_transaction_id = str(generate_internal_transaction_id())
                external_transaction_id = request.headers.get('externalTransactionId')
                internal_process = (internal_transaction_id, external_transaction_id)
                response["internal_transaction_id"] = internal_transaction_id
                response["external_transaction_id"] = external_transaction_id
                message = f"start request: {function_name}, channel: {request.headers.get('channel')}"
                logger.info(message, internal=internal_transaction_id, external=external_transaction_id)
                results = self.internal_management_use_case.get_commercial_ticket_status(internal_transaction_id, external_transaction_id)
                response["error_code"] = 0
                response["message"] = "Datos obtenidos correctamente"
                response["data"] = results
                end_time = default_timer()
                logger.info(f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                            internal=internal_transaction_id, external=external_transaction_id)
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(ex, function_name, internal_process)

        return response, status_code


    def get_commercial_origin(self):
        internal_process = (None, None)
        function_name = "get_commercial_origin"
        response = {}
        status_code = 500
        try:
            if connexion.request.headers:
                start_time = default_timer()
                internal_transaction_id = str(generate_internal_transaction_id())
                external_transaction_id = request.headers.get('externalTransactionId')
                internal_process = (internal_transaction_id, external_transaction_id)
                response["internal_transaction_id"] = internal_transaction_id
                response["external_transaction_id"] = external_transaction_id
                message = f"start request: {function_name}, channel: {request.headers.get('channel')}"
                logger.info(message, internal=internal_transaction_id, external=external_transaction_id)
                results = self.internal_management_use_case.get_commercial_origin(internal_transaction_id, external_transaction_id)
                response["error_code"] = 0
                response["message"] = "Datos obtenidos correctamente"
                response["data"] = results
                end_time = default_timer()
                logger.info(f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                            internal=internal_transaction_id, external=external_transaction_id)
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(ex, function_name, internal_process)

        return response, status_code


    def get_ticket_financial(self):
        internal_process = (None, None)
        function_name = "get_ticket_financial"
        response = {}
        status_code = 500
        try:
            if connexion.request.headers:
                start_time = default_timer()
                internal_transaction_id = str(generate_internal_transaction_id())
                external_transaction_id = request.headers.get('externalTransactionId')
                internal_process = (internal_transaction_id, external_transaction_id)
                response["internal_transaction_id"] = internal_transaction_id
                response["external_transaction_id"] = external_transaction_id
                message = (f"start request: {function_name}, " f"channel: {request.headers.get('channel')}")
                logger.info(message, internal=internal_transaction_id, external=external_transaction_id)
                headers = {k.lower(): v for k, v in request.headers.items()}
                results = self.internal_management_use_case.get_ticket_financial(
                    headers,
                    request.args,
                    internal_transaction_id,
                    external_transaction_id,
                )
                response["error_code"] = 0
                response["message"] = "Datos obtenidos correctamente"
                response["data"] = results
                end_time = default_timer()
                logger.info(f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                    internal=internal_transaction_id,
                    external=external_transaction_id,
                )
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(ex, function_name, internal_process)

        return response, status_code

    def post_ticket_financial(self, body=None):
        """Guarda la gestión del ticket del área financiera."""
        internal_process = (None, None)
        function_name = "post_ticket_financial"
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
                logger.info(
                    message,
                    internal=internal_transaction_id,
                    external=external_transaction_id,
                )
                self.internal_management_use_case.post_ticket_financial(
                    body.get('data'),
                    internal_transaction_id,
                    external_transaction_id,
                )
                response["error_code"] = 0
                response["message"] = "Registro creado correctamente"
                end_time = default_timer()
                logger.info(
                    f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                    internal=internal_transaction_id,
                    external=external_transaction_id,
                )
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(
                ex,
                function_name,
                internal_process,
            )

        return response, status_code

    def put_ticket_financial(self, body=None):
        return self._update_ticket_management(
            "put_ticket_financial",
            self.internal_management_use_case.update_ticket_financial,
        )


    def generate_document_glpi(self, endpoint):
        """Descarga un documento de GLPI sin envolverlo en una respuesta JSON."""
        internal_process = (None, None)
        try:
            document_id = self._validate_document_download_endpoint(endpoint)
            start_time = default_timer()
            internal_transaction_id = str(generate_internal_transaction_id())

            external_transaction_id = request.headers.get('externalTransactionId')
            internal_process = (internal_transaction_id, external_transaction_id)
            message = f"start request: GET, channel: {request.headers.get('channel')}"
            logger.info(message, internal=internal_transaction_id, external=external_transaction_id)
            upstream_response = self.proxy_use_case.proxy(
                method="GET",
                endpoint=endpoint,
                incoming_request=connexion.request,
                internal=getattr(g, "internal", None),
                external=getattr(g, "external", None),
                include_request_query=False,
            )

            # GLPI ya devuelve el binario. Los errores se conservan para que
            # el frontend reciba el codigo original y no un archivo corrupto.
            if not 200 <= upstream_response.status_code < 300:
                return upstream_response

            end_time = default_timer()
            logger.info(
                f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                internal=internal_transaction_id,
                external=external_transaction_id,
            )

            return self._as_download_response(upstream_response, document_id)
        except Exception as ex:
            return CustomAPIException.check_exception(
                ex,
                "generate_document_glpi",
                internal_process,
            )


    def approve_technical_inspection(self, body=None):
        internal_process = (None, None)
        function_name = "approve_technical_inspection"
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
                self.internal_management_use_case.approve_technical_inspection(
                    body.get('data'),
                    internal_transaction_id,
                    external_transaction_id,
                )
                response["error_code"] = 0
                response["message"] = "Inspección aprobada correctamente"
                end_time = default_timer()
                logger.info(f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                    internal=internal_transaction_id, external=external_transaction_id)
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(ex, function_name, internal_process)

        return response, status_code

    def approve_ticket_commercial(self, body=None):
        internal_process = (None, None)
        function_name = "approve_ticket_commercial"
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
                logger.info(message,
                    internal=internal_transaction_id,
                    external=external_transaction_id,
                )
                self.internal_management_use_case.approve_ticket_commercial(
                    body.get('data'),
                    internal_transaction_id,
                    external_transaction_id,
                )
                response["error_code"] = 0
                response["message"] = "Registro creado correctamente"
                end_time = default_timer()
                logger.info(
                    f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                    internal=internal_transaction_id,
                    external=external_transaction_id,
                )
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(
                ex,
                function_name,
                internal_process,
            )

        return response, status_code


    def get_followup_commercial(self):
        internal_process = (None, None)
        function_name = "get_followup_commercial"
        response = {}
        status_code = 500
        try:
            if connexion.request.headers:
                start_time = default_timer()
                internal_transaction_id = str(generate_internal_transaction_id())
                external_transaction_id = request.headers.get('externalTransactionId')
                internal_process = (internal_transaction_id, external_transaction_id)
                response["internal_transaction_id"] = internal_transaction_id
                response["external_transaction_id"] = external_transaction_id
                message = f"start request: {function_name}, channel: {request.headers.get('channel')}"
                logger.info(message, internal=internal_transaction_id, external=external_transaction_id)                
                results = self.internal_management_use_case.get_followup_commercial(request.args, internal_transaction_id, external_transaction_id)
                response["error_code"] = 0
                response["data"] = results
                response["message"] = "Datos obtenidos correctamente"
                end_time = default_timer()
                logger.info(f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                            internal=internal_transaction_id, external=external_transaction_id)
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(ex, function_name, internal_process)
            
        return response, status_code

    def get_inspection_technical(self):
        internal_process = (None, None)
        function_name = "get_inspection_technical"
        response = {}
        status_code = 500
        try:
            if connexion.request.headers:
                start_time = default_timer()
                internal_transaction_id = str(generate_internal_transaction_id())
                external_transaction_id = request.headers.get('externalTransactionId')
                internal_process = (internal_transaction_id, external_transaction_id)
                response["internal_transaction_id"] = internal_transaction_id
                response["external_transaction_id"] = external_transaction_id
                message = f"start request: {function_name}, channel: {request.headers.get('channel')}"
                logger.info(message, internal=internal_transaction_id, external=external_transaction_id)
                headers = {k.lower(): v for k, v in request.headers.items()}
                results = self.internal_management_use_case.get_inspection_technical(headers, request.args, internal_transaction_id, external_transaction_id)
                response["error_code"] = 0
                response["message"] = "Datos obtenidos correctamente"
                response["data"] = results
                end_time = default_timer()
                logger.info(f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                            internal=internal_transaction_id, external=external_transaction_id)
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(ex, function_name, internal_process)

        return response, status_code
    

    def new_followup_commercial(self, body=None):
        internal_process = (None, None)
        function_name = "new_followup_commercial"
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
                logger.info(message,
                    internal=internal_transaction_id,
                    external=external_transaction_id,
                )
                self.internal_management_use_case.new_followup_commercial(
                    body.get('data'),
                    internal_transaction_id,
                    external_transaction_id,
                )
                response["error_code"] = 0
                response["message"] = "Seguimiento creado correctamente"
                end_time = default_timer()
                logger.info(
                    f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                    internal=internal_transaction_id,
                    external=external_transaction_id,
                )
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(
                ex,
                function_name,
                internal_process,
            )

        return response, status_code


    def get_history_area(self, id_inspection):
        internal_process = (None, None)
        function_name = "get_history_area"
        response = {}
        status_code = 500
        try:
            if connexion.request.headers:
                start_time = default_timer()
                internal_transaction_id = str(generate_internal_transaction_id())
                external_transaction_id = request.headers.get('externalTransactionId')
                internal_process = (internal_transaction_id, external_transaction_id)
                response["internal_transaction_id"] = internal_transaction_id
                response["external_transaction_id"] = external_transaction_id
                message = f"start request: {function_name}, channel: {request.headers.get('channel')}"
                logger.info(message, internal=internal_transaction_id, external=external_transaction_id)                
                results = self.internal_management_use_case.get_history_area(id_inspection, internal_transaction_id, external_transaction_id)
                response["error_code"] = 0
                response["data"] = results
                response["message"] = "Datos obtenidos correctamente"
                end_time = default_timer()
                logger.info(f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                            internal=internal_transaction_id, external=external_transaction_id)
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(ex, function_name, internal_process)
            
        return response, status_code


    def get_inspection_materials(self):
        internal_process = (None, None)
        function_name = "get_inspection_materials"
        response = {}
        status_code = 500
        try:
            if connexion.request.headers:
                start_time = default_timer()
                internal_transaction_id = str(generate_internal_transaction_id())
                external_transaction_id = request.headers.get('externalTransactionId')
                internal_process = (internal_transaction_id, external_transaction_id)
                response["internal_transaction_id"] = internal_transaction_id
                response["external_transaction_id"] = external_transaction_id
                message = f"start request: {function_name}, channel: {request.headers.get('channel')}"
                logger.info(message, internal=internal_transaction_id, external=external_transaction_id)
                results = self.internal_management_use_case.get_inspection_materials(request.args, internal_transaction_id, external_transaction_id)
                response["error_code"] = 0
                response["data"] = results
                response["message"] = "Datos obtenidos correctamente"
                end_time = default_timer()
                logger.info(f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                            internal=internal_transaction_id, external=external_transaction_id)
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(ex, function_name, internal_process)

        return response, status_code


    def post_inspection_technical(self, body=None):
        """Guarda la inspeccion tecnica en la base de datos.

        Guardado de inspeccion # noqa: E501

        :param body: 
        :type body: dict | bytes

        :rtype: ResponseGeneric
        """
        internal_process = (None, None)
        function_name = "post_inspection_technical"
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
                self.internal_management_use_case.post_inspection_technical(body.get('data'), internal_transaction_id, external_transaction_id)
                response["error_code"] = 0
                response["message"] = "Registro creado correctamente"
                end_time = default_timer()
                logger.info(f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                    internal=internal_transaction_id, external=external_transaction_id)
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(ex, function_name, internal_process)

        return response, status_code

    def get_dashboard(self):
        internal_process = (None, None)
        function_name = "get_dashboard"
        response = {}
        status_code = 500
        try:
            if connexion.request.headers:
                start_time = default_timer()
                internal_transaction_id = str(generate_internal_transaction_id())
                external_transaction_id = request.headers.get('externalTransactionId')
                internal_process = (internal_transaction_id, external_transaction_id)
                response["internal_transaction_id"] = internal_transaction_id
                response["external_transaction_id"] = external_transaction_id
                message = f"start request: {function_name}, channel: {request.headers.get('channel')}"
                logger.info(message, internal=internal_transaction_id, external=external_transaction_id)
                results = self.internal_management_use_case.get_dashboard(request.args, internal_transaction_id, external_transaction_id)
                response["error_code"] = 0
                response["message"] = "Datos obtenidos correctamente"
                response["data"] = results
                end_time = default_timer()
                logger.info(f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                            internal=internal_transaction_id, external=external_transaction_id)
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(ex, function_name, internal_process)

        return response, status_code

    def get_project_activities(self):
        internal_process = (None, None)
        function_name = "get_project_activities"
        response = {}
        status_code = 500
        try:
            if connexion.request.headers:
                start_time = default_timer()
                internal_transaction_id = str(generate_internal_transaction_id())
                external_transaction_id = request.headers.get('externalTransactionId')
                internal_process = (internal_transaction_id, external_transaction_id)
                response["internal_transaction_id"] = internal_transaction_id
                response["external_transaction_id"] = external_transaction_id
                message = f"start request: {function_name}, channel: {request.headers.get('channel')}"
                logger.info(message, internal=internal_transaction_id, external=external_transaction_id)
                results = self.internal_management_use_case.get_project_activities(internal_transaction_id, external_transaction_id)
                response["error_code"] = 0
                response["message"] = "Datos obtenidos correctamente"
                response["data"] = results
                end_time = default_timer()
                logger.info(f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                            internal=internal_transaction_id, external=external_transaction_id)
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(ex, function_name, internal_process)

        return response, status_code

    def put_inspection_technical(self, id_inspection, body=None):
        internal_process = (None, None)
        function_name = "put_inspection_technical"
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
                self.internal_management_use_case.update_inspection_technical(
                    id_inspection,
                    body.get('data'),
                    internal_transaction_id,
                    external_transaction_id,
                )
                response["error_code"] = 0
                response["message"] = "Registro actualizado correctamente"
                end_time = default_timer()
                logger.info(f"Fin de la transacción, procesada en : {end_time - start_time} milisegundos",
                    internal=internal_transaction_id, external=external_transaction_id)
                status_code = 200
        except Exception as ex:
            response, status_code = CustomAPIException.check_exception(ex, function_name, internal_process)

        return response, status_code


    @staticmethod
    def _validate_document_download_endpoint(endpoint):
        parsed_endpoint = urlsplit((endpoint or "").strip())
        match = re.fullmatch(
            r"Document/(\d+)",
            parsed_endpoint.path.strip("/"),
        )
        query = parse_qsl(parsed_endpoint.query, keep_blank_values=True)
        if (
            parsed_endpoint.scheme
            or parsed_endpoint.netloc
            or parsed_endpoint.fragment
            or match is None
            or query != [("alt", "media")]
        ):
            raise CustomAPIException(
                "El endpoint debe tener el formato Document/{id}?alt=media",
                400,
            )
        return match.group(1)

    @staticmethod
    def _as_download_response(upstream_response, document_id):
        response = Response(
            upstream_response.get_data(),
            status=upstream_response.status_code,
            content_type=upstream_response.headers.get(
                "Content-Type",
                "application/octet-stream",
            ),
        )
        for header_name in ("Cache-Control", "ETag", "Last-Modified"):
            if header_name in upstream_response.headers:
                response.headers[header_name] = upstream_response.headers[header_name]

        disposition = upstream_response.headers.get("Content-Disposition", "")
        if disposition.lower().startswith("inline"):
            disposition = "attachment" + disposition[6:]
        if not disposition.lower().startswith("attachment"):
            disposition = f'attachment; filename="document-{document_id}"'
        response.headers["Content-Disposition"] = disposition
        return response
