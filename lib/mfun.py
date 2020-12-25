import re
from os.path import split, splitext, isfile

import AutoMatlab.lib.config as config


class mfun:
    """Class to extract function documentation from mfile.
    """

    def __init__(self, path, free_format=False):
        # initialize data
        self.defs = []  # functions defintions
        self.snips = []  # snippets to insert, derived from defs
        self.annotation = ''  # one-line description
        self.details = ''  # multi-line documentation
        self.path = path  # mfile path
        [self.root, self.file] = split(self.path)  # [root dir, mfile name]
        [self.fun, self.ext] = splitext(self.file)  # [fuction name, ext]
        self.valid = False

        # check mfile validity
        if not isfile(self.path) or not self.ext == '.m' \
                or self.file == config.SIGNATURES_NAME \
                or self.file == config.CONTENTS_NAME:
            return

        if free_format:
            self.read_free_format()
        else:
            self.read_strict_format()

    def read_strict_format(self):
        """Read mfile, strictly expecting the documentation format employed
        by The Mathworks for their built-in functions.
        """
        # read mfile line by line
        with open(self.path, encoding='cp1252') as fh:
            # find first non-empty line
            line = ""
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
            doc_regex = re.compile(r'^\s*%+[\s%]*(.*\S)')
            # end_regex = re.compile(r'^\s*[^%\s]') % end at first empty comment
            end_regex = re.compile(r'^\s*$')  # end at first empty line
            snip_regex = re.compile(self.fun + r'\(([^\)]*)\)')

            # loop over lines
            last_def = False
            while line:
                if not self.annotation:
                    # look for annotation
                    mo = ann_regex.search(line.strip())
                    if mo:
                        # add annotation
                        self.annotation = mo.group(1)
                        # add documentation header and start new paragraph
                        self.details = '<p><b>{}</b></p><p>'.format(
                            mfun.make_html_compliant(self.annotation))
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
                        # close documentation paragraph
                        self.details += '</p>'
                        while self.details[-7:] == '<p></p>':
                            self.details = self.details[:-7]
                        return

                    # append to function documentation
                    mo = doc_regex.search(line)
                    if mo:
                        # newline
                        if not (self.details[-3:] == '<p>'
                                or self.details[-4:] == '<br>'):
                            self.details += '<br>'
                        # append to documentation paragraph
                        self.details += mfun.make_html_compliant(mo.group(1))
                    else:
                        # start new documentation paragraph
                        self.details += '</p><p>'

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

    def read_free_format(self):
        """Read mfile, accepting any kind of documentation format. This extracts
        less details from the documentation than the strict format does.
        """
        # read mfile line by line
        with open(self.path, encoding='cp1252') as fh:
            # find first non-empty line
            line = ""
            while len(line.strip()) == 0:
                try:
                    line = fh.readline()
                except:
                    return
                if not line:
                    return

            # check validity of first line
            if not line.strip().startswith('function'):
                return

            # prepare regex patterns
            doc_regex = re.compile(r'^\s*%+[\s%]*(.*\S)')
            # end_regex = re.compile(r'^\s*[^%\s]') % end at first empty comment
            end_regex = re.compile(r'^\s*$')  # end at first empty line
            def_regex = re.compile(
                r'^\s*function(.*' + self.fun + r'\(([^\)]*)\))', re.I)

            # get function definition from first line
            mo = def_regex.search(line)
            if not mo:
                return

            # read definition and create snippet from it
            self.defs = [mo.group(1).strip()]
            self.snips = [mfun.definition_to_snippet(self.fun, mo.group(2))]
            self.details = '<p><b>Project function</b></p>'
            self.annotation = 'Project function'
            self.valid = True

            # read next line
            try:
                line = fh.readline()
            except:
                return

            # read function documentation for details
            self.details += '<p>'
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
                    # newline
                    if not (self.details[-3:] == '<p>'
                            or self.details[-4:] == '<br>'):
                        self.details += '<br>'
                    # append to documentation paragraph
                    self.details += mfun.make_html_compliant(mo.group(1))
                else:
                    # start new documentation paragraph
                    self.details += '</p><p>'

                # read next line
                try:
                    line = fh.readline()
                except:
                    break

            # close documentation paragraph
            self.details += '</p>'
            while self.details[-7:] == '<p></p>':
                self.details = self.details[:-7]

    @staticmethod
    def make_html_compliant(text):
        """Replace invalid html characters
        """
        # replace invalid html characters
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
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
