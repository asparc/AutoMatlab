"""Common function across AutoMatlab
"""

import os
import os.path
import re

try:
    import sublime
except:
    class sublime:
        @staticmethod
        def expand_variables(path, vars={}):
            for k, v in vars.items():
                path = path.subs(k, v)
            return path


def abspath(path, base=None, vars={}, regex=False):
    """Convert relative path(s) into absolute path(s) wrt base.

    - Normalizes backslash/forward slash convention per OS
    - Interprets and converts dots in relative path 
    - Expands user home "~"
    - Expands sublime variables in the provided relative path
    - Applies base path to relative path 
      (default base path is the current working directory)
    - Can process regex patterns (assuming a forward slash convention)

    Args:
        path (str/list): Relative path(s)
        base (str, optional): Base path for absolute path
        regex (bool, optional): Process regex patterns in path or base

    Returns:
        str/list: Absolute path(s)
    """
    # process base
    if type(base) == str and not base == "":
        if regex:
            # process regex
            base = _regexpath(base, "", vars)
            if not base:
                return None
        else:
            # do substitutions and normalize path
            base = os.path.normpath(os.path.expanduser(
                sublime.expand_variables(base, vars)))
    else:
        base = ""
    if type(path) == list:
        return [_abspath(p, base, vars, regex) for p in path]
    elif type(path) == str:
        return _abspath(path, base, vars, regex)
    else:
        return path


def _abspath(path, base, vars, regex):
    """Helper for abspath()
    """
    if regex:
        # process regex
        return _regexpath(path, base, vars)
    else:
        # do substitutions and normalize path
        path = os.path.normpath(os.path.expanduser(
            sublime.expand_variables(path, vars)))

        if os.path.isabs(path):
            return path
        else:
            # make absolute
            if base:
                return os.path.join(base, path)
            else:
                return os.path.abspath(path)


def _regexpath(path_pattern, base="", vars={}):
    """Finds path based on regex pattern
    """
    # do substitutions
    path_pattern = os.path.expanduser(
        sublime.expand_variables(path_pattern, vars))

    # split path pattern assuming forward slash convention
    parts = path_pattern.split('/')

    # preprocessing of base
    if base:
        # add base
        parts = [base] + parts
    else:
        if os.path.abspath(path_pattern):
            # restore '/' for absolute path
            parts[0] = parts[0] + '/'

    # clean parts
    parts = [p for p in parts if p]

    if not parts:
        return None

    return _findpath(parts)


def _findpath(parts):
    """Recursive construct path from pattern parts
    """

    # check if finished
    if len(parts) == 1:
        path = os.path.normpath(parts[0])
        if os.path.exists(path):
            return path
        else:
            return None

    # check if next part still is a directory
    if not os.path.isdir(parts[0]):
        return None

    for f in os.listdir(parts[0]) + ['.', '..']:
        # look for pattern match
        mo = re.search(r'^' + parts[1] + r'$', f, re.I)
        if mo:
            # recursively parse pattern parts
            path = _findpath([os.path.join(parts[0], f)] + parts[2:])

            if path:
                # match found
                return path

    # no match found
    return None


if __name__ == '__main__':
    # tests
    sublimeroot_pattern = r'C:/(Program Files|\.)/Sublime Text \d'
    print(abspath([sublimeroot_pattern, 'error'], regex=True))
    print(abspath(r'C:/Matlab/R2017b'))
    matlabroot_pattern = r'C:/(Program Files|\.)/Matlab/R\d{4}[a,b]'
    print(abspath(matlabroot_pattern, regex=True))
    print(abspath('~/AppData', regex=True))
    print(abspath('~/AppData', regex=False))
    print(abspath('toolbox/local/pathdef.m', matlabroot_pattern, regex=True))
    print(abspath('toolbox/local/pathdef.m', 'C:/Matlab/R2017b', regex=True))
    print(abspath(
        r'AppData/Roaming/MathWorks/MATLAB/R\d{4}[a,b]/History.xml', '~',
        regex=True))
    print(abspath(
        r'~/AppData/Roaming/MathWorks/MATLAB/R\d{4}[a,b]/History.xml',
        regex=True))
