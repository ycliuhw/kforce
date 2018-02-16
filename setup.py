import os
from setuptools import setup, find_packages

VERSION = "0.1.1"

ROOT_DIR = os.path.dirname(__file__)

with open(os.path.join(ROOT_DIR, "requirements", "base.txt"), "r") as f:
    install_requires = f.read().splitlines()
    if not install_requires:
        print(
            "Unable to read requirements from the requirements.txt file"
            "That indicates this copy of the source code is incomplete."
        )
        sys.exit(2)

with open(os.path.join(ROOT_DIR, "README.md"), "r") as f:
    long_description = f.read()

if __name__ == "__main__":
    setup(
        name="kforce",
        version=VERSION,
        author="Yang Kelvin Liu",
        author_email="ycliuhw@gmail.com",
        license="New BSD license",
        url="https://github.com/ycliuhw/kforce",
        description="KOPS template automation",
        long_description=long_description,
        packages=find_packages(),
        scripts=["bin/kforce"],
        install_requires=install_requires,
    )
