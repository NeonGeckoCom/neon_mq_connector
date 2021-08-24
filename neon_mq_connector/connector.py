# NEON AI (TM) SOFTWARE, Software Development Kit & Application Development System
#
# Copyright 2008-2021 Neongecko.com Inc. | All Rights Reserved
#
# Notice of License - Duplicating this Notice of License near the start of any file containing
# a derivative of this software is a condition of license for this software.
# Friendly Licensing:
# No charge, open source royalty free use of the Neon AI software source and object is offered for
# educational users, noncommercial enthusiasts, Public Benefit Corporations (and LLCs) and
# Social Purpose Corporations (and LLCs). Developers can contact developers@neon.ai
# For commercial licensing, distribution of derivative works or redistribution please contact licenses@neon.ai
# Distributed on an "AS IS” basis without warranties or conditions of any kind, either express or implied.
# Trademarks of Neongecko: Neon AI(TM), Neon Assist (TM), Neon Communicator(TM), Klat(TM)
# Authors: Guy Daniels, Daniel McKnight, Elon Gasper, Richard Leeds, Kirill Hrymailo
#
# Specialized conversational reconveyance options from Conversation Processing Intelligence Corp.
# US Patents 2008-2021: US7424516, US20140161250, US20140177813, US8638908, US8068604, US8553852, US10530923, US10530924
# China Patent: CN102017585  -  Europe Patent: EU2156652  -  Patents Pending

import uuid
import pika
import pika.exceptions
import threading

from abc import ABC, abstractmethod
from typing import Optional
from neon_utils import LOG
from neon_utils.socket_utils import dict_to_b64

from neon_mq_connector.config import load_neon_mq_config


class ConsumerThread(threading.Thread):
    """Rabbit MQ Consumer class that aims at providing unified configurable interface for consumer threads"""

    def __init__(self, connection_params: pika.ConnectionParameters, queue: str, callback_func: callable,
                 error_func: callable, auto_ack: bool = True, *args, **kwargs):
        """
            :param connection_params: pika connection parameters
            :param queue: Desired consuming queue
            :param callback_func: logic on message receiving
            :param error_func: handler for consumer thread errors
            :param auto_ack: Boolean to enable ack of messages upon receipt
        """
        threading.Thread.__init__(self, *args, **kwargs)
        self.connection = pika.BlockingConnection(connection_params)
        self.callback_func = callback_func
        self.error_func = error_func
        self.queue = queue
        self.channel = self.connection.channel()
        self.channel.basic_qos(prefetch_count=50)
        self.channel.queue_declare(queue=self.queue, auto_delete=False)
        self.channel.basic_consume(on_message_callback=self.callback_func,
                                   queue=self.queue,
                                   auto_ack=auto_ack)

    def run(self):
        """Creating consumer channel"""
        super(ConsumerThread, self).run()
        try:
            self.channel.start_consuming()
        except pika.exceptions.ChannelClosed:
            LOG.debug(f"Channel closed by broker: {self.callback_func}")
        except Exception as e:
            LOG.error(e)
            self.error_func(self, e)

    def join(self, timeout: Optional[float] = ...) -> None:
        """Terminating consumer channel"""
        try:
            self.channel.stop_consuming()
            if self.channel.is_open:
                self.channel.close()
            if self.connection.is_open:
                self.connection.close()
        except Exception as x:
            LOG.error(x)
        finally:
            super(ConsumerThread, self).join()


class MQConnector(ABC):
    """Abstract method for attaching services to MQ cluster"""

    @abstractmethod
    def __init__(self, config: dict, service_name: str):
        """
            :param config: dictionary with current configurations.
                   { "users": {"<service_name>": { "username": "<username>",
                                                   "password": "<password>" },
                     "server": "localhost",
                     "port": 5672
                   }
            :param service_name: name of current service
       """
        self.config = config or load_neon_mq_config()
        if self.config.get("MQ"):
            self.config = self.config["MQ"]
        self._service_id = self.create_unique_id()
        self.service_name = service_name
        self.consumers = dict()

    @property
    def service_id(self):
        return self._service_id

    @property
    def mq_credentials(self):
        """Returns MQ Credentials object based on username and password in configuration"""
        if not self.config:
            raise Exception('Configuration is not set')
        return pika.PlainCredentials(self.config['users'][self.service_name].get('user', 'guest'),
                                     self.config['users'][self.service_name].get('password', 'guest'))

    def get_connection_params(self, vhost, **kwargs) -> pika.ConnectionParameters:
        """
        Gets connection parameters to be used to create an mq connection
        """
        connection_params = pika.ConnectionParameters(host=self.config.get('server', 'localhost'),
                                                      port=int(self.config.get('port', '5672')),
                                                      virtual_host=vhost,
                                                      credentials=self.mq_credentials,
                                                      **kwargs)
        return connection_params

    @staticmethod
    def create_unique_id():
        """Method for generating unique id"""
        return uuid.uuid4().hex

    @classmethod
    def emit_mq_message(cls, connection: pika.BlockingConnection, queue: str, request_data: dict,
                        exchange: Optional[str]) -> str:
        """
            Emits request to the neon api service on the MQ bus

            :param connection: pika connection object
            :param queue: name of the queue to publish in
            :param request_data: dictionary with the request data
            :param exchange: name of the exchange (optional)

            :raises ValueError: invalid request data provided
            :returns message_id: id of the sent message
        """
        if request_data and len(request_data) > 0 and isinstance(request_data, dict):
            message_id = cls.create_unique_id()
            request_data['message_id'] = message_id
            channel = connection.channel()
            channel.basic_publish(exchange=exchange or '',
                                  routing_key=queue,
                                  body=dict_to_b64(request_data),
                                  properties=pika.BasicProperties(expiration='1000'))
            channel.close()
            return message_id
        else:
            raise ValueError(f'Invalid request data provided: {request_data}')

    def create_mq_connection(self, vhost: str = '/', **kwargs):
        """
            Creates MQ Connection on the specified virtual host
            Note: In order to customize behavior, additional parameters can be defined via kwargs.

            :param vhost: address for desired virtual host
            :raises Exception if self.config is not set
        """
        if not self.config:
            raise Exception('Configuration is not set')
        return pika.BlockingConnection(parameters=self.get_connection_params(vhost, **kwargs))

    def register_consumer(self, name: str, vhost: str, queue: str,
                          callback: callable, on_error: Optional[callable] = None,
                          auto_ack: bool = True):
        """
        Registers a consumer for the specified queue. The callback function will handle items in the queue.
        Any raised exceptions will be passed as arguments to on_error.
        :param name: Human readable name of the consumer
        :param vhost: vhost to register on
        :param queue: MQ Queue to read messages from
        :param callback: Method to passed queued messages to
        :param on_error: Optional method to handle any exceptions raised in message handling
        :param auto_ack: Boolean to enable ack of messages upon receipt
        """
        error_handler = on_error or self.default_error_handler
        self.consumers[name] = ConsumerThread(self.get_connection_params(vhost), queue=queue, callback_func=callback,
                                              error_func=error_handler, auto_ack=auto_ack)

    @staticmethod
    def default_error_handler(thread: ConsumerThread, exception: Exception):
        LOG.error(f"{exception} occurred in {thread}")

    def run_consumers(self, names: tuple = (), daemon=True):
        """
            Runs consumer threads based on the name if present (starts all of the declared consumers by default)

            :param names: names of consumers to consider
            :param daemon: to kill consumer threads once main thread is over
        """
        if not names or len(names) == 0:
            names = list(self.consumers)
        for name in names:
            if name in list(self.consumers):
                self.consumers[name].daemon = daemon
                self.consumers[name].start()

    def stop_consumers(self, names: tuple = ()):
        """
            Stops consumer threads based on the name if present (stops all of the declared consumers by default)
        """
        if not names or len(names) == 0:
            names = list(self.consumers)
        for name in names:
            try:
                if name in list(self.consumers):
                    self.consumers[name].join()
            except Exception as e:
                raise ChildProcessError(e)
