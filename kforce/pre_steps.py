import logging
import os
import re
import shutil

import boto3
import yaml
from botocore.errorfactory import ClientError

from .aws_facts import get_vpc_facts

logger = logging.getLogger(__name__)


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
        kops_version = re.search('Version\s*([\d.]+)', self._kops_cmd('version')).group(1)
        with open(os.path.join(self.DIR_TEMPLATE, 'values.yaml.j2')) as f:
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


def ensure_region(self):
    # ugly but useful
    os.environ['AWS_DEFAULT_REGION'] = os.environ.get('AWS_DEFAULT_REGION', None) or self.region


def ensure_tmp_dir_existing_and_empty(self):
    # ensure ./tmp is there and empty before run
    try:
        logger.debug('removing %s', self.DIR_TMP)
        shutil.rmtree(self.DIR_TMP)
    except FileNotFoundError:
        ...
    finally:
        os.makedirs(self.DIR_TMP)


def ensure_ssh_pair(self):

    # ensure aws ec2 key pair
    public_key_name = 'publicKey'
    try:
        with open(self.current_value_file_path) as f:
            public_key_material = yaml.load(f)[public_key_name]
    except (KeyError, TypeError) as e:
        e.args += ('`{}` is a required var, define it in {}'.format(public_key_name, self.current_value_file_path), )
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
            self.DIR_TMP,
            urlsafe_b64encode(ec2_key_pair_key.encode()).decode() + '.pub'
        )
        with open(ssh_public_key_path, 'w') as f:
            f.write(public_key_material)
        cmd += ' -i {ssh_public_key_path}'.format(ssh_public_key_path=ssh_public_key_path, )
        self._kops_cmd(cmd)

    def is_kops_secret_ssh_key_exits():
        cmd = 'get secret --type SSHPublicKey {kops_u} '.format(kops_u=kops_default_admin_name)
        return kops_default_admin_name in (self._kops_cmd(cmd) or '')

    if not is_kops_secret_ssh_key_exits():
        create_kops_secret_ssh_key()


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
