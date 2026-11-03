#!/usr/bin/env python3
"""Phi insertion followed by dominator-tree SSA renaming."""
import argparse
import json
import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from dominance_frontier import load_flow_graph
from dominator_tree import build_dominator_tree
from flow_graph import (BasicBlock, FlowGraph, FlowGraphError, Instruction, NAME, VALUE,
                        LABEL, GOTO, CONDITIONAL, NORMAL, IMAGE_FORMATS,
                        build_flow_graph, output_format, render_image)
from phi_insertion import insert_phi_functions


@dataclass
class Operation:
    kind: str
    line: int
    dest: object = None
    args: list = field(default_factory=list)
    operator: str = ''
    target: str = ''
    incoming: dict = field(default_factory=dict)
    negated: bool = True

    def text(self):
        if self.kind == 'phi':
            return f'{self.dest} := φ(' + ', '.join(f'{v}@{p}' for p, v in self.incoming.items()) + ')'
        if self.kind == 'assign':
            return f'{self.dest} := ' + (self.args[0] if not self.operator else
                                       f'{self.args[0]} {self.operator} {self.args[1]}')
        if self.kind == 'read':
            return f'read {self.dest}'
        if self.kind == 'write':
            return f'write {self.args[0]}'
        if self.kind == 'conditional':
            return f'if {"not " if self.negated else ""}{self.args[0]} goto {self.target}'
        return f'{self.kind} {self.target}'


PHI = re.compile(rf'({NAME})\s*:=\s*φ\((.*)\)')


def parse_operation(instruction):
    text = instruction.text.strip()
    if (match := PHI.fullmatch(text)):
        incoming = {}
        for item in match[2].split(','):
            operand = re.fullmatch(rf'\s*({NAME})@({NAME})\s*', item)
            if operand is None or operand[2] in incoming:
                raise FlowGraphError(f'不正なφ引数: {text}')
            incoming[operand[2]] = operand[1]
        return Operation('phi', 0, dest=match[1], incoming=incoming)
    if (match := LABEL.fullmatch(text)):
        return Operation('label', instruction.line, target=match[1])
    if (match := GOTO.fullmatch(text)):
        return Operation('goto', instruction.line, target=match[1])
    if (match := CONDITIONAL.fullmatch(text)):
        return Operation('conditional', instruction.line, args=[match['condition']],
                         target=match['target'], negated=match['negated'] is not None)
    if NORMAL.fullmatch(text):
        if text.startswith('read '):
            return Operation('read', instruction.line, dest=text.split()[1])
        if text.startswith('write '):
            return Operation('write', instruction.line, args=[text.split()[1]])
        dest, rhs = re.split(r'\s*:=\s*', text)
        parts = rhs.split()
        return Operation('assign', instruction.line, dest=dest.strip(),
                         args=[parts[0]] if len(parts) == 1 else [parts[0], parts[2]],
                         operator='' if len(parts) == 1 else parts[1])
    raise FlowGraphError(f'未対応または不正な命令: {text}')


@dataclass
class SSAResult:
    graph: FlowGraph
    operations: dict
    versions: dict
    undefined: list
    unreachable: list
    verbose: bool = False
    debug_trace: list = field(default_factory=list)

    def debug_report(self):
        lines = ['SSA renaming trace (stack: bottom -> top):']
        for step in self.debug_trace:
            context = '' if step['block'] is None else f' [{step["block"]}]'
            lines.append(f'{step["step"]}: {step["event"]}{context}: {step["detail"]}')
            lines.append('  counters: ' + ', '.join(f'{v}={n}' for v, n in step['counters'].items()))
            lines.append('  stacks: ' + '; '.join(f'{v}=[{", ".join(s)}]' for v, s in step['stacks'].items()))
        return '\n'.join(lines) + '\n'

    def display_graph(self):
        if self.verbose:
            return self.graph
        blocks = [BasicBlock(b.name, [
            replace(i, text=re.sub(rf'@{NAME}', '', i.text)) if i.kind == 'phi' else i
            for i in b.instructions]) for b in self.graph.blocks]
        return FlowGraph(blocks, list(self.graph.edges))

    def to_text(self):
        header = ''
        if self.undefined:
            header += 'undef at ENTRY: ' + ', '.join(self.undefined) + '\n'
        if self.unreachable:
            header += 'unreachable (excluded): ' + ', '.join(self.unreachable) + '\n'
        return header + ('\n' if header else '') + self.display_graph().to_text()

    def to_dot(self):
        return self.display_graph().to_dot()

    def to_json(self):
        data = json.loads(self.graph.to_json())
        data.update(stage='ssa', versions=self.versions, undefined=self.undefined,
                    unreachable=self.unreachable)
        return json.dumps(data, ensure_ascii=False, indent=2) + '\n'


def convert_to_ssa(graph, verbose=False, debug=False):
    """Accept either an ordinary CFG or the output of phi_insertion.py."""
    has_phi = any(i.kind == 'phi' or PHI.fullmatch(i.text.strip())
                  for b in graph.blocks for i in b.instructions)
    original_tree = build_dominator_tree(graph)
    prepared = graph if has_phi else insert_phi_functions(graph).graph
    tree = build_dominator_tree(prepared)
    blocks = [b for b in prepared.blocks if b.name in tree.dominators]
    operations = {b.name: [parse_operation(i) for i in b.instructions] for b in blocks}
    predecessors = {b.name: set() for b in blocks}
    successors = {b.name: set() for b in blocks}
    for edge in prepared.edges:
        if edge.source in successors and edge.target in predecessors:
            successors[edge.source].add(edge.target)
            predecessors[edge.target].add(edge.source)
    # Ordered variable discovery keeps generated names deterministic.
    variables = {}
    for block in blocks:
        ordinary_seen = False
        for op in operations[block.name]:
            if op.kind == 'phi':
                if ordinary_seen:
                    raise FlowGraphError('φ関数はブロックの通常命令より前に置いてください')
                expected = predecessors[block.name] | ({'ENTRY'} if block.name == tree.root else set())
                if set(op.incoming) != expected or any(v != op.dest for v in op.incoming.values()):
                    raise FlowGraphError('SSA変換前のφ引数は各直前ブロックの同じ変数を指定してください')
            elif op.kind != 'label':
                ordinary_seen = True
            for value in ([op.dest] if op.dest else []) + op.args + list(op.incoming.values()):
                if re.fullmatch(NAME, value):
                    variables[value] = None
    used_names = set(variables)
    versions = {}
    counts = {v: 0 for v in variables}

    def allocate(variable, index):
        name = f'{variable}_{index}'
        # Avoid collisions with original names such as x_1 or v$t1_0.
        while name in used_names:
            name += '_'
        used_names.add(name)
        versions[name] = {'variable': variable, 'index': index}
        return name

    initial = {v: allocate(v, 0) for v in variables}
    stacks = {v: [initial[v]] for v in variables}
    used_undefined = set()
    debug_trace = []
    context_block = None

    def record(event, detail):
        if debug:
            debug_trace.append({'step': len(debug_trace) + 1, 'event': event,
                                'block': context_block, 'detail': detail,
                                'counters': dict(counts),
                                'stacks': {v: list(s) for v, s in stacks.items()}})

    record('initialize', '各変数の添字0 (undef) をスタックに積む')

    def current(value):
        if value not in stacks:
            record('constant', f'{value}: 添字を付けずに使用')
            return value  # Integer constant.
        name = stacks[value][-1]
        if name == initial[value]:
            used_undefined.add(name)
        record('use', f'{value} -> {name} (スタック先頭を参照)')
        return name

    def define(variable):
        counts[variable] += 1
        name = allocate(variable, counts[variable])
        stacks[variable].append(name)
        record('push', f'{variable}: counter={counts[variable]}; push {name}')
        return name

    children = {b.name: [] for b in blocks}
    for b in blocks:
        parent = tree.immediate_dominators[b.name]
        if parent is not None:
            children[parent].append(b.name)
    renamed = {b.name: [] for b in blocks}
    phi_arguments = {}
    for b in blocks:
        for index, op in enumerate(operations[b.name]):
            if op.kind == 'phi':
                phi_arguments[b.name, index] = {}
                if b.name == tree.root:
                    phi_arguments[b.name, index]['ENTRY'] = initial[op.dest]
                    used_undefined.add(initial[op.dest])
                    context_block = b.name
                    record('phi_argument', f'ENTRY -> {b.name}: {op.dest} = {initial[op.dest]}')
    events = [('enter', tree.root, None)] if tree.root else []
    while events:
        event, name, pushed = events.pop()
        context_block = name
        if event == 'leave':
            record('leave_begin', f'支配木の子の処理後に {name} の定義を取り除く')
            for variable in reversed(pushed):
                popped = stacks[variable].pop()
                record('pop', f'{variable}: pop {popped}; restore {stacks[variable][-1]}')
            record('leave', f'{name} の処理完了')
            continue
        record('enter', f'支配木のブロック {name} を訪問')
        pushed = []
        for index, op in enumerate(operations[name]):
            record('instruction', f'命令{index + 1}: {op.text()}')
            args = [current(value) for value in op.args]
            dest = op.dest
            if dest is not None:
                pushed.append(dest)
                dest = define(dest)
            renamed[name].append(Operation(op.kind, op.line, dest, args, op.operator, op.target,
                                           phi_arguments[name, index] if op.kind == 'phi' else {}, op.negated))
            record('renamed', f'{dest} := φ(...) (引数は各流入辺で設定)' if op.kind == 'phi'
                   else renamed[name][-1].text())
        # Fill successor phi operands using values at the END of this block.
        for successor in (b.name for b in blocks if b.name in successors[name]):
            for index, op in enumerate(operations[successor]):
                if op.kind == 'phi':
                    value = current(op.dest)
                    phi_arguments[successor, index][name] = value
                    record('phi_argument', f'{name} -> {successor}: {op.dest} = {value}')
        record('visit_children', '支配木の子の訪問順: ' + (', '.join(children[name]) or '(なし)'))
        events.append(('leave', name, pushed))
        events.extend(('enter', child, None) for child in reversed(children[name]))
    for b in blocks:
        for index, original in enumerate(operations[b.name]):
            if original.kind == 'phi':
                incoming = phi_arguments[b.name, index]
                if set(incoming) != set(original.incoming):
                    raise FlowGraphError('φ引数を生成できませんでした')
                renamed[b.name][index].incoming = {p: incoming[p] for p in original.incoming}
                context_block = b.name
                record('phi_complete', renamed[b.name][index].text())
    context_block = None
    record('complete', 'SSA改名完了。スタックは添字0に復元済み（採番カウンタは戻さない）')
    output_blocks = [BasicBlock(b.name, [Instruction(op.line, op.text(), op.kind,
                         target=op.target if op.kind in {'goto', 'conditional'} else '',
                         label=op.target if op.kind == 'label' else '') for op in renamed[b.name]])
                     for b in blocks]
    names = set(renamed)
    edges = [e for e in prepared.edges if e.source in names and (e.target in names or e.target == 'EXIT')]
    return SSAResult(FlowGraph(output_blocks, edges), renamed, versions,
                     [v for v in initial.values() if v in used_undefined], original_tree.unreachable, verbose, debug_trace)


def main():
    parser = argparse.ArgumentParser(description='φ挿入と添字によるSSA変換')
    parser.add_argument('input', nargs='?', help='３番地コードまたはCFG/φ挿入済みJSON')
    parser.add_argument('--input-format', choices=['tac', 'json'])
    parser.add_argument('--format', choices=['text', 'json', 'dot', 'png', 'svg', 'pdf'])
    parser.add_argument('-o', '--output', help='拡張子で出力形式を判定')
    parser.add_argument('-v', '--verbose', action='store_true', help='φ関数の引数に流入ブロック名@Bnを表示')
    parser.add_argument('-d', '--debug', action='store_true', help='スタックと添字による改名の全過程を標準エラーに表示')
    args = parser.parse_args()
    try:
        fmt = output_format(args.output, args.format)
        if fmt in IMAGE_FORMATS and not args.output:
            raise FlowGraphError('画像出力には-oが必要です')
        text = Path(args.input).read_text(encoding='utf-8') if args.input else sys.stdin.read()
        input_fmt = args.input_format or ('json' if args.input and Path(args.input).suffix.lower() == '.json' else 'tac')
        if input_fmt == 'json':
            data = json.loads(text)
            if isinstance(data, dict) and data.get('stage') == 'ssa':
                raise FlowGraphError('入力はSSA変換前のコードを指定してください')
            graph = load_flow_graph(text)
        else:
            graph = build_flow_graph(text)
        result = convert_to_ssa(graph, verbose=args.verbose, debug=args.debug)
        if args.debug:
            sys.stderr.write(result.debug_report())
        if fmt in IMAGE_FORMATS:
            Path(args.output).write_bytes(render_image(result, fmt))
        else:
            output = getattr(result, 'to_' + fmt)()
            if args.output:
                Path(args.output).write_text(output, encoding='utf-8')
            else:
                sys.stdout.write(output)
    except (FlowGraphError, OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f'エラー: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
