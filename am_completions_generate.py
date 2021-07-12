import re
from os import listdir, walk, makedirs
from os.path import isdir, isfile, join, split
import errno
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
    global config, abspath, mfun
    import AutoMatlab.lib.config as config
    from AutoMatlab.lib.abspath import abspath
    from AutoMatlab.lib.mfun import mfun


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
    try:
        fun_dict = json.loads(data)
    except:
        msg = '[WARNING] AutoMatlab - Failed to decode json file: ' + signature
        # print(msg)
        return []

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
        """Initialize threads for completion generation
        """
        super().__init__(window)
        # prepare a (probably unnecessary) thread lock
        self.lock = threading.Lock()
        self.finished = True
        self.n_completions = 0
        self.matlabroot = ''

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
            # print(msg)
            self.window.status_message(msg)

    def show_status(self):
        """Show status bar indicator for ongoing completion generation
        """
        busy = True
        while busy:
            # create moving status bar position
            pos = abs(int(time.time() % 1.5 * 4) - 3)
            msg = "[{}] AutoMatlab - Generating Matlab completions. " \
                "This might take several minutues.".format(
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
        include_dirs = settings.get('include_dirs', [])
        exclude_dirs = settings.get('exclude_dirs', [])
        exclude_patterns = settings.get('exclude_patterns', [])
        use_contents_files = settings.get('use_contents_files', 'dir')
        use_signatures_files = settings.get('use_signatures_files', 'dir')
        use_matlab_path = settings.get('use_matlab_path', 'ignore')

        self.matlabroot = settings.get('matlabroot', 'default')
        if self.matlabroot == 'default':
            self.matlabroot = config.DEFAULT_MATLABROOT
        else:
            self.matlabroot = abspath(self.matlabroot)

        matlab_pathdef_path = settings.get('matlab_pathdef_path', 'default')
        if matlab_pathdef_path == 'default':
            matlab_pathdef_path = config.DEFAULT_MATLAB_PATHDEF_PATH
        matlab_pathdef_path = abspath(matlab_pathdef_path, self.matlabroot)

        # assertions
        try:
            assert type(self.matlabroot) == str, \
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

        # check matlabroot
        if not isfile(join(str(self.matlabroot), 'bin', 'matlab.exe')):
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
        include_dirs = abspath(include_dirs, self.matlabroot)
        exclude_dirs = abspath(exclude_dirs, self.matlabroot)

        # read the matlab path and parse its dirs
        if use_matlab_path in ['dir', 'read']:
            # check pathdef file
            if not isfile(matlab_pathdef_path):
                self.lock.acquire()
                self.error = True
                self.finished = True
                self.lock.release()
                msg = '[ERROR] AutoMatlab - Specified pathdef.m is invalid'
                self.window.status_message(msg)
                raise Exception(msg)
                return

            # get dirs in matlab path
            matlab_path_dirs = process_pathdef(matlab_pathdef_path, 
                self.matlabroot)

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
        for root, dirs, files in walk(join(self.matlabroot, 'toolbox')):
            # apply exclude dirs and patterns
            if any([excl for excl in exclude_dirs if root.startswith(excl)]) \
                    or any([excl for excl in exclude_patterns if excl in root]):
                continue

            # process entire dirs
            if (use_signatures_files == 'dir'
                and config.SIGNATURES_NAME in files) \
                    or (use_contents_files == 'dir'
                        and config.CONTENTS_NAME in files):
                for file in files:
                    self.compose_completion(mfun(join(root, file)))
                continue

            # process signature files
            if use_signatures_files == 'read' \
                    and config.SIGNATURES_NAME in files:
                for fun in process_signature(
                        join(root, config.SIGNATURES_NAME)):
                    self.compose_completion(mfun(join(root, fun + '.m')))

            # process contents files
            if use_contents_files == 'read'\
                    and config.CONTENTS_NAME in files:
                for fun in process_contents(
                        join(root, config.CONTENTS_NAME)):
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

        # get store path
        storage_path = abspath(config.MATLAB_COMPLETIONS_PATH, 
            sublime.packages_path())

        try:
            # make storage dir if non-existent
            makedirs(split(storage_path)[0])
        except OSError as e:
            if e.errno != errno.EEXIST:
                self.lock.acquire()
                self.error = True
                self.finished = True
                self.lock.release()
                self.window.status_message(str(e))
                raise e
                return
        except Exception as e:
            self.lock.acquire()
            self.error = True
            self.finished = True
            self.lock.release()
            self.window.status_message(str(e))
            raise e
            return

        # store results
        with open(storage_path, 'bw') as fh:
            pickle.dump(sorted_matlab_completions, fh)

        self.lock.acquire()
        self.n_completions = len(self.matlab_completions)
        self.finished = True
        self.lock.release()

    def compose_completion(self, mfun_data):
        """Compose completion and add to completions dictionary
        """
        if not mfun_data.valid:
            return

        # add data to matlab completions
        if mfun_data.path.startswith(self.matlabroot + '\\'):
            crop = len(self.matlabroot) + 1
        else:
            crop = 0
        self.matlab_completions[mfun_data.fun.lower()] = \
            [mfun_data.fun, mfun_data.annotation, mfun_data.path[crop:]]
