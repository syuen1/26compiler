#!/usr/bin/env python3
"""Conditional constant propagation: block-based Steps 1--10 from the supplied slide."""
import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from dominance_frontier import load_flow_graph
from flow_graph import (BasicBlock, Edge, FlowGraph, FlowGraphError, Instruction, NAME,
                        IMAGE_FORMATS, output_format, render_image)
from ssa import Operation, parse_operation


@dataclass(frozen=True)
class Value:
    kind: str
    value: object = None

    def text(self):
        return str(self.value) if self.kind == 'constant' else '⊥' if self.kind == 'bottom' else '⊤'

    def to_json(self):
        return {'kind': self.kind, **({'value': self.value} if self.kind == 'constant' else {})}


BOTTOM = Value('bottom')
TOP = Value('top')


def constant(number):
    return Value('constant', int(number))


def join(a, b):
    if a == BOTTOM:
        return b
    if b == BOTTOM or a == b:
        return a
    return TOP


def evaluate_binary(operator, a, b):
    if a == TOP or b == TOP:
        return TOP
    if a == BOTTOM or b == BOTTOM:
        return BOTTOM
    x, y = a.value, b.value
    if operator == 'div' and y == 0:
        return TOP  # Retain the original operation: do not fold a runtime trap.
    operations = {'+': lambda: x+y, '-': lambda: x-y, '*': lambda: x*y,
                  'div': lambda: (abs(x)//abs(y)) * (-1 if (x < 0) != (y < 0) else 1),
                  '=': lambda: x == y, '<>': lambda: x != y, '<': lambda: x < y,
                  '<=': lambda: x <= y, '>': lambda: x > y, '>=': lambda: x >= y}
    return constant(operations[operator]())


@dataclass
class PropagationResult:
    graph: FlowGraph
    executable: dict
    values: dict
    parameters: list
    iterations: int
    trace: list = field(default_factory=list)
    undefined: list = field(default_factory=list)

    def debug_report(self):
        lines = ['Conditional constant propagation: E[B], V[x]']
        for step in self.trace:
            lines.append(f'{step["step"]}: iteration {step["iteration"]}; {step["event"]}')
            lines.append('  E: ' + ', '.join(f'{b} -> {str(v).lower()}' for b, v in step['E'].items()))
            lines.append('  V: ' + ', '.join(f'{x} -> {v.text()}' for x, v in step['V'].items()))
        return '\n'.join(lines) + '\n'

    def to_text(self):
        lines = [f'iterations: {self.iterations}', 'E[B]:']
        lines += [f'  {b} -> {str(v).lower()}' for b, v in self.executable.items()]
        lines += ['V[x]:'] + [f'  {x} -> {v.text()}' for x, v in self.values.items()]
        return '\n'.join(lines) + '\n\n' + self.graph.to_text()

    def to_json(self):
        data = json.loads(self.graph.to_json())
        data.update(stage='conditional-constant-propagation', algorithm='block-based-slide-steps-1-10',
                    E=self.executable, V={x: v.to_json() for x, v in self.values.items()},
                    parameters=self.parameters, iterations=self.iterations)
        # Preserve unresolved entry values for subsequent analyses.
        data['undefined'] = self.undefined
        return json.dumps(data, ensure_ascii=False, indent=2) + '\n'

    def to_dot(self):
        quote = lambda s: json.dumps(s, ensure_ascii=False)
        lines = ['digraph CCP {', '  node [shape=box, fontname="monospace", style=filled];',
                 '  ENTRY [shape=oval, fillcolor="white"];', '  EXIT [shape=oval, fillcolor="white"];']
        for b in self.graph.blocks:
            label = b.name + f'  E[{b.name}] = {str(self.executable[b.name]).lower()}\n'
            label += '\n'.join(f'{i.line}: {i.text}' if i.line else i.text for i in b.instructions)
            fill = '#e5f5e0' if self.executable[b.name] else '#eeeeee'
            lines.append(f'  {quote(b.name)} [label={quote(label)}, fillcolor="{fill}"];')
        root = self.graph.blocks[0].name if self.graph.blocks else 'EXIT'
        lines.append(f'  ENTRY -> {quote(root)};')
        for e in self.graph.edges:
            attrs = []
            if e.kind in {'true', 'false'}:
                attrs.append(f'label={quote(e.kind)}')
            if not self.executable[e.source]:
                attrs.append('style=dashed')
            suffix = ' [' + ', '.join(attrs) + ']' if attrs else ''
            lines.append(f'  {quote(e.source)} -> {quote(e.target)}{suffix};')
        return '\n'.join(lines + ['}']) + '\n'


def propagate_constants(graph, parameters=(), undefined=(), debug=False):
    """Use block feasibility, not executable-edge SCCP, to match the slide.

    Step 7 examines all phi operands, including inactive predecessors.
    Step 8 requires inactive operands to remain bottom.
    Values rise monotonically: bottom -> constant -> top.
    """
    ops = {b.name: [parse_operation(i) for i in b.instructions] for b in graph.blocks}
    if len(ops) != len(graph.blocks):
        raise FlowGraphError('ブロック名が重複しています')
    names, definitions = {}, {}
    predecessors = {b: set() for b in ops}
    outgoing = {b: [] for b in ops}
    for e in graph.edges:
        if e.source not in ops or e.target not in set(ops) | {'EXIT'}:
            raise FlowGraphError('CFGの辺に未定義のブロックがあります')
        outgoing[e.source].append(e)
        if e.target in ops:
            predecessors[e.target].add(e.source)
    root = graph.blocks[0].name if graph.blocks else None
    for b, instructions in ops.items():
        normal_seen = False
        for index, op in enumerate(instructions):
            if op.dest:
                if op.dest in definitions:
                    raise FlowGraphError('SSA形式が必要です。定義の重複: ' + op.dest)
                definitions[op.dest] = b
            for v in ([op.dest] if op.dest else []) + op.args + list(op.incoming.values()):
                if re.fullmatch(NAME, v):
                    names[v] = None
            if op.kind == 'phi':
                if normal_seen or set(op.incoming) != predecessors[b] | ({'ENTRY'} if b == root else set()):
                    raise FlowGraphError('φ関数の配置または流入元が不正です: ' + b)
            elif op.kind != 'label':
                normal_seen = True
            if op.kind in {'conditional', 'goto'} and index != len(instructions) - 1:
                raise FlowGraphError('分岐命令はブロック末尾に必要です')
        last = instructions[-1] if instructions else None
        if last and last.kind == 'conditional':
            if len(outgoing[b]) != 2 or {e.kind for e in outgoing[b]} != {'true', 'false'}:
                raise FlowGraphError('条件分岐にはtrue/falseの辺が必要です')
        elif len({e.target for e in outgoing[b]}) != 1:
            raise FlowGraphError('通常ブロックの後続は１個にしてください')
    undefined = set(undefined)
    parameters = list(dict.fromkeys(parameters))
    # Values without a definition are external inputs, except explicitly marked undef.
    parameters += [x for x in names if x not in definitions and x not in undefined and x not in parameters]
    if any(x not in names or x in definitions for x in parameters):
        raise FlowGraphError('parametersは定義のないSSA引数名を指定してください')
    E = {b: False for b in ops}
    V = {x: BOTTOM for x in names}
    trace, iteration = [], 0
    def record(event):
        if debug:
            trace.append({'step': len(trace) + 1, 'iteration': iteration, 'event': event,
                          'E': dict(E), 'V': dict(V)})
    def mark(b, reason):
        if b in E and not E[b]:
            E[b] = True
            record(reason + f': E[{b}] <- true')
    def update(x, value, reason):
        value = join(V[x], value)
        if value != V[x]:
            V[x] = value
            record(reason + f': V[{x}] <- {value.text()}')
    def value(x):
        return V[x] if x in V else constant(x)
    record('initialize: E[B]=false, V[x]=⊥')
    for x in parameters:
        update(x, TOP, 'Step 1: parameter')
    if root is not None:
        mark(root, 'Step 2: entry')
    while True:
        iteration += 1
        before = dict(E), dict(V)
        record('begin iteration')
        # Step 3: propagate through unique successors.
        for b in ops:
            targets = {e.target for e in outgoing[b]}
            if E[b] and len(targets) == 1:
                mark(next(iter(targets)), f'Step 3: successor of {b}')
        # Steps 4/5 and extensions for literals, copies, and input.
        for b, instructions in ops.items():
            if not E[b]:
                continue
            for op in instructions:
                if op.kind == 'read':
                    update(op.dest, TOP, f'input: {b}: read {op.dest}')
                elif op.kind == 'assign':
                    args = [value(a) for a in op.args]
                    candidate = evaluate_binary(op.operator, *args) if op.operator else args[0]
                    update(op.dest, candidate, f'Step 4/5: {b}: {op.text()}')
        for step in [6, 7, 8]:
            for b, instructions in ops.items():
                if not E[b]:
                    continue
                for op in instructions:
                    if op.kind != 'phi':
                        continue
                    active = [value(x) for pred, x in op.incoming.items() if pred == 'ENTRY' or E[pred]]
                    inactive = [value(x) for pred, x in op.incoming.items() if pred != 'ENTRY' and not E[pred]]
                    constants = {v.value for v in active if v.kind == 'constant'}
                    candidate = BOTTOM
                    if step == 6 and len(constants) > 1:
                        candidate = TOP
                    if step == 7 and TOP in active + inactive:
                        candidate = TOP
                    if step == 8 and active and all(v.kind == 'constant' for v in active) and len(constants) == 1 and all(v == BOTTOM for v in inactive):
                        candidate = active[0]
                    update(op.dest, candidate, f'Step {step}: {b}: {op.text()}')
        # Comparison results are ordinary SSA values. The branch consumes their truth.
        for b, instructions in ops.items():
            if not E[b] or not instructions or instructions[-1].kind != 'conditional':
                continue
            condition = value(instructions[-1].args[0])
            for e in outgoing[b]:
                if condition == TOP or (condition.kind == 'constant' and (e.kind == 'true') == bool(condition.value)):
                    mark(e.target, f'Step {9 if condition == TOP else 10}: branch from {b}')
        record('end iteration')
        if before == (E, V):
            record('fixed point')
            break
    # Substitute known values without removing blocks or edges: retain the slide's E map.
    blocks = []
    for b in graph.blocks:
        rewritten = []
        for original in ops[b.name]:
            op = original
            if E[b.name]:
                if op.dest and V[op.dest].kind == 'constant':
                    op = Operation('assign', op.line, dest=op.dest, args=[str(V[op.dest].value)])
                elif op.kind != 'phi':
                    args = [str(V[a].value) if a in V and V[a].kind == 'constant' else a for a in op.args]
                    op = Operation(op.kind, op.line, op.dest, args, op.operator, op.target, dict(op.incoming), op.negated)
            rewritten.append(op)
        # Keep remaining phis before ordinary assignments folded from phis.
        labels = []
        while rewritten and rewritten[0].kind == 'label':
            labels.append(rewritten.pop(0))
        rewritten = labels + [op for op in rewritten if op.kind == 'phi'] + [op for op in rewritten if op.kind != 'phi']
        blocks.append(BasicBlock(b.name, [Instruction(op.line, op.text(), op.kind,
            target=op.target if op.kind in {'goto', 'conditional'} else '',
            label=op.target if op.kind == 'label' else '') for op in rewritten]))
    return PropagationResult(FlowGraph(blocks, list(graph.edges)), E, V, parameters, iteration,
                             trace, [x for x in names if x in undefined])


def main():
    parser = argparse.ArgumentParser(description='SSA JSONに対する条件付き定数伝播（資料のStep 1〜10）')
    parser.add_argument('input', nargs='?', help='SSA CFG JSON（省略時は標準入力）')
    parser.add_argument('-o', '--output', help='.txt/.json/.dot/.png/.svg/.pdf')
    parser.add_argument('--format', choices=['text', 'json', 'dot', 'png', 'svg', 'pdf'])
    parser.add_argument('--parameter', action='append', default=[], help='実行時引数のSSA変数名（複数指定可）')
    parser.add_argument('-d', '--debug', action='store_true', help='各更新のB→E[B]とx→V[x]を標準エラーに表示')
    args = parser.parse_args()
    try:
        fmt = output_format(args.output, args.format)
        if fmt in IMAGE_FORMATS and not args.output:
            raise FlowGraphError('画像出力には-oが必要です')
        text = Path(args.input).read_text(encoding='utf-8') if args.input else sys.stdin.read()
        graph = load_flow_graph(text)
        data = json.loads(text)
        result = propagate_constants(graph, list(data.get('parameters', [])) + args.parameter,
                                     data.get('undefined', []), args.debug)
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
