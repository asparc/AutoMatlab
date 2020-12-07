import re
from os.path import split, splitext, isfile

import AutoMatlab.lib.constants as constants

class mfun:
    """Class to extract function documentation from mfile.
    """

    def __init__(self, path):
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
                or self.file == constants.SIGNATURES_NAME \
                or self.file == constants.CONTENTS_NAME:
            return

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
            if not ('function' in line or line.strip()[0] == '%'):
                return

            # prepare regex patterns
            ann_regex = re.compile(r'^\s*%+[\s%]*' + self.fun + r'\s*(.*)',
                                   re.I)
            def_regex = re.compile(
                r'^\s*%+[\s%]*((?:\w+\s*=\s*|\[[\w\s\.,]+\]\s*=\s*)?'
                + self.fun + r'\([^\)]*\))', re.I)
            doc_regex = re.compile(r'^\s*%+[\s%]*(.*\S)')
            end_regex = re.compile(r'^\s*[^%\s]')
            snip_regex = re.compile(self.fun + r'\(([^\)]*)\)')

            # loop over lines
            last_def = False
            while line:
                if not self.annotation:
                    # look for annotation
                    mo = ann_regex.search(line.strip())
                    if mo:
                        self.annotation = mo.group(1)
                        # replace invalid html characters
                        ann = self.annotation
                        ann = ann.replace('&', '&amp;')
                        ann = ann.replace('<', '&lt;')
                        ann = ann.replace('>', '&gt;')
                        # add documentation header
                        self.details = '<p><b>{}</b></p>'.format(ann)
                        # start documentation paragraph
                        self.details += '<p>'
                else:
                    # look for function definitions
                    # interrupt at copyright message or at examples
                    lline = line.lower()
                    if 'example' in lline:
                        last_def = True
                    if '#codegen' in lline \
                            or 'copyright' in lline \
                            or end_regex.search(line):
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
                        new_details = mo.group(1)
                        # replace invalid html characters
                        new_details = new_details.replace('&', '&amp;')
                        new_details = new_details.replace('<', '&lt;')
                        new_details = new_details.replace('>', '&gt;')
                        # append to documentation paragraph
                        if not (self.details[-3:] == '<p>'
                                or self.details[-4:] == '<br>'):
                            self.details += '<br>'
                        self.details += new_details
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
                            params = mo.group(1).split(',')
                            snip = self.fun + '('
                            i = 1
                            for param in params:
                                if i > 1:
                                    snip += ', '
                                snip += '${{{}:{}}}'.format(i, param.strip())
                                i += 1
                            snip += ')$0'
                            self.snips.append(snip)

                            # set valid
                            self.valid = True

                # read next line
                try:
                    line = fh.readline()
                except:
                    return
