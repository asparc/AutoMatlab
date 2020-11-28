from os.path import join, abspath, split, isfile, getmtime
import random
import pickle
import collections
import re

import sublime
import sublime_plugin

from .mfun import mfun

# directory for saving completion data
COMPLETIONS_SAVE = join('data', 'completions')

# dict containter for storing completion data
completions = collections.OrderedDict({})
# last modification time for completion data
completions_mtime = 0

# some Matlab easter eggs
easter = ['spy', 'life', 'why', 'toilet', 'image', 'lala', 'penny', 'shower',
          'viper', 'fuc*', 'tetris_2', 'rlc_gui', 'sf_tictacflow', 'eml_fire',
          'eml_asteroids', 'xpsound', 'xpquad', 'wrldtrv', 'vibes', 'truss',
          'makevase', 'lorenz', 'knot', 'imageext', 'eigshow', 'earthmap',
          'census', 'cruller', 'imagesc(hot)', 'logo', 'surf(membrane)',
          'imagesAndVideo', 'step', 'fifteen', 'xpbombs', 'penny']


def load_completions():
    """Load stored completion data into completion dict
    """
    # check if completions data exists
    completions_path = join(split(abspath(__file__))[0], COMPLETIONS_SAVE)
    if isfile(completions_path):
        global completions, completions_mtime

        # check for update of completions data
        mtime = getmtime(completions_path)
        if mtime > completions_mtime:
            completions_mtime = mtime

            # read completions
            with open(completions_path, 'br') as fh:
                completions = pickle.load(fh)


def create_hrefs(details):
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
                # check if completions exist for function
                if ref and completions.get(ref.lower()):
                    # compose href for function
                    href = '<a href="{}">{}</a>'.format(ref.lower(), ref)
                    href_regex = r'\b' + ref + r'\b'
                    hrefs_see = re.sub(href_regex, href, hrefs_see)
        # replace referred function with href
        details = details.replace(mo_see.group(), hrefs_see)

    return details


class AutoMatlab(sublime_plugin.EventListener):

    """AutoMatlab event lister
    """

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

        # reload completions if necessary
        load_completions()

        # ignore case
        prefix = prefix.lower()

        # output container
        out = []

        # check for exact match
        exact = completions.get(prefix)
        if exact:
            # read mfun from mfile to extract all data
            mfun_data = mfun(exact[2])
            if mfun_data.valid:
                mfun_data.details = create_hrefs(mfun_data.details)
                for i in range(len(mfun_data.defs)):
                    out.append([mfun_data.fun + '\t' + mfun_data.defs[i],
                                mfun_data.snips[i]])
                if len(out) == 1:
                    out.append([mfun_data.fun + '\t Easter Egg',
                                easter[random.randrange(len(easter))]])

                # load settings to see if documentation popup should be shown
                settings = sublime.load_settings('AutoMatlab.sublime-settings')
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
                   for fun, data in completions.items()
                   if fun.startswith(prefix)]

        return out

    def update_details_popup(self, fun):
        """Process clicks on hrefs in the function details popup
        """
        mfun_data = mfun(completions.get(fun)[2])
        if mfun_data.valid:
            mfun_data.details = create_hrefs(mfun_data.details)
            self.popup_view.update_popup(mfun_data.details)

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
