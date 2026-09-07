import uuid


def generate_internal_transaction_id():
    """Script para generar el id de la transacción del microservicio (UUID objects according to RFC 4122)

    Returns:
        string: id interno de la transacción
    """
    return uuid.uuid4()


class Transaction:

    def __init__(self):
        self._channel = None
        self._id_external_transaction = None
        self._id_internal_transaction = uuid.uuid4().__str__()

    @property
    def id_external_transaction(self) -> str:
        return self._id_external_transaction

    @property
    def channel(self) -> str:
        return self._channel

    @property
    def id_internal_transaction(self) -> str:
        return self._id_internal_transaction

    @id_external_transaction.setter
    def id_external_transaction(self, value: str) -> None:
        self._id_external_transaction = value

    @channel.setter
    def channel(self, value: str) -> None:
        self._channel = value
