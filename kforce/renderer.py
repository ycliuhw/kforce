import logging
import os
import re
import shutil
import sys
from base64 import urlsafe_b64encode
from difflib import unified_diff
from pprint import pformat
from subprocess import getstatusoutput

import boto3
import yaml
from botocore.errorfactory import ClientError
from jinja2 import Template

from .aws_facts import get_vpc_facts
from .utils import color_diff

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)
BOTO_LOGGER_NAME = 'botocore'
logging.getLogger(BOTO_LOGGER_NAME).setLevel(logging.CRITICAL)  # boto logging is annony and too verbose

CWD = os.getcwd()
TEMPLATE_DIR = os.path.join(CWD, 'templates')
ADDON_DIR = os.path.join(TEMPLATE_DIR, 'addons')

ENVS = (
    's',  # stage
    'u',  # uat
    'p',  # prod
    'm',  # management
)


class KopsRenderer(object):

    vpc_facts = None

    def __init__(self, env, account_name, vpc_id, region='ap-southeast-2', debug=False):
        if debug is True:
            logger.setLevel(logging.DEBUG)
            logging.getLogger(BOTO_LOGGER_NAME).setLevel(logging.DEBUG)

        if not (env and account_name and vpc_id):
            raise ValueError(
                'env -> `{}`, account_name -> `{}`, vpc_id -> `{}` are required!! '.format(env, account_name, vpc_id)
            )
        if env not in ENVS:
            raise ValueError('env -> `{}` has be in `{}`'.format(env, ENVS))
        self.env = env
        self.account_name = account_name
        self.vpc_id = vpc_id
        self.region = region

        self.cluster_name = '{}-{}.k8s.local'.format(self.account_name, self.env)
        self.state_store_name = '%s-k8s-state-store' % self.account_name  # share same bucket for cluster in same account
        self.state_store_uri = 's3://%s' % self.state_store_name
        self.current_vars_dir = os.path.join(CWD, 'vars', self.account_name)
        self.tmp_dir = os.path.join(CWD, 'tmp')
        self.template_rendered_file_name = '%s-%s.yaml' % (self.account_name, self.env)
        self.template_rendered_path = os.path.join(CWD, '__generated__', self.template_rendered_file_name)
        self.current_values_path = os.path.join(self.current_vars_dir, '%s.yaml' % self.env)
        self.root_templates_paths = (os.path.join(TEMPLATE_DIR, 'cluster.yaml'), )

        self.__prepare()

        self.ensure_bin_dependencies()

    def ensure_aws_facts(self):

        self.vpc_facts = get_vpc_facts(vpc_id=self.vpc_id)
        logger.debug('vpc_facts -> \n%s', pformat(self.vpc_facts, indent=4, width=120))

    def ensure_kops_k8s_version_consistency(self):
        # ensure bin dependencies
        BIN_DEPS = (
            'kops',
            'kubectl',
        )
        for bin in BIN_DEPS:
            bin_path = shutil.which(bin)
            if bin_path is None or not os.access(bin_path, os.X_OK):
                raise RuntimeError('`{}` is NOT installed!'.format(bin))

        kops_version = None
        k8s_version = None
        try:
            # ensure kops and k8s has same major and minor version!
            kops_version = re.search('Version\s*([\d.]+)', self.__kops_cmd('version')).group(1)
            with open(os.path.join(TEMPLATE_DIR, 'values.yaml.j2')) as f:
                k8s_version = re.search('kubernetesVersion:\s*([\d.]+)', f.read()).group(1)
            assert kops_version.split('.')[:2] == k8s_version.split('.')[:2]
        except Exception as e:
            e.args += (
                (
                    'kops supports the equivalent Kubernetes `minor` release '
                    'number. `MAJOR.MINOR.PATCH` - https://github.com/kubernetes/kops'
                    '\nVersion mismatch: kops -> {kops_v}, k8s -> {k8s_v}'
                ).format(kops_v=kops_version, k8s_v=k8s_version),
            )
            raise e

    def __prepare(self):
        # ugly but useful
        os.environ['AWS_DEFAULT_REGION'] = os.environ.get('AWS_DEFAULT_REGION', None) or self.region

        # ensure ./tmp is there and empty before run
        try:
            logger.debug('removing %s', self.tmp_dir)
            shutil.rmtree(self.tmp_dir)
        except FileNotFoundError:
            ...
        finally:
            os.makedirs(self.tmp_dir)

        # for i in dir(self):
        #     if not i.startswith('ensure'):
        #         continue
        #     f = getattr(self, i)
        #     if callable(f):
        #         logger.info('doing -> %s', i)
        #         f()

    def ensure_ssh_pair(self):

        # ensure aws ec2 key pair
        public_key_name = 'publicKey'
        try:
            with open(self.current_values_path) as f:
                public_key_material = yaml.load(f)[public_key_name]
        except KeyError as e:
            e.args += ('`{}` is a required var, define it in {}'.format(public_key_name, self.current_values_path), )
            raise e
        ec2_key_pair_key = self.cluster_name
        try:
            ec2 = boto3.client('ec2')
            ec2.import_key_pair(KeyName=ec2_key_pair_key, PublicKeyMaterial=public_key_material)
        except ClientError as e:
            if e.response['Error']['Code'] != 'InvalidKeyPair.Duplicate':
                raise e
            logger.warn('Key pair -> `%s` is already there', ec2_key_pair_key)

        kops_default_admin_name = 'admin'

        def create_kops_secret_ssh_key():
            # create `kops` secret
            cmd = 'create secret sshpublickey {kops_u} '.format(kops_u=kops_default_admin_name)
            ssh_public_key_path = os.path.join(
                self.tmp_dir,
                urlsafe_b64encode(ec2_key_pair_key.encode()).decode() + '.pub'
            )
            with open(ssh_public_key_path, 'w') as f:
                f.write(public_key_material)
            cmd += ' -i {ssh_public_key_path}'.format(ssh_public_key_path=ssh_public_key_path, )
            self.__kops_cmd(cmd)

        def is_kops_secret_ssh_key_exits():
            cmd = 'get secret --type SSHPublicKey {kops_u} '.format(kops_u=kops_default_admin_name)
            return kops_default_admin_name in (self.__kops_cmd(cmd) or '')

        if not is_kops_secret_ssh_key_exits():
            create_kops_secret_ssh_key()

    def ensure_bin_dependencies(self):
        BIN_DEPS = (
            'kops',
            'kubectl',
        )
        for bin in BIN_DEPS:
            bin_path = shutil.which(bin)
            if bin_path is None or not os.access(bin_path, os.X_OK):
                raise RuntimeError('`{}` is NOT installed!'.format(bin))

    def ensure_state_store(self):

        s3 = boto3.resource('s3')
        bucket = s3.Bucket(self.state_store_name)
        try:
            bucket.create(ACL='private', CreateBucketConfiguration=dict(LocationConstraint=self.region))
            bucket_versioning = s3.BucketVersioning(self.state_store_name)
            bucket_versioning.enable()
        except ClientError as e:
            if e.response['Error']['Code'] == 'BucketAlreadyOwnedByYou':
                logger.debug('state store <%s> exists, ignore...', self.state_store_name)
                return
            raise e

    def _build_value_file(self):
        with open(os.path.join(TEMPLATE_DIR, 'values.yaml.j2')) as f:
            value_template = Template(f.read())
        template_rendered = value_template.render(
            env=self.env,
            account_name=self.account_name,
            state_store_name=self.state_store_name,
            vpc_facts=yaml.dump(self.vpc_facts, default_flow_style=False)
        )
        built_value_file_path = os.path.join(self.tmp_dir, 'values.yaml')
        with open(built_value_file_path, 'w') as f:
            f.write(template_rendered)
        return built_value_file_path

    def ensure_dir_and_files(self):

        for f in (
            os.path.join(TEMPLATE_DIR, 'values.yaml.j2'),
            self.current_values_path,
        ) + self.root_templates_paths:
            self._validate_path(f)

    def _validate_path(self, p):
        if os.path.isdir(p) or os.path.isfile(p):
            return True
        raise IOError('`{}` has to be an exisitng file or dir'.format(p))

    def __ensure_dir(self, path, force=False):
        if force is True:
            try:
                shutil.rmtree(path)
            except FileNotFoundError:
                ...

        try:
            os.listdir(path)
        except FileNotFoundError:
            os.makedirs(path)

    def __ensure_file(self, path, force=False):
        if force is True:
            try:
                shutil.rmtree(path)
            except FileNotFoundError:
                ...
        if not os.path.isfile(path):
            open(path, 'w').close()

    def __initialize_templates(self, force):
        from_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'raw_templates')
        to_dir = os.path.join(CWD, 'templates')
        self.__ensure_dir(to_dir, force=force)
        file_list = os.listdir(from_dir)
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
        logger.info('copying templates ->\n\t%s', '\n\t'.join([os.path.join(to_dir, f) for f in file_list]))
        shutil.rmtree(to_dir)
        shutil.copytree(from_dir, to_dir)

        # ensure addon dir
        self.__ensure_dir(ADDON_DIR, force=force)

    def __initialize_vars(self, force):
        # ensure vars dir
        var_dir = os.path.join(CWD, 'vars', self.account_name)
        self.__ensure_dir(var_dir, force=force)
        self.__ensure_dir(os.path.join(var_dir, '%s-addons' % self.env), force=force)
        self.__ensure_dir(os.path.join(var_dir, '%s-snippets' % self.env), force=force)
        self.__ensure_file(os.path.join(var_dir, '%s.yaml' % self.env), force=force)

    def __sh(self, cmd):
        cmd = cmd if isinstance(cmd, (list, tuple)) else [cmd]
        cmd = [sub_flag for flag in cmd for sub_flag in flag.split(' ') if sub_flag]
        cmd_str = ' '.join(cmd)
        logger.info(
            '__sh: env -> `%s`, account -> `%s`, \n\tcmd -> `%s`, \n\tcmd_splitted -> %s', self.env, self.account_name,
            cmd, cmd_str
        )
        exitcode, data = getstatusoutput(cmd_str)
        logger.debug('exitcode -> %s, data -> %s', exitcode, data)
        if exitcode != 0:
            raise RuntimeError(data)
        return data

    def __kops_cmd(self, args):
        args = args if isinstance(args, (list, tuple)) else [args]
        required_global_flags = ' --name={name} --state={state} '.format(
            name=self.cluster_name, state=self.state_store_uri
        )
        args.insert(0, shutil.which('kops'))
        args.append(required_global_flags)
        return self.__sh(args)

    def __kubectl_cmd(self, args):
        args = args if isinstance(args, (list, tuple)) else [args]
        kubectl = shutil.which('kubectl')

        # ensure current context correct
        use_context_args = [kubectl, 'config', 'use-context', self.cluster_name]
        logger.debug('doing -> %s', ' '.join(use_context_args))
        self.__sh(use_context_args)

        if args[0] is not kubectl:
            args.insert(0, kubectl)
        return self.__sh(args)

    def _get_current_cluster_state(self):
        return self.__kops_cmd('get -o yaml')

    def initialize(self, force=False):
        self.__initialize_templates(force=force)
        self.__initialize_vars(force=force)
        self.__ensure_dir(os.path.join(CWD, '__generated__'), force=force)

    def build(self):
        self.ensure_aws_facts()
        self.ensure_dir_and_files()
        self.ensure_kops_k8s_version_consistency()

        cmd = 'toolbox template --format-yaml=true '
        cmd += ''.join([' --values ' + f for f in [self._build_value_file(), self.current_values_path]])
        cmd += ''.join([' --template ' + f for f in self.root_templates_paths])
        snippets_path = os.path.join(self.current_vars_dir, self.env + '-snippets')
        try:
            os.listdir(snippets_path)
            cmd += ' --snippets ' + snippets_path
        except FileNotFoundError:
            ...
        data = self.__kops_cmd(cmd)
        with open(self.template_rendered_path, 'w') as f:
            f.write('---\n\n')
            f.write(data[data.index('apiVersion'):])

    def diff(self):
        try:
            self._validate_path(self.template_rendered_path)
        except IOError:
            raise IOError('Before `diff`, please `make build` first!!!')

        with open(self.template_rendered_path) as f:
            template_to_render = f.read()

        current_state = self._get_current_cluster_state()
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

    def apply(self):
        self.ensure_ssh_pair()
        self.ensure_state_store()

        cmd = 'replace -f %s  --force' % self.template_rendered_path
        self.__kops_cmd(cmd)

        cmd = 'update cluster  --yes'
        self.__kops_cmd(cmd)
        logger.info(
            (
                'Changes may require instances to restart: \n\tkops rolling-update cluster --name {name} --state {state}'
                '\nCheck cluster status:\n\tkops validate cluster --name {name} --state {state}'
            ).format(name=self.cluster_name, state=self.state_store_uri)
        )

    def install_addons(self):
        for addon in os.listdir(ADDON_DIR):
            addon_path = os.path.join(ADD_DIR, addon)
            cmd = 'apply -f %s' % addon_path
            logger.info('doing -> %s', cmd)
            logger.info(self.__kubectl_cmd(cmd))
