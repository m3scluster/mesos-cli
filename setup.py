import os
from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, "README.md"), encoding="utf-8") as f:
    README = f.read()

with open('pip-requirements.txt', 'r') as f:
    install_requires = f.read().splitlines()    

setup(
    name="avmesos-cli",
    version="1.3.0",
    description="Apache Mesos CLI",
    long_description=README,
    long_description_content_type="text/markdown",
    license="Apache License 2.0",
    scripts=['bin/mesos-cli'],
    packages=find_packages(),    
    install_requires=install_requires,    
    author="AVENTER UG (haftungsbeschraenkt)",
    author_email="support@aventer.biz",
    url="https://www.aventer.biz/",
    python_requires=">=3.12",
)
