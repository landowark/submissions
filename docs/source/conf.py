# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import sys
from pathlib import Path
sys.path.append(Path(__file__).parents[2].joinpath('src').absolute().__str__())
# Ensure top-level package shortcuts (backend, frontend, tools) are importable
# by adding src/submissions to sys.path so modules that import e.g. `from frontend`
# can be resolved during autodoc runs.
sys.path.insert(0, Path(__file__).parents[2].joinpath('src', 'submissions').absolute().__str__())
from submissions import __version__, __copyright__, __author__

project = 'RSL Submissions'
copyright = __copyright__
author = f"{__author__['name']} - {__author__['email']}"
release = __version__

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

master_doc = "index"

extensions = [
    'sphinx.ext.doctest',
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.napoleon',
    'sphinx_markdown_builder',
    'sphinx_mdinclude',
   ]

templates_path = ['_templates']
exclude_patterns = []

sys.path.insert(0, Path(__file__).absolute().resolve().parents[2].joinpath("src").__str__())
sys.path.insert(0, Path(__file__).absolute().resolve().parents[2].joinpath("src/procedure").__str__())

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'alabaster'
# html_style = 'custom.css'
html_static_path = ['_static']


# autodoc_mock_imports = ["backend.db.models.procedure"]


# Workaround: SQLAlchemy's `declared_attr` descriptors are not callables and
# cause autodoc to fail when it tries to inspect signatures. Suppress signature
# extraction for those objects to avoid repeated warnings.
def _suppress_declared_attr_signature(app, what, name, obj, options, signature, return_annotation):
    try:
        import sqlalchemy.orm.decl_api as _declapi
        if isinstance(obj, _declapi.declared_attr):
            return (None, None)
    except Exception:
        # If SQLAlchemy isn't available or import fails, do nothing.
        return None


def setup(app):
    app.connect("autodoc-process-signature", _suppress_declared_attr_signature)