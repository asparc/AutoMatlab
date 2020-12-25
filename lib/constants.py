"""Globals, defaults and constants across AutoMatlab

Attributes:
    AUTO_MATLAB_PACKAGE (str): Name of AutoMatlab package
    AUTO_MATLAB_PATH (str): Path to to AutoMatlab package
    CONTENTS_NAME (str): Name of Matlab contents file
    DEFAULT_MATLABROOT (str): Default Matlab installation path
    DEFAULT_MATLAB_PATHDEF_PATH (str): Default path to Matlab pathdef file
    DEFAULT_MATLAB_HISTORY_PATH (str): DEfault path to Matlab history file
    DEFAULT_DOCUMENTATION_SNIPPET_PATH (TYPE): Path to default Matlab 
        documentation snippet
    MATLAB_COMPLETIONS_PATH (str): Path to AutoMatlab-generated completions 
        from Matlab installation
    SIGNATURES_NAME (str): Name of Matlab signatures file

Note: 
    AUTO_MATLAB_PATH, DEFAULT_DOCUMENTATION_SNIPPET_PATH, 
    MATLAB_COMPLETIONS_PATH: all require the calling sublime plugin to be 
    loaded before this module is imported.
"""

import sublime

from AutoMatlab.lib.common import abspath

# name of AutoMatlab package
AUTO_MATLAB_PACKAGE = 'AutoMatlab'

# AutoMatlab directory
AUTO_MATLAB_PATH = abspath(AUTO_MATLAB_PACKAGE, sublime.packages_path())

# AutoMatlab documentation
DEFAULT_DOCUMENTATION_SNIPPET_PATH = abspath(
    'Snippets/matlab_documentation.sublime-snippet', AUTO_MATLAB_PATH)

# AutoMatlab completions
MATLAB_COMPLETIONS_PATH = abspath("data/matlab_completions", AUTO_MATLAB_PATH)

# AutoMatlab commands
EMPTY_MATLAB_HISTORY_MESSAGE = 'Empty Matlab command history'
DEFAULT_MATLAB_HISTORY_LENGTH = 100
matlabroot_pattern = \
    r'C:/(Program Files|\.)/Matlab/R\d{4}[a,b]'
DEFAULT_AUTO_HOTKEY_PATH = abspath('C:/Program Files/AutoHotkey/AutoHotkey.exe')
AUTO_HOTKEY_SCRIPT = 'run_in_matlab.ahk'

# default Matlab directories and files
matlabroot_pattern = \
    r'C:/(Program Files|\.)/Matlab/R\d{4}[a,b]'
matlab_history_pattern = \
    r'~/AppData/Roaming/MathWorks/MATLAB/R\d{4}[a,b]/History.xml'
DEFAULT_MATLABROOT = abspath(matlabroot_pattern, regex=True)
DEFAULT_MATLAB_PATHDEF_PATH = abspath('toolbox/local/pathdef.m',
                                      DEFAULT_MATLABROOT)
DEFAULT_MATLAB_HISTORY_PATH = abspath(matlab_history_pattern, regex=True)
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
