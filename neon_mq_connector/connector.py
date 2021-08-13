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
import threading

from abc import ABC, abstractmethod
from typing import Optional
from neon_utils import LOG
from neon_utils.socket_utils import dict_to_b64


class ConsumerThread(threading.Thread):
    """Rabbit MQ Consumer class that aims at providing unified configurable interface for consumer threads"""

    def __init__(self, connection: pika.BlockingConnection, queue: str, callback_func: callable, *args, **kwargs):
        """
            :param connection: MQ connection object
            :param queue: Desired consuming queue
            :param callback_func: logic on message receiving
        """
        threading.Thread.__init__(self, *args, **kwargs)
        self.connection = connection
        self.callback_func = callback_func
        self.queue = queue
        self.channel = self.connection.channel()
        self.channel.basic_qos()  # TODO: Add prefetch_count limit and check message ack DM
        self.channel.queue_declare(queue=self.queue, auto_delete=False)
        self.channel.basic_consume(on_message_callback=self.callback_func,
                                   queue=self.queue,
                                   auto_ack=False)

    def run(self):
        """Creating consumer channel"""
        super(ConsumerThread, self).run()
        try:
            self.channel.start_consuming()
        except pika.exceptions.ChannelWrongStateError:
            LOG.error("Channel not open!")
        except pika.exceptions.ChannelClosed:
            pass
        except pika.exceptions.StreamLostError as e:
            LOG.error(f'Consuming error: {e}')
        except Exception as x:
            LOG.error(x)
        LOG.debug(f"Consumer Thread stopped: {self.callback_func}")

    def join(self, timeout: Optional[float] = ...) -> None:
        """Terminating consumer channel"""
        try:
            self.channel.close()
            self.connection.close()
        except pika.exceptions.StreamLostError as e:
            pass
            # LOG.error(f'Consuming error: {e}')
        except Exception as x:
            LOG.error(x)
        finally:
            super(ConsumerThread, self).join()


class MQConnector(ABC):
    """Abstract method for attaching services to MQ cluster"""

    @abstractmethod
    def __init__(self, config: dict, service_name: str):
        """
            :param config: dictionary with current configurations
            :param service_name: name of current service
       """
        self.config = config
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
        return pika.PlainCredentials(self.config['MQ']['users'][self.service_name].get('user', 'guest'),
                                     self.config['MQ']['users'][self.service_name].get('password', 'guest'))

    @staticmethod
    def create_unique_id():
        """Method for generating unique id"""
        return uuid.uuid4().hex

    @classmethod
    def emit_mq_message(cls, connection: pika.BlockingConnection, queue: str, request_data: dict,
                        exchange: Optional[str]) -> int:
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
        connection_params = pika.ConnectionParameters(host=self.config['MQ'].get('server', 'localhost'),
                                                      port=int(self.config['MQ'].get('port', '5672')),
                                                      virtual_host=vhost,
                                                      credentials=self.mq_credentials,
                                                      **kwargs)
        return pika.BlockingConnection(parameters=connection_params)

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
