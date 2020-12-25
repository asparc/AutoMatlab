"""Configuration of globals, constants and defaults across AutoMatlab

Attributes:
    DEFAULT_MATLABROOT (str): Default Matlab installation path
    DEFAULT_MATLAB_HISTORY_PATH (str): Default path to Matlab history file
    DEFAULT_MATLAB_PATHDEF_PATH (str): Default path to Matlab pathdef file
    DEFAULT_AUTO_HOTKEY_PATH (str): Default path to AutoHotkey executable
    CONTENTS_NAME (str): Name of Matlab contents file
    SIGNATURES_NAME (str): Name of Matlab signatures file
    EMPTY_MATLAB_HISTORY_MESSAGE (str): Message to show in command pael when 
        no Matlab history was found.
    AUTO_HOTKEY_SCRIPT (str): Name of AutoHotkey script to run matlab commands
    MATLAB_COMPLETIONS_PATH (str): Path to AutoMatlab completions, generated 
        from Matlab installation
    MAX_LOADED_PROJECT_COMPLETIONS (int): Maximum number of projects for which
        completion information is kept stored in memory.
    EASTER (list): A list of Matlab easter eggs.

Note: 
    Some of variables depend on Sublime API functions. They require the
    Sublime plugin to be loaded before this module is imported:
    - MATLAB_COMPLETIONS_PATH
"""

import sublime

from AutoMatlab.lib.abspath import abspath

# paths for default settings
matlabroot_pattern = \
    r'C:/(Program Files|\.)/Matlab/R\d{4}[a,b]'
matlab_history_pattern = \
    r'~/AppData/Roaming/MathWorks/MATLAB/R\d{4}[a,b]/History.xml'

DEFAULT_MATLABROOT = abspath(matlabroot_pattern, regex=True)
DEFAULT_MATLAB_HISTORY_PATH = abspath(matlab_history_pattern, regex=True)
DEFAULT_MATLAB_PATHDEF_PATH = abspath('toolbox/local/pathdef.m',
                                      DEFAULT_MATLABROOT)
DEFAULT_AUTO_HOTKEY_PATH = abspath(
    'C:/Program Files/AutoHotkey/AutoHotkey.exe')

# standard Matlab files
CONTENTS_NAME = 'Contents.m'
SIGNATURES_NAME = 'functionSignatures.json'

# AutoMatlab commands
EMPTY_MATLAB_HISTORY_MESSAGE = 'Empty Matlab command history'
AUTO_HOTKEY_SCRIPT = 'run_in_matlab.ahk'

# AutoMatlab completions
MATLAB_COMPLETIONS_PATH = abspath("AutoMatlab/data/matlab_completions",
                                  sublime.packages_path())
MAX_LOADED_PROJECT_COMPLETIONS = 7
EASTER = ['spy', 'life', 'why', 'image', 'penny', 'shower',
          'xpsound', 'xpquad', 'xpbombs', 'wrldtrv', 'vibes', 'truss',
          'makevase', 'lorenz', 'knot', 'imageext', 'earthmap',
          'cruller', 'logo', 'surf(membrane)',
          'imagesAndVideo', 'fifteen']
# toolbox easter eggs: 'rlc_gui', 'sf_tictacflow', 'eml_fire', 'eml_asteroids'
# failing easter eggs: 'toilet', 'lala', 'shower', 'viper', 'eigshow', 'census'
