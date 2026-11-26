#!/usr/bin/env python3
"""Compute block liveness from flow_graph.py CFG JSON, with optional SSA phi nodes."""

import argparse
import json
from pathlib import Path
import re
import sys

NAME = r'[A-Za-z_][A-Za-z_0-9$]*'
VALUE = rf'(?:-?[0-9]+|{NAME})'
VARIABLE = re.compile(NAME)
PHI = re.compile(rf'({NAME})\s*:=\s*(?:φ|phi)\s*\((.*)\)')
PHI_ARG = re.compile(rf'({VALUE})\s*@\s*({NAME})')
ASSIGN = re.compile(
    rf'({NAME})\s*:=\s*({VALUE})'
    rf'(?:\s+(?:\+|-|\*|/|div|=|==|<>|!=|<=|>=|<|>|&&|\|\|)\s+({VALUE}))?'
)
BRANCH = re.compile(rf'(?:if\s+(?:not\s+)?|if-not\s+)({VALUE})\s+goto\s+{NAME}')
CONTROL = re.compile(rf'(?:label|goto)\s+{NAME}')
READ = re.compile(rf'read\s+({NAME})')
WRITE = re.compile(rf'write\s+({VALUE})')


def instruction_use_def(text):
    """Return the operands read and the destination written by an instruction."""
    if match := ASSIGN.fullmatch(text):
        dest, left, right = match.groups()
        return {left, right}, dest
    if match := READ.fullmatch(text):
        return set(), match[1]
    if match := BRANCH.fullmatch(text) or WRITE.fullmatch(text):
        return {match[1]}, None
    if CONTROL.fullmatch(text):
        return set(), None
    raise ValueError(f'未対応の命令: {text}')


def analyze_liveness(cfg):
    """Return LiveIn before phi definitions and LiveOut across outgoing edges."""
    blocks = {}
    for block in cfg['blocks']:
        name = block['name']
        if name in blocks or name in {'ENTRY', 'EXIT'}:
            raise ValueError(f'不正な基本ブロック名: {name}')
        blocks[name] = [instruction['text'].strip() for instruction in block['instructions']]

    entry = cfg.get('entry', next(iter(blocks), 'EXIT'))
    if entry not in blocks and (blocks or entry != 'EXIT'):
        raise ValueError(f'不正な入口ブロック: {entry}')
    successors = {name: set() for name in blocks}
    predecessors = {name: set() for name in blocks}
    for edge in cfg['edges']:
        source, target = edge['source'], edge['target']
        if source not in blocks or (target not in blocks and target != 'EXIT'):
            raise ValueError(f'不正なCFG辺: {source} → {target}')
        if target != 'EXIT':
            successors[source].add(target)
            predecessors[target].add(source)

    uses = {name: set() for name in blocks}
    definitions = {name: set() for name in blocks}
    edge_uses = {}
    for name, instructions in blocks.items():
        ordinary_seen = False
        for text in instructions:
            if match := PHI.fullmatch(text):
                if ordinary_seen:
                    raise ValueError(f'{name}: φ関数はブロック先頭に置いてください')
                definitions[name].add(match[1])
                seen = set()
                for item in match[2].split(','):
                    operand = PHI_ARG.fullmatch(item.strip())
                    if operand is None or operand[2] in seen:
                        raise ValueError(f'{name}: 不正なφ引数: {item}')
                    value, pred = operand.groups()
                    seen.add(pred)
                    if VARIABLE.fullmatch(value):
                        edge_uses.setdefault((pred, name), set()).add(value)
                if seen - {'ENTRY'} != predecessors[name] or ('ENTRY' in seen and name != entry):
                    raise ValueError(f'{name}: φ引数と前任ブロックが一致しません')
                continue
            operands, dest = instruction_use_def(text)
            ordinary_seen |= text.split()[0] != 'label'
            uses[name].update(
                value for value in operands
                if value is not None and VARIABLE.fullmatch(value) and value not in definitions[name]
            )
            if dest is not None:
                definitions[name].add(dest)

    live_in = {name: set() for name in blocks}
    live_out = {name: set() for name in blocks}
    changed = True
    while changed:
        changed = False
        for name in reversed(blocks):
            outgoing = set()
            for successor in successors[name]:
                outgoing.update(live_in[successor])
                outgoing.update(edge_uses.get((name, successor), ()))
            incoming = uses[name] | (outgoing - definitions[name])
            if incoming != live_in[name] or outgoing != live_out[name]:
                live_in[name] = incoming
                live_out[name] = outgoing
                changed = True

    return live_in, live_out


def format_table(live_in, live_out):
    def format_set(values):
        return '{' + ', '.join(values) + '}' if values else '∅'

    rows = ['| 基本ブロック | live_in | live_out |', '|---|---|---|']
    for name, incoming in live_in.items():
        rows.append(f'| {name} | {format_set(incoming)} | {format_set(live_out[name])} |')
    return '\n'.join(rows) + '\n'


def main():
    parser = argparse.ArgumentParser(description='CFG JSONから基本ブロックごとの生存変数を計算')
    parser.add_argument('input', type=Path, help='flow_graph.py または ssa.py の出力JSON')
    parser.add_argument('--tab', action='store_true', help='Markdownの表で出力')
    parser.add_argument('-o', '--output', type=Path, help='出力ファイル（省略時は標準出力）')
    args = parser.parse_args()
    try:
        cfg = json.loads(args.input.read_text(encoding='utf-8'))
        live_in, live_out = analyze_liveness(cfg)
        result = {
            'live_in': {name: sorted(values) for name, values in live_in.items()},
            'live_out': {name: sorted(values) for name, values in live_out.items()},
        }
        if args.tab:
            output = format_table(result['live_in'], result['live_out'])
        else:
            output = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.output:
            args.output.write_text(output, encoding='utf-8')
        else:
            sys.stdout.write(output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f'エラー: {error}\n')


if __name__ == '__main__':
    main()
