import re
from os import listdir, walk
from os.path import join, normpath, isfile, isdir, \
    isabs, abspath, split, expanduser
import json
import pickle
import collections

import sublime
import sublime_plugin

from .mfun import mfun

# constants
DEFAULT_MATLABROOT = ('C:', 'C:/Program Files')
DEFAULT_MATLAB_PATHDEF_PATH = 'toolbox/local/pathdef.m'
SIGNATURES_NAME = 'functionSignatures.json'
CONTENTS_NAME = 'Contents.m'
COMPLETIONS_SAVE = 'data/completions'
DEFAULT_MDOC_SNIPPET_PATH = 'AutoMatlab/Snippets/mdoc.sublime-snippet'


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
        for d in DEFAULT_MATLABROOT:
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

    # check if matlab_pathdef_path is absolute path
    if not isabs(expanduser(normpath(matlab_pathdef_path))):
        matlab_pathdef_path = join(matlabroot,
                                   expanduser(normpath(matlab_pathdef_path)))

    if not isfile(matlab_pathdef_path):
        return []

    # open pathdef file
    with open(join(matlabroot, normpath(matlab_pathdef_path)),
              encoding='cp1252') as fh:
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
                        matlab_path_dirs.append(join(matlabroot,
                                                     normpath(mo.group(1))))
                else:
                    # read dir as absolute dir
                    mo = abs_dir_regex.search(line)
                    if mo:
                        matlab_path_dirs.append(normpath(mo.group(1)))
            # start processing at BEGIN ENTRIES
            if 'BEGIN ENTRIES' in line:
                process_line = True
            # read next line
            line = fh.readline()

    return matlab_path_dirs


class GenerateAutoMatlabCommand(sublime_plugin.WindowCommand):

    """Generate Matlab autocompletion information by parsing the
    current Matlab installation.

    TODO: Run in separate thread.
    """

    def run(self):
        self.completions = {}

        # read settings
        settings = sublime.load_settings('AutoMatlab.sublime-settings')
        matlab_search_dir = settings.get('matlabroot', 'default')
        matlab_pathdef_path = settings.get('matlab_pathdef_path',
                                           DEFAULT_MATLAB_PATHDEF_PATH)
        include_dirs = settings.get('include_dirs', [])
        exclude_dirs = settings.get('exclude_dirs', [])
        exclude_patterns = settings.get('exclude_patterns', [])
        use_contents_files = settings.get('use_contents_files', 'dir')
        use_signatures_files = settings.get('use_signatures_files', 'dir')
        use_matlab_path = settings.get('use_matlab_path', 'ignore')

        # assertions
        try:
            assert type(matlab_search_dir) == str, \
                "[ERROR] AutoMatlab - matlabroot is not of type 'str'"
            assert type(matlab_pathdef_path) == str, \
                "[ERROR] AutoMatlab - matlab_pathdef_path is not of type 'str'"
            assert type(include_dirs) == list, \
                "[ERROR] AutoMatlab - include_dirs is not of type 'list'"
            assert type(exclude_dirs) == list, \
                "[ERROR] AutoMatlab - exclude_dirs is not of type 'list'"
            assert type(exclude_patterns) == list, \
                "[ERROR] AutoMatlab - exclude_patterns is not of type 'list'"
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

        # process and complete include/exclude dirs
        include_dirs = [expanduser(normpath(d))
                        if isabs(expanduser(normpath(d)))
                        else expanduser(normpath(join(matlabroot, d)))
                        for d in include_dirs]
        exclude_dirs = [expanduser(normpath(d))
                        if isabs(expanduser(normpath(d)))
                        else expanduser(normpath(join(matlabroot, d)))
                        for d in exclude_dirs]

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
                    for file in listdir(path_dir):
                        self.compose_completion(mfun(join(path_dir, file)))

        # walk through files of matlab toolboxes
        for root, dirs, files in walk(join(matlabroot, 'toolbox')):
            # check exclude dirs and patterns
            if any([d for d in exclude_dirs if root.startswith(d)]) \
                    or any([p for p in exclude_patterns if p in root]):
                continue

            # process entire dirs
            if (use_signatures_files == 'dir' and SIGNATURES_NAME in files) \
                    or (use_contents_files == 'dir' and CONTENTS_NAME in files):
                for file in files:
                    self.compose_completion(mfun(join(root, file)))
                continue

            # process signature files
            if use_signatures_files == 'read' and SIGNATURES_NAME in files:
                for fun in process_signature(join(root, SIGNATURES_NAME)):
                    self.compose_completion(mfun(join(root, fun + '.m')))

            # process contents files
            if use_contents_files == 'read' and CONTENTS_NAME in files:
                for fun in process_contents(join(root, CONTENTS_NAME)):
                    self.compose_completion(mfun(join(root, fun + '.m')))

        # parse custom dirs
        for include_dir in include_dirs:
            parse_subdirs = False
            if include_dir[-1] == '*':
                include_dir = include_dir[:-1]
                parse_subdirs = True
            for root, dirs, files in walk(include_dir):
                # extract completion from file
                for f in files:
                    self.compose_completion(mfun(join(root, f)))
                # set which subdirs to include
                if parse_subdirs:
                    # subject to exclude patterns all
                    dirs[:] = [d for d in dirs
                        if not any([p for p in exclude_patterns if p in d])]
                else:
                    # exclude all
                    dirs[:] = []

        print(self.completions.keys())

        # sort results
        sorted_completions = collections.OrderedDict(
            sorted(self.completions.items()))

        # store results
        with open(join(split(abspath(__file__))[0],
                       normpath(COMPLETIONS_SAVE)), 'bw') as fh:
            pickle.dump(sorted_completions, fh)

        self.window.status_message(
            '[INFO] AutoMatlab - Found {}'.format(len(sorted_completions))
            + ' Matlab function completions')

    def compose_completion(self, mfun):
        if not mfun.valid:
            return

        # add data to completions
        self.completions[mfun.fun.lower()]=[mfun.fun,
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
                                      {'by': 'word_ends', 'forward': True})

class DocumentAutoMatlabCommand(sublime_plugin.TextCommand):

    """Generate a snippet for documenting matlab functions

    TODO: add matlab classes
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
        snip_path = normpath(settings.get('mdoc_snippet_path',
                                          DEFAULT_MDOC_SNIPPET_PATH))
        print('----', snip_path)
        if not isabs(snip_path):
            snip_path = join(sublime.packages_path(), snip_path)
        if isfile(snip_path):
            with open(snip_path) as fh:
                snip_all = fh.read()
        else:
            msg = '[ERROR] AutoMatlab - invalid mdoc snippet path.'
            self.view.window().status_message(msg)
            return

        # extract mdoc snippet content
        pattern = r'<!\[CDATA\[([\s\S]*)\]]>'
        mo = re.search(pattern, snip_all)
        if not mo:
            msg = '[ERROR] AutoMatlab - mdoc snippet could not ' \
                'be found.'
            self.view.window().status_message(msg)
            return
        snip = mo.group(1).strip()

        # some validity check on the mdoc snippet
        mo = re.findall(r'^[^\n]*\${MDOC_NAME_MARKER}', snip)
        if not mo:
            msg = '[ERROR] AutoMatlab - ${MDOC_NAME_MARKER} is compulsory in ' \
                'first line of mdoc snippet.'
            self.view.window().status_message(msg)
            return

        mo = re.findall(r'^\W*\${MDOC_NAME}', snip)
        if not mo:
            msg = '[ERROR] AutoMatlab - ${MDOC_NAME} is compulsory as ' \
                'first word of mdoc snippet.'
            self.view.window().status_message(msg)
            return

        mo = re.search(r'^[^\n]*(\${MDOC_\w*_MARKER}).+', snip, re.M)
        if mo:
            msg = '[ERROR] AutoMatlab - ' + mo.group(1) + ' should be at end ' \
                'of line in mdoc snippet.'
            self.view.window().status_message(msg)
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
            self.view.run_command(
                'insert_snippet', {'contents': snip + '\n\n'})
        else:
            msg = '[Warning] AutoMatlab - documentation already exists.'
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
                    msg = '[ERROR] AutoMatlab - mdoc argument (marker) field' \
                        'is missing for ${' + mdoc_block_marker + '}' \
                        ' of mdoc snippet.'
                    self.view.window().status_message(msg)
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
