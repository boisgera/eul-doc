#!/usr/bin/env python

# Python 2.7 Standard Library
import ConfigParser
import os
import shutil
import sys
import tempfile

# Pip Package Manager
try:
    import pip
    import setuptools
    import pkg_resources
except ImportError:
    error = "pip is not installed, refer to <{url}> for instructions."
    raise ImportError(error.format(url="http://pip.readthedocs.org"))

def local(path):
    return os.path.join(os.path.dirname(__file__), path)


# Extra Third-Party Libraries
# ------------------------------------------------------------------------------
sys.path.insert(0, local(".lib"))
setup_requires = ["about>=5.1,<6"]
def not_found(req):
    error  = "{req!r} not found; install it locally with:\n"
    error += "    pip install --target=.lib --ignore-installed {req!r}"
    return ImportError(error.format(req=req))
def local_conflict(req, found):
    error  = "Found {found!r} locally that conflicts with {req!r}.\n"
    error += "Delete the '.lib' directory and start over."
    raise ImportError(error.format(found=found, req=req))
for req in setup_requires:
    try:
        require = lambda *r: pkg_resources.WorkingSet().require(*r)
        require(req)
    except pkg_resources.DistributionNotFound:
        raise not_found(req)
    except pkg_resources.VersionConflict as version_error:
        found_dist = version_error.args[0]
        found = found_dist.project_name + "==" + found_dist.version
        if found_dist.location == local(".lib"):
            raise local_conflict(req=req, found=found)
        else:
            raise not_found(req)
import about


# Eul's Doc Metadata
# ------------------------------------------------------------------------------
tmp_dir = tempfile.mkdtemp()
source = local("euldoc/about.py")
target = os.path.join(tmp_dir, "about_euldoc.py")
shutil.copyfile(source, target)
sys.path.insert(0, tmp_dir)
import about_euldoc
del sys.path[0]
shutil.rmtree(tmp_dir)


# Setup
# ------------------------------------------------------------------------------
info = dict(
  metadata     = about.get_metadata(about_euldoc),
  contents     = {
                   "packages": setuptools.find_packages()
                 },
  requirements = {
                   "install_requires": ["pandoc==1.0.0a14"],
                 }, 
  scripts      = {
                   "entry_points": {
                     "console_scripts": ["eul-doc=euldoc:main"],
                   }
                 },
  plugins      = {},
  tests        = {},
)

if __name__ == "__main__":
    kwargs = {k:v for dct in info.values() for (k,v) in dct.items()}
    setuptools.setup(**kwargs)

