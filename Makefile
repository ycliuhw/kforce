cwd 			 = $(shell pwd)
virtualenv_dir 	 = $(cwd)/venv
python_base_path = $(shell which python3.6)

kops_iam_id      = kops

# defaults
region 		 	 ?= ap-southeast-2
account_name 	 ?= domainsandbox
debug            ?= False  # True or False


.PHONY: ensure_venv
ensure_venv:
	test -d venv || virtualenv -p $(python_base_path) $(virtualenv_dir)


.PHONY: install-deps
install-deps: ensure_venv
	$(virtualenv_dir)/bin/pip install -r requirements/dev.txt


.PHONY: isort
isort:
	isort --recursive --quiet kforce/ bin/ tests/  # --check-only


.PHONY: yapf
yapf:
	yapf --recursive --in-place kforce/ bin/ tests/ setup.py conftest.py


.PHONY: pytest
pytest:
	py.test --spec --cov=kforce --cov-report html --cov-report term tests


.PHONY: test
test: isort yapf  pytest


.PHONY: test
pypi-upload:
	python setup.py sdist upload -r pypi


PHONY: install
install:
	$(virtualenv_dir)/bin/python setup.py install


.PHONY: ensure_iam
ensure_iam: install-deps
	# create group
	. $(virtualenv_dir)/bin/activate; aws iam create-group --group-name $(kops_iam_id)
	# attach group policies
	aws iam attach-group-policy --policy-arn arn:aws:iam::aws:policy/AmazonEC2FullAccess --group-name $(kops_iam_id)
	aws iam attach-group-policy --policy-arn arn:aws:iam::aws:policy/AmazonRoute53FullAccess --group-name $(kops_iam_id)
	aws iam attach-group-policy --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess --group-name $(kops_iam_id)
	aws iam attach-group-policy --policy-arn arn:aws:iam::aws:policy/IAMFullAccess --group-name $(kops_iam_id)
	aws iam attach-group-policy --policy-arn arn:aws:iam::aws:policy/AmazonVPCFullAccess --group-name $(kops_iam_id)
	# create user
	aws iam create-user --user-name $(kops_iam_id)
	# add user to group
	aws iam add-user-to-group --user-name $(kops_iam_id) --group-name $(kops_iam_id)
	# echo hint
	@echo Now, create access key using $(kops_iam_id) account to execute other cmd!


.PHONY: create_access_key
create_access_key:
	. $(virtualenv_dir)/bin/activate; aws iam create-access-key --user-name $(kops_iam_id)


.PHONY: build
build:
	. $(virtualenv_dir)/bin/activate; ./bin/kforce build --account-name=$(account_name) --env=$(env) --vpc-id=$(vpc_id) --region=$(region) --debug=$(debug)


.PHONY: diff
diff:
	. $(virtualenv_dir)/bin/activate; ./bin/kforce diff --account-name=$(account_name) --env=$(env) --vpc-id=$(vpc_id) --region=$(region) --debug=$(debug)


.PHONY: apply
apply:
	. $(virtualenv_dir)/bin/activate; ./bin/kforce apply --account-name=$(account_name) --env=$(env) --vpc-id=$(vpc_id) --region=$(region) --debug=$(debug)
