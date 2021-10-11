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
import time
from typing import Union, Callable

from neon_utils import LOG


def get_timeout(backoff_factor: float, number_of_retries: int) -> float:
    """
        Gets timeout based on backoff_factor

        :param backoff_factor: value of backoff factor
        :param number_of_retries: current number of retries made

        Examples:
            >>> __backoff_factor, __number_of_retries = 0.1, 1
            >>> timeout = get_timeout(__backoff_factor, __number_of_retries)
            >>> assert timeout == 0.1
            >>>
            >>> __backoff_factor, __number_of_retries = 0.1, 2
            >>> timeout = get_timeout(__backoff_factor, __number_of_retries)
            >>> assert timeout == 0.2
    """
    return backoff_factor * (2 ** (number_of_retries - 1))


def retry(callback_on_exceeded: Union[str, Callable] = None, callback_on_attempt_failure: Union[str, Callable] = None,
          num_retries: int = 3, backoff_factor: int = 5, use_self: bool = False,
          callback_on_attempt_failure_args: list = None, callback_on_exceeded_args: list = None):
    """
        Decorator for generic retrying function execution

        :param use_self: to call a function from current class instance (defaults to False)
        :param num_retries: num of retries for function execution
        :param callback_on_exceeded: function to call when all attempts fail (is s
        :param callback_on_exceeded_args: args for :param callback_on_exceeded
        :param callback_on_attempt_failure: function to call when single attempt fails
        :param callback_on_attempt_failure_args: args for :param callback_on_attempt_failure
        :param backoff_factor: value of backoff factor for setting delay between function execution retry,
                               refer to "get_timeout()" for details
    """
    # TODO: given function shows non-thread-safe behaviour for Consumer Thread, need to fix this before using
    if not callback_on_attempt_failure_args:
        callback_on_attempt_failure_args = []
    if not callback_on_exceeded_args:
        callback_on_exceeded_args = []

    def decorator(function):
        def wrapper(self, *args, **kwargs):
            with_self = use_self and self
            num_attempts = 0
            while num_attempts < num_retries:
                LOG.info(f'Retrying {function} execution. Attempt #{num_attempts}')
                try:
                    if with_self:
                        return function(self, *args, **kwargs)
                    else:
                        return function(*args, **kwargs)
                except Exception as e:
                    for i in range(len(callback_on_attempt_failure_args)):
                        if callback_on_attempt_failure_args[i] == 'e':
                            callback_on_attempt_failure_args[i] = e
                        elif callback_on_attempt_failure_args[i] == 'self':
                            callback_on_attempt_failure_args[i] = self
                    if callback_on_attempt_failure:
                        if with_self and isinstance(callback_on_attempt_failure, str):
                            getattr(self, callback_on_attempt_failure)(*callback_on_attempt_failure_args)
                        elif isinstance(callback_on_attempt_failure, Callable):
                            callback_on_attempt_failure(*callback_on_attempt_failure_args)
                    sleep_timeout = get_timeout(backoff_factor=backoff_factor, number_of_retries=num_attempts)
                    LOG.error(f'{function} execution failed due to exception: {e}. Timeout for {sleep_timeout} secs')
                    num_attempts += 1
                    time.sleep(sleep_timeout)
            LOG.error(f'Failed to execute function after {num_retries} attempts')
            if callback_on_exceeded:
                if with_self and isinstance(callback_on_exceeded, str):
                    return getattr(self, callback_on_exceeded)(*callback_on_exceeded_args)
                elif isinstance(callback_on_exceeded, Callable):
                    return callback_on_exceeded(*callback_on_exceeded_args)
        return wrapper
    return decorator

