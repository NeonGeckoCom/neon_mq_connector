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


import threading
from typing import Optional

import pika.exceptions
from ovos_utils import LOG
from pika.exchange_type import ExchangeType

from neon_mq_connector.utils import consumer_utils


class BlockingConsumerThread(threading.Thread):
    """
    Consumer thread implementation based on pika.BlockingConnection
    """

    # retry to handle connection failures in case MQ server is still starting
    def __init__(self, connection_params: pika.ConnectionParameters,
                 queue: str,
                 callback_func: callable,
                 error_func: callable = consumer_utils.default_error_handler,
                 auto_ack: bool = True,
                 queue_reset: bool = False,
                 queue_exclusive: bool = False,
                 exchange: Optional[str] = None,
                 exchange_reset: bool = False,
                 exchange_type: str = ExchangeType.direct, *args, **kwargs):
        """
        Rabbit MQ Consumer class that aims at providing unified configurable
        interface for consumer threads
        :param connection_params: pika connection parameters
        :param queue: Desired consuming queue
        :param callback_func: logic on message receiving
        :param error_func: handler for consumer thread errors
        :param auto_ack: Boolean to enable ack of messages upon receipt
        :param queue_reset: If True, delete an existing queue `queue`
        :param queue_exclusive: Marks declared queue as exclusive
            to a given channel (deletes with it)
        :param exchange: exchange to bind queue to (optional)
        :param exchange_reset: If True, delete an existing exchange `exchange`
        :param exchange_type: type of exchange to bind to from ExchangeType
            (defaults to direct)
            follow: https://www.rabbitmq.com/tutorials/amqp-concepts.html
            to learn more about different exchanges
        """
        threading.Thread.__init__(self, *args, **kwargs)
        self._consumer_started = threading.Event()  # annotates that ConsumerThread is running
        self._consumer_started.clear()
        self._is_consumer_alive = True  # annotates that ConsumerThread is alive and shall be recreated

        self.callback_func = callback_func
        self.error_func = error_func
        self.auto_ack = auto_ack

        self.exchange = exchange or ''
        self.exchange_type = exchange_type or ExchangeType.direct
        self.exchange_reset = exchange_reset

        self.queue = queue or ''
        self.queue_reset = queue_reset
        self.queue_exclusive = queue_exclusive

        self.connection_params = connection_params
        self.connection = None
        self.channel = None

    @property
    def is_consumer_alive(self) -> bool:
        return self._is_consumer_alive

    @property
    def is_consuming(self) -> bool:
        return self._consumer_started.is_set()

    def run(self):
        """Creating consumer channel"""
        if not self.is_consuming:
            try:
                super(BlockingConsumerThread, self).run()
                self._create_connection()
                self._consumer_started.set()
                self.channel.start_consuming()
            except (pika.exceptions.ChannelClosed,
                    pika.exceptions.ConnectionClosed) as e:
                LOG.info(f"Closed {e.reply_code}: {e.reply_text}")
                if self._is_consumer_alive:
                    self._close_connection()
                    self.error_func(self, e)
            except pika.exceptions.StreamLostError as e:
                if self._is_consumer_alive:
                    self.error_func(self, e)
            except Exception as e:
                if self._is_consumer_alive:
                    self._close_connection()
                self.error_func(self, e)

    def _create_connection(self):
        self.connection = pika.BlockingConnection(self.connection_params)
        self.channel = self.connection.channel()
        self.channel.basic_qos(prefetch_count=50)
        if self.queue_reset:
            self.channel.queue_delete(queue=self.queue)
        declared_queue = self.channel.queue_declare(queue=self.queue,
                                                    auto_delete=False,
                                                    exclusive=self.queue_exclusive)
        if self.exchange:
            if self.exchange_reset:
                self.channel.exchange_delete(exchange=self.exchange)
            self.channel.exchange_declare(exchange=self.exchange,
                                          exchange_type=self.exchange_type,
                                          auto_delete=False)
            self.channel.queue_bind(queue=declared_queue.method.queue,
                                    exchange=self.exchange)
        self.channel.basic_consume(on_message_callback=self.callback_func,
                                   queue=self.queue,
                                   auto_ack=self.auto_ack)

    def join(self, timeout: Optional[float] = None) -> None:
        """Terminating consumer channel"""
        if self._is_consumer_alive:
            self._close_connection()
            super(BlockingConsumerThread, self).join(timeout=timeout)

    def _close_connection(self):
        self._is_consumer_alive = False
        try:
            if self.connection and self.connection.is_open:
                self.connection.close()
        except pika.exceptions.StreamLostError:
            pass
        except Exception as e:
            LOG.exception(f"Failed to close connection due to unexpected exception: {e}")
        self._consumer_started.clear()
