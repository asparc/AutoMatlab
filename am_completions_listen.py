import random
import pickle
import collections
import re
import threading
from os import walk
from os.path import isfile, splitext, getmtime, join, split

import sublime
import sublime_plugin


def plugin_loaded():
    """Do imports that need to wait for Sublime API initilization
    """
    global config, abspath, mfun
    import AutoMatlab.lib.config as config
    from AutoMatlab.lib.abspath import abspath
    from AutoMatlab.lib.mfun import mfun


class AutoMatlabCompletionsListener(sublime_plugin.EventListener):

    """Sublime event lister for completions
    """

    def __init__(self):
        # containters for completion data
        self.matlab_completions = collections.OrderedDict({})
        self.project_completions = collections.OrderedDict({})
        self.file_completions = collections.OrderedDict({})
        self.loaded_project_completions = collections.OrderedDict({})
        # last modification time for completion data
        self.matlab_completions_mtime = 0
        self.loaded_project_completions_mtime = {}
        # threading
        self.load_file_thread = threading.Thread()
        self.file_completions_lock = threading.Lock()
        self.load_project_thread = threading.Thread()
        self.project_completions_lock = threading.Lock()
        # flags
        self.warned = False
        self.reset_mtimes = True
        # other
        self.locfun_regex = \
            re.compile(r'^\s*function\s+(?:(?:\w+\s*=\s*|'
                       r'\[[\w\s\.,]+\]\s*=\s*)?(\w+)\([^\)]*(\)|\.\.\.))')

    def on_query_completions(self, view, prefix, locations):
        """Construct AutoMatlab completion list.

        Two cases are distinguised:
        - exact matches with the completion trigger of a matlab function
          yield detailed function documentation
        - prefix matches yield a list of matlab functions that start with
          the supplied prefix
        """
        if not view.match_selector(locations[0], 'source.matlab'):
            return []

        # read settings
        settings = sublime.load_settings('AutoMatlab.sublime-settings')

        # read matlabroot
        matlabroot = settings.get('matlabroot', 'default')
        if matlabroot == 'default':
            matlabroot = config.DEFAULT_MATLABROOT
        else:
            matlabroot = abspath(matlabroot)

        # load matlab completions
        if settings.get('matlab_completions', True):
            self.load_matlab_completions(view.window())
        else:
            self.matlab_completions_mtime = 0
            self.matlab_completions = collections.OrderedDict({})

        # load project/folder completions
        self.project_completions_lock.acquire()
        if settings.get('project_completions', True):
            # load project completions
            self.project_completions = self.loaded_project_completions.get(
                view.window().extract_variables().get('project_base_name'), {})
        else:
            self.project_completions = collections.OrderedDict({})
        if not self.project_completions:
            if settings.get('current_folder_completions', True):
                # load current folder completions
                if len(view.window().folders()) == 1:
                    self.project_completions = \
                        self.loaded_project_completions.get(
                            view.window().folders()[0], {})
                else:
                    self.project_completions = \
                        self.loaded_project_completions.get(
                            view.window().extract_variables().get(
                                'file_path'), {})
            else:
                self.project_completions = collections.OrderedDict({})
        self.project_completions_lock.release()

        # load file completions
        file_completions = {}
        if settings.get('current_file_completions', True):
            self.file_completions_lock.acquire()
            file_completions = self.file_completions
            self.file_completions_lock.release()

        # ignore case
        prefix_low = prefix.lower()

        # output container
        out = []
        html = ''

        # check for exact match
        if prefix_low in file_completions.keys():
            [out, html] = self.extract_local_function_documentation(
                view.window().extract_variables().get('file'), prefix)
        elif prefix_low in self.project_completions.keys():
            # read project documentation format from settings
            if view.window().project_data():
                project_settings = view.window().project_data().get(
                    'auto_matlab', {})
            else:
                project_settings = {}
            free_format = project_settings.get('free_documentation_format')
            if free_format == None \
                    or not settings.get('project_completions', True):
                free_format = settings.get('free_documentation_format', True)
            # read mfun from mfile to extract all data
            if free_format:
                mfun_data = mfun(self.project_completions[prefix_low][2],
                    'Project function', True)
            else:
                mfun_data = mfun(self.project_completions[prefix_low][2], 
                    deep=True)

            if mfun_data.valid:
                html = self.create_hrefs(mfun_data.html)
                for i in range(len(mfun_data.defs)):
                    out.append([mfun_data.fun + '\t' + mfun_data.defs[i],
                                mfun_data.snips[i]])
        elif prefix_low in self.matlab_completions.keys():
            # read mfun from mfile to extract all data
            mfun_data = mfun(abspath(self.matlab_completions[prefix_low][2],
                matlabroot), deep=True)
            if mfun_data.valid:
                html = self.create_hrefs(mfun_data.html)
                for i in range(len(mfun_data.defs)):
                    out.append([mfun_data.fun + '\t' + mfun_data.defs[i],
                                mfun_data.snips[i]])

        if out:
            # postprocess exact match output
            if len(out) == 1:
                out.append([out[0][0].split('\t')[0] + '\t Easter Egg',
                            config.EASTER[random.randrange(
                                len(config.EASTER))]])

            # load settings to see if documentation popup should be shown
            documentation_popup = settings.get(
                'documentation_popup', False)
            if documentation_popup:
                view.show_popup(html,
                                sublime.COOPERATE_WITH_AUTO_COMPLETE,
                                max_width=750, max_height=400,
                                on_navigate=self.update_documentation_popup)
                self.popup_view = view
        else:
            # check for partial prefix_low match
            out = [[data[0] + '\t' + data[1], data[0]]
                   for fun, data in file_completions.items()
                   if fun.startswith(prefix_low)] \
                + [[data[0] + '\t' + data[1], data[0]]
                   for fun, data in self.project_completions.items()
                   if fun.startswith(prefix_low)] \
                + [[data[0] + '\t' + data[1], data[0]]
                   for fun, data in self.matlab_completions.items()
                   if fun.startswith(prefix_low)]
        # return (out, sublime.INHIBIT_WORD_COMPLETIONS)
        return (out)

        comp = [
            sublime.CompletionItem(
                "fn",
                annotation="Ik sta rechts",
                completion="gefopt",
                kind=sublime.KIND_FUNCTION
            ),
            sublime.CompletionItem(
                "for",
                annotation="Ik sta ook rechts",
                completion="nutteloos",
                kind=(sublime.KIND_ID_FUNCTION, 'l', 'builtin'),
                details="<a><web>"
                # https://nl.mathworks.com/support/search.html?fq[]=asset_type_name:documentation/function&q=disp
            ),
        ]

        cl = sublime.CompletionList(comp, flags=sublime.INHIBIT_WORD_COMPLETIONS);
        return cl


    def on_text_command(self, view, command_name, args):
        """Redefine a number of sublime commands to obtain smoother
        behaviour. Mainly focused on reloading the completion list and
        on hiding the function documentation popup.
        """
        if not view.match_selector(0, 'source.matlab'):
            return []

        if view.is_auto_complete_visible() \
                and command_name == 'move' \
                and args['by'] == 'lines':
            # load settings to see if navigation should be overridden
            settings = sublime.load_settings('AutoMatlab.sublime-settings')
            ctrl_nav = settings.get('ctrl_completion_navigation', False)
            if ctrl_nav:
                view.run_command('hide_popup')
                view.run_command('hide_auto_complete')
            return None

        if command_name == 'auto_complete' \
                and view.is_auto_complete_visible():
            view.run_command('hide_auto_complete'),
            view.run_command('hide_popup'),
            return None

    def on_post_text_command(self, view, command_name, args):
        """Redefine a number of sublime commands to obtain smoother
        behaviour. Mainly focused on reloading the completion list and
        on hiding the function documentation popup.
        """
        if not view.match_selector(0, 'source.matlab'):
            return []

        # make sure popup disappears together with autocomplete
        if command_name == 'hide_auto_complete' \
                or (view.is_popup_visible()
                    and not view.is_auto_complete_visible()):
            view.run_command('hide_popup')

    def on_post_save(self, view):
        """Update project completions upon saving of mfile
        """
        # check if it was a sublime project/settings file that was saved
        file_name = view.window().extract_variables().get('file_name')
        if file_name:
            ext = splitext(file_name)[1]
            if ext == '.sublime-project' or ext == '.sublime-settings':
                self.reset_mtimes = True

        if not view.match_selector(0, 'source.matlab'):
            return

        # update file completions
        self.load_file_completions_thread(view.window())

        # update project completions
        self.load_project_completions_thread(view.window())

    def on_activated(self, view):
        """Create project completions upon first loading of mfile
        """
        if not view.match_selector(0, 'source.matlab'):
            return

        # create file completions
        self.load_file_completions_thread(view.window())

        # create project completions
        self.load_project_completions_thread(view.window(), self.reset_mtimes)

    def load_file_completions_thread(self, window):
        """Start worker thread to load current file completions
        """
        # read settings
        settings = sublime.load_settings('AutoMatlab.sublime-settings')
        if not settings.get('current_file_completions', True):
            return

        # check if thread is already running
        if self.load_file_thread.is_alive():
            return
        else:
            # create and start worker thread
            self.load_file_thread = threading.Thread(
                target=self.load_file_completions,
                args=(window.extract_variables().get('file'),))
            self.load_file_thread.start()

    def load_file_completions(self, file):
        """Load completion data from the local functions in the current file
        """
        if not file or not isfile(file):
            self.file_completions_lock.acquire()
            self.file_completions = collections.OrderedDict({})
            self.file_completions_lock.release()
            return

        completions = {}

        with open(file, encoding='cp1252') as fh:
            # find first non-empty line
            line = ''
            while len(line.strip()) == 0:
                try:
                    line = fh.readline()
                except:
                    self.file_completions_lock.acquire()
                    self.file_completions = collections.OrderedDict({})
                    self.file_completions_lock.release()
                    return
                if not line:
                    self.file_completions_lock.acquire()
                    self.file_completions = collections.OrderedDict({})
                    self.file_completions_lock.release()
                    return

            # start reading after first non-empty line
            for line in fh:
                # find function definitions
                mo = self.locfun_regex.search(line)
                if mo:
                    fun = mo.group(1)
                    completions[fun.lower()] = [fun, 'Local function']

        # sort the completions
        sorted_completions = collections.OrderedDict(
            sorted(completions.items()))

        # update file completions
        self.file_completions_lock.acquire()
        self.file_completions = sorted_completions
        self.file_completions_lock.release()

    def load_project_completions_thread(self, window, update=True):
        """Start worker thread to load project completions
        """
        # read settings
        settings = sublime.load_settings('AutoMatlab.sublime-settings')

        # check project type: sublime project or matlab current folder
        project = ''
        if settings.get('project_completions', True):
            project = window.extract_variables().get('project_base_name')
            project_info = window.extract_variables()

        if not project and settings.get('current_folder_completions', True):
            if len(window.folders()) == 1:
                project = window.folders()[0]
            else:
                project = window.extract_variables().get('file_path')
            project_info = project

        if not project or not project_info:
            return

        if not update:
            # don't update if project already exists
            self.project_completions_lock.acquire()
            loaded_projects = self.loaded_project_completions.keys()
            self.project_completions_lock.release()
            if project in loaded_projects:
                return

        # check if thread is already running
        if self.load_project_thread.is_alive():
            return
        else:
            # create and start worker thread
            self.load_project_thread = threading.Thread(
                target=self.load_project_completions,
                args=(project_info, window.project_data(),
                      window.folders(), self.reset_mtimes))
            self.load_project_thread.start()
            self.reset_mtimes = False

    def load_project_completions(self, project_info, project_settings,
                                 project_folders, reset_mtimes=False):
        """Load project-specific completion data into completion dict
        """
        completions = {}
        include_dirs = None
        exclude_dirs = []
        exclude_patterns = []
        settings = sublime.load_settings('AutoMatlab.sublime-settings')
        free_format = settings.get('free_documentation_format', True)

        if type(project_info) == str:
            # case: use working dir
            project = project_info
            if len(project_folders) == 1:
                # case: sublime working dir: include all subdirs ('*')
                include_dirs = [abspath('*', project_folders[0])]
            else:
                # case: matlab working dir: include all package dirs ('+')
                include_dirs = [abspath('+', project_info),
                                abspath(join('private', '+'), project_info)]
        else:
            # case: use project dir(s)
            project = project_info.get('project_base_name')
            folder = project_info.get('folder')
            if not project or not folder:
                return None

            # get project dirs
            project_settings_auto_matlab = project_settings.get(
                'auto_matlab', {})
            if project_settings_auto_matlab:
                # read project dirs from project_settings_auto_matlab
                include_dirs = abspath(project_settings_auto_matlab.get(
                    'include_dirs', None), folder, project_info)
                exclude_dirs = abspath(project_settings_auto_matlab.get(
                    'exclude_dirs', []), folder, project_info)
                exclude_patterns = project_settings_auto_matlab.get(
                    'exclude_patterns', [])
            if include_dirs == None:
                # set default project dirs if unspecified
                # (and also apply the exclude dirs)
                include_dirs = [abspath('*', d)
                                for d in project_folders
                                if not any([excl for excl in exclude_dirs
                                            if abspath(d).startswith(excl)])]
            if not include_dirs:
                return None

            # overwrite free_format on project level
            if 'free_documentation_format' \
                    in project_settings_auto_matlab.keys() \
                    and settings.get('project_completions', True):
                free_format = project_settings_auto_matlab.get(
                    'free_documentation_format', True)

        # reset modified time for completions, if necessary
        if reset_mtimes:
            for key in self.loaded_project_completions_mtime.keys():
                self.loaded_project_completions_mtime[key] = 0

        # get last update time for project completions
        if not self.loaded_project_completions_mtime.get(project):
            self.loaded_project_completions_mtime[project] = 0
        completions_mtime = self.loaded_project_completions_mtime[project]
        last_mtime = completions_mtime

        # parse project include dirs
        for include in include_dirs:
            # check wildcard
            if not include:
                continue
            wildcard = include[-1]
            if wildcard in ['+', '*']:
                include = include[:-1]
            for root, dirs, files in walk(include):
                # process file for completions
                for f in files:
                    # check if matlab file
                    [fun, ext] = splitext(f)
                    if not ext == '.m':
                        continue

                    # check if file changed since last time
                    file_mtime = getmtime(join(root, f))
                    if file_mtime > completions_mtime:
                        if file_mtime > last_mtime:
                            last_mtime = file_mtime
                        # read mfun
                        if free_format:
                            mfun_data = mfun(join(root, f), 'Project function')
                        else:
                            mfun_data = mfun(join(root, f))
                        if not mfun_data.valid:
                            continue

                        # add data to matlab completions
                        completions[mfun_data.fun.lower()] = \
                            [mfun_data.fun, mfun_data.annotation,
                             mfun_data.path]
                    else:
                        # copy previous completion
                        prev_completion = self.loaded_project_completions.get(
                            project, {}).get(fun)
                        if prev_completion:
                            completions[fun] = prev_completion
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

        # sort the completions
        sorted_completions = collections.OrderedDict(
            sorted(completions.items()))

        popped_key = ''
        # update project completions dict and modified time
        self.project_completions_lock.acquire()
        self.loaded_project_completions[project] = sorted_completions
        # ensure loaded project completions size stays within sane limits
        if len(self.loaded_project_completions) \
                > config.MAX_LOADED_PROJECT_COMPLETIONS:
            popped_key = self.loaded_project_completions.popitem(False)[0]
        self.project_completions_lock.release()
        self.loaded_project_completions_mtime[project] = last_mtime
        self.loaded_project_completions_mtime.pop(popped_key, None)

    def load_matlab_completions(self, window):
        """Load stored matlab completion data into completion dict
        """
        completions_name = split(config.MATLAB_COMPLETIONS_PATH)[-1]
        completions_path = abspath(
            sublime.find_resources(completions_name)[-1],
            join(sublime.packages_path(), ".."))

        if isfile(completions_path):
            # load user-generated matlab completions data
            mtime = getmtime(completions_path)
            # check for update of matlab_completions data
            if mtime > self.matlab_completions_mtime:
                self.matlab_completions_mtime = mtime

                # read matlab_completions
                with open(completions_path, 'br') as fh:
                    self.matlab_completions = pickle.load(fh)
        else:
            # load default matlab completions data
            if not self.matlab_completions:
                try:
                    # read binary sublime resource
                    completions_bytes = \
                        sublime.load_binary_resource(sublime.find_resources(
                            completions_name)[-1])
                    self.matlab_completions = pickle.loads(completions_bytes)
                except:
                    self.matlab_completions = collections.OrderedDict({})

        if not self.matlab_completions and not self.warned:
            self.warned = True
            msg = '[WARNING] AutoMatlab - No Matlab completions found. ' \
                'Try generating them through the command palette.'
            # print(msg)
            window.status_message(msg)

    def create_hrefs(self, html):
        """Detailed Matlab function documentation contains references to
        other function ("see also"). Extract these references and wrap them
        in html href tags.
        """
        # locate 'see also'
        see_regex = re.compile(
            r'<p>(?:&nbsp;)*see&nbsp;also:?(?:&nbsp;)*(.*?)\.?<\/p>', re.I)
        mo_see = see_regex.search(html)

        # extract referred functions
        if mo_see:
            hrefs_see = mo_see.group()
            parts = mo_see.group(1).replace('<br>',' ')
            parts = parts.replace(',',' ')
            parts = parts.replace('&nbsp;',' ')
            parts = parts.split()
            for ref in parts:
                if ref:
                    # check if completions exist for referred function
                    linkable = self.project_completions.get(ref.lower())
                    if not linkable:
                        linkable = self.matlab_completions.get(ref.lower())
                    if linkable:
                        # compose href for function
                        href = '<a href="{}">{}</a>'.format(ref.lower(),
                                                            ref)
                        href_regex = r'\b' + ref + r'\b'
                        hrefs_see = re.sub(href_regex, href, hrefs_see)
            # replace referred function with href
            html = html.replace(mo_see.group(), hrefs_see)

        return html

    def update_documentation_popup(self, fun):
        """Process clicks on hrefs in the function documentation popup
        """
        # load settings
        settings = sublime.load_settings('AutoMatlab.sublime-settings')
        # get mfun data from project or matlab completions
        if fun in self.project_completions.keys():
            # read project documentation format from settings
            if sublime.active_window().project_data():
                project_settings = sublime.active_window().project_data().get(
                    'auto_matlab', {})
            else:
                project_settings = {}

            free_format = project_settings.get('free_documentation_format')
            if free_format == None \
                    or not settings.get('project_completions', True):
                free_format = settings.get('free_documentation_format', True)

            # read mfun
            if free_format:
                mfun_data = mfun(self.project_completions.get(fun)[2],
                    'Project function', True)
            else:
                mfun_data = mfun(self.project_completions.get(fun)[2], 
                    deep=True)
        else:
            # read mfun
            matlabroot = settings.get('matlabroot', 'default')
            if matlabroot == 'default':
                matlabroot = config.DEFAULT_MATLABROOT
            else:
                matlabroot = abspath(matlabroot)

            mfun_data = mfun(abspath(self.matlab_completions.get(fun)[2],
                matlabroot), deep=True)

        # update popup contents
        if mfun_data.valid:
            self.popup_view.update_popup(self.create_hrefs(mfun_data.html))

    def extract_local_function_documentation(self, file, fun):
        """Extract documentation for local function
        """
        if not isfile(file):
            return [None, None]

        doc_regex = re.compile(r'^\s*%+[\s%]*(.*\S)')
        # end_regex = re.compile(r'^\s*[^%\s]') % end at first empty comment
        end_regex = re.compile(r'^\s*$')  # end at first empty line
        def_regex = re.compile(
            r'^\s*function(.*(' + fun + r')\(([^\)]*)\))', re.I)

        out = []
        doc = ''
        with open(file, encoding='cp1252') as fh:
            # find first non-empty line
            line = ''
            while len(line.strip()) == 0:
                try:
                    line = fh.readline()
                except:
                    return [None, None]
                if not line:
                    return [None, None]

            # start reading after first non-empty line
            found = False
            add = ''
            for line in fh:
                # combine multiline statements
                multiline = add + line.strip()
                if multiline.endswith('...'):
                    add = multiline[:-3]
                    continue
                else:
                    add = ''

                # find function definition
                mo = def_regex.search(multiline)
                if mo:
                    found = True
                    # read defintion
                    definition = mo.group(1).strip()
                    fun = mo.group(2)
                    # create snippet from defintiion
                    snip = mfun.definition_to_snippet(fun, mo.group(3))
                    # compose output
                    out = [fun + '\t' + definition, snip]
                    continue

                if found:
                    # read function documentation until end regex
                    if end_regex.search(line):
                        break

                    # append to function documentation
                    mo = doc_regex.search(line)
                    if mo:
                        if not doc:
                            # initialize doc
                            doc = '<p><b>{} - {}</b></p><p>'.format(
                                fun,'Local function')
                        # newline
                        if not (doc[-3:] == '<p>'
                                or doc[-4:] == '<br>'):
                            doc += '<br>'
                        # append to documentation paragraph
                        doc += mfun.make_html_compliant(mo.group(1))
                    else:
                        # start new documentation paragraph
                        doc += '</p><p>'

        # close documentation paragraph
        doc += '</p>'
        while doc[-7:] == '<p></p>':
            doc = doc[:-7]

        return [[out], doc]
