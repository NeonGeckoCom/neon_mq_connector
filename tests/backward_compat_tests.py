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
import unittest

from parameterized import parameterized

from neon_mq_connector import MQConnector
from neon_mq_connector.config import Configuration
from neon_mq_connector.consumers import SelectConsumerThread, BlockingConsumerThread


class OldMQConnectorChild(MQConnector):

    def callback_func_1(self, channel, method, properties, body):
        self.func_1_ok = True
        channel.basic_ack(delivery_tag=method.delivery_tag)

    def __init__(self, config: dict, service_name: str):
        super().__init__(config=config, service_name=service_name)
        self.vhost = '/neon_testing'
        self.func_1_ok = False


class TestBackwardCompatibility(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        file_path = os.path.join(os.path.dirname(__file__), "test_config.json")
        cls.connector = OldMQConnectorChild(config=Configuration(file_path=file_path).config_data,
                                            service_name='test')
        cls.connector.run(run_sync=False)

    @parameterized.expand(
        input=[
            (
                "async_mode_enabled",  # test name
                True,  # async consumer flag
                SelectConsumerThread,  # expected consumer instance
            ),
            (
                "async_mode_disabled",
                False,
                BlockingConsumerThread,
            )
        ]
    )
    def test_stable_register_consumer_args(
        self,
        test_name,
        async_mode_enabled,
        expected_consumer_instance,
    ):
        self.connector.async_consumers_enabled = async_mode_enabled
        # Required connector.register_consumer() arguments order:
        # name: str, vhost: str, queue: str,
        # callback: callable, on_error: Optional[callable] = None,
        # auto_ack: bool = True
        self.connector.register_consumer(
            name="test_consumer",
            vhost=self.connector.vhost,
            queue='test',
            callback=self.connector.callback_func_1,
            on_error=self.connector.default_error_handler,
            auto_ack=False,
        )

        self.assertIsInstance(self.connector.consumers['test_consumer'], expected_consumer_instance)
        self.assertEqual(self.connector.consumers['test_consumer'].queue, 'test')
