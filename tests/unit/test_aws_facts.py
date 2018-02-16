from unittest import TestCase

from lib.aws_facts import get_vpc_facts
from moto import mock_ec2


@mock_ec2
class TestAwsFacts(TestCase):
    def test_check_rt_internet_facing(self):
        pass
