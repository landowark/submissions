# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import sys
from pathlib import Path
sys.path.append(Path(__file__).parents[2].joinpath('src').absolute().__str__())
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