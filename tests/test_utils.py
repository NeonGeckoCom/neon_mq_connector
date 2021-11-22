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

import os
import sys
import time
import unittest
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from neon_mq_connector.utils import RepeatingTimer
from neon_mq_connector.utils.connection_utils import get_timeout, retry, wait_for_mq_startup


def callback_on_failure():
    """Simple callback on failure"""
    return False


class TestMQConnectorUtils(unittest.TestCase):

    counter = 0

    def repeating_method(self):
        """Simple method incrementing counter by one"""
        self.counter += 1

    @retry(num_retries=3, backoff_factor=0.1, callback_on_exceeded=callback_on_failure, use_self=True)
    def method_passing_on_nth_attempt(self, num_attempts: int = 3) -> bool:
        """
            Simple method that is passing check only after n-th attempt
            :param num_attempts: number of attempts before passing
        """
        if self.counter < num_attempts-1:
            self.repeating_method()
            raise AssertionError('Awaiting counter equal to 3')
        return True

    def test_01_get_timeout(self):
        """Tests of getting timeout with backoff factor applied"""
        __backoff_factor, __number_of_retries = 0.1, 1
        timeout = get_timeout(__backoff_factor, __number_of_retries)
        self.assertEqual(timeout, 0.1)
        __number_of_retries += 1
        timeout = get_timeout(__backoff_factor, __number_of_retries)
        self.assertEqual(timeout, 0.2)
        __number_of_retries += 1
        timeout = get_timeout(__backoff_factor, __number_of_retries)
        self.assertEqual(timeout, 0.4)

    def test_02_retry_succeed(self):
        """Testing retry decorator"""
        outcome = self.method_passing_on_nth_attempt(num_attempts=3)
        self.assertTrue(outcome)
        self.assertEqual(2, self.counter)

    def test_03_retry_failed(self):
        """Testing retry decorator"""
        outcome = self.method_passing_on_nth_attempt(num_attempts=4)
        self.assertFalse(outcome)
        self.assertEqual(3, self.counter)

    def test_repeating_timer(self):
        """Testing repeating timer thread"""
        interval_timeout = 3
        timer_thread = RepeatingTimer(interval=0.9, function=self.repeating_method)
        timer_thread.start()
        time.sleep(interval_timeout)
        timer_thread.cancel()
        self.assertEqual(self.counter, 3)

    def test_wait_for_mq_startup(self):
        self.assertTrue(wait_for_mq_startup("api.neon.ai", 5672))
        self.assertFalse(wait_for_mq_startup("api.neon.ai", 443, 1))

    def setUp(self) -> None:
        self.counter = 0
