import sys
import traceback

from swagger_server.models import ResponseError
from loguru import logger


class CustomAPIException(Exception):

    def __init__(self, message: str, status_code: int = 500, data: dict = None):
        self.status_code = status_code
        self.data = data

        super().__init__(message)

    @staticmethod
    def check_exception(error, function_name: str, internal_process: tuple = None):
        status_code = 500
        response = ResponseError(
            error_code=-1, message='Hubo un error al procesar la petición, por favor notificar al area encargada'
        )
        package_name = None
        try:
            internal = external = None
            msg_error: str = str(error)
            line: int = None
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback_info = traceback.extract_tb(exc_traceback)

            # Retrieve the module or class name where the exception originated
            if traceback_info:
                package_name = traceback_info[-1][0]  # Get the last item in the traceback
                i_package_name: int = package_name.find('-ms\\')
                package_name = package_name[i_package_name + 4 if i_package_name != 0 else None:]
                package_name = package_name.replace('\\', '.').replace('.py', '')
                line = traceback_info[-1][1]
                function_name = traceback_info[-1][2]

            internal, external = internal_process
            response.internal_transaction_id = internal
            response.external_transaction_id = external
            if isinstance(error, CustomAPIException):  # Es un error esperado, para notificar error al cliente
                status_code = error.status_code
                message = str(error)
                if error.data is not None:
                    response.data = error.data
                response.message = message
            else:  # En caso no sea un error custom, se agrega la línea para validar donde ocurrió el error no esperado
                if line:
                    msg_error = f'{msg_error} in line: {line}'

            if logger:
                msg_error = f'{package_name}:{function_name} {msg_error}'
                logger.error('Error: {}', msg_error, internal=internal, external=external)
        except Exception as ex:
            print('check_exception', internal_process, str(error), str(ex))
        
        return response.to_dict(), status_code
