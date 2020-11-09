from os.path import join, abspath, split, isfile, getmtime
import random
import pickle
import collections

import sublime
import sublime_plugin

from .mfun import mfun

COMPLETIONS_SAVE = join('data', 'completions')

completions = collections.OrderedDict({})
completions_mtime = 0

easter = ['spy', 'life', 'why', 'toilet', 'image', 'lala', 'penny', 'shower', 
'viper', 'fuc*', 'tetris_2', 'rlc_gui', 'sf_tictacflow', 'eml_fire', 
'eml_asteroids', 'xpsound', 'xpquad', 'wrldtrv', 'vibes', 'truss', 'makevase', 
'lorenz', 'knot', 'imageext', 'eigshow', 'earthmap', 'census', 'cruller', 
'imagesc(hot)', 'logo', 'surf(membrane)', 'imagesAndVideo', 'step', 
'fifteen', 'xpbombs', 'penny']

def load_completions():
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


class AutoMatlab(sublime_plugin.EventListener):
    def on_query_completions(self, view, prefix, locations):
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
                for i in range(len(mfun_data.defs)):
                    out.append([mfun_data.fun + '\t' + mfun_data.defs[i],
                                mfun_data.snips[i]])
                if len(out) == 1:
                    out.append([mfun_data.fun + '\t Easter Egg', 
                        easter[random.randrange(len(easter))]])
                view.show_popup(mfun_data.details,
                                sublime.COOPERATE_WITH_AUTO_COMPLETE,
                                max_width=750, max_height=400)
        else:
            out = [[data[0] + '\t' + data[1], data[0]]
                   for fun, data in completions.items()
                   if fun.startswith(prefix)]

        return out

    def on_text_command(self, view, command_name, args):
        if not view.match_selector(view.sel()[0].a, 'source.matlab'):
            return []

        if view.is_auto_complete_visible() \
                and command_name == 'move' \
                and args['by'] == 'lines':
            settings = sublime.load_settings('AutoMatlab.sublime-settings')
            preserve = settings.get('preserve_up_down_keys', False)
            try:
                assert type(preserve) == bool, \
                    "[ERROR] AutoMatlab - preserve_up_down_keys is not of type 'bool'"
            except Exception as e:
                view.window().status_message(str(e))
                raise e
            if preserve:
                view.run_command('hide_popup')
                view.run_command('hide_auto_complete')
            return None

        if command_name == 'auto_complete' \
                and view.is_auto_complete_visible():
            view.run_command('hide_auto_complete'),
            view.run_command('hide_popup'),
            return None

    def on_post_text_command(self, view, command_name, args):
        if not view.match_selector(view.sel()[0].a, 'source.matlab'):
            return []

        # make sure popup disappears together with autocomplete
        if command_name == 'hide_auto_complete' \
                or (view.is_popup_visible() \
                and not view.is_auto_complete_visible()):
            view.run_command('hide_popup')