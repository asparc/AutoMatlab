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


class GenerateAutoMatlabCommand(sublime_plugin.WindowCommand):

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
                n_completions = self.n_completions
                busy = False
            self.lock.release()
        msg = '[INFO] AutoMatlab - Found {}'.format(n_completions) \
            + ' Matlab function completions'
        print(msg)
        self.window.status_message(msg)

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
            self.window.status_message(str(e))
            raise e

        # check if matlab installation can be found
        matlabroot = find_matlabroot(matlab_search_dir)
        if not matlabroot:
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
                                      {'by': 'word_ends', 'forward': True})

class DocumentAutoMatlabCommand(sublime_plugin.TextCommand):

    """Generate a snippet for documenting matlab functions
    """

    def run(self, edit):
        settings = sublime.load_settings('AutoMatlab.sublime-settings')

        # read first line
        region1 = self.view.line(0)
        line1 = self.view.substr(region1)

        # extract function definition components
        pattern = r'^\s*function\s+((?:\[(.*)\]\s*=|(\w+)\s*=|)' \
            r'\s*(\w+)\((.*)\))'
        mo = re.search(pattern, line1)
        if not mo:
            msg = '[WARNING] AutoMatlab - Could not find Matlab' \
                'function signature.'
            print(msg)
            self.view.window().status_message(msg)
            return

        # get signature, outargs, function name, inargs
        signature = mo.group(1)
        outargs = []
        if mo.group(2):
            outargs = [arg.strip() for arg in mo.group(2).split(',')]
        if mo.group(3):
            outargs = [arg.strip() for arg in mo.group(3).split(',')]
        fun = mo.group(4)
        inargs = []
        if mo.group(5):
            inargs = [arg.strip() for arg in mo.group(5).split(',')]
        if settings.get('mdoc_upper_case_signature', False):
            signature = signature.upper()
            fun = fun.upper()
            inargs = [arg.upper() for arg in inargs]
            outargs = [arg.upper() for arg in outargs]

        # read mdoc snippet
        snip_path = settings.get('mdoc_snippet_path',
                                 constants.DEFAULT_MDOC_SNIPPET_PATH)
        if isfile(abspath(snip_path)):
            snip_path = abspath(snip_path)
        elif sublime.find_resources(snip_path):
            snip_path = abspath(sublime.find_resources(snip_path)[-1],
                                join(sublime.packages_path(), ".."))
        else:
            msg = '[ERROR] AutoMatlab - Invalid mdoc snippet path.'
            self.view.window().status_message(msg)
            raise Exception(msg)
            return

        with open(snip_path) as fh:
            snip_all = fh.read()

        # extract mdoc snippet content
        pattern = r'<!\[CDATA\[([\s\S]*)\]]>'
        mo = re.search(pattern, snip_all)
        if not mo:
            msg = '[ERROR] AutoMatlab - Mdoc snippet could not ' \
                'be found.'
            self.view.window().status_message(msg)
            raise Exception(msg)
            return
        snip = mo.group(1).strip()

        # some validity check on the mdoc snippet
        mo = re.findall(r'^[^\n]*\${MDOC_NAME_MARKER}', snip)
        if not mo:
            msg = '[ERROR] AutoMatlab - ${MDOC_NAME_MARKER} is compulsory in ' \
                'first line of mdoc snippet.'
            self.view.window().status_message(msg)
            raise Exception(msg)
            return

        mo = re.findall(r'^\W*\${MDOC_NAME}', snip)
        if not mo:
            msg = '[ERROR] AutoMatlab - ${MDOC_NAME} is compulsory as ' \
                'first word of mdoc snippet.'
            self.view.window().status_message(msg)
            raise Exception(msg)
            return

        mo = re.search(r'^[^\n]*(\${MDOC_\w*_MARKER}).+', snip, re.M)
        if mo:
            msg = '[ERROR] AutoMatlab - ' + mo.group(1) + ' should be at end ' \
                'of line in mdoc snippet.'
            self.view.window().status_message(msg)
            raise Exception(msg)
            return

        # check if function is already documented
        region2 = self.view.line(region1.end() + 1)
        line2 = self.view.substr(region2)
        if not re.search(r'\s*%+[\s%]*' + fun, line2):
            # compose documentation snippet
            snip = self.compose_documentation_snippet(snip, signature,
                                                      fun, inargs, outargs)

            # insert snippet
            self.view.sel().clear()
            self.view.sel().add(region1.end() + 1)
            if self.view.size() == region1.size():
                self.view.run_command(
                    'insert_snippet', {'contents': '\n' + snip + '\n\n'})
            else:
                self.view.run_command(
                    'insert_snippet', {'contents': snip + '\n\n'})
        else:
            msg = '[WARNING] AutoMatlab - Documentation already exists.'
            print(msg)
            self.view.window().status_message(msg)
            return

    def compose_documentation_snippet(self, snip, signature,
                                      fun, inargs, outargs):
        """Compose new documentation snippet based on function signature
        """
        # insert function name and signature
        snip = re.sub(r'\${MDOC_NAME}', fun, snip)
        snip = re.sub(r'\${MDOC_SIGNATURE}', signature, snip)

        # process input argument block
        snip = self.compose_arg_snip_lines(snip, inargs,
                                           'MDOC_INARG_BLOCK_MARKER',
                                           'MDOC_INARG_MARKER', 'MDOC_INARG')
        snip = self.compose_arg_snip_lines(snip, outargs,
                                           'MDOC_OUTARG_BLOCK_MARKER',
                                           'MDOC_OUTARG_MARKER', 'MDOC_OUTARG')
        snip = self.compose_arg_snip_lines(snip, inargs + outargs,
                                           'MDOC_ARG_BLOCK_MARKER',
                                           'MDOC_ARG_MARKER', 'MDOC_ARG')

        # remove lines with just MARKERS
        snip = re.sub(r'^[%\s]+\${\w+MARKER}', '%', snip, flags=re.M)
        # remove sequential empty lines
        snip = re.sub(r'^[%\s]+\n^[%\s]+$', '%', snip, flags=re.M)

        return snip

    def compose_arg_snip_lines(self, snip, args, mdoc_block_marker,
                               mdoc_arg_marker, mdoc_arg):
        """Compose function argument part of snippet, line by line
        """
        # check if argument block is specified in mdoc snippet
        mo = re.search(r'^.*\${' + mdoc_block_marker + '}', snip, re.M)
        if mo:
            if args:
                mo = re.search(
                    r'^.*\${' + mdoc_arg_marker + '}.*$', snip, re.M)
                if not (mo and re.search(r'\${' + mdoc_arg + '}', mo.group())):
                    msg = '[ERROR] AutoMatlab - Mdoc argument (marker) field' \
                        'is missing for ${' + mdoc_block_marker + '}' \
                        ' of mdoc snippet.'
                    self.view.window().status_message(msg)
                    raise Exception(msg)
                    return

                # create argument line template and extract tab index
                template = mo.group()
                mo = re.search(r'\${(\d+):', template)
                index = int(mo.group(1)) if mo else 0
                shift = 0
                # initialize with first argument snippet
                args_snip = re.sub(r'\${' + mdoc_arg + '}', args[0], template)
                for arg in args[1:]:
                    # shift tab indexes in arg snippet template
                    shift += 1
                    template = self.shift_tab_indexes(template)
                    # add arg to arg snip
                    args_snip += '\n' + \
                        re.sub(r'\${' + mdoc_arg + '}', arg, template)
                # shift tab indexes in snippet
                if index:
                    snip = self.shift_tab_indexes(snip, index, shift)
                # insert args_snip in snippet and return
                return re.sub(r'^.*\${' + mdoc_arg_marker + '}.*$', args_snip,
                              snip, flags=re.M)
            else:
                # clear argument related lines
                snip = re.sub(r'^.*\${' + mdoc_arg_marker + '}.*$', '', snip,
                              flags=re.M)
                snip = re.sub(r'^.*\${' + mdoc_block_marker + '}.*$', '', snip,
                              flags=re.M)
        return snip

    def shift_tab_indexes(self, snip, num=0, shift=1):
        """Shift all tab indexes higher than num by shift
        """
        # get all tab indexes
        mo = re.findall(r'\${(\d+):', snip)
        if mo:
            # shift tab indexes by shift
            for i in range(max([int(i) for i in mo]), num, -1):
                snip = re.sub(r'\${' + str(i) + r':',
                              '${' + str(i + shift) + ':', snip)
        return snip
