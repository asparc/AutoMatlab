Features:

- Makes 'See also' links
- Classes are not supported
- Default keybinging for autocomplete: ctrl+space, not alt+/ (might be default in windows anyways?)
- Project-specific settings for autocompletion and documentation:
    + Group: 'auto_matlab'
        * include_dirs
        * exclude_dirs
        * exclude_patterns
        * free_documentation_format
        * documentation_upper_case_signature
        * documentation_snippet

Only includes .m files with a certain documentation quality (according to template)

Project and current file autocompletions are refreshed upon save (so not if save is done externally, e.g. in Matlab)

- Combine with 
    + mlint via SublimeLinter! (other combos?)
    + AutoHotKey
    + MBeautifier? (as run_matlab_command)

- run matlab command (sublime variables accepted, extended with $line, $package_parent, $package_member)

- Only for windows, not for Mac or Linux

- Explain Ctrl+Space.... and that you have to press it twice because of Sublime....

Todo for classes:
- Process class folders (@folders)
- Read class defintions (classdef)
- Produce class documentation from snippets
