#!/usr/bin/env python3
"""Build the intersection graph of SSA live subtrees."""

import argparse
from collections import defaultdict
from itertools import combinations
import json
from pathlib import Path
import subprocess
import sys


def build_interference_graph(subtrees):
    # Group variables by tree node, then add every pair in each group.
    variables_at = defaultdict(list)
    variables = sorted(subtrees)
    for variable in variables:
        nodes = subtrees[variable]['blocks']
        for node in sorted(set(nodes)):
            variables_at[node].append(variable)

    intersections = defaultdict(list)
    for node, occupants in sorted(variables_at.items()):
        for pair in combinations(occupants, 2):
            intersections[pair].append(node)
    return {
        'granularity': 'basic_block',
        'vertices': variables,
        'edges': [
            {'source': source, 'target': target, 'shared_blocks': blocks}
            for (source, target), blocks in sorted(intersections.items())
        ],
    }


def write_png(graph, output):
    ids = {variable: f'v{index}' for index, variable in enumerate(graph['vertices'])}
    lines = ['graph Interference {', '  node [shape=ellipse, fontname="sans-serif"];']
    for variable, node_id in ids.items():
        label = json.dumps(variable, ensure_ascii=False)
        lines.append(f'  {node_id} [label={label}];')
    for edge in graph['edges']:
        source, target = ids[edge['source']], ids[edge['target']]
        lines.append(f'  {source} -- {target};')
    lines.append('}')
    try:
        png = subprocess.run(
            ['dot', '-Tpng'], input='\n'.join(lines).encode('utf-8'),
            capture_output=True, check=True,
        )
    except FileNotFoundError as error:
        raise ValueError('PNG出力にはGraphvizの dot コマンドが必要です') from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.decode('utf-8', errors='replace').strip()
        raise ValueError(f'GraphvizによるPNG出力に失敗しました: {detail}') from error
    output.write_bytes(png.stdout)


def main():
    parser = argparse.ArgumentParser(description='基本ブロック単位の生存部分木の交差グラフを作成')
    parser.add_argument('input', type=Path, help='live_subtrees.py の出力JSON')
    parser.add_argument('-o', '--output', type=Path, help='出力先（.pngは画像、省略時はJSONを標準出力）')
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding='utf-8'))
        graph = build_interference_graph(data['subtrees'])
        if args.output and args.output.suffix.lower() == '.png':
            write_png(graph, args.output)
            return
        output = json.dumps(graph, ensure_ascii=False, indent=2) + '\n'
        if args.output:
            args.output.write_text(output, encoding='utf-8')
        else:
            sys.stdout.write(output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f'エラー: {error}\n')


if __name__ == '__main__':
    main()
