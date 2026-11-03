#!/usr/bin/env python3
"""Lower SSA phi functions to edge-local, sequentially scheduled copies."""
import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from dominance_frontier import load_flow_graph
from flow_graph import (BasicBlock, Edge, FlowGraph, FlowGraphError, Instruction,
                        IMAGE_FORMATS, output_format, render_image)
from ssa import Operation, parse_operation


def schedule_parallel_copies(copies, newtemp):
    """Schedule simultaneous assignments, using a temporary to break cycles."""
    if len({dest for dest, _ in copies}) != len(copies):
        raise FlowGraphError('並列コピーの左辺が重複しています')
    pending = [(d, s) for d, s in copies if d != s]
    result = []
    while pending:
        sources = {s for _, s in pending}
        safe = next((i for i, (dest, _) in enumerate(pending) if dest not in sources), None)
        if safe is not None:
            result.append(pending.pop(safe))
        else:
            dest = pending[0][0]
            temp = newtemp()
            result.append((temp, dest))
            pending = [(d, temp if s == dest else s) for d, s in pending]
    return result


@dataclass
class PhiElimination:
    graph: FlowGraph
    undefined: list
    copy_blocks: list
    temporaries: list

    def to_text(self):
        header = ('undef at ENTRY: ' + ', '.join(self.undefined) + '\n\n') if self.undefined else ''
        return header + self.graph.to_text()

    def to_dot(self):
        return self.graph.to_dot()

    def to_tac(self):
        return '\n'.join(i.text for b in self.graph.blocks for i in b.instructions) + ('\n' if self.graph.blocks else '')

    def to_json(self):
        data = json.loads(self.graph.to_json())
        data.update(stage='phi-eliminated', undefined=self.undefined,
                    copy_blocks=self.copy_blocks, temporaries=self.temporaries)
        return json.dumps(data, ensure_ascii=False, indent=2) + '\n'


def eliminate_phi_functions(graph, undefined=()):
    """Use dedicated edge blocks for copies, including critical edges.

    Rebuild explicit jumps and true-path trampolines so both CFG edges and a
    flattened TAC listing preserve exactly the same control flow.
    """
    operations = {b.name: [parse_operation(i) for i in b.instructions] for b in graph.blocks}
    names = set(operations)
    if len(names) != len(graph.blocks):
        raise FlowGraphError('ブロック名が重複しています')
    if not names:
        return PhiElimination(FlowGraph([], []), list(undefined), [], [])
    root = graph.blocks[0].name
    outgoing = {n: [] for n in names}
    predecessors = {n: set() for n in names}
    for edge in graph.edges:
        if edge.source not in names or edge.target not in names | {'EXIT'}:
            raise FlowGraphError('未定義のブロックへの辺があります')
        if edge not in outgoing[edge.source]:
            outgoing[edge.source].append(edge)
        if edge.target in names:
            predecessors[edge.target].add(edge.source)
    phis = {n: [] for n in names}
    reserved = set(names) | {'ENTRY', 'EXIT'} | set(undefined)
    label_owners = {}
    for name, ops in operations.items():
        ordinary_seen = False
        for index, op in enumerate(ops):
            reserved.update(([op.dest] if op.dest else []) + op.args + list(op.incoming.values()))
            if op.kind == 'label':
                if op.target in label_owners:
                    raise FlowGraphError('ラベルが重複しています')
                label_owners[op.target] = name
                reserved.add(op.target)
            elif op.kind == 'phi':
                if ordinary_seen:
                    raise FlowGraphError('φ関数はブロック先頭に置いてください')
                expected = predecessors[name] | ({'ENTRY'} if name == root else set())
                if set(op.incoming) != expected:
                    raise FlowGraphError(f'{name}: φ関数の引数と直前ブロックが一致しません')
                phis[name].append(op)
            else:
                ordinary_seen = True
                if op.kind in {'goto', 'conditional'} and index != len(ops) - 1:
                    raise FlowGraphError('分岐命令はブロック末尾に置いてください')
    # Check the original CFG against its terminators before rewriting targets.
    for name, ops in operations.items():
        last = ops[-1] if ops else None
        edges = outgoing[name]
        if last and last.kind == 'conditional':
            if len(edges) != 2 or {e.kind for e in edges} != {'true', 'false'}:
                raise FlowGraphError('条件分岐にはtrue/falseの２辺が必要です')
            jumped = next(e for e in edges if e.kind == ('false' if last.negated else 'true'))
            if label_owners.get(last.target) != jumped.target:
                raise FlowGraphError('条件分岐のラベルとCFGの辺が一致しません')
        elif len(edges) != 1:
            raise FlowGraphError('通常ブロックには後続辺が１本必要です')
        elif last and last.kind == 'goto' and label_owners.get(last.target) != edges[0].target:
            raise FlowGraphError('gotoのラベルとCFGの辺が一致しません')

    counters = {}
    def fresh(prefix):
        count = counters.get(prefix, 0) + 1
        while f'{prefix}{count}' in reserved:
            count += 1
        counters[prefix] = count
        name = f'{prefix}{count}'
        reserved.add(name)
        return name

    temporaries = []
    def newtemp():
        temp = fresh('pcopy')
        temporaries.append(temp)
        return temp

    # Give every original block and the final exit a jump label.
    labels = {}
    for b in graph.blocks:
        ops = operations[b.name]
        labels[b.name] = ops[0].target if ops and ops[0].kind == 'label' else fresh('ssa_label')
    labels['EXIT'] = fresh('ssa_exit')
    copy_blocks, copy_operations, redirects = [], {}, {}
    entry_copy = None
    for block in graph.blocks:
        target = block.name
        incoming = (['ENTRY'] if target == root else []) + [b.name for b in graph.blocks if b.name in predecessors[target]]
        for pred in incoming:
            copies = [(op.dest, op.incoming[pred]) for op in phis[target]]
            scheduled = schedule_parallel_copies(copies, newtemp)
            if not scheduled:
                continue
            name = fresh('C')
            copy_blocks.append(name)
            labels[name] = fresh('ssa_copy')
            copy_operations[name] = [Operation('assign', 0, dest=d, args=[s]) for d, s in scheduled]
            redirects[pred, target] = name
            if pred == 'ENTRY':
                entry_copy = name

    result_blocks, result_edges = [], []
    def append_block(name, ops):
        result_blocks.append(BasicBlock(name, [Instruction(op.line, op.text(), op.kind,
            target=op.target if op.kind in {'goto', 'conditional'} else '',
            label=op.target if op.kind == 'label' else '') for op in ops]))

    def add_copy_block(name, target):
        append_block(name, [Operation('label', 0, target=labels[name])] + copy_operations[name]
                     + [Operation('goto', 0, target=labels[target])])
        result_edges.append(Edge(name, target, 'goto'))

    if entry_copy:
        add_copy_block(entry_copy, root)
    for block in graph.blocks:
        name = block.name
        ops = operations[name]
        kept = [op for op in ops if op.kind not in {'phi', 'goto', 'conditional'}]
        if not kept or kept[0].kind != 'label':
            kept.insert(0, Operation('label', 0, target=labels[name]))
        if ops and ops[-1].kind == 'conditional':
            last = ops[-1]
            targets = {e.kind: redirects.get((name, e.target), e.target) for e in outgoing[name]}
            trampoline = fresh('T')
            labels[trampoline] = fresh('ssa_true')
            kept.append(Operation('conditional', last.line, args=list(last.args), target=labels[targets['false']]))
            append_block(name, kept)
            result_edges += [Edge(name, targets['false'], 'false'), Edge(name, trampoline, 'true')]
            # Physically next to the conditional: this is its true fallthrough.
            append_block(trampoline, [Operation('label', 0, target=labels[trampoline]),
                                     Operation('goto', 0, target=labels[targets['true']])])
            result_edges.append(Edge(trampoline, targets['true'], 'goto'))
        else:
            target = outgoing[name][0].target
            destination = redirects.get((name, target), target)
            kept.append(Operation('goto', 0, target=labels[destination]))
            append_block(name, kept)
            result_edges.append(Edge(name, destination, 'goto'))
    for (pred, target), name in redirects.items():
        if pred != 'ENTRY':
            add_copy_block(name, target)
    # Last label is the exit of the flattened TAC, rather than a basic block.
    # Give it its own output block so every emitted jump has a real label.
    exit_block = fresh('E')
    append_block(exit_block, [Operation('label', 0, target=labels['EXIT'])])
    result_edges = [Edge(e.source, exit_block if e.target == 'EXIT' else e.target, e.kind) for e in result_edges]
    result_edges.append(Edge(exit_block, 'EXIT', 'fallthrough'))
    return PhiElimination(FlowGraph(result_blocks, result_edges), list(undefined), copy_blocks, temporaries)


def main():
    parser = argparse.ArgumentParser(description='SSAのφ関数を辺上のコピーに変換')
    parser.add_argument('input', nargs='?', help='SSA形式のCFG JSON（省略時は標準入力）')
    parser.add_argument('--format', choices=['text', 'json', 'dot', 'png', 'svg', 'pdf', 'tac'])
    parser.add_argument('-o', '--output', help='.txt/.json/.dot/.png/.svg/.pdf/.tac')
    args = parser.parse_args()
    try:
        if args.output and Path(args.output).suffix.lower() == '.tac':
            if args.format not in {None, 'tac'}:
                raise FlowGraphError('--formatと出力拡張子が一致しません')
            fmt = 'tac'
        else:
            fmt = output_format(args.output, args.format)
        if fmt in IMAGE_FORMATS and not args.output:
            raise FlowGraphError('画像出力には-oが必要です')
        text = Path(args.input).read_text(encoding='utf-8') if args.input else sys.stdin.read()
        data = json.loads(text)
        graph = load_flow_graph(text)
        result = eliminate_phi_functions(graph, data.get('undefined', []))
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
