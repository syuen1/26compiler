#!/usr/bin/env python3
"""Compute dominance frontiers from a CFG JSON or generated TAC."""
import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from dominator_tree import build_dominator_tree
from flow_graph import BasicBlock, Edge, FlowGraph, FlowGraphError, Instruction, build_flow_graph


@dataclass
class DominanceFrontiers:
    root: object
    frontiers: dict
    unreachable: list
    local: dict = field(default_factory=dict)
    up: dict = field(default_factory=dict)
    up_by_child: dict = field(default_factory=dict)
    postorder: list = field(default_factory=list)

    def to_text(self, verbose=False):
        if self.root is None:
            return '(empty flow graph)\n'
        lines = [f'root: {self.root}', '']
        for name, frontier in self.frontiers.items():
            members = ', '.join(n for n in self.frontiers if n in frontier)
            lines.append(f'DF({name}) = {{{members}}}')
        if self.unreachable:
            lines.append('\nunreachable: ' + ', '.join(self.unreachable))
        if verbose:
            def members(values):
                return '{' + ', '.join(n for n in self.frontiers if n in values) + '}'
            lines += ['', 'DF_local / DF_up (dominator-tree postorder):',
                      'order: ' + ' -> '.join(self.postorder)]
            for name in self.postorder:
                lines += ['', name + ':', f'  DF_local({name}) = {members(self.local[name])}']
                for child, detail in self.up_by_child[name].items():
                    lines.append(f'  child {child}: DF({child}) = {members(detail["candidates"])}; '
                                 f'keep = {members(detail["kept"])}; '
                                 f'exclude (idom(y) = {name}) = {members(detail["excluded"])}')
                lines += [f'  DF_up({name}) = {members(self.up[name])}',
                          f'  DF({name}) = DF_local({name}) union DF_up({name}) = {members(self.frontiers[name])}']
        return '\n'.join(lines) + '\n'

    def to_json(self, verbose=False):
        data = {'root': self.root, 'frontiers': {
            name: [n for n in self.frontiers if n in frontier]
            for name, frontier in self.frontiers.items()}, 'unreachable': self.unreachable}
        if verbose:
            def ordered(values):
                return [n for n in self.frontiers if n in values]
            data.update(df_local={n: ordered(v) for n, v in self.local.items()},
                        df_up={n: ordered(v) for n, v in self.up.items()},
                        postorder=self.postorder,
                        df_up_by_child={n: {c: {k: ordered(v) for k, v in d.items()}
                                              for c, d in children.items()}
                                        for n, children in self.up_by_child.items()})
        return json.dumps(data, ensure_ascii=False, indent=2) + '\n'


def compute_dominance_frontiers(graph):
    """Compute DF_local and DF_up bottom-up on the dominator tree.

    DF_local(x) = {y in successors(x) | idom(y) != x}
    DF_up(x) = union({y in DF(c) | idom(y) != x} for children c of x)
    DF(x) = DF_local(x) union DF_up(x).
    """
    tree = build_dominator_tree(graph)
    frontiers = {b.name: set() for b in tree.blocks}
    successors = {n: set() for n in frontiers}
    children = {n: [] for n in frontiers}
    for name in frontiers:
        parent = tree.immediate_dominators[name]
        if parent is not None:
            children[parent].append(name)
    for edge in graph.edges:
        if edge.source in frontiers and edge.target in frontiers:
            successors[edge.source].add(edge.target)
    postorder = []
    pending = [(tree.root, False)] if tree.root is not None else []
    while pending:
        name, finished = pending.pop()
        if finished:
            postorder.append(name)
        else:
            pending.append((name, True))
            pending.extend((c, False) for c in reversed(children[name]))
    local, up, by_child = {}, {}, {}
    for name in postorder:
        local[name] = {y for y in successors[name] if tree.immediate_dominators[y] != name}
        up[name], by_child[name] = set(), {}
        for child in children[name]:
            candidates = frontiers[child]
            kept = {y for y in candidates if tree.immediate_dominators[y] != name}
            by_child[name][child] = {'candidates': set(candidates), 'kept': kept,
                                    'excluded': candidates - kept}
            up[name] |= kept
        frontiers[name] = local[name] | up[name]
    return DominanceFrontiers(tree.root, frontiers, tree.unreachable, local, up, by_child, postorder)


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
    parser.add_argument('-v', '--verbose', action='store_true', help='DF_local・DF_upと子からの伝播過程を表示')
    args = parser.parse_args()
    try:
        fmt = args.format or ('json' if args.output and Path(args.output).suffix.lower() == '.json' else 'text')
        if args.output:
            suffix = Path(args.output).suffix.lower()
            if suffix not in {'.txt', '.json'} or (suffix == '.json') != (fmt == 'json'):
                raise FlowGraphError('出力は形式と一致する.txtまたは.jsonを指定してください')
        text = Path(args.input).read_text(encoding='utf-8') if args.input else sys.stdin.read()
        graph = load_flow_graph(text) if args.input_format == 'json' else build_flow_graph(text)
        result = getattr(compute_dominance_frontiers(graph), 'to_' + fmt)(verbose=args.verbose)
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
