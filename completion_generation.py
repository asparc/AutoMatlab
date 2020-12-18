import re
from os import listdir, walk
from os.path import join, normpath, isfile, isdir
import json
import pickle
import collections
import time
import threading

import sublime
import sublime_plugin


def plugin_loaded():
    """Do imports that need to wait for Sublime API initilization
    """
    global abspath, mfun, constants
    import AutoMatlab.lib.constants as constants
    from AutoMatlab.lib.common import abspath
    from AutoMatlab.lib.mfun import mfun


def find_matlabroot(search):
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
        for d in constants.DEFAULT_MATLABROOT:
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


def process_pathdef(matlab_pathdef_path, matlabroot):
    """Process pathdef.m file to extract all directories in the Matlab path.
    """
    matlab_path_dirs = []
    abs_dir_regex = re.compile(r"'(.+);'")
    rel_dir_regex = re.compile(r"'[\\\/]*(.+);'")

    # make absolute path
    matlab_pathdef_path = abspath(matlab_pathdef_path, matlabroot)

    if not isfile(matlab_pathdef_path):
        return []

    # open pathdef file
    with open(matlab_pathdef_path, encoding='cp1252') as fh:
        line = fh.readline()
        process_line = False

        # read line by line
        while line:
            # stop processing at END ENTRIES
            if 'END ENTRIES' in line:
                break
            # process lines containing directories
            if process_line:
                if 'matlabroot' in line:
                    # ensure dir is extracted as relative dir
                    mo = rel_dir_regex.search(line)
                    if mo:
                        matlab_path_dirs.append(
                            abspath(mo.group(1), matlabroot))
                else:
                    # read dir as absolute dir
                    mo = abs_dir_regex.search(line)
                    if mo:
                        matlab_path_dirs.append(abspath(mo.group(1)))
            # start processing at BEGIN ENTRIES
            if 'BEGIN ENTRIES' in line:
                process_line = True
            # read next line
            line = fh.readline()

    return matlab_path_dirs


class GenerateAutoMatlabCompletionsCommand(sublime_plugin.WindowCommand):

    """Generate Matlab autocompletion information by parsing the
    current Matlab installation.
    """

    def __init__(self, window):
        super().__init__(window)
        # prepare a (probably unnecessary) thread lock
        self.lock = threading.Lock()
        self.finished = True
        self.n_completions = 0

    def run(self):
        """Start threads for generating matlab completion
        """
        # prevent simultaneous threads for matlab completion generation
        self.lock.acquire()
        finished = self.finished
        if finished:
            self.finished = False
        self.lock.release()
        if finished:
            # run threads to generate matlab completions
            self.error = False
            threading.Thread(target=self.show_status).start()
            threading.Thread(target=self.generate_completions).start()
        else:
            msg = '[INFO] AutoMatlab - Matlab completions are already ' \
                'being generated'
            print(msg)
            self.window.status_message(msg)

    def show_status(self):
        """Show status bar indicator for ongoing completion generation
        """
        busy = True
        while busy:
            # create moving status bar position
            pos = abs(int(time.time() % 1.5 * 4) - 3)
            msg = "[{}] AutoMatlab - Generating Matlab completions".format(
                " " * pos + "=" + " " * (3 - pos))
            self.window.status_message(msg)
            time.sleep(0.125)
            # check if matlab completion generation finished
            self.lock.acquire()
            if self.finished:
                busy = False
                if not self.error:
                    msg = '[INFO] AutoMatlab - Found {}'.format(
                        self.n_completions) + ' Matlab function completions'
                    print(msg)
                    self.window.status_message(msg)
            self.lock.release()

    def generate_completions(self):
        """Generate matlab completions
        """
        self.matlab_completions = {}

        # read settings
        settings = sublime.load_settings('AutoMatlab.sublime-settings')
        matlab_search_dir = settings.get('matlabroot', 'default')
        matlab_pathdef_path = \
            settings.get('matlab_pathdef_path',
                         constants.DEFAULT_MATLAB_PATHDEF_PATH)
        include_dirs = settings.get('include_dirs', [])
        exclude_dirs = settings.get('exclude_dirs', [])
        exclude_patterns = settings.get('exclude_patterns', [])
        use_contents_files = settings.get('use_contents_files', 'dir')
        use_signatures_files = settings.get('use_signatures_files', 'dir')
        use_matlab_path = settings.get('use_matlab_path', 'ignore')

        # assertions
        try:
            assert type(matlab_search_dir) == str, \
                "[ERROR] AutoMatlab - Matlabroot is not of type 'str'"
            assert type(matlab_pathdef_path) == str, \
                "[ERROR] AutoMatlab - Matlab_pathdef_path is not of type 'str'"
            assert type(include_dirs) == list, \
                "[ERROR] AutoMatlab - Include_dirs is not of type 'list'"
            assert type(exclude_dirs) == list, \
                "[ERROR] AutoMatlab - Exclude_dirs is not of type 'list'"
            assert type(exclude_patterns) == list, \
                "[ERROR] AutoMatlab - Exclude_patterns is not of type 'list'"
            assert use_contents_files in ['dir', 'read', 'ignore'], \
                "[ERROR] AutoMatlab - Invalid value for 'use_contents_files'"
            assert use_signatures_files in ['dir', 'read', 'ignore'], \
                "[ERROR] AutoMatlab - Invalid value for 'use_signatures_files'"
            assert use_matlab_path in ['dir', 'read', 'ignore'], \
                "[ERROR] AutoMatlab - Invalid value for 'use_signatures_files'"
        except Exception as e:
            self.lock.acquire()
            self.error = True
            self.finished = True
            self.lock.release()
            self.window.status_message(str(e))
            raise e
            return

        # check if matlab installation can be found
        matlabroot = find_matlabroot(matlab_search_dir)
        if not matlabroot:
            self.lock.acquire()
            self.error = True
            self.finished = True
            self.lock.release()
            msg = '[ERROR] AutoMatlab - Matlab installation could not be' \
                'found at specified location'
            self.window.status_message(msg)
            raise Exception(msg)
            return

        # process include/exclude dirs
        include_dirs = abspath(include_dirs, matlabroot)
        exclude_dirs = abspath(exclude_dirs, matlabroot)

        # read the matlab path and parse its dirs
        if use_matlab_path in ['dir', 'read']:
            # get dirs in matlab path
            matlab_path_dirs = process_pathdef(matlab_pathdef_path, matlabroot)
            if not matlab_path_dirs:
                self.lock.acquire()
                self.error = True
                self.finished = True
                self.lock.release()
                msg = '[ERROR] AutoMatlab - Specified pathdef.m is invalid'
                self.window.status_message(msg)
                raise Exception(msg)
                return

            # parse dirs in matlab path
            for path_dir in matlab_path_dirs:
                if isdir(path_dir):
                    # apply exclude dirs and patterns
                    if any([excl for excl in exclude_dirs
                            if path_dir.startswith(excl)]) \
                            or any([excl for excl in exclude_patterns
                                    if excl in path_dir]):
                        continue

                    # process files in path dir
                    for file in listdir(path_dir):
                        self.compose_completion(mfun(join(path_dir, file)))

        # walk through files of matlab toolboxes
        for root, dirs, files in walk(join(matlabroot, 'toolbox')):
            # apply exclude dirs and patterns
            if any([excl for excl in exclude_dirs if root.startswith(excl)]) \
                    or any([excl for excl in exclude_patterns if excl in root]):
                continue

            # process entire dirs
            if (use_signatures_files == 'dir'
                and constants.SIGNATURES_NAME in files) \
                    or (use_contents_files == 'dir'
                        and constants.CONTENTS_NAME in files):
                for file in files:
                    self.compose_completion(mfun(join(root, file)))
                continue

            # process signature files
            if use_signatures_files == 'read' \
                    and constants.SIGNATURES_NAME in files:
                for fun in process_signature(
                        join(root, constants.SIGNATURES_NAME)):
                    self.compose_completion(mfun(join(root, fun + '.m')))

            # process contents files
            if use_contents_files == 'read'\
                    and constants.CONTENTS_NAME in files:
                for fun in process_contents(
                        join(root, constants.CONTENTS_NAME)):
                    self.compose_completion(mfun(join(root, fun + '.m')))

        # parse custom include dirs
        for include in include_dirs:
            # check wildcard
            if not include:
                continue
            wildcard = include[-1]
            if wildcard in ['+', '*']:
                include = include[:-1]
            for root, dirs, files in walk(include):
                # extract completion from file
                for f in files:
                    self.compose_completion(mfun(join(root, f)))
                # set which subdirs to include
                if wildcard == '+':
                    # only include package dirs and apply exclude dirs/patterns
                    dirs[:] = \
                        [d for d in dirs
                         if d.startswith('+')
                            and not(any([excl for excl in exclude_dirs
                                         if abspath(d, root).startswith(excl)])
                                    or any([excl for excl in exclude_patterns
                                            if excl in d and not excl == "+"]))]
                elif wildcard == '*':
                    # apply exclude dirs/patterns
                    dirs[:] = \
                        [d for d in dirs
                         if not(any([excl for excl in exclude_dirs
                                     if abspath(d, root).startswith(excl)])
                                or any([excl for excl in exclude_patterns
                                        if excl in d]))]
                else:
                    # exclude all
                    dirs[:] = []

        # sort results
        sorted_matlab_completions = collections.OrderedDict(
            sorted(self.matlab_completions.items()))

        # store results
        with open(constants.MATLAB_COMPLETIONS_PATH, 'bw') as fh:
            pickle.dump(sorted_matlab_completions, fh)

        self.lock.acquire()
        self.n_completions = len(self.matlab_completions)
        self.finished = True
        self.lock.release()

    def compose_completion(self, mfun_data):
        if not mfun_data.valid:
            return

        # add data to matlab completions
        self.matlab_completions[mfun_data.fun.lower()] = \
            [mfun_data.fun, mfun_data.annotation, mfun_data.path]
