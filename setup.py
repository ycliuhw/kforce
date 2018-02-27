import os
import sys
from setuptools import setup
from pip.req import parse_requirements
from pip.download import PipSession

VERSION = "0.1.24"

scripts = ["bin/kforce"]

install_requires = [str(ir.req) for ir in parse_requirements("requirements/base.txt", session=PipSession())]

if __name__ == "__main__":
    setup(
        name="kforce",
        version=VERSION,
        author="Yang Kelvin Liu",
        author_email="ycliuhw@gmail.com",
        license="Apache License 2.0",
        url="https://github.com/ycliuhw/kforce",
        description="KOPS template automation",
        packages=["kforce"],
        scripts=scripts,
        keywords=["k8s", "kops", "kubernetes", "template"],
        install_requires=install_requires,
        # include_package_data=True,
        package_data={"kforce": ["raw_templates/*"]},
    )
