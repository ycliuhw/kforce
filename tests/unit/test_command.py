from importlib import import_module
from unittest import TestCase

import pytest
from kforce import commands


class TestCommands(TestCase):

    def setUp(self):
        params = dict(env='s', account_name='acc1', vpc_id='vpc-xxxx')
        self.cmd = commands.Commands(**params)

    def test_register(self):
        cmds = [
            'new',
            'build',
            'diff',
            'apply',
            'install',
        ]
        module = import_module('kforce.commands')
        for c_name in cmds:
            c = getattr(self.cmd, c_name)
            c_raw = getattr(module, c_name.title())
            assert c.__name__ == '_run'
            assert isinstance(c.__self__, c_raw)


class TestCommand(TestCase):

    def setUp(self):
        params = dict(env='s', account_name='acc1', vpc_id='vpc-xxxx')
        self.c = commands.Command(**params)

    def test_env_check(self):
        params = dict(env='this is not a valid env', account_name='acc1', vpc_id='vpc-xxxx')
        with pytest.raises(ValueError):
            commands.Command(**params)

        params = dict(env='s', account_name='acc1', vpc_id='vpc-xxxx')
        assert commands.Command(**params).env == 's'
