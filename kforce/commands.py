import logging

from . import init_logger

logger = logging.getLogger(__name__)


class UnSupportedCommand(BaseException):
    ...


class Command(object):

    def run(self, env, account_name, vpc_id, region='ap-southeast-2', debug=False):
        init_logger(debug)

        # logger.info('%s.run: args -> %s, kwargs -> %s', self.__class__.__name__, args, kwargs)
        logger.info('%s.run: args/kwargs -> %s', self.__class__.__name__, (env, account_name, vpc_id, region, debug))

        logger.debug('%s.run: args/kwargs -> %s', self.__class__.__name__, (env, account_name, vpc_id, region, debug))

    @classmethod
    def get_name(cls):
        return cls.__name__.lower()


class Build(Command):
    pass


class Diff(Command):
    pass


class Apply(Command):
    pass


class Install(Command):
    """"Install Addons via `kubectl`"""
    pass


class Commands(object):

    __enabled_cmds = (
        Build,
        Diff,
        Apply,
        Install,
    )

    def __register(self):
        for klass in self.__enabled_cmds:
            setattr(self, klass.get_name(), klass())

    def __init__(self):
        self.__register()
