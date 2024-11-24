import asyncio

import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import AbstractIncomingMessage
from ovos_utils import LOG

from neon_mq_connector.utils import consumer_utils


class AsyncConsumer:
    def __init__(self, connection_params, queue, callback_func, *args, **kwargs):
        self.channel = None
        self.connection = None
        self.connection_params = connection_params
        self.queue = queue
        self.callback_func = lambda message: self._async_on_message_wrapper(message, callback_func)
        self.error_func = kwargs.get("error_func", consumer_utils.default_error_handler)
        self.no_ack = not kwargs.get("auto_ack", True)
        self.queue_reset = kwargs.get("queue_reset", False)
        self.queue_exclusive = kwargs.get("queue_exclusive", False)
        self.exchange = kwargs.get("exchange", "")
        self.exchange_reset = kwargs.get("exchange_reset", False)
        self.exchange_type = kwargs.get("exchange_type", ExchangeType.DIRECT.value)
        self._is_consuming = False
        self._is_consumer_alive = True
        self._consumer_stop_event = asyncio.Event()

    async def create_connection(self):
        return await aio_pika.connect_robust(
            host=self.connection_params.host,
            port=self.connection_params.port,
            login=self.connection_params.credentials.username,
            password=self.connection_params.credentials.password,
            virtualhost=self.connection_params.virtual_host,
        )

    async def connect(self):
        try:
            self.connection = await self.create_connection()
            async with self.connection:
                self.channel = await self.connection.channel()
                await self.channel.set_qos(prefetch_count=50)
                if self.queue_reset:
                    await self.channel.queue_delete(self.queue)
                self.queue = await self.channel.get_queue(name=self.queue)
                if self.exchange:
                    if self.exchange_reset:
                        await self.channel.exchange_delete(self.exchange)
                    self.exchange = await self.channel.get_exchange(name=self.exchange)
                    await self.queue.bind(exchange=self.exchange)
                await self.queue.consume(self.callback_func, exclusive=self.queue_exclusive, no_ack=self.no_ack)
        except asyncio.CancelledError:
            LOG.info("Consumer startup cancelled.")
        except Exception as e:
            LOG.error(f"Error during consumer startup: {e}")
            await self.cleanup()
            raise

    async def start(self):
        LOG.info("Starting consumer...")
        while self._is_consumer_alive:
            try:
                await self.connect()
                self._is_consuming = True
                LOG.info("Consumer started successfully.")
                await self._consumer_stop_event.wait()
                break
            except Exception as e:
                self.error_func(self, e)
                LOG.warning("Retrying connection in 5 seconds...")
                await asyncio.sleep(5)
        LOG.info("Consumer shutting down...")
        await self.cleanup()

    async def stop(self):
        LOG.info("Stopping consumer...")
        if self._is_consumer_alive:
            self._consumer_stop_event.set()
            await self.cleanup()
            self._is_consuming = False
            self._is_consumer_alive = False

    async def cleanup(self):
        try:
            if self.channel and not self.channel.is_closed:
                await self.channel.close()
            if self.connection and not self.connection.is_closed:
                await self.connection.close()
        except Exception as e:
            LOG.error(f"Error during cleanup: {e}")

    @classmethod
    async def _async_on_message_wrapper(cls, message: AbstractIncomingMessage, callback: callable):
        async with message.process(ignore_processed=True):
            await callback(message)