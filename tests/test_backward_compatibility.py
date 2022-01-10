import os
import unittest

from neon_mq_connector import MQConnector
from neon_mq_connector.config import Configuration
from neon_mq_connector.connector import ConsumerThread


class OldMQConnectorChild(MQConnector):

    def callback_func_1(self, channel, method, properties, body):
        self.func_1_ok = True
        channel.basic_ack(delivery_tag=method.delivery_tag)

    def __init__(self, config: dict, service_name: str):
        super().__init__(config=config, service_name=service_name)
        self.vhost = '/test'
        self.func_1_ok = False


class TestBackwardCompatibility(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        file_path = os.environ.get('CONNECTOR_CONFIG', "~/.local/share/neon/credentials.json")
        cls.connector = OldMQConnectorChild(config=Configuration(file_path=file_path).config_data,
                                            service_name='test')
        cls.connector.run(run_sync=False)

    def test_stable_register_consumer_args(self):
        try:
            # Required connector.register_consumer() arguments order:
            # name: str, vhost: str, queue: str,
            # callback: callable, on_error: Optional[callable] = None,
            # auto_ack: bool = True
            self.connector.register_consumer("test_consumer",
                                             self.connector.vhost,
                                             'test',
                                             self.connector.callback_func_1,
                                             self.connector.default_error_handler,
                                             False)
            self.assertIsInstance(self.connector.consumers['test_consumer'], ConsumerThread)
            self.assertEqual(self.connector.consumers['test_consumer'].queue, 'test')
            self.assertEqual(self.connector.consumers['test_consumer'].exchange, '')
        except Exception as ex:
            self.fail(f'Registering consumer failed: {ex}')
