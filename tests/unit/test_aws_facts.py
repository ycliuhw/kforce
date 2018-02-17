import os
from unittest import TestCase

from kforce.aws_facts import get_vpc_facts
from moto import mock_ec2


@mock_ec2
class TestAwsFacts(TestCase):

    def setUp(self):
        ...

    def test_check_rt_internet_facing(self):
        ...
