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
        self.check_exact_match = False
        # other
        self.locfun_regex = \
            re.compile(r'^\s*function\s+(?:(?:\w+\s*=\s*|'
                       r'\[[\w\s\.,]+\]\s*=\s*)?(\w+)\([^\)]*(\)|\.\.\.))')

    def get_mfun_data(self, window, fun, init=True):
        """Obtain mfun_data for the specified function
        """
        fun_low = fun.lower()

        # read settings
        settings = sublime.load_settings('AutoMatlab.sublime-settings')

        if init:
            # load from file completions
            if settings.get('current_file_completions', True):
                self.load_file_completions(window.extract_variables().get('file'))

            if fun_low in self.file_completions.keys():
                return mfun(window.extract_variables().get('file'),
                    'Local function', local=fun_low)

        # load project/folder completions
        if not self.project_completions:
            project = ''
            # check project type: sublime project or matlab current folder
            if settings.get('project_completions', True):
                project = window.extract_variables().get('project_base_name')
                project_info = window.extract_variables()
            if not project and settings.get('current_folder_completions', True):
                if len(window.folders()) == 1:
                    project = window.folders()[0]
                else:
                    project = window.extract_variables().get('file_path')
                project_info = project
            if project and project_info:
                self.load_project_completions(project_info, window.project_data(), 
                    window.folders(), True)
                self.project_completions = self.loaded_project_completions.get(
                    window.extract_variables().get('project_base_name'), {})

        if fun_low in self.project_completions.keys():
            if window.project_data():
                project_settings = window.project_data().get(
                    'auto_matlab', {})
            else:
                project_settings = {}
            free_format = project_settings.get('free_documentation_format')
            if free_format == None \
                    or not settings.get('project_completions', True):
                free_format = settings.get('free_documentation_format', True)
            # read mfun from mfile to extract all data
            if free_format:
                return mfun(self.project_completions[fun_low][2],
                    'Project function', deep=init)
            else:
                return mfun(self.project_completions[fun_low][2], 
                    deep=init)

        # load matlab completions
        if (not self.matlab_completions) \
                and settings.get('matlab_completions', True):
            self.load_matlab_completions()

        # read matlabroot
        matlabroot = settings.get('matlabroot', 'default')
        if matlabroot == 'default':
            matlabroot = config.DEFAULT_MATLABROOT
        else:
            matlabroot = abspath(matlabroot)
        
        if fun_low in self.matlab_completions.keys():
            return mfun(abspath(self.matlab_completions[fun_low][2],
                matlabroot), deep=init)

        return None


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

        # check for exact match
        mfun_data = None
        prefix_low = prefix.lower()
        links = ''
        if self.check_exact_match:
            self.check_exact_match = False
            if prefix_low in file_completions.keys():
                mfun_data = mfun(view.window().extract_variables().get('file'),
                    'Local function', local=prefix_low)
                links = \
                    "<a href=\'subl:goto_line {{\"line\":\"{}\"}}\'>Goto</a>".format(
                    file_completions[prefix_low][2]) \
                    + " " + \
                    "<a href=\'subl:show_auto_matlab_documentation_panel {{\"fun\":\"{}\"}}\'>Panel</a>".format(
                        prefix_low)
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
                links = \
                    "<a href=\'subl:open_file {{\"file\":\"{}\"}}\'>Goto</a>".format(
                    abspath(mfun_data.path).replace('\\','\\\\')) \
                    + " " + \
                    "<a href=\'subl:show_auto_matlab_documentation_panel {{\"fun\":\"{}\"}}\'>Panel</a>".format(
                        prefix_low)
            elif prefix_low in self.matlab_completions.keys():
                # read mfun from mfile to extract all data
                mfun_data = mfun(abspath(self.matlab_completions[prefix_low][2],
                    matlabroot), deep=True)
                links = \
                    "<a href=\'subl:open_file {{\"file\":\"{}\"}}\'>Goto</a>".format(
                    abspath(mfun_data.path, matlabroot).replace('\\','\\\\')) \
                    + " " + \
                    "<a href=\'subl:show_auto_matlab_documentation_panel {{\"fun\":\"{}\"}}\'>Panel</a>".format(
                        prefix_low)
                if mfun_data.help_browser:
                    links += " " + \
                    "<a href=\'subl:open_url {{\"url\":\"{}\"}}\'>Browser</a>".format(
                    mfun_data.help_browser.replace('\\','\\\\'))
                if mfun_data.help_web:
                    links += " " + \
                    "<a href=\'subl:open_url {{\"url\":\"{}\"}}\'>Web</a>".format(
                    mfun_data.help_web)

        # check if data for exact match found
        if mfun_data and mfun_data.valid:
            # build completion list
            compl = []
            for i in range(len(mfun_data.snips)):
                compl.append(sublime.CompletionItem(
                    mfun_data.fun,
                    annotation=mfun_data.defs[i],
                    completion=mfun_data.snips[i],
                    completion_format = sublime.COMPLETION_FORMAT_SNIPPET,
                    kind=(sublime.KIND_ID_SNIPPET,'s','Documentation'),
                    details=links
                ))

            # add easter egg to force >1 items in completion list
            if len(compl) == 1:
                compl.append(sublime.CompletionItem(
                    mfun_data.fun,
                    annotation='Easter Egg',
                    completion=config.EASTER[random.randrange(
                                len(config.EASTER))],
                    kind=sublime.KIND_SNIPPET,
                    details=links
                ))

            # finalize completion list
            cl = sublime.CompletionList(compl, 
                flags=sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_REORDER 
                | sublime.INHIBIT_EXPLICIT_COMPLETIONS);

            # load settings to see if documentation popup should be shown
            documentation_popup = settings.get('documentation_popup', False)
            if documentation_popup:
                view.show_popup(self.create_hrefs(mfun_data.html),
                                sublime.COOPERATE_WITH_AUTO_COMPLETE,
                                max_width=750, max_height=400,
                                on_navigate=self.update_documentation_popup)
                self.popup_view = view

        else:

            # check for partial prefix_low match
            compl = [
                sublime.CompletionItem(
                    data[0],
                    annotation=data[1],
                    completion=data[0],
                    kind=(sublime.KIND_ID_FUNCTION, 'l', 'Local function'))
                for fun, data in file_completions.items()
                if fun.startswith(prefix_low)
                ] + [
                sublime.CompletionItem(
                    data[0],
                    annotation=data[1],
                    completion=data[0],
                    kind=(sublime.KIND_ID_FUNCTION, 'p', 'Project function'))
                for fun, data in self.project_completions.items()
                if fun.startswith(prefix_low)
                ] + [
                sublime.CompletionItem(
                    data[0],
                    annotation=data[1],
                    completion=data[0],
                    kind=(sublime.KIND_ID_FUNCTION, 'b', 'Built-in function'))
                for fun, data in self.matlab_completions.items()
                if fun.startswith(prefix_low)]

            cl = sublime.CompletionList(compl)

        if not compl and view.is_popup_visible():
            view.hide_popup()

        return cl


    def on_text_command(self, view, command_name, args):
        """Redefine a number of sublime commands to obtain smoother
        behaviour. Mainly focused on reloading the completion list and
        on hiding the function documentation popup.
        """
        if not view.match_selector(0, 'source.matlab'):
            return []
        
        if command_name == 'auto_complete':
            self.check_exact_match = True
            return None


    def on_post_text_command(self, view, command_name, args):
        """Redefine a number of sublime commands to obtain smoother
        behaviour. Mainly focused on reloading the completion list and
        on hiding the function documentation popup.
        """
        if not view.match_selector(0, 'source.matlab'):
            return []

        # make sure popup disappears together with autocomplete
        if command_name == 'hide_popup':
            view.run_command('hide_auto_complete')


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
            iLine = 0
            while len(line.strip()) == 0:
                try:
                    iLine += 1
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
                iLine += 1
                # find function definitions
                mo = self.locfun_regex.search(line)
                if mo:
                    fun = mo.group(1)
                    completions[fun.lower()] = [fun, 'Local function', iLine]

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


    def load_matlab_completions(self, window=None):
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
            if window:
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
            parts = mo_see.group(1).replace('<br>',' ').replace(
                ',',' ').replace('&nbsp;',' ').split()
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
                        ref_regex = r'\b' + ref + r'\b'
                        hrefs_see = re.sub(ref_regex, href, hrefs_see)
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


class ShowAutoMatlabDocumentationPanelCommand(sublime_plugin.TextCommand):

    """Run a command in Matlab, via AutoHotkey
    """

    def run(self, edit, fun=None):
        """Create panel with function documentation.
        """
        if not fun:
            # read function at cursor
            fun = self.view.substr(self.view.word(self.view.sel()[0]))
        
        # switch to output panel
        self.view.run_command('hide_auto_complete')
        self.view.run_command('hide_popup')
        window = self.view.window()
        window.destroy_output_panel('auto_matlab')
        panel = window.create_output_panel('auto_matlab')

        # reader to for function documentation
        fun_reader = AutoMatlabCompletionsListener()
        mfun_data = fun_reader.get_mfun_data(window, fun)

        if mfun_data:
            # find hrefs in text and preprocess text
            [text, hrefs] = self.find_hrefs(mfun_data.text, window, fun_reader)

            # make documentation title phantom
            title = '<p><b>{} - {}</b></p>'.format(mfun_data.fun, 
                            mfun.make_html_compliant(mfun_data.annotation))
            phantoms = [sublime.Phantom(sublime.Region(0,0), title, 
                sublime.LAYOUT_INLINE)]

            # make href phantoms
            for ref, loc in hrefs.items():
                phantoms.append(sublime.Phantom(sublime.Region(loc+1,loc+1), 
                    '<a href="{}">{}</a>'.format(ref.lower(), ref), 
                    sublime.LAYOUT_INLINE, self.update_documentation_panel))

            # fill output panel with documentation text
            panel.run_command("append", 
                {"characters": '\n' + text.rstrip() + ' '})

            # show output panel, with the phantoms
            self.phantom_set = sublime.PhantomSet(panel, 
                'auto_matlab_documentation')
            self.phantom_set.update(phantoms)
            window.run_command('show_panel', {'panel':'output.auto_matlab'})
        else:
            msg = '[WARNING] AutoMatlab - No documentation found' \
                + ' for function: {}.'.format(fun)
            if window:
                window.status_message(msg)


    def find_hrefs(self, text, window, fun_reader):
        """Detailed Matlab function documentation contains references to
        other function ("see also"). Extract these references wrap them
        in html href tags. Also provide their location and cut them from the
        text.
        """
        # locate 'see also'
        see_regex = re.compile(r'\n\s*see also:?\s*([\s\S]*?)\.?\n\n', re.I)
        mo_see = see_regex.search(text + '\n')

        # extract referred functions
        hrefs = {}
        if mo_see:
            start_see = mo_see.start()
            hrefs_see = mo_see.group()
            parts = mo_see.group(1).replace(',',' ').split()
            for ref in parts:
                if ref:
                    # check if completions exist for referred function
                    mfun_data = fun_reader.get_mfun_data(window, ref, False)
                    if mfun_data and mfun_data.valid:
                        # locate ref within hrefs_see and cut it out
                        ref_regex = r'\b' + ref + r'\b'
                        mo_ref = re.search(ref_regex, hrefs_see)
                        start = mo_ref.start()
                        end = start + len(ref)
                        hrefs_see = hrefs_see[:start] + hrefs_see[end:]
                        hrefs[ref] = start_see + start

            # replace referred function with href
            text = text.replace(mo_see.group().rstrip(), hrefs_see.rstrip())

        return text, hrefs

    def update_documentation_panel(self, fun):
        sublime.active_window().run_command(
            'show_auto_matlab_documentation_panel', {'fun':fun})

