import os
from setuptools import setup, find_packages

VERSION = "0.1.1"

ROOT_DIR = os.path.dirname(__file__)

with open(os.path.join(ROOT_DIR, 'requirements', 'base.txt'), 'r') as f:
    install_requires = requirements_file.read().splitlines()
    if not install_requires:
        print(
            "Unable to read requirements from the requirements.txt file"
            "That indicates this copy of the source code is incomplete."
        )
        sys.exit(2)

scripts = ("bin/kforece", )


def read(filename):
    full_path = os.path.join(src_dir, filename)
    with open(full_path) as fd:
        return fd.read()


if __name__ == "__main__":
    setup(
        name="kforce",
        version=VERSION,
        author="Yang Kelvin Liu",
        author_email="ycliuhw@gmail.com",
        license="New BSD license",
        url="https://github.com/ycliuhw/kforce",
        description="KOPS template automation",
        long_description=read("README.md"),
        packages=find_packages(),
        scripts=scripts,
        install_requires=install_requires,
    )
