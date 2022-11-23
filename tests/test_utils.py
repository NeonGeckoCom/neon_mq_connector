# NEON AI (TM) SOFTWARE, Software Development Kit & Application Framework
# All trademark and other rights reserved by their respective owners
# Copyright 2008-2022 Neongecko.com Inc.
# Contributors: Daniel McKnight, Guy Daniels, Elon Gasper, Richard Leeds,
# Regina Bloomstine, Casimiro Ferreira, Andrii Pernatii, Kirill Hrymailo
# BSD-3 License
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from this
#    software without specific prior written permission.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS  BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
# OR PROFITS;  OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE,  EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import os
import sys
import time
import unittest
import pika

from threading import Thread
from neon_utils.socket_utils import dict_to_b64, b64_to_dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from neon_mq_connector.utils import RepeatingTimer
from neon_mq_connector.utils.connection_utils import get_timeout, retry, wait_for_mq_startup
from neon_mq_connector.utils.client_utils import MQConnector

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
TEST_PATH = os.path.join(ROOT_DIR, "tests", "ccl_files")

INPUT_CHANNEL = str(time.time())
OUTPUT_CHANNEL = str(time.time())


def callback_on_failure():
    """Simple callback on failure"""
    return False


class TestMQConnector(MQConnector):
    def __init__(self, config: dict, service_name: str, vhost: str):
        super().__init__(config, service_name)
        self.vhost = vhost

    @staticmethod
    def respond(channel, method, _, body):
        request = b64_to_dict(body)
        response = dict_to_b64({"message_id": request["message_id"],
                                "success": True,
                                "request_data": request["data"]})
        reply_channel = request.get("routing_key") or OUTPUT_CHANNEL
        channel.queue_declare(queue=reply_channel)
        channel.basic_publish(exchange='',
                              routing_key=reply_channel,
                              body=response,
                              properties=pika.BasicProperties(expiration='1000'))
        channel.basic_ack(delivery_tag=method.delivery_tag)


class TestMQConnectorUtils(unittest.TestCase):

    counter = 0

    def repeating_method(self):
        """Simple method incrementing counter by one"""
        self.counter += 1

    @retry(num_retries=3, backoff_factor=0.1,
           callback_on_exceeded=callback_on_failure, use_self=True)
    def method_passing_on_nth_attempt(self, num_attempts: int = 3) -> bool:
        """
            Simple method that is passing check only after n-th attempt
            :param num_attempts: number of attempts before passing
        """
        if self.counter < num_attempts-1:
            self.repeating_method()
            raise AssertionError('Awaiting counter equal to 3')
        return True

    def test_01_get_timeout(self):
        """Tests of getting timeout with backoff factor applied"""
        __backoff_factor, __number_of_retries = 0.1, 1
        timeout = get_timeout(__backoff_factor, __number_of_retries)
        self.assertEqual(timeout, 0.1)
        __number_of_retries += 1
        timeout = get_timeout(__backoff_factor, __number_of_retries)
        self.assertEqual(timeout, 0.2)
        __number_of_retries += 1
        timeout = get_timeout(__backoff_factor, __number_of_retries)
        self.assertEqual(timeout, 0.4)

    def test_02_retry_succeed(self):
        """Testing retry decorator"""
        outcome = self.method_passing_on_nth_attempt(num_attempts=3)
        self.assertTrue(outcome)
        self.assertEqual(2, self.counter)

    def test_03_retry_failed(self):
        """Testing retry decorator"""
        outcome = self.method_passing_on_nth_attempt(num_attempts=4)
        self.assertFalse(outcome)
        self.assertEqual(3, self.counter)

    def test_repeating_timer(self):
        """Testing repeating timer thread"""
        interval_timeout = 3
        timer_thread = RepeatingTimer(interval=0.9,
                                      function=self.repeating_method)
        timer_thread.start()
        time.sleep(interval_timeout)
        timer_thread.cancel()
        self.assertEqual(self.counter, 3)

    def test_wait_for_mq_startup(self):
        self.assertTrue(wait_for_mq_startup("api.neon.ai", 5672))
        self.assertFalse(wait_for_mq_startup("www.neon.ai", 5672, 1))

    def setUp(self) -> None:
        self.counter = 0


class MqUtilTests(unittest.TestCase):
    test_connector = None

    @classmethod
    def setUpClass(cls) -> None:
        from neon_mq_connector.utils.client_utils import _default_mq_config
        vhost = "/neon_testing"
        cls.test_connector = TestMQConnector(config=_default_mq_config,
                                             service_name="mq_handler",
                                             vhost=vhost)
        cls.test_connector.register_consumer("neon_utils_test", vhost,
                                             INPUT_CHANNEL,
                                             cls.test_connector.respond,
                                             auto_ack=False)
        cls.test_connector.run_consumers()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.test_connector.stop_consumers()

    def test_send_mq_request_valid(self):
        from neon_mq_connector.utils.client_utils import send_mq_request
        request = {"data": time.time()}
        response = send_mq_request("/neon_testing", request, INPUT_CHANNEL)
        self.assertIsInstance(response, dict)
        self.assertTrue(response["success"])
        self.assertEqual(response["request_data"], request["data"])

    def test_send_mq_request_spec_output_channel_valid(self):
        from neon_mq_connector.utils.client_utils import send_mq_request
        request = {"data": time.time()}
        response = send_mq_request("/neon_testing", request,
                                   INPUT_CHANNEL, OUTPUT_CHANNEL)
        self.assertIsInstance(response, dict)
        self.assertTrue(response["success"])
        self.assertEqual(response["request_data"], request["data"])

    def test_multiple_mq_requests(self):
        from neon_mq_connector.utils.client_utils import send_mq_request
        responses = dict()
        processes = []

        def check_response(name: str):
            request = {"data": time.time()}
            response = send_mq_request("/neon_testing", request, INPUT_CHANNEL)
            self.assertIsInstance(response, dict)
            if not isinstance(response, dict):
                responses[name] = {'success': False,
                                   'reason': 'Response is not a dict',
                                   'response': response}
                return
            if not response.get("success"):
                responses[name] = {'success': False,
                                   'reason': 'Response success flag not true',
                                   'response': response}
                return
            if response.get("request_data") != request["data"]:
                responses[name] = {'success': False,
                                   'reason': "Response data doesn't match request",
                                   'response': response}
                return
            responses[name] = {'success': True}

        for i in range(8):
            p = Thread(target=check_response, args=(str(i),))
            p.start()
            processes.append(p)

        for p in processes:
            p.join(60)

        self.assertEqual(len(processes), len(responses))
        for resp in responses.values():
            self.assertTrue(resp['success'], resp.get('reason'))

    def test_send_mq_request_invalid_vhost(self):
        from neon_mq_connector.utils.client_utils import send_mq_request
        with self.assertRaises(ValueError):
            send_mq_request("invalid_endpoint", {}, "test", "test", timeout=5)
