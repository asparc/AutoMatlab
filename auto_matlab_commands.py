import re
import subprocess
import collections
import errno
from os import makedirs
from os.path import join, isfile, split
import xml.etree.ElementTree as ET

import sublime
import sublime_plugin

# initialize globals, necessary to communicate between
# SublimeCommand class and SublimeEventListener class
activating_command_panel = False
navigating_history = False
command_panel_view_id = None
last_typed_command = ""
last_highlighted_index = -1


def plugin_loaded():
    """Do imports that need to wait for Sublime API initilization
    """
    global config, abspath
    import AutoMatlab.lib.config as config
    from AutoMatlab.lib.abspath import abspath


def get_view_content(view_id):
    """Read content of specified view
    """
    view = sublime.View(view_id)
    return view.substr(sublime.Region(0, view.size()))


def extract_matlab_history():
    """Extract commands from matlab history
    """
    settings = sublime.load_settings('AutoMatlab.sublime-settings')
    history_length = settings.get('matlab_history_length', 100)
    history_path = settings.get('matlab_history_path', 'default')
    if history_path == 'default':
        history_path = config.DEFAULT_MATLAB_HISTORY_PATH
    else:
        history_path = abspath(history_path)

    if not isfile(history_path):
        return None

    # try reading history_path
    # (might yield error when simultaneously being writting by matlab?)
    try:
        root = ET.parse(history_path).getroot()
    except:
        return []

    history = []
    # get sessions from history and parse in reversed order
    for session in root.findall('session')[::-1]:
        # parse commands per sessions (in reversed order)
        for command in session[::-1]:
            # select commands (not timestamps)
            if command.get('execution_time'):
                history.append(command.text)
            if len(history) == history_length:
                break
        if len(history) == history_length:
            break

    return list(collections.OrderedDict.fromkeys(history))

class OpenAutoMatlabCommandPanelCommand(sublime_plugin.TextCommand):

    """Open the AutoMatlab command panel, for running commands in Matlab
    """

    def run(self, edit):
        """Open quick command panel for Matlab commands
        """
        # initialize variables
        global activating_command_panel, navigating_history, \
            last_typed_command, matlab_history
        activating_command_panel = True
        navigating_history = False
        last_typed_command = ""

        matlab_history = extract_matlab_history()
        if matlab_history == None:
            msg = '[WARNING] AutoMatlab - Specified History.xml is invalid'
            print(msg)
            self.view.window().status_message(msg)

        if matlab_history:
            # show matlab history in quick panel
            self.view.window().show_quick_panel(
                matlab_history, self.selected, sublime.MONOSPACE_FONT,
                0, self.highlighted)
        else:
            # show quick panel with 'empty history' message
            self.view.window().show_quick_panel(
                [config.EMPTY_MATLAB_HISTORY_MESSAGE], self.selected, 0,
                0, self.highlighted)

    def selected(self, index):
        """Process Matlab command selected in quick panel
        """
        if index == -1:
            # case: cancelled
            return

        if matlab_history:
            # case: selected from history
            self.view.window().run_command('run_matlab_command',
                                           {'command': matlab_history[index]})
        else:
            # case: no history, but enter was pressed to run command
            global last_typed_command
            self.view.window().run_command('run_matlab_command',
                                           {'command': last_typed_command})

    def highlighted(self, index):
        """Process change in highlighted Matlab command in quick panel
        """
        if not matlab_history:
            return

        global last_highlighted_index, last_typed_command, \
            command_panel_view_id, navigating_history
        if last_highlighted_index == -1:
            # initiliaze
            last_highlighted_index = index
            return

        # user is navigating with up/down arrows -> move cursor to EOL
        if get_view_content(command_panel_view_id) == last_typed_command:
            view = sublime.View(command_panel_view_id)
            view.run_command('move_to', {'to': 'eol', 'extend': False})

        # store selection
        last_typed_command = get_view_content(command_panel_view_id)
        last_highlighted_index = index


class InsertAutoMatlabHistoryCommand(sublime_plugin.TextCommand):

    """Insert selected history entry in the AutoMatlab command panel,
    if cursor is at EOL.
    """

    def run(self, edit):
        """Insert selected entry from quick panel as quick panel input
        """
        # check if command panel is open
        if not self.view.settings().get('auto_matlab_command_panel'):
            return

        # get current selection
        sel = self.view.sel()
        if not len(sel):
            return
        a = sel[0].begin()
        b = sel[0].end()

        # check if EOL case
        if matlab_history and b == self.view.size() and a == b:
            # insert history in EOl case
            self.view.replace(edit, sublime.Region(0, b),
                              matlab_history[last_highlighted_index])
            sel.clear()
            sel.add(sublime.Region(self.view.size(), self.view.size()))
        else:
            # normal 'right' behaviour
            self.view.run_command(
                'move', {"by": "characters", "forward": True})

class RunAutoMatlabCommandInputCommand(sublime_plugin.TextCommand):

    """Run the command from the input box of the AutoMatlab command panel
    """

    def run(self, edit):
        """Run command input from quick panel
        """
        # check if command panel is open
        if not self.view.settings().get('auto_matlab_command_panel'):
            return

        # get command, close panel, run command
        command = get_view_content(self.view.id())
        if command:
            self.view.window().run_command('run_matlab_command',
                                           {'command': command})
            self.view.window().run_command('hide_overlay')
        else:
            msg = '[Warning] AutoMatlab - No Matlab command provided'
            self.view.window().status_message(msg)


class AutoMatlabCommandPanelListener(sublime_plugin.EventListener):

    """Manage activation and deactivation of command panel
    """

    def on_activated(self, view):
        """Initialize quick panel for Matlab commands
        """
        # check if command panel was activated
        global activating_command_panel, command_panel_view_id
        if activating_command_panel:
            activating_command_panel = False
            # get matlab comand panel id
            command_panel_view_id = view.id()
            parent_id = view.window().active_sheet().view().id()
            # set view settings private to command panel
            view.settings().set('auto_matlab_command_panel', True)
            view.settings().set('auto_matlab_command_panel_parent', parent_id)
            # set status message
            sublime.View(parent_id).set_status(
                'auto_matlab_command_panel',
                '[RIGHT] Insert history, '
                '[TAB] Run input, '
                '[ENTER] Run selection')

    def on_deactivated(self, view):
        """Clean up quick panel for Matlab commands
        """
        global last_typed_command
        if view.settings().get('auto_matlab_command_panel'):
            # store last command
            last_typed_command = get_view_content(view.id())
            # remove status message
            parent_id = view.settings().get('auto_matlab_command_panel_parent')
            sublime.View(parent_id).erase_status('auto_matlab_command_panel')


class RunMatlabCommandCommand(sublime_plugin.WindowCommand):

    """Run a command in Matlab, via AutoHotkey
    """

    def run(self, command):
        """Run the provided command in Matlab, using AutoHotkey.
        Any sublime variable in the command will be replaced by its value.
        """
        # get sublime variables and extend for matlab
        vars = self.window.extract_variables()
        vars['line'] = str(1)
        vars['column'] = str(1)
        vars['selection'] = ''
        vars['package_parent'] = ''
        vars['package_member'] = ''

        # update current line and selection
        view = self.window.active_sheet().view()
        if len(view.sel()):
            rowcol = view.rowcol(view.sel()[0].a)
            vars['line'] = str(rowcol[0] + 1)
            vars['column'] = str(rowcol[1] + 1)

            for region in view.sel():
                vars['selection'] += view.substr(region)

        # update the matlab package parent and package member
        mo = re.search(r'(.*\\(?!\+).*?|.*)\\\+?(.*)\.m', vars['file'])
        if mo:
            vars['package_parent'] = mo.group(1)
            vars['package_member'] = re.sub(r'\\\+?', '.', mo.group(2))

        # substitute sublime variables in command
        command = sublime.expand_variables(command, vars)

        # read ahk settings
        settings = sublime.load_settings('AutoMatlab.sublime-settings')
        ahk_return_focus = settings.get('auto_hotkey_return_focus', True)
        ahk_sleep_multiplier = settings.get('auto_hotkey_sleep_multiplier', 1)
        ahk_path = settings.get('auto_hotkey_path', 'default')
        if ahk_path == 'default':
            ahk_path = config.DEFAULT_AUTO_HOTKEY_PATH

        # check ahk path
        if not isfile(ahk_path):
            msg = '[ERROR] AutoMatlab - Specified AutoHotkey path is invalid'
            self.window.status_message(msg)
            raise Exception(msg)
            return

        # find ahk script
        ahk_script_resource = sublime.find_resources(
            config.AUTO_HOTKEY_SCRIPT)[-1]
        ahk_script_path = abspath(ahk_script_resource,
                                  join(sublime.packages_path(), '..'))

        if not isfile(ahk_script_path):
            # create ahk dir
            try:
                makedirs(split(ahk_script_path)[0])
            except OSError as e:
                if e.errno != errno.EEXIST:
                    self.window.status_message(str(e))
                    raise e
                    return
            except Exception as e:
                self.window.status_message(str(e))
                raise e
                return
            # create ahk script
            with open(ahk_script_path, 'w') as fh:
                fh.write(sublime.load_resource(ahk_script_resource).replace(
                    '\r\n', '\n'))

        # run command
        subprocess.Popen([ahk_path,
                          ahk_script_path,
                          command,
                          '1' if ahk_return_focus else '0',
                          str(ahk_sleep_multiplier)])


class ToggleAutoHotkeyFocusCommand(sublime_plugin.WindowCommand):

    """Toggle whether AutoHotkey will return the focus to Sublime
    """

    def run(self):
        """Toggle whether AutoHotkey will return the focus to Sublime
        """
        # get settings
        settings = sublime.load_settings('AutoMatlab.sublime-settings')

        # update settings
        settings.set('auto_hotkey_return_focus',
                     False if settings.get('auto_hotkey_return_focus')
                     else True)

        # inform user
        if settings.get('auto_hotkey_return_focus'):
            msg = '[INFO] AutoMatlab - AutoHotkey return focus activated ' \
                '(non-persistent)'
        else:
            msg = '[INFO] AutoMatlab - AutoHotkey return focus deactiveted ' \
                '(non-persistent)'
        print(msg)
        self.window.status_message(msg)
