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
import time

from asyncio import Event
from typing import Optional

import pika.exceptions
from ovos_utils import LOG
from pika.channel import Channel
from pika.exchange_type import ExchangeType
from pika.frame import Method

from neon_mq_connector.utils import consumer_utils


class SelectConsumerThread(threading.Thread):
    """
    Consumer thread implementation based on pika.SelectConnection
    """

    def __init__(self,
                 connection_params: pika.ConnectionParameters,
                 queue: str,
                 callback_func: callable,
                 error_func: callable = consumer_utils.default_error_handler,
                 auto_ack: bool = True,
                 queue_reset: bool = False,
                 queue_exclusive: bool = False,
                 exchange: Optional[str] = None,
                 exchange_reset: bool = False,
                 exchange_type: str = ExchangeType.direct,
                 *args, **kwargs):
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
        self._consumer_started = Event()  # annotates that ConsumerThread is running
        self._channel_closed = threading.Event()
        self._is_consumer_alive = True  # annotates that ConsumerThread is alive and shall be recreated
        self._stopping = False
        self.callback_func = callback_func
        self.error_func = error_func
        self.exchange = exchange or ''
        self.exchange_type = exchange_type or ExchangeType.direct
        self.queue = queue or ''
        self.channel = None
        self.queue_exclusive = queue_exclusive
        self.auto_ack = auto_ack

        self.connection_params = connection_params
        self.queue_reset = queue_reset
        self.exchange_reset = exchange_reset

        self.connection: Optional[pika.SelectConnection] = None
        self.connection_failed_attempts = 0
        self.max_connection_failed_attempts = 3

    def create_connection(self) -> pika.SelectConnection:
        return pika.SelectConnection(parameters=self.connection_params,
                                     on_open_callback=self.on_connected,
                                     on_open_error_callback=self.on_connection_fail,
                                     on_close_callback=self.on_close,)

    def on_connected(self, _):
        """Called when we are fully connected to RabbitMQ"""
        self.connection.channel(on_open_callback=self.on_channel_open)

    def on_connection_fail(self, *_, **__):
        """ Called when connection to RabbitMQ fails"""
        self.connection_failed_attempts += 1
        if self.connection_failed_attempts > self.max_connection_failed_attempts:
            LOG.error(f'Failed establish MQ connection after {self.connection_failed_attempts} attempts')
            self.error_func("Connection not established")
            self._close_connection(mark_consumer_as_dead=True)
        else:
            self.reconnect()

    def on_channel_open(self, new_channel: Channel):
        """Called when our channel has opened"""
        new_channel.add_on_close_callback(self.on_channel_close)
        self.channel = new_channel
        if self.queue_reset:
            self.channel.queue_delete(queue=self.queue,
                                      if_unused=True,
                                      callback=self.declare_queue)
        else:
            self.declare_queue()
        self._consumer_started.set()

    def on_channel_close(self, *_, **__):
        LOG.info(f"Channel closed.")
        self._channel_closed.set()

    def declare_queue(self, _unused_frame: Optional[Method] = None):
        return self.channel.queue_declare(queue=self.queue,
                                          exclusive=self.queue_exclusive,
                                          auto_delete=False,
                                          callback=self.on_queue_declared)

    def on_queue_declared(self, _unused_frame: Optional[Method] = None):
        """Called when RabbitMQ has told us our Queue has been declared, frame is the response from RabbitMQ"""
        if self.exchange:
            self.setup_exchange()
        else:
            self.set_qos()

    def setup_exchange(self):
        if self.exchange_reset:
            self.channel.exchange_delete(exchange=self.exchange, callback=self.declare_exchange)
        else:
            self.declare_exchange()

    def declare_exchange(self, _unused_frame: Optional[Method] = None):
        self.channel.exchange_declare(exchange=self.exchange,
                                      exchange_type=self.exchange_type,
                                      auto_delete=False,
                                      callback=self.bind_exchange_to_queue)

    def bind_exchange_to_queue(self, _unused_frame: Optional[Method] = None):
        try:
            self.channel.queue_bind(
                queue=self.queue,
                exchange=self.exchange,
                callback=self.set_qos
            )
        except Exception as e:
            LOG.error(f"Error binding queue '{self.queue}' to exchange '{self.exchange}': {e}")

    def set_qos(self, _unused_frame: Optional[Method] = None):
        self.channel.basic_qos(prefetch_count=50, callback=self.start_consuming)

    def start_consuming(self, _unused_frame: Optional[Method] = None):
        self.channel.basic_consume(queue=self.queue,
                                   on_message_callback=self.on_message,
                                   auto_ack=self.auto_ack)

    def on_message(self, channel, method, properties, body):
        try:
            self.callback_func(channel, method, properties, body)
        except Exception as e:
            self.error_func(self, e)

    def on_close(self, _, e):
        self._consumer_started.clear()
        if isinstance(e, pika.exceptions.ConnectionClosed):
            LOG.info(f"Connection closed normally: {e}")
        else:
            LOG.error(f"Closing MQ connection due to exception: {e}")
        if not self._stopping:
            # Connection was gracefully closed by the server. Try to re-connect
            LOG.info(f"Trying to reconnect after server closed connection")
            self.reconnect()

    @property
    def is_consumer_alive(self) -> bool:
        return self._is_consumer_alive

    @property
    def is_consuming(self) -> bool:
        return self._consumer_started.is_set()

    def run(self):
        """Starting connection io loop """
        if not self.is_consuming:
            try:
                self.connection: pika.SelectConnection = self.create_connection()
                self.connection.ioloop.start()
            except (pika.exceptions.ChannelClosed,
                    pika.exceptions.ConnectionClosed) as e:
                LOG.info(f"Closed {e.reply_code}: {e.reply_text}")
                if not self._stopping:
                    # Connection was unexpectedly closed
                    self._close_connection()
                    self.error_func(self, e)
            except Exception as e:
                LOG.error(f"Failed to start io loop on consumer thread {self.name!r}: {e}")
                self._close_connection()
                self.error_func(self, e)
        else:
            LOG.warning("Consumer already running!")

    def _close_connection(self, mark_consumer_as_dead: bool = True):
        try:
            self._stopping = True
            if self.connection and not (self.connection.is_closed or self.connection.is_closing):
                self.connection.close()
                LOG.info(f"Waiting for channel close")
                if not self._channel_closed.wait(15):
                    raise TimeoutError(f"Timeout waiting for channel close. "
                                       f"is_closed={self.channel.is_closed}")
                LOG.info(f"Channel closed")

                # Wait for the connection to close
                waiter = threading.Event()
                while not self.connection.is_closed:
                    waiter.wait(1)
                LOG.info(f"Connection closed")

            if self.connection:
                self.connection.ioloop.stop()
            # self.connection = None
        except Exception as e:
            LOG.error(f"Failed to close connection for Consumer {self.name!r}: {e}")
        self._is_consuming = False
        self._consumer_started.clear()
        if mark_consumer_as_dead:
            self._is_consumer_alive = False
        else:
            self._stopping = False

    def reconnect(self, wait_interval: int = 5):
        self._close_connection(mark_consumer_as_dead=False)
        # TODO: Find a better way to wait for shutdown/server restart. This will
        #   fail to reconnect if the server isn't back up within `wait_interval`
        time.sleep(wait_interval)
        self.run()

    def join(self, timeout: Optional[float] = None) -> None:
        """Terminating consumer channel"""
        if self.is_consumer_alive:
            self._close_connection(mark_consumer_as_dead=True)
        LOG.info(f"Stopped consumer. Waiting up to {timeout}s for thread to terminate.")
        try:
            super().join(timeout=timeout)
        except Exception as e:
            LOG.exception(e)
