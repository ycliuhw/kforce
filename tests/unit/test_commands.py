import os
from importlib import import_module
from unittest import TestCase
from unittest.mock import MagicMock, create_autospec

import mockfs
import pytest
from kforce import commands


class TestCommands(TestCase):

    def setUp(self):
        params = dict(env='s', account_name='acc1', vpc_id='vpc-xxxx')
        self.cmd = commands.CommandFactory(**params)

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
        self.mfs = mockfs.replace_builtins()

        params = dict(env='s', account_name='acc1', vpc_id='vpc-xxxx')
        self.c = commands.Command(**params)

        for p in self.c.required_paths:
            self.mfs.add_entries({p: 'magic'})

    def tearDown(self):
        mockfs.restore_builtins()

    def test_env_check(self):
        params = dict(env='this is not a valid env', account_name='acc1', vpc_id='vpc-xxxx')
        with pytest.raises(ValueError):
            commands.Command(**params)

        params = dict(env='s', account_name='acc1', vpc_id='vpc-xxxx')
        assert commands.Command(**params).env == 's'

    def test_pre_run(self):
        params = dict(env='s', account_name='acc1', vpc_id='vpc-xxxx', debug=True)

        def fake_func():
            ...

        c = commands.Command(**params)
        ensure_func_names = [i for i in dir(c) if i.startswith('ensure') and callable(getattr(c, i))]
        for i in ensure_func_names:
            setattr(c, i, create_autospec(fake_func))
        setattr(c, 'run', create_autospec(fake_func))
        c._run()

        getattr(c, 'run').assert_called_once()
        for i in ensure_func_names:
            getattr(c, i).assert_called_once()


class TestNew(TestCase):

    def setUp(self):
        self.cwd = os.getcwd()
        templates = [
            {
                'path': '%s/kforce/raw_templates/cluster.yaml' % self.cwd
            }, {
                'path': '%s/kforce/raw_templates/values.yaml.j2' % self.cwd
            }
        ]
        for t in templates:
            with open(t['path']) as f:
                t['content'] = f.read()

        self.mfs = mockfs.replace_builtins()

        self.mfs.add_entries({t['path']: t['content'] for t in templates})

        self.mfs.add_entries({self.cwd + 'tmp': 'magic'})
        params = dict(env='s', account_name='acc1', vpc_id='vpc-xxxx')
        self.c = commands.New(**params)

        for p in self.c.required_paths + [
            '%s/kforce/raw_templates/cluster.yaml' % self.cwd,
            '%s/kforce/raw_templates/values.yaml.j2' % self.cwd
        ]:
            self.mfs.add_entries({p: 'magic'})

    def tearDown(self):
        mockfs.restore_builtins()

    # def test_all_path_created(self):
    #     # self.c.run()
    #     # files = ['templates/cluster.yaml', 'templates/values.yaml.j2']
    #     # dirs = ['templates/addons']
    #     print(os.listdir(self.cwd))
