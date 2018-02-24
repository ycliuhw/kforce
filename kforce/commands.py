import logging
import os

from . import init_logger

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

    def _run(self):
        self.pre_run()
        self.run()

    def run(self):
        raise NotImplementedError()

    @classmethod
    def get_name(cls):
        return cls.__name__.lower()

    def pre_run(self):
        for i in dir(self):
            if not i.startswith('ensure'):
                continue
            f = getattr(self, i)
            if callable(f):
                logger.debug(
                    'pre_run -> `%s.%s` for command -> `%s`', self.__class__.__name__, f.__name__, self.get_name()
                )
                f(self)

    def ensure_DIR_TMP(self, obj):
        print('ensure_DIR_TMP -> ', obj.DIR_TMP)


class Build(Command):

    def run(self):
        logger.info('%s.run...', self.get_name())


class Diff(Command):

    def run(self):
        logger.info('%s.run...', self.get_name())


class Apply(Command):

    def run(self):
        logger.info('%s.run...', self.get_name())


class Install(Command):
    """"Install Addons via `kubectl`"""

    def run(self):
        logger.info('%s.run...', self.get_name())


class Commands(object):

    __enabled_cmds = (
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
