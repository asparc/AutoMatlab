Features:

- Makes 'See also' links
- Classes are not supported
- Default keybinging for autocomplete: ctrl+space, not alt+/ (might be default in windows anyways?)
- Project-specific settings for autocompletion and mdoc

Todo for classes:
- Process class folders (@folders)
- Read class defintions (classdef)
- Produce class documentation from snippets

Only includes .m files with a certain documentation quality (according to template)

Project and current file autocompletions are refreshed upon save (so not if save is done externally, e.g. in Matlab)

- Combine with 
    + mlint via SublimeLinter! (other combos?)
    + AutoHotKey
    + MBeautifier? (as run_matlab_command)

- run matlab command (sublime variables accepted, extended with $line, $package_parent, $package_member)

- Only for windows, so far