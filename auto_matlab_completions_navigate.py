import sublime
import sublime_plugin

class NavigateAutoMatlabCompletionsCommand(sublime_plugin.TextCommand):

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
