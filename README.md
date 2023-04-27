# Neon MQ Connector
The Neon MQ Connector is an MQ interface for microservices.

## Configuration
By default, this package will use [ovos-config](https://github.com/openvoiceos/ovos-config)
to read default configuration. In general, configuration should be passed to the
`MQConnector` object at init.

### Legacy Configuration
A global configuration for the MQ Connector may be specified at `~/.config/neon/mq_config.json`. This configuration file 
may contain the following keys:
 - `server`: The hostname or IP address of the MQ server to connect to. If left blank, this defaults to `"localhost"`
 - `port`: The port used by the MQ server. If left blank, this defaults to `5672`
 - `users`: A mapping of service names to credentials. Note that not all users will have permissions required to access each service.

```json
{
  "server": "localhost",
  "port": 5672,
  "users": {
    "<service_name>": {
      "username": "<username>",
      "password": "<password>"
    }
  }
}
```

## Services
The `MQConnector` class should be extended by a class providing some specific service.
Service classes will specify the following parameters.
 - `service_name`: Name of the service, used to identify credentials in configuration
 - `vhost`: Virtual host to connect to; messages are all constrained to this namespace.
 - `consumers`: Dict of names to `ConsumerThread` objects. A `ConsumerThread` will accept a connection to a particular `connection`, a `queue`, and a `callback_func`
   - `connection`: MQ connection to the `vhost` specified above.
   - `queue`: Queue to monitor within the `vhost`. A `vhost` may handle multiple queues.
   - `callback_func`: Function to call when a message arrives in the `queue`

### Callback Functions
A callback function should have the following signature:
```python
def handle_api_input(self,
                     channel: pika.channel.Channel,
                     method: pika.spec.Basic.Return,
                     properties: pika.spec.BasicProperties,
                     body: bytes):
    """
        Handles input requests from MQ to Neon API

        :param channel: MQ channel object (pika.channel.Channel)
        :param method: MQ return method (pika.spec.Basic.Return)
        :param properties: MQ properties (pika.spec.BasicProperties)
        :param body: request body (bytes)
    """
```
Generally, `body` should be decoded into a `dict`, and that `dict` should contain `message_id`. The `message_id` should 
be included in the body of any response to associate the response to the request.
A response may be sent via:
```python
 channel.queue_declare(queue='<queue>')

 channel.basic_publish(exchange='',
                       routing_key='<queue>',
                       body=<data>,
                       properties=pika.BasicProperties(expiration='1000')
                       )
```
Where `<queue>` is the queue to which the response will be published, and `data` is a `bytes` response (generally a `base64`-encoded `dict`).
