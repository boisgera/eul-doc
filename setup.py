#!/usr/bin/env python

# Python 3 Standard Library
pass

# Third-Party Libraries
import setuptools


metadata = {
    "name": "eul-doc",
    "version": "2.0.0",
    "license": "MIT License",
    "author": "Sébastien Boisgérault",
    "author_email": "<Sebastien.Boisgerault@gmail.com>",
    "url": "https://github.com/boisgera/eul-doc",
    "description": "Eul's Document Transforms",
    "classifiers": [
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: MIT License",
        "Topic :: Text Editors :: Text Processing",
    ],
}

contents = {"packages": setuptools.find_packages()}

requirements = {"install_requires": ["pandoc==2.1"]}

if __name__ == "__main__":
    kwargs = {**metadata, **contents, **requirements}
    setuptools.setup(**kwargs)
