#!/usr/bin/env python3
from swagger_server.utils.logs.logging import log
import connexion
from connexion.resolver import MethodViewResolver

from swagger_server.controllers import clear_context, set_log_context
from swagger_server.encoder import JSONEncoder

from swagger_server.models import ResponseError
from connexion.exceptions import ValidationError, ProblemException, BadRequestProblem, NonConformingResponse, \
    UnsupportedMediaTypeProblem, AuthenticationProblem
from flask import request
from flask_cors import CORS

from swagger_server.utils.log import configure_logger

# VARIABLES (CAMBIAR DE PENDIENDO DE CADA MS)
MS_NAME: str = 'proxy-glpi-ms'
MS_PORT: int = 2127
ORIGINS = [] #Origins permitidos en prod
# ------------------------------------------------------------------------
log()


def custom_error_handler(error):
    message = 'Hubo un error en el servidor'
    external_transaction_id = None
    status_code: int = 500

    # Obtenemos el cuerpo de la solicitud almacenado en el middleware
    custom_body = getattr(request, 'custom_body', None)
    if custom_body:
        external_transaction_id = custom_body.get('externalTransactionId', None)

    error_response = ResponseError(
        error_code=-1,
        message=message,
        data=None,
        external_transaction_id=external_transaction_id,
        internal_transaction_id=None
    )
    try:
        detail = getattr(error, 'detail', None)

        if detail is None:
            detail = str(error)

        title = getattr(error, 'title', None)
        status = getattr(error, 'status', status_code)
        # print(type(error))

        status_code = status
        # print(detail, title, status)
        error_response.message = detail
    except:
        error_response.message = message
    finally:
        return JSONEncoder().default(error_response), status_code


def store_request_body():
    """
        Obtiene el body del request, en caso se haya realizado correctamente
    """
    try:
        request.custom_body = request.get_json()
    except Exception as ex:
        pass  # print(str(ex))


def add_handler(flask_app):
    flask_app.add_error_handler(AuthenticationProblem, custom_error_handler)
    flask_app.add_error_handler(UnsupportedMediaTypeProblem, custom_error_handler)
    flask_app.add_error_handler(ProblemException, custom_error_handler)
    flask_app.add_error_handler(BadRequestProblem, custom_error_handler)
    flask_app.add_error_handler(NonConformingResponse, custom_error_handler)
    flask_app.add_error_handler(ValidationError, custom_error_handler)
    flask_app.add_error_handler(AssertionError, custom_error_handler)
    flask_app.add_error_handler(Exception, custom_error_handler)
    flask_app.add_error_handler(400, custom_error_handler)
    flask_app.add_error_handler(500, custom_error_handler)
    return flask_app


def create_app():
    configure_logger()
    # Configurar flask app
    flask_app = connexion.App(__name__, specification_dir='./swagger/', server_args = {'static_folder':'../static'})
    flask_app.app.json_handler = JSONEncoder
    flask_app.add_api('swagger.yaml', arguments={'title': MS_NAME}, pythonic_params=True,
                      resolver=MethodViewResolver("swagger_server.controllers"))
    flask_app.app.json_handler.include_nulls = True

    # Registramos nuestro handler de errores personalizados para las excepciones de validación.
    flask_app = add_handler(flask_app=flask_app)

    # Add CORS origins
    CORS(flask_app.app, resources={r"/*": {"origins": "*"}})

    flask_app.app.before_request(store_request_body)
    flask_app.app.before_request(set_log_context)  # Establecer variables globales y logger
    flask_app.app.after_request(clear_context)  # Limpiar logger luego de la solicitud

    return flask_app


def create_app_test():
    app = create_app()
    return app.app


if __name__ == '__main__':
    app = create_app()
    app.run(port=MS_PORT, debug=False)  # Para hacer debug con el IDE, se debe colocar en "False"

app = create_app().app
