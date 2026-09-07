# coding: utf-8

from __future__ import absolute_import

from flask import json
from six import BytesIO

from swagger_server.models.generic_response import GenericResponse  # noqa: E501
from swagger_server.models.request_post_logbook_entry import RequestPostLogbookEntry  # noqa: E501
from swagger_server.models.response_error import ResponseError  # noqa: E501
from swagger_server.models.response_post_logbook_entry import ResponsePostLogbookEntry  # noqa: E501
from swagger_server.models.response_post_logbook_out import ResponsePostLogbookOut  # noqa: E501
from swagger_server.test import BaseTestCase


class TestGlpiProxyController(BaseTestCase):
    """GlpiProxyController integration test stubs"""

    def test_delete_proxy(self):
        """Test case for delete_proxy

        Metodos delete para apis de glpi
        """
        headers = [('external_transaction_id', 'external_transaction_id_example'),
                   ('channel', 'channel_example')]
        response = self.client.open(
            '/proxy-glpi',
            method='DELETE',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_proxy(self):
        """Test case for get_proxy

        Metodo para cualquier api get del glpi
        """
        headers = [('external_transaction_id', 'external_transaction_id_example'),
                   ('channel', 'channel_example')]
        response = self.client.open(
            '/proxy-glpi',
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_post_proxy(self):
        """Test case for post_proxy

        Metodos post para apis de glpi
        """
        body = RequestPostLogbookEntry()
        response = self.client.open(
            '/proxy-glpi',
            method='POST',
            data=json.dumps(body),
            content_type='application/json')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))


if __name__ == '__main__':
    import unittest
    unittest.main()
