import re
from os.path import split, splitext, isfile

import AutoMatlab.lib.config as config


class mfun:
    """Class to extract function documentation from mfile.
    """

    def __init__(self, path, annotation='', deep=False):
        # initialize data
        self.defs = []  # functions defintions
        self.snips = []  # snippets to insert, derived from defs
        self.annotation = annotation  # one-line description
        self.doc = ''  # multi-line documentation
        self.path = path  # mfile path
        [self.root, self.file] = split(self.path)  # [root dir, mfile name]
        [self.fun, self.ext] = splitext(self.file)  # [fuction name, ext]
        self.valid = False

        # check mfile validity
        if not isfile(self.path) or not self.ext == '.m' \
                or self.file == config.SIGNATURES_NAME \
                or self.file == config.CONTENTS_NAME:
            return

        if self.annotation:
            self.__check_validity()
            if self.valid and deep:
                self.__read_free_documentation()
        else:
            self.__read_annotation()
            if self.annotation:
                self.valid = True
                if deep:
                    self.__read_strict_documentation()

    
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

            # check validity of first line
            sline = line.strip()
            if not(sline.startswith('function')
                    or (sline[0] == '%' and self.fun.lower() in sline.lower())):
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

            # function definition found -> valid Matlab function
            self.valid = True


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
            doc_regex = re.compile(r'^\s*%+[\s%]*(.*\S)')
            # end_regex = re.compile(r'^\s*[^%\s]') % end at first empty comment
            end_regex = re.compile(r'^\s*$')  # end at first empty line
            snip_regex = re.compile(self.fun + r'\(([^\)]*)\)')

            # loop over lines
            last_def = False
            doc_started = False
            while line:
                if not self.doc:
                    # look for annotation line and start doc from there
                    mo = ann_regex.search(line.strip())
                    if mo:
                        self.doc = '<p><b>{} - {}</b></p><p>'.format(self.fun,
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
                        self.doc += '</p>'
                        while self.doc[-7:] == '<p></p>':
                            self.doc = self.doc[:-7]
                        return

                    # append to function documentation
                    mo = doc_regex.search(line)
                    if mo:
                        # newline
                        if not (self.doc[-3:] == '<p>'
                                or self.doc[-4:] == '<br>'):
                            self.doc += '<br>'
                        # append to documentation paragraph
                        self.doc += mfun.make_html_compliant(mo.group(1))
                        doc_started = True
                    else:
                        if doc_started:
                            # start new documentation paragraph
                            self.doc += '</p><p>'

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

            # make documentation with annotation and start new paragraph
            self.doc = '<p><b>{} - {}</b></p><p>'.format(self.fun, 
                mfun.make_html_compliant(self.annotation))

            # prepare regex patterns
            doc_regex = re.compile(r'^\s*%+[\s%]*(.*\S)')
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
            self.doc += '<p>'
            doc_started = False
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
                    if not (self.doc[-3:] == '<p>'
                            or self.doc[-4:] == '<br>'):
                        self.doc += '<br>'
                    # append to documentation paragraph
                    self.doc += mfun.make_html_compliant(mo.group(1))
                    doc_started = True
                else:
                    if doc_started:
                        # start new documentation paragraph
                        self.doc += '</p><p>'

                # read next line
                try:
                    line = fh.readline()
                except:
                    break

            # close documentation paragraph
            self.doc += '</p>'
            while self.doc[-7:] == '<p></p>':
                self.doc = self.doc[:-7]

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
