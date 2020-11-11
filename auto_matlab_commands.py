import re
from os import listdir, walk
from os.path import join, normpath, isfile, isdir, abspath, split
import json
import pickle
import collections

import sublime
import sublime_plugin

from .mfun import mfun

# constants
DEFAULT_MATLAB_INSTALL_DIRS = ('C:', 'C:/Program Files')
SIGNATURES_NAME = 'functionSignatures.json'
CONTENTS_NAME = 'Contents.m'
COMPLETIONS_SAVE = join('data', 'completions')


def find_matlab(search):
    """Find the Matlab installation directory.
    """
    def search_dir(d):
        if not isdir(d):
            return False
        # check logical dirs and subdirs
        # if exists, add matlab (upper/lower case) to d
        dirs = listdir(d)
        d = join(d,
                 dict(zip([d.lower() for d in dirs], dirs)).get('matlab', ''))
        # if exists, add most recent matlab version to d
        dirs = listdir(d)
        vers = [d for d in sorted(dirs) if re.search(r'R\d+[ab]', d)]
        d = join(d, vers[-1] if len(vers) else '')
        # locate matlab.exe and toolsbox
        if not(isfile(join(d, 'bin', 'matlab.exe'))
               and isdir(join(d, 'toolbox'))):
            return False

        # success
        return normpath(d)

    # check different search options
    if search == 'default':
        for d in DEFAULT_MATLAB_INSTALL_DIRS:
            res = search_dir(normpath(d))
            if res:
                return res
    elif type(search) == str:
        return search_dir(normpath(search))
    return False


def process_signature(signature):
    """Process a functionSignatures.json file to extract Matlab function names
    from it.

    Although functionSignatures.json contains the autocompletion information
    that Matlab natively uses, only the function names are extracted from this
    file by AutoMatlab. The reason is that the autocompletion information in 
    functionSignatures.json is very inconsistent and incomplete.
    """
    if not isfile(signature):
        return []

    # read as string data
    with open(signature) as fh:
        data = fh.read()

    # remove comments, as the python json parses has issues with those
    pattern = r'\/\/.*'
    data = re.sub(pattern, '', data)

    # remove linebreak in multiline strings, as they are not standard json
    pattern = r'\.\.\.\s+'
    data = re.sub(pattern, '', data)

    # place comma's between sequences of strings, as this is required for json
    pattern = r'"\s+"'
    data = re.sub(pattern, '","', data)

    # # read json with custom decoder, to retain duplicate keys
    # decoder = json.JSONDecoder(object_pairs_hook=lambda x: tuple(x))
    # signatures = decoder.decode(data)
    # read json
    fun_dict = json.loads(data)

    # extract all function names
    funs = []
    for fun in fun_dict.keys():
        funs.append(fun)

    return funs


def process_contents(contents):
    """Process a Contents.m file to extract Matlab function names from it.

    This function expects the default Matlab structure of Contents.m files. 
    Unfortunately, this structure is not always faithfully applied, in which
    case AutoMatlab won't recognize the functions.
    """
    if not isfile(contents):
        return []

    # read data line by line
    funs = []
    with open(contents, encoding='cp1252') as fh:
        try:
            line = fh.readline()
        except:
            return funs
        while line:
            # interrupt at copyright message
            if 'copyright' in line.lower():
                break
            # extract function name
            pattern = r'^\s*%\s*(\w+)\s+-'
            mo = re.search(pattern, line)
            if mo:
                funs.append(mo.group(1))

            # read next line
            try:
                line = fh.readline()
            except:
                return funs
    return funs


class GenerateAutoMatlabCommand(sublime_plugin.WindowCommand):

    """Generate Matlab autocompletion information by parsing the
    current Matlab installation.

    TODO: Run in separate thread.
    """

    def run(self):
        self.completions = {}

        # read settings
        settings = sublime.load_settings('AutoMatlab.sublime-settings')
        matlab_search_dir = settings.get('matlab_install_dir', 'default')
        include_dirs = settings.get('include_dirs', [])
        exclude_dirs = settings.get('exclude_dirs', [])
        contents_files = settings.get('contents_files', 'dir')
        signatures_files = settings.get('signatures_files', 'dir')

        # assertions
        try:
            assert type(matlab_search_dir) == str, \
                "[ERROR] AutoMatlab - matlab_install_dir is not of type 'str'"
            assert type(include_dirs) == list, \
                "[ERROR] AutoMatlab - include_dirs is not of type 'list'"
            assert type(exclude_dirs) == list, \
                "[ERROR] AutoMatlab - exclude_dirs is not of type 'list'"
            assert contents_files in ['dir', 'read', 'ignore'], \
                "[ERROR] AutoMatlab - Invalid value for 'contents_files'"
            assert signatures_files in ['dir', 'read', 'ignore'], \
                "[ERROR] AutoMatlab - Invalid value for 'signatures_files'"
        except Exception as e:
            self.window.status_message(str(e))
            raise e

        # check if matlab installation can be found
        matlab_install_dir = find_matlab(matlab_search_dir)
        if not matlab_install_dir:
            msg = '[ERROR] AutoMatlab - Matlab installation could not be found'
            self.window.status_message(msg)
            raise Exception(msg)
            return

        # prepend include_dirs and check if they exist
        include_dirs = [normpath(join(matlab_install_dir, d))
                        for d in include_dirs
                        if isdir(join(matlab_install_dir, d))]

        # prepend exclude_dirs
        exclude_dirs = [normpath(join(matlab_install_dir, d))
                        for d in exclude_dirs]

        # walk through files of matlab toolboxes
        for root, dirs, files in walk(join(matlab_install_dir, 'toolbox')):
            if 'demo' in root or '+' in root or '@' in root \
                    or any([d for d in exclude_dirs if d in root]):
                continue

            # process entire dirs
            if (signatures_files == 'dir' and SIGNATURES_NAME in files) \
                    or (contents_files == 'dir' and CONTENTS_NAME in files):
                for file in files:
                    self.compose_completion(mfun(join(root, file)))
                continue

            # process signature files
            if signatures_files == 'read' and SIGNATURES_NAME in files:
                for fun in process_signature(join(root, SIGNATURES_NAME)):
                    self.compose_completion(mfun(join(root, fun + '.m')))

            # process contents files
            if contents_files == 'read' and CONTENTS_NAME in files:
                for fun in process_contents(join(root, CONTENTS_NAME)):
                    self.compose_completion(mfun(join(root, fun + '.m')))

        # parse custom dirs
        for root in include_dirs:
            for file in listdir(root):
                self.compose_completion(mfun(join(root, file)))

        # sort results
        sorted_completions = collections.OrderedDict(
            sorted(self.completions.items()))

        # store results
        with open(join(split(abspath(__file__))[0],
                       COMPLETIONS_SAVE), "bw") as fh:
            pickle.dump(sorted_completions, fh)

        self.window.status_message(
            '[INFO] AutoMatlab - Found {}'.format(len(sorted_completions))
            + ' Matlab function completions')

    def compose_completion(self, mfun):
        if not mfun.valid:
            return

        # add data to completions
        self.completions[mfun.fun.lower()] = [mfun.fun,
                                              mfun.annotation, mfun.path]


class NavigateAutoMatlabCommand(sublime_plugin.TextCommand):

    """Redefine the commands for navigating through the autocompletion popup.
    """

    def run(self, edit, amount):
        if amount > 0:
            self.view.run_command('auto_complete')
        elif amount < 0:
            self.view.run_command('auto_complete_prev')
        else:
            settings = sublime.load_settings('AutoMatlab.sublime-settings')
            right_commit = settings.get('ctrl_right_commit', False)
            if right_commit:
                self.view.run_command('commit_completion')
            else:
                self.view.run_command('move',
                    {'by':'word_ends', 'forward': True})