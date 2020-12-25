import re
from os.path import join, isfile

import sublime
import sublime_plugin


def plugin_loaded():
    """Do imports that need to wait for Sublime API initilization
    """
    global abspath, constants
    import AutoMatlab.lib.constants as constants
    from AutoMatlab.lib.common import abspath

class GenerateAutoMatlabDocumentationCommand(sublime_plugin.TextCommand):

    """Generate a snippet for documenting Matlab functions
    """

    def run(self, edit):
        """Insert snippet for Matlab function
        """
        settings = sublime.load_settings('AutoMatlab.sublime-settings')
        project_settings = self.view.window().project_data().get(
            'auto_matlab', {})

        # read first line
        region1 = self.view.line(0)
        line1 = self.view.substr(region1)

        # extract function definition components
        pattern = r'^\s*function\s+((?:\[(.*)\]\s*=|(\w+)\s*=|)' \
            r'\s*(\w+)\((.*)\))'
        mo = re.search(pattern, line1)
        if not mo:
            msg = '[WARNING] AutoMatlab - Could not find Matlab' \
                'function signature.'
            print(msg)
            self.view.window().status_message(msg)
            return

        # get signature, outargs, function name, inargs
        signature = mo.group(1)
        outargs = []
        if mo.group(2):
            outargs = [arg.strip() for arg in mo.group(2).split(',')]
        if mo.group(3):
            outargs = [arg.strip() for arg in mo.group(3).split(',')]
        fun = mo.group(4)
        inargs = []
        if mo.group(5):
            inargs = [arg.strip() for arg in mo.group(5).split(',')]
        upper = project_settings.get('documentation_upper_case_signature')
        if upper == None:
            upper = settings.get('documentation_upper_case_signature', False)
        if upper:
            signature = signature.upper()
            fun = fun.upper()
            inargs = [arg.upper() for arg in inargs]
            outargs = [arg.upper() for arg in outargs]

        # read matlab documentation snippet
        snip_path = project_settings.get('documentation_snippet_path')
        if not snip_path:
            snip_path = settings.get(
                'documentation_snippet_path',
                constants.DEFAULT_DOCUMENTATION_SNIPPET_PATH)
        if isfile(abspath(snip_path)):
            snip_path = abspath(snip_path)
        elif sublime.find_resources(snip_path):
            snip_path = abspath(sublime.find_resources(snip_path)[-1],
                                join(sublime.packages_path(), ".."))
        else:
            msg = '[ERROR] AutoMatlab - Invalid documentation snippet path.'
            self.view.window().status_message(msg)
            raise Exception(msg)
            return

        with open(snip_path) as fh:
            snip_all = fh.read()

        # extract documentation snippet content
        pattern = r'<!\[CDATA\[([\s\S]*)\]]>'
        mo = re.search(pattern, snip_all)
        if not mo:
            msg = '[ERROR] AutoMatlab - Documentation snippet could not ' \
                'be found.'
            self.view.window().status_message(msg)
            raise Exception(msg)
            return
        snip = mo.group(1).strip()

        # some validity checks on the documentation snippet
        mo = re.findall(r'^[^\n]*\${MDOC_NAME_MARKER}', snip)
        if not mo:
            msg = '[ERROR] AutoMatlab - ${MDOC_NAME_MARKER} is compulsory in ' \
                'first line of documentation snippet.'
            self.view.window().status_message(msg)
            raise Exception(msg)
            return

        mo = re.findall(r'^\W*\${MDOC_NAME}', snip)
        if not mo:
            msg = '[ERROR] AutoMatlab - ${MDOC_NAME} is compulsory as ' \
                'first word of documentation snippet.'
            self.view.window().status_message(msg)
            raise Exception(msg)
            return

        mo = re.search(r'^[^\n]*(\${MDOC_\w*_MARKER}).+', snip, re.M)
        if mo:
            msg = '[ERROR] AutoMatlab - ' + mo.group(1) + ' should be at end ' \
                'of line in documentation snippet.'
            self.view.window().status_message(msg)
            raise Exception(msg)
            return

        # check if function is already documented
        region2 = self.view.line(region1.end() + 1)
        line2 = self.view.substr(region2)
        if not re.search(r'\s*%+[\s%]*' + fun, line2):
            # compose documentation snippet
            snip = self.compose_documentation_snippet(snip, signature,
                                                      fun, inargs, outargs)

            # insert snippet
            self.view.sel().clear()
            self.view.sel().add(region1.end() + 1)
            if self.view.size() == region1.size():
                self.view.run_command(
                    'insert_snippet', {'contents': '\n' + snip + '\n\n'})
            else:
                self.view.run_command(
                    'insert_snippet', {'contents': snip + '\n\n'})
        else:
            msg = '[WARNING] AutoMatlab - Documentation already exists.'
            print(msg)
            self.view.window().status_message(msg)
            return

    def compose_documentation_snippet(self, snip, signature,
                                      fun, inargs, outargs):
        """Compose new documentation snippet based on function signature
        """
        # insert function name and signature
        snip = re.sub(r'\${MDOC_NAME}', fun, snip)
        snip = re.sub(r'\${MDOC_SIGNATURE}', signature, snip)

        # process input argument block
        snip = self.compose_arg_snip_lines(snip, inargs,
                                           'MDOC_INARG_BLOCK_MARKER',
                                           'MDOC_INARG_MARKER', 'MDOC_INARG')
        snip = self.compose_arg_snip_lines(snip, outargs,
                                           'MDOC_OUTARG_BLOCK_MARKER',
                                           'MDOC_OUTARG_MARKER', 'MDOC_OUTARG')
        snip = self.compose_arg_snip_lines(snip, inargs + outargs,
                                           'MDOC_ARG_BLOCK_MARKER',
                                           'MDOC_ARG_MARKER', 'MDOC_ARG')

        # remove lines with just MARKERS
        snip = re.sub(r'^[%\s]+\${\w+MARKER}', '%', snip, flags=re.M)
        # remove sequential empty lines
        snip = re.sub(r'^[%\s]+\n^[%\s]+$', '%', snip, flags=re.M)

        return snip

    def compose_arg_snip_lines(self, snip, args, mdoc_block_marker,
                               mdoc_arg_marker, mdoc_arg):
        """Compose function argument part of snippet, line by line
        """
        # check if argument block is specified in documentation snippet
        mo = re.search(r'^.*\${' + mdoc_block_marker + '}', snip, re.M)
        if mo:
            if args:
                mo = re.search(
                    r'^.*\${' + mdoc_arg_marker + '}.*$', snip, re.M)
                if not (mo and re.search(r'\${' + mdoc_arg + '}', mo.group())):
                    msg = '[ERROR] AutoMatlab - Argument (marker) field' \
                        'is missing for ${' + mdoc_block_marker + '}' \
                        ' of documentation snippet.'
                    self.view.window().status_message(msg)
                    raise Exception(msg)
                    return

                # create argument line template and extract tab index
                template = mo.group()
                mo = re.search(r'\${(\d+):', template)
                index = int(mo.group(1)) if mo else 0
                shift = 0
                # initialize with first argument snippet
                args_snip = re.sub(r'\${' + mdoc_arg + '}', args[0], template)
                for arg in args[1:]:
                    # shift tab indexes in arg snippet template
                    shift += 1
                    template = self.shift_tab_indexes(template)
                    # add arg to arg snip
                    args_snip += '\n' + \
                        re.sub(r'\${' + mdoc_arg + '}', arg, template)
                # shift tab indexes in snippet
                if index:
                    snip = self.shift_tab_indexes(snip, index, shift)
                # insert args_snip in snippet and return
                return re.sub(r'^.*\${' + mdoc_arg_marker + '}.*$', args_snip,
                              snip, flags=re.M)
            else:
                # clear argument related lines
                snip = re.sub(r'^.*\${' + mdoc_arg_marker + '}.*$', '', snip,
                              flags=re.M)
                snip = re.sub(r'^.*\${' + mdoc_block_marker + '}.*$', '', snip,
                              flags=re.M)
        return snip

    def shift_tab_indexes(self, snip, num=0, shift=1):
        """Shift all tab indexes higher than num by shift
        """
        # get all tab indexes
        mo = re.findall(r'\${(\d+):', snip)
        if mo:
            # shift tab indexes by shift
            for i in range(max([int(i) for i in mo]), num, -1):
                snip = re.sub(r'\${' + str(i) + r':',
                              '${' + str(i + shift) + ':', snip)
        return snip
