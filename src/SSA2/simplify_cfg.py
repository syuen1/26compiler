#!/usr/bin/env python3
"""Merge straight-line CFG blocks and remove their internal goto/label pair."""
import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from dominance_frontier import load_flow_graph
from flow_graph import (BasicBlock, Edge, FlowGraph, FlowGraphError, Instruction,
                        IMAGE_FORMATS, build_flow_graph, output_format, render_image)
from ssa import parse_operation


@dataclass
class Simplification:
    graph: FlowGraph
    merged: list
    undefined: list

    def to_text(self):
        prefix = ('undef at ENTRY: ' + ', '.join(self.undefined) + '\n\n') if self.undefined else ''
        return prefix + self.graph.to_text()

    def to_dot(self):
        return self.graph.to_dot()

    def to_json(self):
        data = json.loads(self.graph.to_json())
        data.update(stage='cfg-simplified', merged=self.merged, undefined=self.undefined)
        return json.dumps(data, ensure_ascii=False, indent=2) + '\n'

    def to_tac(self):
        return '\n'.join(i.text for b in self.graph.blocks for i in b.instructions) + ('\n' if self.graph.blocks else '')


def simplify_cfg(graph, undefined=()):
    blocks = [BasicBlock(b.name, list(b.instructions)) for b in graph.blocks]
    edges = list(dict.fromkeys(graph.edges))
    if not blocks:
        return Simplification(FlowGraph([], []), [], list(undefined))
    root = blocks[0].name
    names = {b.name for b in blocks}
    if len(names) != len(blocks):
        raise FlowGraphError('基本ブロック名が重複しています')
    if any(e.source not in names or e.target not in names | {'EXIT'} for e in edges):
        raise FlowGraphError('未定義のブロックを参照する辺があります')
    if any(i.kind == 'phi' or 'φ(' in i.text for b in blocks for i in b.instructions):
        raise FlowGraphError('先にφ関数を消去してください')
    # Validate branch targets before deleting labels.
    labels = {parse_operation(i).target: b.name for b in blocks for i in b.instructions
              if parse_operation(i).kind == 'label'}
    for b in blocks:
        for index, instruction in enumerate(b.instructions):
            op = parse_operation(instruction)
            if op.kind in {'goto', 'conditional'}:
                if index != len(b.instructions) - 1:
                    raise FlowGraphError('分岐命令は基本ブロック末尾に置いてください')
                out = [e for e in edges if e.source == b.name]
                wanted = [e.target for e in out if op.kind == 'goto' or
                          e.kind == ('false' if op.negated else 'true')]
                if wanted != [labels.get(op.target)]:
                    raise FlowGraphError('ジャンプ先とCFGの辺が一致しません')
    merged = []
    while True:
        by_name = {b.name: b for b in blocks}
        predecessors = {n: set() for n in by_name}
        successors = {n: set() for n in by_name}
        for e in edges:
            successors[e.source].add(e.target)
            if e.target in predecessors:
                predecessors[e.target].add(e.source)
        candidate = None
        for b in blocks:
            if len(successors[b.name]) != 1:
                continue
            target = next(iter(successors[b.name]))
            if target not in by_name or target in {root, b.name} or predecessors[target] != {b.name}:
                continue
            last = parse_operation(b.instructions[-1]) if b.instructions else None
            if last and last.kind == 'conditional':
                continue
            candidate = b.name, target
            break
        if candidate is None:
            break
        source, target = candidate
        before, after = by_name[source], by_name[target]
        if before.instructions and parse_operation(before.instructions[-1]).kind == 'goto':
            before.instructions.pop()
        body = list(after.instructions)
        while body and parse_operation(body[0]).kind == 'label':
            body.pop(0)
        before.instructions.extend(body)
        edges = [Edge(source if e.source == target else e.source,
                      source if e.target == target else e.target, e.kind)
                 for e in edges if not (e.source == source and e.target == target)]
        edges = list(dict.fromkeys(edges))
        blocks = [b for b in blocks if b.name != target]
        merged.append({'source': source, 'removed': target})

    # Arrange true fallthrough paths next to their conditional. After a nonadjacent
    # merge, other block positions may have moved; explicit jumps handle the rest.
    by_name = {b.name: b for b in blocks}
    reserved = set(by_name) | set(labels) | {'ENTRY', 'EXIT'}
    def fresh(prefix):
        i = 1
        while f'{prefix}{i}' in reserved:
            i += 1
        value = f'{prefix}{i}'
        reserved.add(value)
        return value
    def ensure_label(name):
        block = by_name[name]
        if block.instructions and parse_operation(block.instructions[0]).kind == 'label':
            return parse_operation(block.instructions[0]).target
        label = fresh('cfg_label')
        block.instructions.insert(0, Instruction(0, 'label ' + label, 'label', label=label))
        return label
    order, visited = [], set()
    def place(start):
        name = start
        while name in by_name and name not in visited:
            visited.add(name)
            order.append(by_name[name])
            out = [e for e in edges if e.source == name]
            last = parse_operation(by_name[name].instructions[-1]) if by_name[name].instructions else None
            if not last or last.kind != 'conditional':
                break
            fallthrough_kind = 'true' if last.negated else 'false'
            true_edges = [e for e in out if e.kind == fallthrough_kind]
            if len(true_edges) != 1:
                raise FlowGraphError('条件分岐の通過先の辺が必要です')
            target = true_edges[0].target
            if target in by_name and target not in visited:
                name = target
                continue
            # Already placed targets (including self-loops) need a true trampoline.
            if target == 'EXIT':
                raise FlowGraphError('true辺のEXITはラベル付き終了ブロックにしてください')
            trampoline = fresh('F')
            label = ensure_label(target)
            order.append(BasicBlock(trampoline, [Instruction(0, 'goto ' + label, 'goto', target=label)]))
            edges.remove(true_edges[0])
            edges.extend([Edge(name, trampoline, fallthrough_kind), Edge(trampoline, target, 'goto')])
            break
    for block in blocks:
        place(block.name)
    # Ensure nonconditional fallthrough still reaches its designated successor.
    for i, block in enumerate(order):
        last = parse_operation(block.instructions[-1]) if block.instructions else None
        if last and last.kind in {'goto', 'conditional'}:
            continue
        out = [e for e in edges if e.source == block.name]
        if len(out) != 1:
            raise FlowGraphError('通常ブロックには後続辺が１本必要です')
        target = out[0].target
        following = order[i + 1].name if i + 1 < len(order) else 'EXIT'
        if target != following:
            if target == 'EXIT':
                exit_name = fresh('X')
                exit_label = fresh('cfg_exit')
                order.append(BasicBlock(exit_name, [Instruction(0, 'label ' + exit_label, 'label', label=exit_label)]))
                edges.remove(out[0])
                edges.append(Edge(block.name, exit_name, 'goto'))
                edges.append(Edge(exit_name, 'EXIT', 'fallthrough'))
                label = exit_label
            else:
                label = ensure_label(target)
            block.instructions.append(Instruction(0, 'goto ' + label, 'goto', target=label))
    return Simplification(FlowGraph(order, edges), merged, list(undefined))


def main():
    parser = argparse.ArgumentParser(description='直線的な基本ブロックを結合してgoto/labelを除去')
    parser.add_argument('input', nargs='?', help='CFG JSONまたは３番地コード')
    parser.add_argument('--input-format', choices=['json', 'tac'])
    parser.add_argument('--format', choices=['text', 'json', 'dot', 'png', 'svg', 'pdf', 'tac'])
    parser.add_argument('-o', '--output')
    args = parser.parse_args()
    try:
        fmt = 'tac' if args.output and Path(args.output).suffix.lower() == '.tac' else output_format(args.output, args.format)
        if fmt == 'tac' and args.format not in {None, 'tac'}:
            raise FlowGraphError('出力形式と拡張子が一致しません')
        if fmt in IMAGE_FORMATS and not args.output:
            raise FlowGraphError('画像出力には-oが必要です')
        text = Path(args.input).read_text(encoding='utf-8') if args.input else sys.stdin.read()
        input_fmt = args.input_format or ('json' if args.input and Path(args.input).suffix.lower() == '.json' else 'tac')
        if input_fmt == 'json':
            graph = load_flow_graph(text)
            undefined = json.loads(text).get('undefined', [])
        else:
            graph, undefined = build_flow_graph(text), []
        result = simplify_cfg(graph, undefined)
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
