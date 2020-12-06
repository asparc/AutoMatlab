import random
import pickle
import collections
import re
import threading
from os import walk
from os.path import isfile, splitext, getmtime, join

import sublime
import sublime_plugin


def plugin_loaded():
    """Do imports that need to wait for Sublime API initilization
    """
    global abspath, mfun, constants
    import AutoMatlab.lib.constants as constants
    from AutoMatlab.lib.common import abspath
    from AutoMatlab.lib.mfun import mfun


# some Matlab easter eggs
EASTER = ['spy', 'life', 'why', 'toilet', 'image', 'lala', 'penny', 'shower',
          'viper', 'fuc*', 'tetris_2', 'rlc_gui', 'sf_tictacflow', 'eml_fire',
          'eml_asteroids', 'xpsound', 'xpquad', 'wrldtrv', 'vibes', 'truss',
          'makevase', 'lorenz', 'knot', 'imageext', 'eigshow', 'earthmap',
          'census', 'cruller', 'imagesc(hot)', 'logo', 'surf(membrane)',
          'imagesAndVideo', 'step', 'fifteen', 'xpbombs', 'penny']


class AutoMatlab(sublime_plugin.EventListener):

    """AutoMatlab event lister
    """

    def __init__(self):
        # containters for completion data
        self.matlab_completions = collections.OrderedDict({})
        self.project_completions = collections.OrderedDict({})
        self.loaded_project_completions = collections.OrderedDict({})
        # last modification time for completion data
        self.matlab_completions_mtime = 0
        self.loaded_project_completions_mtime = {}
        # threading
        self.load_project_thread = threading.Thread()
        self.project_completions_lock = threading.Lock()
        # flags
        self.warned = False

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

        # load matlab completions
        if settings.get('matlab_completions', True):
            self.load_matlab_completions(view.window())

        if settings.get('project_completions', True):
            # load project completions
            self.project_completions_lock.acquire()
            self.project_completions = self.loaded_project_completions.get(
                view.window().extract_variables().get('project_base_name'), {})
            self.project_completions_lock.release()
        if not self.project_completions \
                and settings.get('current_folder_completions', True):
            # load current folder completions
            self.project_completions_lock.acquire()
            self.project_completions = self.loaded_project_completions.get(
                view.window().extract_variables().get('file_path'), {})
            self.project_completions_lock.release()

        if settings.get('current_file_completions', True):
            pass

        # ignore case
        prefix = prefix.lower()

        # output container
        out = []

        # check for exact match
        exact = self.project_completions.get(prefix)
        if not exact:
            exact = self.matlab_completions.get(prefix)
        if exact:
            # read mfun from mfile to extract all data
            mfun_data = mfun(exact[2])
            if mfun_data.valid:
                mfun_data.details = self.create_hrefs(mfun_data.details)
                for i in range(len(mfun_data.defs)):
                    out.append([mfun_data.fun + '\t' + mfun_data.defs[i],
                                mfun_data.snips[i]])
                if len(out) == 1:
                    out.append([mfun_data.fun + '\t Easter Egg',
                                EASTER[random.randrange(len(EASTER))]])

                # load settings to see if documentation popup should be shown
                documentation_popup = settings.get(
                    'documentation_popup', False)
                if documentation_popup:
                    view.show_popup(mfun_data.details,
                                    sublime.COOPERATE_WITH_AUTO_COMPLETE,
                                    max_width=750, max_height=400,
                                    on_navigate=self.update_details_popup)
                    self.popup_view = view
        else:
            out = [[data[0] + '\t' + data[1], data[0]]
                   for fun, data in self.project_completions.items()
                   if fun.startswith(prefix)] \
                + [[data[0] + '\t' + data[1], data[0]]
                   for fun, data in self.matlab_completions.items()
                   if fun.startswith(prefix)]
        return out

    def on_text_command(self, view, command_name, args):
        """Redefine a number of sublime commands to obtain smoother
        behaviour. Mainly focused on reloading the completion list and
        on hiding the function details popup.
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
        on hiding the function details popup.
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
        if not view.match_selector(0, 'source.matlab'):
            return

        # udpate project completions
        self.load_project_completions_thread(view.window())

    def on_activated(self, view):
        """Create project completions upon first loading of mfile
        """
        if not view.match_selector(0, 'source.matlab'):
            return

        # create project completions
        self.load_project_completions_thread(view.window(), False)

    def load_project_completions_thread(self, window, update=True):
        """Start worker thread to load project completions
        """
        # read settings
        settings = sublime.load_settings('AutoMatlab.sublime-settings')

        # check project type: sublime project or matlab current folder
        project = ""
        if settings.get('project_completions', True):
            project = window.extract_variables().get('project_base_name')
            project_info = window.extract_variables()

        if not project and settings.get('current_folder_completions', True):
            project = window.extract_variables().get('file_path')
            project_info = project

        if not project:
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
                args=(project_info, window.project_data(), window.folders()))
            self.load_project_thread.start()

    def load_project_completions(self, project_info, project_settings,
                                 project_folders):
        """Load project-specific completion data into completion dict
        """
        completions = {}
        include_dirs = None
        exclude_dirs = []
        exclude_patterns = []

        if type(project_info) == str:
            # case: use working dir
            project = project_info
            include_dirs = [abspath('+', project_info), 
                abspath(join('private', '+'), project_info)]
        else:
            # case: use project dir(s)
            project = project_info.get('project_base_name')
            folder = project_info.get('folder')
            if not project or not folder:
                return None

            # get project dirs
            settings = project_settings.get('auto_matlab')
            if settings:
                # read project dirs from settings
                include_dirs = abspath(settings.get(
                    'include_dirs', None), folder, project_info)
                exclude_dirs = abspath(settings.get(
                    'exclude_dirs', []), folder, project_info)
                exclude_patterns = settings.get(
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

        popped_key = ""
        # update project completions dict and modified time
        self.project_completions_lock.acquire()
        self.loaded_project_completions[project] = sorted_completions
        # ensure loaded project completions size stays within sane limits
        if len(self.loaded_project_completions) \
                > constants.MAX_LOADED_PROJECT_COMPLETIONS:
            popped_key = self.loaded_project_completions.popitem(False)[0]
        self.project_completions_lock.release()
        self.loaded_project_completions_mtime[project] = last_mtime
        self.loaded_project_completions_mtime.pop(popped_key, None)

    def load_matlab_completions(self, window):
        """Load stored matlab completion data into completion dict
        """
        # check if matlab_completions data exists
        if isfile(constants.MATLAB_COMPLETIONS_PATH):
            # check for update of matlab_completions data
            mtime = getmtime(constants.MATLAB_COMPLETIONS_PATH)
            if mtime > self.matlab_completions_mtime:
                self.matlab_completions_mtime = mtime

                # read matlab_completions
                with open(constants.MATLAB_COMPLETIONS_PATH, 'br') as fh:
                    self.matlab_completions = pickle.load(fh)
        else:
            if not self.warned:
                self.warned = True
                msg = '[WARNING] AutoMatlab - No Matlab completions found. ' \
                    'Try generating them through the command palette.'
                print(msg)
                window.status_message(msg)

    def create_hrefs(self, details):
        """Detailed Matlab function documentation contains references to
        other function ("see also"). Extract these references and wrap them
        in html href tags.
        """
        # locate 'see also'
        see_regex = re.compile(r'<p>see also:?\s*(.*?)\.?<\/p>', re.I)
        mo_see = see_regex.search(details)

        # extract referred functions
        if mo_see:
            hrefs_see = mo_see.group()
            for parts in mo_see.group(1).split(','):
                for ref in parts.split('<br>'):
                    ref = ref.strip()
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
            details = details.replace(mo_see.group(), hrefs_see)

        return details

    def update_details_popup(self, fun):
        """Process clicks on hrefs in the function details popup
        """
        # get mfun data from project or matlab completions
        if fun in self.project_completions.keys():
            mfun_data = mfun(self.project_completions.get(fun)[2])
        else:
            mfun_data = mfun(self.matlab_completions.get(fun)[2])

        # update popup contents
        if mfun_data.valid:
            mfun_data.details = self.create_hrefs(mfun_data.details)
            self.popup_view.update_popup(mfun_data.details)
