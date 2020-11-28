import re
from os.path import split, splitext, isfile

SIGNATURES_NAME = 'functionSignatures.json'
CONTENTS_NAME = 'Contents.m'

class mfun:

    """Tools to extract function info from mfile description.
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
                or self.file == SIGNATURES_NAME \
                or self.file == CONTENTS_NAME:
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
                    if 'copyright' in lline \
                            or 'author(s):' in lline \
                            or 'authors:' in lline \
                            or 'revised:' in lline \
                            or '#codegen' in lline \
                            or end_regex.search(line):
                        # close documentation paragraph
                        if self.details[-3:] == '<p>':
                            self.details = self.details[:-3]
                        else:
                            self.details += '</p>'
                        return

                    # append to function documentation
                    mo = doc_regex.search(line)
                    if mo:
                        details = mo.group(1)
                        # replace invalid html characters
                        details = details.replace('&', '&amp;')
                        details = details.replace('<', '&lt;')
                        details = details.replace('>', '&gt;')
                        # append to documentation paragraph
                        if not (self.details[-3:] == '<p>'
                                or self.details[-4:] == '<br>'):
                            self.details += '<br>'
                        self.details += details
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
                                snip += '${{{}:{}}}'.format(i, param)
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
