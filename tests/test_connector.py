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
import threading
import time
import unittest
import pytest
import pika

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from neon_mq_connector.config import Configuration
from neon_mq_connector.connector import MQConnector, ConsumerThread
from neon_utils import LOG


class MQConnectorChild(MQConnector):

    def callback_func_1(self, channel, method, properties, body):
        if self.func_2_ok:
            self.consume_event.set()
        self.func_1_ok = True
        channel.basic_ack(delivery_tag=method.delivery_tag)

    def callback_func_2(self, channel, method, properties, body):
        if self.func_1_ok:
            self.consume_event.set()
        self.func_2_ok = True
        channel.basic_ack(delivery_tag=method.delivery_tag)

    def callback_func_after_message(self, channel, method, properties, body):
        self.consume_event.set()
        self.callback_ok = True
        channel.basic_ack(delivery_tag=method.delivery_tag)

    def callback_func_error(self, channel, method, properties, body):
        raise Exception("Exception to Handle")

    def handle_error(self, thread: ConsumerThread, exception: Exception):
        self.exception = exception
        self.consume_event.set()

    @property
    def consume_event(self):
        if not self._consume_event or self._consume_event.is_set():
            self._consume_event = threading.Event()
        return self._consume_event

    def __init__(self, config: dict, service_name: str):
        super().__init__(config=config, service_name=service_name)
        self.vhost = '/test'
        self.func_1_ok = False
        self.func_2_ok = False
        self.callback_ok = False
        self.exception = None
        self._consume_event = None
        self.register_consumer(name="error", vhost=self.vhost, queue="error", callback=self.callback_func_error,
                               on_error=self.handle_error, auto_ack=False)


    def run(self, run_consumers: bool = True, run_sync: bool = True, **kwargs):
        super().run(run_consumers=True, run_sync=False, **kwargs)


class MQConnectorChildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        file_path = os.environ.get('CONNECTOR_CONFIG', "~/.local/share/neon/credentials.json")
        cls.connector_instance = MQConnectorChild(config=Configuration(file_path=file_path).config_data,
                                                  service_name='test')
        cls.connector_instance.run()

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.connector_instance.stop()
        except ChildProcessError as e:
            LOG.error(e)

    def test_not_null_service_id(self):
        self.assertIsNotNone(self.connector_instance.service_id)

    @pytest.mark.timeout(30)
    def test_mq_messaging(self):
        self.connector_instance.func_1_ok = False
        self.connector_instance.func_2_ok = False
        test_consumers = ('test1', 'test2',)
        self.connector_instance.stop_consumers(names=test_consumers)
        self.connector_instance.register_consumer(name="test1", vhost=self.connector_instance.vhost,
                                                  exchange='',
                                                  queue='test',
                                                  callback=self.connector_instance.callback_func_1,
                                                  auto_ack=False)
        self.connector_instance.register_consumer(name="test2", vhost=self.connector_instance.vhost,
                                                  exchange='',
                                                  queue='test1',
                                                  callback=self.connector_instance.callback_func_2,
                                                  auto_ack=False)
        self.connector_instance.run_consumers(names=test_consumers)
        with self.connector_instance.create_mq_connection(vhost=self.connector_instance.vhost) as mq_conn:
            self.connector_instance.emit_mq_message(mq_conn,
                                                    queue='test',
                                                    request_data={'data': 'Hello!'},
                                                    exchange='',
                                                    expiration=4000)
            self.connector_instance.emit_mq_message(mq_conn,
                                                    queue='test1',
                                                    request_data={'data': 'Hello 2!'},
                                                    exchange='',
                                                    expiration=4000)

        self.connector_instance.consume_event.wait(5)
        self.assertTrue(self.connector_instance.func_1_ok)
        self.assertTrue(self.connector_instance.func_2_ok)

    @pytest.mark.timeout(30)
    def test_publish_subscribe(self):
        self.connector_instance.func_1_ok = False
        self.connector_instance.func_2_ok = False
        test_consumers = ('test1', 'test2',)
        self.connector_instance.stop_consumers(names=test_consumers)
        self.connector_instance.register_subscriber(name="test1",
                                                    vhost=self.connector_instance.vhost,
                                                    exchange='test',
                                                    callback=self.connector_instance.callback_func_1,
                                                    auto_ack=False)
        self.connector_instance.register_subscriber(name="test2", vhost=self.connector_instance.vhost,
                                                    exchange='test',
                                                    callback=self.connector_instance.callback_func_2,
                                                    auto_ack=False)
        self.connector_instance.run_consumers(names=test_consumers)
        with self.connector_instance.create_mq_connection(vhost=self.connector_instance.vhost) as mq_conn:
            self.connector_instance.publish_message(mq_conn,
                                                    exchange='test',
                                                    request_data={'data': 'Hello!'},
                                                    expiration=4000)
        self.connector_instance.consume_event.wait(5)
        self.assertTrue(self.connector_instance.func_1_ok)
        self.assertTrue(self.connector_instance.func_2_ok)

    @pytest.mark.timeout(30)
    def test_error(self):
        with self.connector_instance.create_mq_connection(vhost=self.connector_instance.vhost) as mq_conn:
            self.connector_instance.emit_mq_message(mq_conn,
                                                    queue='error',
                                                    request_data={'data': 'test'},
                                                    exchange='',
                                                    expiration=4000)
        self.connector_instance.consume_event.wait(5)
        self.assertIsInstance(self.connector_instance.exception, Exception)
        self.assertEqual(str(self.connector_instance.exception), "Exception to Handle")

    def test_consumer_after_message(self):
        with self.connector_instance.create_mq_connection(vhost=self.connector_instance.vhost) as mq_conn:
            self.connector_instance.emit_mq_message(mq_conn,
                                                    queue='test3',
                                                    request_data={'data': 'test'},
                                                    exchange='',
                                                    expiration=3000)

        self.connector_instance.register_consumer("test_consumer_after_message",
                                                  self.connector_instance.vhost, "test3",
                                                  self.connector_instance.callback_func_after_message, auto_ack=False)
        self.connector_instance.run_consumers(("test_consumer_after_message",))
        self.connector_instance.consume_event.wait(5)
        self.assertTrue(self.connector_instance.callback_ok)
