#!/usr/bin/env python3
"""Compute dominance frontiers from a CFG JSON or generated TAC."""
import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from dominator_tree import build_dominator_tree
from flow_graph import BasicBlock, Edge, FlowGraph, FlowGraphError, Instruction, build_flow_graph


@dataclass
class DominanceFrontiers:
    root: object
    frontiers: dict
    unreachable: list

    def to_text(self):
        if self.root is None:
            return '(empty flow graph)\n'
        lines = [f'root: {self.root}', '']
        for name, frontier in self.frontiers.items():
            members = ', '.join(n for n in self.frontiers if n in frontier)
            lines.append(f'DF({name}) = {{{members}}}')
        if self.unreachable:
            lines.append('\nunreachable: ' + ', '.join(self.unreachable))
        return '\n'.join(lines) + '\n'

    def to_json(self):
        return json.dumps({'root': self.root, 'frontiers': {
            name: [n for n in self.frontiers if n in frontier]
            for name, frontier in self.frontiers.items()}, 'unreachable': self.unreachable},
            ensure_ascii=False, indent=2) + '\n'


def compute_dominance_frontiers(graph):
    """For every reachable edge p -> y, walk p's idom chain up to idom(y).

    DF(x) = {y | some predecessor p of y is dominated by x,
                  and x does not strictly dominate y}.
    All edges are examined, including single-predecessor root self-loops.
    """
    tree = build_dominator_tree(graph)
    frontiers = {b.name: set() for b in tree.blocks}
    for edge in graph.edges:
        if edge.source not in frontiers or edge.target not in frontiers:
            continue
        runner = edge.source
        stop = tree.immediate_dominators[edge.target]
        while runner is not None and runner != stop:
            frontiers[runner].add(edge.target)
            runner = tree.immediate_dominators[runner]
    return DominanceFrontiers(tree.root, frontiers, tree.unreachable)


def load_flow_graph(text):
    """Read flow_graph.py JSON; block names alone also suffice for analysis."""
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError('CFGはJSONオブジェクトで指定してください')
        blocks = data['blocks']
        raw_edges = data['edges']
        if not isinstance(blocks, list) or not isinstance(raw_edges, list):
            raise ValueError('blocksとedgesは配列で指定してください')
        names = [b if isinstance(b, str) else b['name'] for b in blocks]
        if any(not isinstance(n, str) or not n or n in {'ENTRY', 'EXIT'} for n in names):
            raise ValueError('基本ブロック名はENTRY/EXIT以外の空でない文字列にしてください')
        if len(set(names)) != len(names):
            raise ValueError('基本ブロック名が重複しています')
        entry = data.get('entry', names[0] if names else 'EXIT')
        if entry not in names and not (not names and entry == 'EXIT'):
            raise ValueError('entryは基本ブロック名を指定してください')
        if names:
            names = [entry] + [n for n in names if n != entry]
        edges = []
        for edge in raw_edges:
            source, target = edge['source'], edge['target']
            if source not in names or target not in names + ['EXIT']:
                raise ValueError('辺に未定義のブロック名があります')
            edges.append(Edge(source, target, edge.get('kind', 'flow')))
        instructions = {}
        for block in blocks:
            if isinstance(block, dict):
                raw = block.get('instructions', [])
                if not isinstance(raw, list):
                    raise ValueError('instructionsは配列で指定してください')
                instructions[block['name']] = [Instruction(**item) for item in raw]
        return FlowGraph([BasicBlock(name, instructions.get(name, [])) for name in names], edges)
    except (ValueError, KeyError, TypeError) as error:
        raise FlowGraphError(f'不正なCFG JSON: {error}') from error


def main():
    parser = argparse.ArgumentParser(description='フローグラフから各ブロックの支配境界を計算')
    parser.add_argument('input', nargs='?', help='CFG JSON（省略時は標準入力）')
    parser.add_argument('--input-format', choices=['json', 'tac'], default='json')
    parser.add_argument('--format', choices=['text', 'json'])
    parser.add_argument('-o', '--output', help='.txtまたは.json（省略時は標準出力）')
    args = parser.parse_args()
    try:
        fmt = args.format or ('json' if args.output and Path(args.output).suffix.lower() == '.json' else 'text')
        if args.output:
            suffix = Path(args.output).suffix.lower()
            if suffix not in {'.txt', '.json'} or (suffix == '.json') != (fmt == 'json'):
                raise FlowGraphError('出力は形式と一致する.txtまたは.jsonを指定してください')
        text = Path(args.input).read_text(encoding='utf-8') if args.input else sys.stdin.read()
        graph = load_flow_graph(text) if args.input_format == 'json' else build_flow_graph(text)
        result = getattr(compute_dominance_frontiers(graph), 'to_' + fmt)()
        if args.output:
            Path(args.output).write_text(result, encoding='utf-8')
        else:
            sys.stdout.write(result)
    except (FlowGraphError, OSError, UnicodeError) as error:
        print(f'エラー: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
