from tarr import compiler_base
from datetime import datetime, timedelta

from tarr.compiler_base import (
    Instruction, BranchingInstruction,
    RETURN_TRUE, RETURN_FALSE,
    IF, ELIF, ELSE, ENDIF,
    IF_NOT, ELIF_NOT)


class InstructionStatistic(object):

    index = int
    item_count = int
    success_count = int
    failure_count = int
    run_time = timedelta

    def __init__(self, index):
        self.index = index
        self.item_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.run_time = timedelta()

    @property
    def had_exception(self):
        return self.item_count > self.success_count + self.failure_count

    def merge(self, from_stat):
        assert self.index == from_stat.index
        self.item_count += from_stat.item_count
        self.success_count += from_stat.success_count
        self.failure_count += from_stat.failure_count
        self.run_time += from_stat.run_time


class ToTextVisitor(compiler_base.ProgramVisitor):

    def __init__(self):
        self.lines = []

    def text(self):
        return '\n'.join(self.lines)

    def addline(self, line, is_comment=False):
        self.lines.append(line)

    def addcomment(self, line):
        self.addline('     ' + line)

    def addcode(self, instruction, line):
        self.addline('{0:4d} {1}'.format(instruction.index, line))

    def format_branch(self, instruction, name):
        self.addcode(instruction, name)
        on_success = instruction.next_instruction(exit_status=True).index
        on_failure = instruction.next_instruction(exit_status=False).index
        self.addcomment('  # True  -> {0}'.format(on_success))
        self.addcomment('  # False -> {0}'.format(on_failure))

    def format_instruction(self, instruction, name):
        self.addcode(instruction, name)

    def enter_subprogram(self, label, instructions):
        if label is not None:
            self.addline('')
            self.addline('DEF ("{0}")'.format(label))

    def leave_subprogram(self, label):
        if label is None:
            self.addline('END OF MAIN PROGRAM')
        else:
            self.addline('END # {0}'.format(label))

    def visit_return(self, i_return):
        if i_return.return_value is None:
            self.format_instruction(i_return, 'RETURN')
        else:
            self.format_instruction(
                i_return, 'RETURN {0}'.format(i_return.return_value))

    def visit_instruction(self, instruction):
        self.addcode(instruction, instruction.instruction_name)

    def visit_branch(self, i_branch):
        self.format_branch(i_branch, i_branch.instruction_name)


class ToTextVisitorWithStatistics(ToTextVisitor):

    def __init__(self, statistics):
        super(ToTextVisitorWithStatistics, self).__init__()
        self.statistics = statistics

    def format_branch(self, instruction, name):
        statistics = self.statistics[instruction.index]
        self.addcode(instruction, name)
        on_success = instruction.next_instruction(exit_status=True).index
        on_failure = instruction.next_instruction(exit_status=False).index
        self.addcomment(
            '  # True  -> {0}   (*{1.success_count})'
            .format(on_success, statistics))
        self.addcomment(
            '  # False -> {0}   (*{1.failure_count})'
            .format(on_failure, statistics))

    def format_instruction(self, instruction, name):
        statistics = self.statistics[instruction.index]
        self.addcode(
            instruction, '{0}   (*{1.item_count})'.format(name, statistics))


class ToDotVisitor(compiler_base.ProgramVisitor):

    def __init__(self):
        self.lines = ['digraph {', '', 'compound = true;']
        self.inter_cluster_edges = []

    def text(self):
        extras = []
        if self.inter_cluster_edges:
            extras.extend(['', '// inter-cluster-edges'])
            extras.extend(self.inter_cluster_edges)
        extras.append('}')
        return '\n'.join(self.lines + extras)

    def addline(self, line, is_comment=False):
        self.lines.append(line)

    def add_inter_cluster_edge(self, instruction1, instruction2, label):
        self.inter_cluster_edges.append(
            self.format_edge(instruction1, instruction2, label))

    def enter_subprogram(self, label, instructions):
        self.addline('')
        self.addline('subgraph {} {{'.format(self.cluster_name(label)))
        if label is not None:
            self.addline('    label = "{}";'.format(self.escape(label)))
            self.addline('')

    def leave_subprogram(self, label):
        self.addline('}')

    def visit_return(self, i_return):
        if i_return.return_value is None:
            node_name = 'RETURN'
        else:
            node_name = 'RETURN {0}'.format(i_return.return_value)
        self.add_return_node(i_return, node_name)

    def visit_instruction(self, instruction):
        self.format_instruction(instruction, instruction.instruction_name)

    def visit_branch(self, i_branch):
        self.format_branch(i_branch, i_branch.instruction_name)

    def cluster_name(self, label):
        return '"cluster_{}"'.format(self.escape(label))

    def node_name(self, instruction):
        return 'node_{}'.format(instruction.index)

    def escape(self, label):
        return str(label).replace('"', r'\"')

    def add_node(self, instruction, name):
        node = self.node_name(instruction)
        self.addline('    {} [label="{}"];'.format(node, self.escape(name)))

    def add_return_node(self, instruction, name):
        self.add_node(instruction, name)

    def format_edge(self, instruction1, instruction2, label):
        node1 = self.node_name(instruction1)
        node2 = self.node_name(instruction2)
        attrs = dict()
        if label:
            attrs['label'] = '"{}"'.format(self.escape(label))
        if attrs:
            formatted_attrs = ' [{}]'.format(
                ','.join(
                    '{}={}'.format(attr, value)
                    for (attr, value) in attrs.iteritems()))
        else:
            formatted_attrs = ''

        return '    {} -> {}{};'.format(node1, node2, formatted_attrs)

    def add_edge(self, instruction1, instruction2, label):
        self.addline(self.format_edge(instruction1, instruction2, label))

    def format_branch(self, instruction, name):
        self.add_node(instruction, name)
        on_success = instruction.next_instruction(exit_status=True)
        on_failure = instruction.next_instruction(exit_status=False)
        self.add_edge(instruction, on_success, label='True')
        self.add_edge(instruction, on_failure, label='False')

    def format_instruction(self, instruction, name):
        self.add_node(instruction, name)
        next_instruction = instruction.next_instruction(exit_status=True)
        self.add_edge(instruction, next_instruction, label='')


class ToDotVisitorWithStatistics(ToDotVisitor):

    def __init__(self, statistics):
        super(ToDotVisitorWithStatistics, self).__init__()
        self.statistics = statistics

    def add_return_node(self, instruction, name):
        statistics = self.statistics[instruction.index]
        self.add_node(
            instruction, '{0}: {1.item_count}'.format(name, statistics))

    def format_branch(self, instruction, name):
        self.add_node(instruction, name)
        on_success = instruction.next_instruction(exit_status=True)
        on_failure = instruction.next_instruction(exit_status=False)
        statistics = self.statistics[instruction.index]
        self.add_edge(
            instruction, on_success,
            label='True: {0.success_count}'.format(statistics))
        self.add_edge(
            instruction, on_failure,
            label='False: {0.failure_count}'.format(statistics))


class Program(compiler_base.Program):

    statistics = list

    def __init__(self, program):
        super(Program, self).__init__(program)
        self.statistics = [
            InstructionStatistic(i) for i in xrange(len(self.instructions))]

    # Visualizations
    def to_text(self, with_statistics=False):
        if with_statistics:
            v = ToTextVisitorWithStatistics(self.statistics)
        else:
            v = ToTextVisitor()
        self.accept(v)
        return v.text()

    def to_dot(self, with_statistics=False):
        if with_statistics:
            v = ToDotVisitorWithStatistics(self.statistics)
        else:
            v = ToDotVisitor()
        self.accept(v)
        return v.text()

    # Runner

    def run_instruction(self, instruction, flag, data):
        stat = self.statistics[instruction.index]
        stat.item_count += 1

        before = datetime.now()

        next_instruction, flag, data = instruction.run(flag, data)

        after = datetime.now()

        if flag:
            stat.success_count += 1
        else:
            stat.failure_count += 1

        stat.run_time += after - before

        return next_instruction, flag, data


# decorators to make simple functions into Instructions

class TarrInstructionBase(object):

    def __init__(self, func):
        self.func = func

    def clone(self):
        return self.__class__(self.func)

    @property
    def instruction_name(self):
        return self.func.__name__


class TarrRuleInstruction(TarrInstructionBase, Instruction):

    def run(self, flag, data):
        data.payload = self.func(data.payload)
        return self.next_instruction, flag, data


def rule(func):
    '''
    Decorator, enable function to be used as an instruction in a Tarr program.

    Usage:

    @rule
    def func(data):
        ...
        return data
    '''
    func.compile = TarrRuleInstruction(func).compile
    return func


class TarrBranchInstruction(TarrInstructionBase, BranchingInstruction):

    def run(self, flag, data):
        if self.func(data.payload):
            return self.instruction_on_yes, True, data
        else:
            return self.instruction_on_no, False, data


def branch(func):
    '''
    Decorator, enable function to be used as a condition in a Tarr program.

    Usage:

    @branch
    def cond(data):
        ...
        return {True | False}
    '''
    func.compile = TarrBranchInstruction(func).compile
    return func


HAVE_NOT_DONE_IT = object()


class TarrBranchRuleInstruction(TarrBranchInstruction):

    def run(self, flag, data):
        output = self.func(data.payload)
        done_it = output is not HAVE_NOT_DONE_IT
        if done_it:
            data.payload = output
            return self.instruction_on_yes, True, data
        else:
            return self.instruction_on_no, False, data


# FIXME: rename to branch_if_not_done
def branch_rule(func):
    '''
    Decorator, enable function to be used as both a rule and a condition
    in a Tarr program.

    The intended use is to try to make progress and return with the special
    value HAVE_NOT_DONE_IT if could not make it, otherwise the new value.

    WARNING: if the input is modified in-place, its value WILL be modified
    even if returning HAVE_NOT_DONE_IT!

    To use as a condition: return either the input or the special value
    HAVE_NOT_DONE_IT.
    To use as a rule: return the modified input data.

    Usage:

    @branch_rule
    def maybe_rule(data):
        ...
        return {data | HAVE_NOT_DONE_IT}
    '''
    func.compile = TarrBranchRuleInstruction(func).compile
    return func


__all__ = [
    'Program',
    'branch', 'rule', 'branch_rule', 'HAVE_NOT_DONE_IT',
    'RETURN_TRUE', 'RETURN_FALSE',
    'IF', 'ELIF', 'ELSE', 'ENDIF',
    'IF_NOT', 'ELIF_NOT',
]
