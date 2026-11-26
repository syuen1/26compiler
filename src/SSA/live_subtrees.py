#!/usr/bin/env python3
"""Build block-level live subtrees from an SSA CFG and liveness.py output."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from liveness import PHI, VARIABLE, instruction_use_def


def immediate_dominators(cfg):
    names = [block['name'] for block in cfg['blocks']]
    if not names:
        return {}

    entry = cfg.get('entry', names[0])
    successors = {name: set() for name in names}
    predecessors = {name: set() for name in names}
    for edge in cfg['edges']:
        source, target = edge['source'], edge['target']
        if target != 'EXIT':
            successors[source].add(target)
            predecessors[target].add(source)

    reachable = {entry}
    pending = [entry]
    while pending:
        for target in successors[pending.pop()]:
            if target not in reachable:
                reachable.add(target)
                pending.append(target)

    dominators = {name: set(reachable) for name in names if name in reachable}
    dominators[entry] = {entry}
    changed = True
    while changed:
        changed = False
        for name in dominators:
            if name == entry:
                continue
            incoming = predecessors[name] & reachable
            common = set.intersection(*(dominators[pred] for pred in incoming))
            updated = common | {name}
            if updated != dominators[name]:
                dominators[name] = updated
                changed = True

    parents = {entry: None}
    for name in dominators:
        if name != entry:
            strict = dominators[name] - {name}
            parents[name] = max(strict, key=lambda candidate: len(dominators[candidate]))
    return parents


def compute_live_subtrees(cfg, liveness):
    parents = immediate_dominators(cfg)
    blocks = cfg['blocks']
    names = {block['name'] for block in blocks}
    for key in ('live_in', 'live_out'):
        if set(liveness[key]) != names:
            raise ValueError(f'{key} の基本ブロック名がCFGと一致しません')

    live_blocks = {}
    defined = set()
    for block in blocks:
        name = block['name']
        if name not in parents:
            continue
        live = set(liveness['live_in'][name]) | set(liveness['live_out'][name])
        for instruction in block['instructions']:
            text = instruction['text'].strip()
            if phi := PHI.fullmatch(text):
                dest = phi[1]
            else:
                operands, dest = instruction_use_def(text)
                live.update(value for value in operands if value is not None and VARIABLE.fullmatch(value))
            if dest is not None:
                if dest in defined:
                    raise ValueError(f'SSA形式が必要です。複数の定義があります: {dest}')
                defined.add(dest)
                live_blocks.setdefault(dest, set())
        for variable in live:
            live_blocks.setdefault(variable, set()).add(name)

    subtrees = {}
    for variable, occupied in sorted(live_blocks.items()):
        nodes = [block['name'] for block in blocks if block['name'] in occupied]
        roots = [node for node in nodes if parents[node] not in occupied]
        if len(roots) > 1:
            raise ValueError(f'{variable} の生存範囲が支配木上で非連結です。SSA CFGと対応する生存解析結果を指定してください')
        subtrees[variable] = {
            'root': roots[0] if roots else None,
            'blocks': nodes,
            'edges': [
                {'source': parents[node], 'target': node}
                for node in nodes if parents[node] in occupied
            ],
        }
    return {
        'immediate_dominators': parents,
        'unreachable': [block['name'] for block in blocks if block['name'] not in parents],
        'subtrees': subtrees,
    }


def subtrees_to_dot(subtrees):
    lines = [
        'digraph LiveSubtrees {',
        '  graph [bgcolor=white, pad=0.2, nodesep=0.3, ranksep=0.35];',
        '  node [shape=box, style="rounded,filled", fillcolor="#f1f5f9", fontname="sans-serif"];',
        '  edge [color="#475569"];',
    ]
    for index, (variable, tree) in enumerate(subtrees.items()):
        lines.append(f'  subgraph cluster_{index} {{')
        lines.append(f'    label={json.dumps(variable, ensure_ascii=False)};')
        lines.append('    color="#cbd5e1"; style=rounded;')
        node_ids = {block: f'n{index}_{position}' for position, block in enumerate(tree['blocks'])}
        for block, node_id in node_ids.items():
            fill = ', fillcolor="#bfdbfe"' if block == tree['root'] else ''
            lines.append(f'    {node_id} [label={json.dumps(block, ensure_ascii=False)}{fill}];')
        for edge in tree['edges']:
            source, target = node_ids[edge['source']], node_ids[edge['target']]
            lines.append(f'    {source} -> {target};')
        if not node_ids:
            lines.append(f'    empty_{index} [label="∅", shape=plaintext, style=""];')
        lines.append('  }')
    if not subtrees:
        lines.append('  empty [label="∅", shape=plaintext, style=""];')
    return '\n'.join(lines + ['}', ''])


def write_png(subtrees, output):
    try:
        rendered = subprocess.run(
            ['dot', '-Tpng'], input=subtrees_to_dot(subtrees).encode('utf-8'),
            capture_output=True, check=True,
        )
    except FileNotFoundError as error:
        raise ValueError('PNG出力にはGraphvizの dot コマンドが必要です') from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.decode('utf-8', errors='replace').strip()
        raise ValueError(f'GraphvizによるPNG出力に失敗しました: {detail}') from error
    output.write_bytes(rendered.stdout)


def main():
    parser = argparse.ArgumentParser(description='SSAの各変数について支配木上の生存部分木を求める')
    parser.add_argument('liveness', type=Path, help='liveness.py のJSON出力')
    parser.add_argument('--cfg', type=Path, required=True, help='生存解析に使ったSSA CFG JSON')
    parser.add_argument('-o', '--output', type=Path, help='.png で画像を保存。それ以外はJSON（省略時は標準出力）')
    args = parser.parse_args()
    try:
        cfg = json.loads(args.cfg.read_text(encoding='utf-8'))
        liveness = json.loads(args.liveness.read_text(encoding='utf-8'))
        result = compute_live_subtrees(cfg, liveness)
        if args.output and args.output.suffix.lower() == '.png':
            write_png(result['subtrees'], args.output)
            return
        output = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.output:
            args.output.write_text(output, encoding='utf-8')
        else:
            sys.stdout.write(output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f'エラー: {error}\n')


if __name__ == '__main__':
    main()
