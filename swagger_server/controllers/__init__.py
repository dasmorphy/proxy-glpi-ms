from timeit import default_timer
from swagger_server.utils.transactions.transaction import generate_internal_transaction_id
from flask import g
import connexion


def clear_context(response):
    # Limpiar el contexto de log después de cada request
    end_time = default_timer()
    message = f"{round((end_time - g.start_time) * 1000)} ms"
    """"""

    # Se agregan headers en response
    response.headers['X-Channel'] = g.channel
    response.headers['X-System'] = g.system
    response.headers['X-External-Transaction-Id'] = g.external
    response.headers['X-Internal-Transaction-Id'] = g.internal

    return response


def set_log_context():
    # Establecer
    g.start_time = default_timer()
    g.internal = generate_internal_transaction_id()

    channel = connexion.request.headers.get('X-Channel')
    if channel is None:
        channel = connexion.request.headers.get('X_Channel')
    g.channel = channel
    system = connexion.request.headers.get('X-System')
    if system is None:
        system = connexion.request.headers.get('X_System')
    g.system = system
    external = connexion.request.headers.get('X-External-Transaction-Id')
    if external is None:
        external = connexion.request.headers.get('X_External_Transaction_Id')
    g.external = external
