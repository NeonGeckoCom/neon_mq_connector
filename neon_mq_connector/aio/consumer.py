from typing import Optional

import aio_pika

from aio_pika.abc import AbstractIncomingMessage
from aio_pika.exchange import ExchangeType

from neon_mq_connector.utils import consumer_utils


class AsyncConsumer:
    def __init__(
        self,
        connection_params,
        queue,
        callback_func: callable,
        error_func: callable = consumer_utils.default_error_handler,
        auto_ack: bool = True,
        queue_reset: bool = False,
        queue_exclusive: bool = False,
        exchange: Optional[str] = None,
        exchange_reset: bool = False,
        exchange_type: str = ExchangeType.DIRECT.value,
        *args,
        **kwargs,
    ):
        self.channel = None
        self.connection = None
        self.connection_params = connection_params
        self.queue = queue
        self.callback_func = lambda message: self._async_on_message_wrapper(message, callback_func)
        self.error_func = error_func
        self.no_ack = auto_ack
        self.queue_reset = queue_reset
        self.queue_exclusive = queue_exclusive
        self.exchange = exchange or ''
        self.exchange_reset = exchange_reset
        self.exchange_type = exchange_type or ExchangeType.DIRECT.value
        self._is_consuming = False
        self._is_consumer_alive = True

    async def connect(self) -> None:
        """
        Utilises aio-pika as a base interface for establishing async MQ connection
        Upon establishing connection, declares queue and exchange if applicable
        """
        self.connection = await aio_pika.connect_robust(**self.connection_params)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=50)
        if self.queue_reset:
            await self.channel.queue_delete(self.queue)
        self.queue = await self.channel.declare_queue(
            self.queue,
            auto_delete=False,
            exclusive=self.queue_exclusive
        )
        if self.exchange:
            if self.exchange_reset:
                await self.channel.exchange_delete(self.exchange)
            self.exchange = await self.channel.declare_exchange(
                self.exchange,
                self.exchange_type,
                auto_delete=False
            )
            await self.queue.bind(self.exchange)
        await self.queue.consume(self.callback_func, no_ack=self.no_ack)

    @property
    def is_consumer_alive(self) -> bool:
        """
        Flag specifying whether consumer thread is alive
        :return: True if consumer thread is alive, False otherwise
        """
        return self._is_consumer_alive

    async def start(self):
        if not self._is_consuming:
            try:
                await self.connect()
                self._is_consuming = True
            except Exception as e:
                self._is_consuming = False
                self.error_func(self, e)

    async def stop(self):
        if self._is_consumer_alive:
            try:
                await self.queue.cancel()
                await self.channel.close()
                await self.connection.close()
            except Exception as e:
                self.error_func(self, e)
            finally:
                self._is_consuming = False
                self._is_consumer_alive = False

    @classmethod
    async def _async_on_message_wrapper(cls, message: AbstractIncomingMessage, callback: callable):
        """
        Async wrapper to process asynchronous MQ messages
        :param message: `AbstractIncomingMessage` instance
        :param callback: the actual callback function
        :return:
        """
        async with message.process(ignore_processed=True):
            await callback(message)
