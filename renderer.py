import logging
import os
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

logging.basicConfig(
    level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)
BOTO_LOGGER_NAME = 'botocore'
logging.getLogger(BOTO_LOGGER_NAME).setLevel(
    logging.CRITICAL
)  # boto logging is annony and too verbose

CWD = os.getcwd()
TEMPLATE_DIR = os.path.join(CWD, 'templates')

ENVS = (
    's',  # stage
    'u',  # uat
    'p',  # prod
    'm',  # management
)


class KopsRenderer(object):

    vpc_facts = None

    def __init__(
        self, env, account_name, vpc_id, region='ap-southeast-2', debug=False
    ):
        if debug is True:
            logger.setLevel(logging.DEBUG)
            logging.getLogger(BOTO_LOGGER_NAME).setLevel(logging.DEBUG)

        if not (env and account_name and vpc_id):
            raise ValueError(
                'env -> `{}`, account_name -> `{}`, vpc_id -> `{}` are required!! '.
                format(env, account_name, vpc_id)
            )
        if env not in ENVS:
            raise ValueError('env -> `{}` has be in `{}`'.format(env, ENVS))
        self.env = env
        self.account_name = account_name
        self.vpc_id = vpc_id
        self.region = region

        self.cluster_name = '{}-{}.k8s.local'.format(
            self.account_name, self.env
        )
        self.state_store_name = '%s-k8s-state-store' % self.account_name
        self.state_store_uri = 's3://' + self.state_store_name
        self.current_vars_dir = os.path.join(CWD, 'vars', self.account_name)
        self.tmp_dir = os.path.join(CWD, 'tmp')
        self.path_template_rendered = os.path.join(
            CWD, '__generated__',
            '{}-{}.yaml'.format(self.account_name, self.env)
        )
        self.current_values_path = os.path.join(
            self.current_vars_dir, '%s.yaml' % self.env
        )
        self.paths_root_templates = (
            os.path.join(TEMPLATE_DIR, 'cluster.yaml'),
        )

        self.__prepare()

    def ensure_aws_facts(self):

        self.vpc_facts = get_vpc_facts(vpc_id=self.vpc_id)
        logger.debug(
            'vpc_facts -> \n%s', pformat(self.vpc_facts, indent=4, width=120)
        )

    def __prepare(self):
        # ugly but useful
        os.environ['AWS_DEFAULT_REGION'] = os.environ.get(
            'AWS_DEFAULT_REGION', None
        ) or self.region

        # ugly but it's required
        try:
            logger.debug('removing %s', self.tmp_dir)
            shutil.rmtree(self.tmp_dir)
        except FileNotFoundError:
            ...
        finally:
            os.makedirs(self.tmp_dir)

        for i in dir(self):
            if not i.startswith('ensure'):
                continue
            f = getattr(self, i)
            if callable(f):
                logger.info('doing -> %s', i)
                f()

    def ensure_ssh_pair(self):
        # ensure aws ec2 key pair
        public_key_name = 'publicKey'
        try:
            with open(self.current_values_path) as f:
                public_key_material = yaml.load(f.read())[public_key_name]
        except KeyError as e:
            e.args += (
                '`{}` is a required var, define it in {}'.format(
                    public_key_name, self.current_values_path
                ),
            )
            raise e
        ec2_key_pair_key = self.cluster_name
        try:
            ec2 = boto3.client('ec2')
            ec2.import_key_pair(
                KeyName=ec2_key_pair_key, PublicKeyMaterial=public_key_material
            )
        except ClientError as e:
            if e.response['Error']['Code'] != 'InvalidKeyPair.Duplicate':
                raise e
            logger.warn('Key pair -> `%s` is already there', ec2_key_pair_key)

        kops_default_admin_name = 'admin'

        def create_kops_secret_ssh_key():
            # create `kops` secret
            cmd = 'kops create secret sshpublickey {kops_u} --name {name} --state {state}'.format(
                name=self.cluster_name,
                state=self.state_store_uri,
                kops_u=kops_default_admin_name
            )
            ssh_public_key_path = os.path.join(
                self.tmp_dir,
                urlsafe_b64encode(ec2_key_pair_key.encode()).decode() + '.pub'
            )
            with open(ssh_public_key_path, 'w') as f:
                f.write(public_key_material)
            cmd += ' -i {ssh_public_key_path}'.format(
                ssh_public_key_path=ssh_public_key_path,
            )
            self.__exec(cmd)

        def is_kops_secret_ssh_key_exits():
            cmd = 'kops get secret --type SSHPublicKey {kops_u} --name {name} --state {state}'.format(
                name=self.cluster_name,
                state=self.state_store_uri,
                kops_u=kops_default_admin_name
            )
            return kops_default_admin_name in (self.__exec(cmd) or '')

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
            bucket.create(
                ACL='private',
                CreateBucketConfiguration=dict(LocationConstraint=self.region)
            )
            bucket_versioning = s3.BucketVersioning(self.state_store_name)
            bucket_versioning.enable()
        except ClientError as e:
            if e.response['Error']['Code'] == 'BucketAlreadyOwnedByYou':
                logger.debug(
                    'state store <%s> exists, ignore...', self.state_store_name
                )
                return
            raise e

    def _build_value_file(self):
        with open(os.path.join(TEMPLATE_DIR, 'values.yaml.j2')) as f:
            template = Template(f.read())
        template_rendered = template.render(
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
        ) + self.paths_root_templates:
            self._validate_path(f)

    def _validate_path(self, p):
        if os.path.isdir(p) or os.path.isfile(p):
            return True
        raise IOError('`{}` has to be an exisitng file or dir'.format(p))

    def __exec(self, cmd):
        cmd_splitted = [i for i in cmd.split(' ') if i]
        logger.info(
            '__exec: env -> `%s`, account -> `%s`, \n\tcmd -> `%s`, \n\tcmd_splitted -> %s',
            self.env, self.account_name, cmd, cmd_splitted
        )
        exitcode, data = getstatusoutput(cmd)
        logger.debug('exitcode -> %s, data -> %s', exitcode, data)
        if exitcode != 0:
            raise RuntimeError(data)
        return data

    def _get_current_cluster_state(self):
        return self.__exec(
            'kops get --name={name} --state={state} -o yaml'.format(
                name=self.cluster_name, state=self.state_store_uri
            )
        )

    def build(self):
        cmd = 'kops toolbox template --format-yaml=true '
        cmd += ''.join(
            [
                ' --values ' + f
                for f in [self._build_value_file(), self.current_values_path]
            ]
        )
        cmd += ''.join([' --template ' + f for f in self.paths_root_templates])
        snippets_path = os.path.join(
            self.current_vars_dir, self.env + '-snippets'
        )
        try:
            os.listdir(snippets_path)
            cmd += ' --snippets ' + snippets_path
        except FileNotFoundError:
            ...
        data = self.__exec(cmd)
        with open(self.path_template_rendered, 'w') as f:
            f.write('---{}'.format(data[data.index('\n'):]))

    def diff(self):
        try:
            self._validate_path(self.path_template_rendered)
        except IOError:
            raise IOError('Before `diff`, please `make build` first!!!')

        with open(self.path_template_rendered) as f:
            template_to_render = f.read()

        current_state = self._get_current_cluster_state()
        if 'No cluster found' in current_state:
            logger.info(
                'No existing cluster named `%s` found!', self.cluster_name
            )
            current_state = ''
        diff_result = unified_diff(
            current_state.splitlines(),
            template_to_render.splitlines(),
            fromfile='current_state',
            tofile=self.path_template_rendered
        )
        for line in color_diff(diff_result):
            sys.stdout.write('\n' + line)

    def apply(self):
        cmd = 'kops replace -f {file} --name={name} --state={state}  --force'.format(
            file=self.path_template_rendered,
            name=self.cluster_name,
            state=self.state_store_uri
        )
        self.__exec(cmd)

        cmd = 'kops update cluster --name={name} --state={state}  --yes'.format(
            name=self.cluster_name, state=self.state_store_uri
        )
        self.__exec(cmd)
        logger.info(
            (
                'Changes may require instances to restart: \n\tkops rolling-update cluster --name {name} --state {state}'
                '\nCheck cluster status:\n\tkops validate cluster --name {name} --state {state}'
            ).format(name=self.cluster_name, state=self.state_store_uri)
        )
