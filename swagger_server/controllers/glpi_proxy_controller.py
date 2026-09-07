from asyncio.log import logger

import connexion
from flask.views import MethodView
import six

from swagger_server.models.generic_response import GenericResponse  # noqa: E501
from swagger_server.models.request_post_logbook_entry import RequestPostLogbookEntry  # noqa: E501
from swagger_server.models.response_error import ResponseError  # noqa: E501
from swagger_server.models.response_post_logbook_entry import ResponsePostLogbookEntry  # noqa: E501
from swagger_server.models.response_post_logbook_out import ResponsePostLogbookOut  # noqa: E501
from swagger_server import util


class GlpiProxyView(MethodView):
    def __init__(self):
        self.logger = logger
        

    def delete_glpi(external_transaction_id, channel):  # noqa: E501
        """Metodos delete para apis de glpi

        Realiza delete para todas las apis del glpi # noqa: E501

        :param external_transaction_id: 
        :type external_transaction_id: str
        :param channel: 
        :type channel: str

        :rtype: ResponsePostLogbookOut
        """
        return 'do some magic!'


    def get_glpi(external_transaction_id, channel):  # noqa: E501
        """Metodo para cualquier api get del glpi

        Realiza consultas para todas las api get del glpi # noqa: E501

        :param external_transaction_id: 
        :type external_transaction_id: str
        :param channel: 
        :type channel: str

        :rtype: GenericResponse
        """
        return 'do some magic!'


    def post_glpi(body=None):  # noqa: E501
        """Metodos post para apis de glpi

        Realiza post para todas las apis del glpi # noqa: E501

        :param body: 
        :type body: dict | bytes

        :rtype: ResponsePostLogbookEntry
        """
        if connexion.request.is_json:
            body = RequestPostLogbookEntry.from_dict(connexion.request.get_json())  # noqa: E501
        return 'do some magic!'
