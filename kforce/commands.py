import logging
import os
import re
import shutil
import sys
from difflib import unified_diff
from subprocess import getstatusoutput

import yaml
from jinja2 import Template

from . import init_logger
from .pre_steps import (
    ensure_aws_facts,
    ensure_kops_k8s_version_consistency,
    ensure_region,
    ensure_ssh_pair,
    ensure_state_store,
    ensure_tmp_dir_existing_and_empty,
)
from .utils import color_diff

logger = logging.getLogger(__name__)


class UnSupportedCommand(BaseException):
    ...


ENVS = (
    's',  # stage
    'u',  # uat
    'p',  # prod
    'm',  # management
)


class Command(object):

    DIR_ROOT = os.getcwd()
    DIR_TEMPLATE = os.path.join(DIR_ROOT, 'templates')
    DIR_ADDON = os.path.join(DIR_TEMPLATE, 'addons')
    DIR_TMP = os.path.join(DIR_ROOT, 'tmp')

    @property
    def required_paths(self):
        return (
            self.DIR_TEMPLATE,
            self.DIR_ADDON,
            self.current_value_file_path,
            self.cluster_template_path,
        )

    ensure_region = ensure_region
    ensure_kops_k8s_version_consistency = ensure_kops_k8s_version_consistency
    ensure_tmp_dir_existing_and_empty = ensure_tmp_dir_existing_and_empty

    def ensure_dir_and_files(self):
        for p in self.required_paths:
            self._validate_path(p)
            logger.debug('OK, -> %s', p)

    def __init__(self, env, account_name, vpc_id, region='ap-southeast-2', debug=False):
        init_logger(debug=debug)

        logger.debug('%s.__init__: args/kwargs -> %s', self.get_name(), (env, account_name, vpc_id, region, debug))

        if env not in ENVS:
            raise ValueError('env -> `{}` has be in `{}`'.format(env, ENVS))

        self.env = env
        self.account_name = account_name
        self.vpc_id = vpc_id
        self.region = region

        self.cluster_name = '{}-{}.k8s.local'.format(self.account_name, self.env)

        self.state_store_name = '%s-k8s-state-store' % self.account_name  # share same bucket for cluster in same account
        self.state_store_uri = 's3://%s' % self.state_store_name

        self.template_rendered_path = os.path.join(
            self.DIR_ROOT, '__generated__', '{}-{}.yaml'.format(self.account_name, self.env)
        )

        self.current_vars_dir = os.path.join(self.DIR_ROOT, 'vars', self.account_name)
        self.current_value_file_path = os.path.join(self.current_vars_dir, '%s.yaml' % self.env)
        self.cluster_template_path = os.path.join(self.DIR_TEMPLATE, 'cluster.yaml')

    def _run(self, *args, **kwargs):
        self.__pre_run()
        self.run(*args, **kwargs)

    def run(self):
        raise NotImplementedError()

    @classmethod
    def get_name(cls):
        return cls.__name__.lower()

    def __pre_run(self):
        for i in dir(self):
            if not i.startswith('ensure'):
                continue
            f = getattr(self, i)
            if callable(f):
                logger.debug(
                    '__pre_run -> `%s.%s` for command -> `%s`', self.__class__.__name__, f.__name__, self.get_name()
                )
                f()

    def _validate_path(self, p):
        if os.path.isdir(p) or os.path.isfile(p):
            return True
        raise IOError('`{}` has to be an exisitng file or dir'.format(p))

    def _ensure_dir(self, path, force=False):
        if force is True:
            try:
                shutil.rmtree(path)
            except FileNotFoundError:
                ...

        try:
            os.listdir(path)
        except FileNotFoundError:
            os.makedirs(path)

    def _ensure_file(self, path, force=False):
        if force is True:
            try:
                shutil.rmtree(path)
            except FileNotFoundError:
                ...
        if not os.path.isfile(path):
            open(path, 'w').close()

    def _sh(self, cmd):
        cmd = cmd if isinstance(cmd, (list, tuple)) else [cmd]
        cmd = [sub_flag for flag in cmd for sub_flag in flag.split(' ') if sub_flag]
        cmd_str = ' '.join(cmd)
        logger.info(
            '_sh: env -> `%s`, account -> `%s`, \n\tcmd -> `%s`, \n\tcmd_splitted -> %s', self.env, self.account_name,
            cmd, cmd_str
        )
        exitcode, data = getstatusoutput(cmd_str)
        logger.debug('exitcode -> %s, data -> %s', exitcode, data)
        if exitcode != 0:
            raise RuntimeError(data)
        return data

    def _kops_cmd(self, args):
        args = args if isinstance(args, (list, tuple)) else [args]
        required_global_flags = ' --name={name} --state={state} '.format(
            name=self.cluster_name, state=self.state_store_uri
        )
        args.insert(0, shutil.which('kops'))
        args.append(required_global_flags)
        return self._sh(args)

    def _kubectl_cmd(self, args):
        args = args if isinstance(args, (list, tuple)) else [args]
        kubectl = shutil.which('kubectl')

        # ensure current context correct
        use_context_args = [kubectl, 'config', 'use-context', self.cluster_name]
        logger.debug('doing -> %s', ' '.join(use_context_args))
        self._sh(use_context_args)

        if args[0] is not kubectl:
            args.insert(0, kubectl)
        return self._sh(args)


class New(Command):

    DIR_RAW_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'raw_templates')

    @property
    def required_paths(self):
        return (
            self.DIR_TEMPLATE,
            self.DIR_ADDON,
            self.cluster_template_path,
        )

    def __initialize_templates(self, force):
        to_dir = self.DIR_TEMPLATE
        self._ensure_dir(to_dir, force=force)
        file_list = os.listdir(self.DIR_RAW_TEMPLATE)
        if force is False:
            try:
                existing_files = os.listdir(to_dir)
                for f in file_list:
                    assert f in existing_files
                logger.info(
                    'initialize skipped coz all template are there, to reset all templates, run this cmd with `force=True`'
                )
                return
            except AssertionError:
                ...

        # ensure template
        logger.info('copying templates to ->\n\t%s', '\n\t'.join([os.path.join(to_dir, f) for f in file_list]))
        shutil.rmtree(to_dir)
        shutil.copytree(self.DIR_RAW_TEMPLATE, to_dir)

        # ensure addon dir
        self._ensure_dir(self.DIR_ADDON, force=force)

    def __initialize_vars(self, force):
        # ensure vars dir
        self._ensure_dir(self.current_vars_dir, force=force)
        self._ensure_dir(os.path.join(self.current_vars_dir, '%s-addons' % self.env), force=force)
        self._ensure_dir(os.path.join(self.current_vars_dir, '%s-snippets' % self.env), force=force)
        self._ensure_file(os.path.join(self.current_vars_dir, '%s.yaml' % self.env), force=force)

    def run(self, force=False):
        logger.info('%s.run: force -> %s', self.get_name(), force)
        self.__initialize_templates(force=force)
        self.__initialize_vars(force=force)
        self._ensure_dir(os.path.join(self.DIR_ROOT, '__generated__'), force=force)


class Build(Command):

    ensure_aws_facts = ensure_aws_facts

    @property
    def required_paths(self):
        return super().required_paths + (
            self.DIR_TMP,
            self.current_vars_dir,
        )

    def run(self):
        logger.info('%s.run...', self.get_name())

        cmd = 'toolbox template --format-yaml=true '
        cmd += ''.join([' --values ' + f for f in [self.__build_value_file(), self.current_value_file_path]])
        # cmd += ''.join([' --template ' + f for f in self.root_templates_paths])
        cmd += ' --template %s' % self.cluster_template_path
        snippets_path = os.path.join(self.current_vars_dir, self.env + '-snippets')
        try:
            os.listdir(snippets_path)
            cmd += ' --snippets ' + snippets_path
        except FileNotFoundError:
            ...
        data = self._kops_cmd(cmd)
        with open(self.template_rendered_path, 'w') as f:
            f.write('---\n\n')
            f.write(data[data.index('apiVersion'):])

    def __build_value_file(self):
        with open(os.path.join(self.DIR_TEMPLATE, 'values.yaml.j2')) as f:
            value_template = Template(f.read())
        template_rendered = value_template.render(
            env=self.env,
            account_name=self.account_name,
            state_store_name=self.state_store_name,
            vpc_facts=yaml.dump(self.vpc_facts, default_flow_style=False)
        )
        built_value_file_path = os.path.join(self.DIR_TMP, 'values.yaml')
        with open(built_value_file_path, 'w') as f:
            f.write(template_rendered)
        return built_value_file_path


class Diff(Command):

    @property
    def required_paths(self):
        return super().required_paths + (
            self.DIR_TMP,
            self.template_rendered_path,
        )

    def run(self):
        logger.info('%s.run...', self.get_name())

        try:
            self._validate_path(self.template_rendered_path)
        except IOError:
            raise IOError('Before `diff`, please `make build` first!!!')

        with open(self.template_rendered_path) as f:
            template_to_render = f.read()

        current_state = self.__get_current_cluster_state()
        if 'No cluster found' in current_state:
            logger.info('No existing cluster named `%s` found!', self.cluster_name)
            current_state = ''
        diff_result = unified_diff(
            current_state.splitlines(),
            template_to_render.splitlines(),
            fromfile='current_state',
            tofile=self.template_rendered_path
        )
        for line in color_diff(diff_result):
            sys.stdout.write('\n' + line)

    def __get_current_cluster_state(self):
        return self._kops_cmd('get -o yaml')


class Apply(Command):

    ensure_ssh_pair = ensure_ssh_pair
    ensure_state_store = ensure_state_store

    @property
    def required_paths(self):
        return super().required_paths + (self.template_rendered_path, )

    def run(self):
        logger.info('%s.run...', self.get_name())

        cmd = 'replace -f %s  --force' % self.template_rendered_path
        self._kops_cmd(cmd)

        cmd = 'update cluster  --yes'
        self._kops_cmd(cmd)
        logger.info(
            (
                'Changes may require instances to restart: \n\tkops rolling-update cluster --name {name} --state {state}'
                '\nCheck cluster status:\n\tkops validate cluster --name {name} --state {state}'
            ).format(name=self.cluster_name, state=self.state_store_uri)
        )


class Install(Command):
    """"Install Addons via `kubectl`"""

    def run(self):
        logger.info('%s.run...', self.get_name())

        for addon in os.listdir(self.DIR_ADDON):
            addon_path = os.path.join(self.DIR_ADDON, addon)
            cmd = 'apply -f %s' % addon_path
            logger.info('doing -> %s', cmd)
            logger.info(self._kubectl_cmd(cmd))


class CommandFactory(object):

    __enabled_cmds = (
        New,
        Build,
        Diff,
        Apply,
        Install,
    )

    def __register(self, **kwargs):
        for klass in self.__enabled_cmds:
            setattr(self, klass.get_name(), klass(**kwargs)._run)

    def __init__(self, **kwargs):
        self.__register(**kwargs)
