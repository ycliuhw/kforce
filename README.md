# Kubernetes

![build-status](http://nginx.k8s.domainsecurity.cc/api/badges/ycliuhw/kforce/status.svg?branch=master)
[![MIT Licence](https://badges.frapsoft.com/os/mit/mit.svg?v=103)](https://opensource.org/licenses/mit-license.php)
[![Open Source Love](https://badges.frapsoft.com/os/v1/open-source.svg?v=103)](https://github.com/ellerbrock/open-source-badges/)


## Create and manage K8S cluster using templates in an automated way ^.^

----

> <https://github.com/kubernetes/kops/blob/master/docs/cluster_spec.md>

### Requirements

----

* [kops](https://github.com/kubernetes/kops/)
* python3.6

### Installation

----

#### from pypi

----

```bash
pip install kforce
```

#### from source

----

```bash
git clone https://github.com/ycliuhw/kforce.git
cd kforce

virtualenv -p $(which python3.6) venv
source venv/bin/activate
python setup.py install
```

### Usage

----

#### create `kops` iam group, attach related policies, create user then add user to group:

```bash
AWS_PROFILE=[admin] make ensure_iam
```

#### create access key for `kops` user

```bash
AWS_PROFILE=[admin] make create_access_key
```

#### initialize templates dirs for a new cluster

```bash
AWS_PROFILE=[kops] kforce initialize --account-name=[aws-account1] --env=[s|p|u|m] --vpc-id=vpc-xxxx [--force=True]
```

#### build kops template

```bash
AWS_PROFILE=[kops] kforce build --account-name=[aws-account1] --env=[s|p|u|m] --vpc-id=vpc-xxxx
```

#### diff kops template

```bash
AWS_PROFILE=[kops] kforce diff --account-name=[aws-account1] --env=[s|p|u|m] --vpc-id=vpc-xxxx
```

![make diff](img/make-diff.png)

#### apply kops template to create the cluster

```bash
AWS_PROFILE=[kops] kforce apply --account-name=[aws-account1] --env=[s|p|u|m] --vpc-id=vpc-xxxx
```

### directory structure

----

```text
.
├── Makefile
├── README.md
├── __generated__
│   ├── README.md
│   ├── cre-m.yaml
│   ├── domainmobile-p.yaml
│   ├── domainnonprod-s.yaml
│   └── domainsandbox-s.yaml
├── addons
│   ├── README.md
│   └── cluster_role.yaml
├── img
│   └── make-diff.png
├── requirements.txt
├── templates
│   ├── addons
│   │   ├── README.md
│   │   ├── autoscaler.yaml
│   │   ├── dashboard.yaml
│   │   ├── external-dns.yaml
│   │   ├── fluentd.yaml
│   │   ├── ingress-nginx-external.yaml
│   │   └── ingress-nginx-internal.yaml
│   ├── cluster.yaml
│   ├── snippets
│   │   └── gpu.yaml
│   └── values.yaml.j2
└── vars
    ├── aws-account-1
    │   ├── m
    │   │   ├── addons
    │   │   ├── ig
    │   │   │   ├── m-class-ondemand.yaml
    │   │   │   └── m-class-spot.yaml
    │   │   ├── snippets
    │   │   └── values.yaml
    │   ├── p
    │   │   ├── addons
    │   │   ├── ig
    │   │   ├── snippets
    │   │   └── values.yaml
    │   └── s
    ├── aws-account-2
    │   ├── m
    │   │   ├── addons
    │   │   ├── ig
    │   │   │   ├── m-class-ondemand.yaml
    │   │   │   └── m-class-spot.yaml
    │   │   ├── snippets
    │   │   └── values.yaml
    │   ├── p
    │   │   ├── addons
    │   │   ├── ig
    │   │   ├── snippets
    │   │   └── values.yaml
```
