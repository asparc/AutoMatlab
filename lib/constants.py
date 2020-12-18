"""Globals across AutoMatlab

Attributes:
    AUTO_MATLAB_NAME (str): Name of AutoMatlab package
    AUTO_MATLAB_PATH (str): Path to to AutoMatlab package
    CONTENTS_NAME (str): Name of Matlab contents file
    DEFAULT_MATLAB_PATHDEF_PATH (str): Relative path to Matlab pathdef file
    DEFAULT_MATLABROOT (tuple): Default Matlab installation directories
    DEFAULT_MDOC_SNIPPET_PATH (TYPE): Path to default AutoMatlab 
        documentation (mdoc) snippet
    MATLAB_COMPLETIONS_PATH (str): Path to AutoMatlab-generated completions 
        from Matlab installation
    SIGNATURES_NAME (str): Name of Matlab signatures file
"""

import sublime

from AutoMatlab.lib.common import abspath

# name of AutoMatlab package
AUTO_MATLAB_NAME = "AutoMatlab"

# AutoMatlab directory
AUTO_MATLAB_PATH = abspath(AUTO_MATLAB_NAME, sublime.packages_path())

# AutoMatlab documentation
DEFAULT_MDOC_SNIPPET_PATH = \
    abspath('Snippets/mdoc.sublime-snippet', AUTO_MATLAB_PATH)

# AutoMatlab completion
MATLAB_COMPLETIONS_PATH = abspath("data/matlab_completions", AUTO_MATLAB_PATH)

# default Matlab directories and files
DEFAULT_MATLABROOT = ('C:\\Matlab', 'C:\\Program Files\\Matlab')
DEFAULT_MATLAB_PATHDEF_PATH = 'toolbox/local/pathdef.m'
SIGNATURES_NAME = 'functionSignatures.json'
CONTENTS_NAME = 'Contents.m'

# other
MAX_LOADED_PROJECT_COMPLETIONS = 7

EASTER = ['spy', 'life', 'why', 'image', 'penny', 'shower',
          'xpsound', 'xpquad', 'xpbombs', 'wrldtrv', 'vibes', 'truss',
          'makevase', 'lorenz', 'knot', 'imageext', 'earthmap',
          'cruller', 'logo', 'surf(membrane)',
          'imagesAndVideo', 'fifteen']
# toolbox easter eggs: 'rlc_gui', 'sf_tictacflow', 'eml_fire', 'eml_asteroids'
# failing easter eggs: 'toilet', 'lala', 'shower', 'viper', 'eigshow', 'census'
