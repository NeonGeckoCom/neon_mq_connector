# NEON AI (TM) SOFTWARE, Software Development Kit & Application Framework
# All trademark and other rights reserved by their respective owners
# Copyright 2008-2025 Neongecko.com Inc.
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
import inspect

from functools import wraps
from typing import Optional, Type, Callable, Any, Tuple

import pika.channel

from ovos_utils.log import LOG
from pydantic import BaseModel, ValidationError

from neon_mq_connector.utils.network_utils import b64_to_dict


def create_mq_callback(
    callback: Optional[
        Callable[
            [
                pika.channel.Channel,
                pika.spec.Basic.Deliver,
                pika.spec.BasicProperties,
                bytes,
            ],
            Any
        ]
    ] = None,
    *,
    include_callback_props: Tuple[str] = ('body',),
    request_model: Optional[Type[BaseModel]] = None,
):
    """
    Creates MQ callback method by filtering relevant MQ attributes. Use this
    decorator to simplify creation of MQ callbacks.

    Note that the consumer must have `auto_ack=True` specified at registration
    if the decorated function does not accept `channel` and `method` kwargs that
    are required to acknowledge a message.

    :param callback: callable to wrap into this decorator
    :param include_callback_props: tuple of `pika` callback arguments to include (defaults to ('body',))
    :param request_model: pydantic request model to convert received body to
    """

    if callback and callable(callback):  # No arguments passed, used directly
        return create_mq_callback(
            include_callback_props=include_callback_props,
            request_model=request_model,
        )(callback)

    if not include_callback_props:
        include_callback_props = ()

    def wrapper(f):
        def _parse_kwargs(*f_args) -> dict:
            mq_props = ['channel', 'method', 'properties', 'body']
            callback_kwargs = {}

            for idx in range(len(mq_props)):
                if mq_props[idx] in include_callback_props:
                    value = f_args[idx]
                    if idx == 3:
                        if value and isinstance(value, bytes):
                            dict_data = b64_to_dict(value)
                            callback_kwargs['body'] = dict_data
                        elif value and isinstance(value, dict):
                            callback_kwargs['body'] = value
                        else:
                            raise TypeError(f'Invalid body received, expected: '
                                            f'bytes string; got: {type(value)}')
                        if request_model:
                            callback_kwargs['body'] = request_model.model_validate(
                                obj=callback_kwargs['body'],
                            )
                    else:
                        callback_kwargs[mq_props[idx]] = value
            return callback_kwargs

        @wraps(f)
        def wrapped_classmethod(self, *f_args):
            try:
                parsed_request_kwargs = _parse_kwargs(*f_args)
                res = f(self, **parsed_request_kwargs)

                body = parsed_request_kwargs.get('body') or {}
                if isinstance(body, BaseModel):
                    body = body.model_dump()

                routing_key = body.get('routing_key')
                message_id = body.get('message_id')

                if routing_key and res and isinstance(res, dict):
                    res.setdefault("context", {}).setdefault("mq", {}).setdefault("message_id", message_id)
                    self.send_message(
                        request_data=res,
                        vhost=res.pop('vhost', self.vhost),
                        queue=routing_key,
                    )
            except ValidationError as val_err:
                LOG.error(f'Validation error when parsing request data of {f.__name__} failed due to '
                          f'error={val_err}')
                res = None
            except Exception as ex:
                LOG.error(f'Execution of {f.__name__} failed due to '
                          f'exception={ex}')
                res = None
            return res

        @wraps(f)
        def wrapped(*f_args):
            try:
                res = f(**_parse_kwargs(*f_args))
            except ValidationError as val_err:
                LOG.error(f'Validation error when parsing request data of {f.__name__} failed due to '
                          f'error={val_err}')
                res = None
            except Exception as ex:
                LOG.error(f'Execution of {f.__name__} failed due to '
                          f'exception={ex}')
                res = None
            return res

        # Use the appropriate wrapper for a class method vs a function
        signature = inspect.signature(f).parameters
        if 'self' in signature:
            return wrapped_classmethod
        return wrapped

    return wrapper
