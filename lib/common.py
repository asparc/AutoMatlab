"""Common function across AutoMatlab
"""

import os

import sublime

def abspath(path, base=None, vars={}):
    """Convert relative path(s) into absolute path(s) wrt base.

    - Normalizes backslash/forward slash convention per OS
    - Interprets and converts dots in relative path 
    - Expands user home "~"
    - Expands sublime variables in the provided relative path
    - Applies base path to relative path 
      (default base path is the current working directory)

    Args:
        path (str/list): Relative path(s)
        base (str, optional): Base path for absolute path
        vars (dict, optional): Sublime variables to expand

    Returns:
        str/list: Absolute path(s)
    """
    if type(base) == str:
        base = os.path.normpath(os.path.expanduser(
            sublime.expand_variables(base, vars)))
    else:
        base = ""
    if type(path) == list:
        return [_abspath(p, base, vars) for p in path]
    elif type(path) == str:
        return _abspath(path, base, vars)
    else:
        return path


def _abspath(path, base, vars):
    """Helper for abspath()
    """
    path = os.path.normpath(os.path.expanduser(
        sublime.expand_variables(path, vars)))
    if os.path.isabs(path):
        return path
    else:
        if base:
            return os.path.join(base, path)
        else:
            return os.path.abspath(path)