import threading
from typing import Optional

import pika.exceptions
from ovos_utils import LOG
from pika.exchange_type import ExchangeType

from neon_mq_connector.utils import consumer_utils


class ConsumerThread(threading.Thread):

    # retry to handle connection failures in case MQ server is still starting
    def __init__(self,
                 connection_params: pika.ConnectionParameters,
                 queue: str, callback_func: callable,
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
        self._is_consuming = False  # annotates that ConsumerThread is running
        self._is_consumer_alive = True  # annotates that ConsumerThread is alive and shall be recreated
        self.connection = pika.BlockingConnection(connection_params)
        self.callback_func = callback_func
        self.error_func = error_func
        self.exchange = exchange or ''
        self.exchange_type = exchange_type or ExchangeType.direct
        self.queue = queue or ''
        self.channel = self.connection.channel()
        self.channel.basic_qos(prefetch_count=50)
        if queue_reset:
            self.channel.queue_delete(queue=self.queue)
        declared_queue = self.channel.queue_declare(queue=self.queue,
                                                    auto_delete=False,
                                                    exclusive=queue_exclusive)
        if self.exchange:
            if exchange_reset:
                self.channel.exchange_delete(exchange=self.exchange)
            self.channel.exchange_declare(exchange=self.exchange,
                                          exchange_type=self.exchange_type,
                                          auto_delete=False)
            self.channel.queue_bind(queue=declared_queue.method.queue,
                                    exchange=self.exchange)
        self.channel.basic_consume(on_message_callback=self.callback_func,
                                   queue=self.queue,
                                   auto_ack=auto_ack)

    @property
    def is_consumer_alive(self) -> bool:
        return self._is_consumer_alive

    @property
    def is_consuming(self) -> bool:
        return self._is_consuming

    def run(self):
        """Creating consumer channel"""
        if not self._is_consuming:
            try:
                super(ConsumerThread, self).run()
                self._is_consuming = True
                self.channel.start_consuming()
            except Exception as e:
                self._is_consuming = False
                if isinstance(e, pika.exceptions.ChannelClosed):
                    LOG.error(f"Channel closed by broker: {self.callback_func}")
                else:
                    LOG.error(e)
                    self.error_func(self, e)
                self.join(allow_restart=True)

    def join(self, timeout: Optional[float] = ..., allow_restart: bool = True) -> None:
        """Terminating consumer channel"""
        if self._is_consumer_alive:
            try:
                self.channel.stop_consuming()
                if self.channel.is_open:
                    self.channel.close()
                if self.connection.is_open:
                    self.connection.close()
            except Exception as x:
                LOG.error(x)
            finally:
                self._is_consuming = False
                if not allow_restart:
                    self._is_consumer_alive = False
                super(ConsumerThread, self).join(timeout=timeout)
