import re

import sublime
import sublime_plugin

class PairMatlabStatementsCommand(sublime_plugin.TextCommand):

    """Find opening statement that is paired with the current 'end'
    """

    general_keywords = 'if|for|while|switch|try|function|classdef'
    class_keywords = 'properties|methods|events|enumeration'

    def iskeyword(self, point):
        """Does the code contain a Matlab keyword at the point?
        """
        all_scopes = self.view.scope_name(point)
        return any([scope.startswith('keyword') 
            for scope in all_scopes.split()])

    def run(self, edit, action='popup'):
        """Find opening statement that is paired with the current 'end'
        """
        # determine valid keywords
        keywords = self.general_keywords
        all_code = self.view.substr(sublime.Region(0, self.view.size()))
        if all_code.lstrip().startswith('classdef'):
            keywords += '|' + self.class_keywords

        # get current selection
        sel = self.view.sel()
        if not len(sel):
            return
        reg_key = self.view.word(sel[0])
        text_key = self.view.substr(reg_key).strip()

        # check if the current selection equals a valid keyword
        if not self.iskeyword(reg_key.begin()) \
                or not text_key in keywords + '|end':
            if not(action == 'jump' or action == 'select'):
                msg = '[WARNING] AutoMatlab - Cursor not in open/end keyword.'
                self.view.window().status_message(msg)
            return

        if text_key == 'end':
            reg_paired = self.pair_with_open_statement(reg_key, keywords)
            # the below disregards edge-cases with partial one-line statements
            # or with , or ; in strings or comments
            if self.view.line(reg_key) == self.view.line(reg_paired):
                sel_lines = [reg_key.begin(), reg_paired.end()]
            else:
                sel_lines = [self.view.full_line(reg_key.begin()).begin(), 
                             self.view.full_line(reg_paired.end()).end()]
        else:
            reg_paired = self.pair_with_end_statement(reg_key, keywords)
            if self.view.line(reg_key) == self.view.line(reg_paired):
                sel_lines = [reg_key.end(), reg_paired.begin()]
            else:
                sel_lines = [self.view.full_line(reg_key.end()).end(), 
                             self.view.full_line(reg_paired.begin()).begin()]
        if reg_paired == None:
            if not(action == 'jump' or action == 'select'):
                msg = '[WARNING] AutoMatlab - Cannot pair statement: ' \
                    'invalid syntax.'
                self.view.window().status_message(msg)
            return

        if action == 'jump':
            self.view.show(reg_paired)
            self.view.sel().clear()
            self.view.sel().add(sublime.Region(reg_paired.end()))
        elif action == 'select':
            self.view.sel().clear()
            self.view.sel().add(sublime.Region(min(sel_lines), max(sel_lines)))
        else:
            # read the text surrounding the paired statement
            reg_line = self.view.full_line(reg_paired)            
            reg_surround = self.view.lines(
                sublime.Region(reg_line.begin() - 1, reg_line.end() + 1))
            text_lines = [self.view.substr(reg).rstrip() 
                          for reg in reg_surround]
            nr_lines = [self.view.rowcol(reg.a)[0] + 1 for reg in reg_surround]

            # make paired statement bold
            nr_paired = self.view.rowcol(reg_line.a)[0] + 1
            borders_paired = [reg_paired.begin() - reg_line.begin(),
                              reg_paired.end() - reg_line.begin()]
            text_paired = text_lines[nr_lines.index(nr_paired)]
            text_lines[nr_lines.index(nr_paired)] = \
                text_paired[:borders_paired[0]] + '<i><b>' \
                + text_paired[borders_paired[0]:borders_paired[1]] \
                + '</b></i>'+ text_paired[borders_paired[1]:]

            # remove the minimum indentation
            lstrip_lines = [len(text) - len(text.lstrip()) 
                            for text in text_lines]
            text_lines = \
                ['&nbsp;'*(lstrip_lines[ii]-min(lstrip_lines)) 
                    + text_lines[ii].lstrip() 
                for ii in range(len(text_lines))]

            # add line numbers and concatenate text lines
            text = ''
            for ii in range(len(nr_lines)):
                text += \
                    '&nbsp;'*(len(str(max(nr_lines)))-len(str(nr_lines[ii]))) \
                    + '{}: {}<br>'.format(nr_lines[ii], text_lines[ii])

            # add hyperlink link
            text += '<a href="{}">goto</a> <a href="{}">select</a>'.format(
                reg_paired, sel_lines)
            self.view.show_popup(text, 
                max_width=80*self.view.em_width(), 
                max_height=5*self.view.line_height(), 
                on_navigate=self.select)


    def pair_with_open_statement(self, reg, keywords):
        """Find the open statement paired with the end statement
        in region reg.
        """
        # read all code until current end statement
        code = self.view.substr(sublime.Region(0, reg.end()))

        # look for end statements
        pattern = r'(?:\W|^)(end)(?:\W|$)'
        mo_end = re.finditer(pattern, code, re.M)

        # look for opening statements to pair
        pattern = r'(?:\W|^)(' + keywords + r')(?:\W|$)'
        mo_open = re.finditer(pattern, code, re.M)

        # strip non-keywords
        end_statements = sorted([mo.start(1)
            for mo in mo_end
            if self.iskeyword(mo.start(1))], reverse=True)
        open_statements = sorted([mo.start(1) 
            for mo in mo_open
            if self.iskeyword(mo.start(1))], reverse=True)

        # check validity of open/end combinations
        no = len(open_statements)
        ne = len(end_statements)
        if ne > no:
            return None

        for ii in range(no):
            # check how many end statements come after each open statement,
            # starting from the last open statement
            end_after = sum([open_statements[ii] < estat 
                for estat in end_statements])
            # the paired open statement is found when end_after matches
            # the current counter
            if end_after == ii+1:
                reg_paired = self.view.word(open_statements[ii])
                break
        return reg_paired

    def pair_with_end_statement(self, reg, keywords):
        """Find the end statement paired with the open statement
        in region reg.
        """
        # read all code from current open statement
        code = self.view.substr(sublime.Region(reg.begin(), self.view.size()))

        # look for end statements
        pattern = r'(?:\W|^)(end)(?:\W|$)'
        mo_end = re.finditer(pattern, code, re.M)

        # look for opening statements to pair
        pattern = r'(?:\W|^)(' + keywords + r')(?:\W|$)'
        mo_open = re.finditer(pattern, code, re.M)

        # strip non-keywords
        end_statements = sorted([reg.begin() + mo.start(1)
            for mo in mo_end
            if self.iskeyword(reg.begin() + mo.start(1))])
        open_statements = sorted([reg.begin() + mo.start(1) 
            for mo in mo_open
            if self.iskeyword(reg.begin() + mo.start(1))])

        # check validity of open/end combinations
        no = len(open_statements)
        ne = len(end_statements)
        if no > ne:
            print(code, no, ne)
            return None

        for ii in range(ne):
            # check how many open statements come before each end statement,
            # starting from the first end statement
            open_before = sum([end_statements[ii] > ostat 
                for ostat in open_statements])
            # the paired end statement is found when open_before matches
            # the current counter
            if open_before == ii+1:
                reg_paired = self.view.word(end_statements[ii])
                break
        return reg_paired

    def select(self, reg):
        """Select the lines between the paired open/end statements
        """
        reg = eval(reg)

        ###
        # these lines are necessary to force the view to update (Sublime bug?)
        self.view.sel().clear()
        self.view.sel().add(sublime.Region(reg[0]))
        self.view.run_command('insert', {'characters':' '})
        self.view.run_command('left_delete')
        ###

        self.view.show(reg[1])
        self.view.sel().clear()
        self.view.sel().add(sublime.Region(reg[0], reg[1]))