import re
from os.path import split, splitext, isfile, abspath, sep, join

import AutoMatlab.lib.config as config


class mfun:
    """Class to extract function documentation from mfile.
    """

    def __init__(self, path, annotation='', deep=False, local=''):
        # initialize data
        self.defs = [] # functions defintions
        self.snips = [] # snippets to insert, derived from defs
        self.annotation = annotation # one-line description
        self.doc = [] # multi-line documentation
        self.path = abspath(path)  # mfile path
        [self.root, self.file] = split(self.path)  # [root dir, mfile name]
        [self.fun, self.ext] = splitext(self.file)  # [fuction name, ext]
        if local:
            self.fun = local
        self.matlabroot = abspath(self.path.split('toolbox')[0])
        self.valid = False

        # check mfile validity
        if not isfile(self.path) or not self.ext == '.m' \
                or self.file == config.SIGNATURES_NAME \
                or self.file == config.CONTENTS_NAME:
            return

        # handle local function separately
        if self.annotation:
            if 'local' in self.annotation.lower():
                self.__read_local_documentation()
            else:
                self.__check_validity()
                if self.valid and deep:
                    self.__read_free_documentation()
        else:
            self.__read_annotation()
            if self.annotation:
                self.valid = True
                if deep:
                    self.__read_strict_documentation()


    def __check_validity(self):
        """Check validity of mfile: does it contain a Matlab function?
        """
        # read mfile line by line
        with open(self.path, encoding='cp1252') as fh:
            # find first non-empty line
            line = ''
            while len(line.strip()) == 0:
                try:
                    line = fh.readline()
                except:
                    return
                if not line:
                    return

            # check validity of first line
            sline = line.strip()
            if not sline.startswith('function'):
                return

            # prepare regex patterns
            def_regex = re.compile(
                r'^\s*function(.*(' + self.fun + r')\(([^\)]*)\))', re.I)

            # get function definition from first line
            while sline.endswith('...'):
                # multiline definition
                try:
                    sline = sline[:-3] + fh.readline().strip()
                except:
                    return

            mo = def_regex.search(sline)
            if not mo:
                return

            # update function upper/lower case
            self.fun = mo.group(2)

            # function definition found -> valid Matlab function
            self.valid = True


    def __read_annotation(self):
        """Read annotation from mfile, expecting the documentation format 
        employed by The Mathworks for their built-in functions.
        """
        # read mfile line by line
        with open(self.path, encoding='cp1252') as fh:
            # find first non-empty line
            line = ''
            while len(line.strip()) == 0:
                try:
                    line = fh.readline()
                except:
                    return
                if not line:
                    return

            # check validity of first line and optionally update function name
            sline = line.strip()
            if sline.startswith('function'):
                # update function upper/lower case
                def_regex = re.compile(
                    r'^\s*function(.*(' + self.fun + r')\(([^\)]*)\))', re.I)
                mo = def_regex.search(sline)
                if mo:
                    # update function upper/lower case
                    self.fun = mo.group(2)
                else:
                    return
            elif sline[0] == '%' and self.fun.lower() in sline.lower():
                # function upper/lower case comes from file name
                pass
            else:
                return

            # prepare annotation regex pattern
            ann_regex = re.compile(
                r'^\s*%+[\s%]*' + self.fun + r'\s*(.*)', re.I)

            # loop over lines
            found = False
            while (not found) and line:
                # look for annotation
                mo = ann_regex.search(line.strip())
                if mo:
                    # add annotation
                    self.annotation = mo.group(1)
                    found = True

                # read next line
                try:
                    line = fh.readline()
                except:
                    return

    def __read_local_documentation(self):
        """Read documentation for local function
        """
        with open(self.path, encoding='cp1252') as fh:
            # find first non-empty line
            line = ''
            while len(line.strip()) == 0:
                try:
                    line = fh.readline()
                except:
                    return
                if not line:
                    return

            # prepare regex patterns
            doc_regex = re.compile(r'^\s*%+[\s%]*(.*\S)')
            # end_regex = re.compile(r'^\s*[^%\s]') % end at first empty comment
            end_regex = re.compile(r'^\s*$')  # end at first empty line
            def_regex = re.compile(
                r'^\s*function(.*(' + self.fun + r')\(([^\)]*)\))', re.I)

            # start reading after first non-empty line
            self.doc = []
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
                    # read defintion
                    self.defs = [mo.group(1).strip()]
                    # create snippet from defintiion
                    self.fun = mo.group(2)
                    self.snips = [mfun.definition_to_snippet(
                        self.fun, mo.group(3))]
                    self.valid = True

                if self.valid:
                    # read function documentation until end regex
                    if end_regex.search(line):
                        break

                    # append to function documentation
                    mo = doc_regex.search(line)
                    if mo:
                        self.doc.append(mo.group(1))
                    elif self.doc:
                        self.doc.append('')


    def __read_strict_documentation(self):
        """Read mfile, strictly expecting the documentation format employed
        by The Mathworks for their built-in functions.
        """
        # read mfile line by line
        with open(self.path, encoding='cp1252') as fh:
            # find first non-empty line
            line = ''
            while len(line.strip()) == 0:
                try:
                    line = fh.readline()
                except:
                    return
                if not line:
                    return

            # check validity of first line
            sline = line.strip()
            if not(sline.startswith('function')
                    or (sline[0] == '%' and self.fun.lower() in sline.lower())):
                return

            # prepare regex patterns
            ann_regex = re.compile(
                r'^\s*%+[\s%]*' + self.fun + r'\s*(.*)', re.I)
            def_regex = re.compile(
                r'^\s*%+[\s%]*((?:\w+\s*=\s*|\[[\w\s\.,]+\]\s*=\s*)?'
                + self.fun + r'\([^\)]*\))', re.I)
            doc_regex = re.compile(r'^\s*%+([\s%]*.*\S)')
            # end_regex = re.compile(r'^\s*[^%\s]') % end at first empty comment
            end_regex = re.compile(r'^\s*$')  # end at first empty line
            snip_regex = re.compile(self.fun + r'\(([^\)]*)\)')

            # loop over lines
            last_def = False
            self.doc = None
            while line:
                if self.doc == None:
                    # look for annotation line and start doc from there
                    mo = ann_regex.search(line.strip())
                    if mo:
                        self.doc = []
                else:
                    # look for function definitions
                    # interrupt at copyright message, examples or comments end
                    lline = line.lower()
                    if 'example' in lline:
                        last_def = True
                    if end_regex.search(line) \
                            or 'copyright' in lline:
                            # or '#codegen' in lline \
                            # or 'author(s):' in lline \
                            # or 'authors:' in lline \
                            # or 'revised:' in lline \
                        return

                    # append to function documentation
                    mo = doc_regex.search(line)
                    if mo:
                        self.doc.append(mo.group(1))
                    elif self.doc:
                        self.doc.append('')

                    if not last_def:
                        # extract function definitions
                        mo = def_regex.search(line)
                        if mo:
                            self.defs.append(mo.group(1).lower().replace(
                                self.fun.lower(), self.fun))

                            # create snippet from def
                            mo = snip_regex.search(self.defs[-1])
                            self.snips.append(mfun.definition_to_snippet(
                                self.fun, mo.group(1)))

                            # set valid
                            self.valid = True

                # read next line
                try:
                    line = fh.readline()
                except:
                    return


    def __read_free_documentation(self):
        """Read mfile, accepting any kind of documentation format. This extracts
        less semantic details from the documentation as compared to the strict
        documentation format.
        """
        # read mfile line by line
        with open(self.path, encoding='cp1252') as fh:
            # find first non-empty line
            line = ''
            while len(line.strip()) == 0:
                try:
                    line = fh.readline()
                except:
                    return
                if not line:
                    return

            # check validity of first line
            sline = line.strip()
            if not sline.startswith('function'):
                return

            # prepare regex patterns
            doc_regex = re.compile(r'^\s*%+([\s%]*.*\S)')
            # end_regex = re.compile(r'^\s*[^%\s]') % end at first empty comment
            end_regex = re.compile(r'^\s*$')  # end at first empty line
            def_regex = re.compile(
                r'^\s*function(.*' + self.fun + r'\(([^\)]*)\))', re.I)

            # get function definition from first line
            while sline.endswith('...'):
                # multiline definition
                try:
                    sline = sline[:-3] + fh.readline().strip()
                except:
                    return

            mo = def_regex.search(sline)
            if not mo:
                return

            # read definition and create snippet from it
            self.defs = [mo.group(1).strip()]
            self.snips = [mfun.definition_to_snippet(self.fun, mo.group(2))]
            self.valid = True

            # read next line
            try:
                line = fh.readline()
            except:
                return
            if not line:
                return

            # read function documentation
            self.doc = []
            while line:
                # interrupt at copyright message or comments end
                lline = line.lower()
                if end_regex.search(line) \
                        or 'copyright' in lline:
                        # or '#codegen' in lline \
                        # or 'author(s):' in lline \
                        # or 'authors:' in lline \
                        # or 'revised:' in lline \
                    break

                # append to function documentation
                mo = doc_regex.search(line)
                if mo:
                    self.doc.append(mo.group(1))
                elif self.doc:
                    self.doc.append('')

                # read next line
                try:
                    line = fh.readline()
                except:
                    break

    @property
    def html(self):
        """Format docstring in html"""

        if not self.valid:
            return ''

        # header
        html = '<p><b>{} - {}</b></p><p>'.format(self.fun, 
                        mfun.make_html_compliant(self.annotation))
        if not self.doc:
            return html

        # get minimum whitespace in doc
        crop = min([len(line) - len(line.lstrip()) 
                   for line in self.doc if line.strip()])

        # body
        for line in self.doc:
            if not line.strip():
                # start new documentation paragraph
                html += '</p><p>'
            else:
                # newline
                if not (html[-3:] == '<p>'
                        or html[-4:] == '<br>'):
                    html += '<br>'
                # append to documentation paragraph
                html += mfun.make_html_compliant(line[crop:])

        # close final paragraph
        html += '</p>'
        while html[-7:] == '<p></p>':
            html = html[:-7]

        return html

    @property
    def text(self):
        """Format docstring in html"""

        if not self.valid or not self.doc:
            return ''

        # get minimum whitespace in doc
        crop = min([len(line) - len(line.lstrip()) 
                   for line in self.doc if line.strip()])

        # body
        text = ''
        for line in self.doc:
            if line.strip():
                # append to documentation paragraph
                text += line[crop:]
            text += '\n'

        return text

    @property
    def panel(self):
        """Format docstring in html"""

    @property
    def help_browser(self):
        """Get path to Matlab help file."""

        rel_url = self.__get_help_rel_url()
        if rel_url:
            return join(self.matlabroot, rel_url)
        else:
            return None

    @property
    def help_web(self):
        """Get url to Matlab help webpage."""

        rel_url = self.__get_help_rel_url()
        if rel_url:
            return 'https://www.mathworks.com/' + rel_url.replace('\\','/')
        else:
            return None


    def __get_help_rel_url(self):
        """Get relative url to Matlab help page."""

        if not 'toolbox' in self.path:
            return None

        # search in default matlab help
        help = join('help', 'matlab', 'ref', self.fun + '.html')
        if isfile(join(self.matlabroot, help)):
            return help

        # search in toolbox help
        parts = self.path.split(sep)
        idx = parts.index('toolbox')
        if len(parts) > idx + 1:
            toolbox = parts[idx + 1]
            if toolbox == 'shared' and len(parts) > idx + 2:
                toolbox = parts[idx + 2]
                if toolbox.endswith('lib'):
                    toolbox = toolbox[:-3]
            help = join('help', toolbox, self.fun + '.html')
            if isfile(join(self.matlabroot, help)):
                return help
            help = join('help', toolbox, 'ref', self.fun + '.html')
            if isfile(join(self.matlabroot, help)):
                return help
            help = join('help', toolbox, 'ug', self.fun + '.html')
            if isfile(join(self.matlabroot, help)):
                return help
            help = join('help', toolbox, 'slref', self.fun + '.html')
            if isfile(join(self.matlabroot, help)):
                return help

        # give up
        return None

    @staticmethod
    def make_html_compliant(text):
        """Replace invalid html characters
        """
        # replace invalid html characters
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        text = text.replace(' ', '&nbsp;')
        return text

    @staticmethod
    def definition_to_snippet(fun, params):
        """Transform function defintion into sublime snippet
        """
        snip = fun + '('
        i = 1
        # split params string in individual params
        for param in params.split(','):
            if i > 1:
                snip += ', '
            # add sublime field markers to snippet
            snip += '${{{}:{}}}'.format(i, param.strip())
            i += 1
        snip += ')$0'
        return snip
