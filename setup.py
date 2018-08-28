import os

import setuptools


def local_file(name):
    return os.path.relpath(os.path.join(os.path.dirname(__file__), name))


SOURCE = local_file("src")
README = local_file("README.md")

setuptools.setup(
    name="drmnotes",
    # Not actually published on pypi
    version='0.0.0',
    author="David R. MacIver",
    author_email="david@drmaciver.com",
    packages=setuptools.find_packages(SOURCE),
    package_dir={"": SOURCE},
    url=("https://github.com/DRMacIver/each/"),
    license="GPL v3",
    description="A tool for running programs on many inputs",
    zip_safe=False,
    install_requires=["attrs>=18.0.0", "click",],
    entry_points={"console_scripts": ["drmnotes=drmnotes.__main__:main"]},
    long_description=open(README).read(),
)
