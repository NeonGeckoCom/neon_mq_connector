# NEON AI (TM) SOFTWARE, Software Development Kit & Application Framework
# All trademark and other rights reserved by their respective owners
# Copyright 2008-2024 Neongecko.com Inc.
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
from unittest.mock import Mock

import pytest

from unittest import TestCase

from pika.connection import ConnectionParameters
from pika.credentials import PlainCredentials
from pika.exchange_type import ExchangeType

from .fixtures import rmq_instance


@pytest.mark.usefixtures("rmq_instance")
class TestBlockingConsumer(TestCase):

    def test_blocking_consumer_thread(self):
        from neon_mq_connector.consumers.blocking_consumer import BlockingConsumerThread
        connection_params = ConnectionParameters(host='localhost',
                                                 port=self.rmq_instance.port,
                                                 virtual_host="/neon_testing",
                                                 credentials=PlainCredentials(
                                                     "test_user",
                                                     "test_password"))
        queue = "test_q"
        callback = Mock()
        error = Mock()

        # Valid thread
        test_thread = BlockingConsumerThread(connection_params, queue, callback,
                                             error)
        self.assertEqual(test_thread.callback_func, callback)
        self.assertEqual(test_thread.error_func, error)
        self.assertIsInstance(test_thread.auto_ack, bool)
        self.assertIsInstance(test_thread.exchange, str)
        self.assertIsInstance(test_thread.exchange_type, ExchangeType)
        self.assertIsInstance(test_thread.exchange_reset, bool)
        self.assertEqual(test_thread.queue, queue)
        self.assertIsInstance(test_thread.queue_reset, bool)
        self.assertIsInstance(test_thread.queue_exclusive, bool)
        self.assertEqual(test_thread.connection_params, connection_params)

        self.assertTrue(test_thread.is_consumer_alive)
        self.assertFalse(test_thread.is_consuming)

        test_thread.start()
        test_thread._consumer_started.wait(5)
        self.assertTrue(test_thread.is_consuming)
        self.assertTrue(test_thread.channel.is_open)

        test_thread.join(30)
        self.assertFalse(test_thread.is_consuming)
        self.assertTrue(test_thread.channel.is_closed)
        self.assertFalse(test_thread.is_consumer_alive)

        # Invalid thread connection
        connection_params.port = 80
        test_thread = BlockingConsumerThread(connection_params, queue, callback,
                                             error)
        test_thread.start()
        test_thread._consumer_started.wait(5)
        self.assertFalse(test_thread.is_consuming)
        self.assertIsNone(test_thread.channel)

        test_thread.join(30)
        self.assertFalse(test_thread.is_consuming)
        self.assertFalse(test_thread.is_consumer_alive)


@pytest.mark.usefixtures("rmq_instance")
class TestSelectConsumer(TestCase):
    from neon_mq_connector.consumers.select_consumer import SelectConsumerThread
    # TODO
