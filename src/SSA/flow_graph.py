#!/usr/bin/env python3
"""Split generated three-address code into basic blocks and build a CFG."""
import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


class FlowGraphError(ValueError):
    pass


@dataclass(frozen=True)
class Instruction:
    line: int
    text: str
    kind: str
    target: str = ''
    label: str = ''


@dataclass
class BasicBlock:
    name: str
    instructions: list


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    kind: str


@dataclass
class FlowGraph:
    blocks: list
    edges: list

    def to_text(self):
        lines = []
        for block in self.blocks:
            lines.append(f'{block.name}:')
            lines.extend(f'  {i.line:>3}: {i.text}' if i.line else f'       {i.text}'
                         for i in block.instructions)
            outgoing = [e for e in self.edges if e.source == block.name]
            lines.append('  -> ' + ', '.join(
                f'{e.target} [{e.kind}]' if e.kind in {'true', 'false'} else e.target
                for e in outgoing))
            lines.append('')
        if not self.blocks:
            lines.append('(empty code)')
        return '\n'.join(lines).rstrip() + '\n'

    def to_dot(self):
        # JSON quoting also escapes the text needed in Graphviz quoted strings.
        quote = lambda s: json.dumps(s, ensure_ascii=False)
        lines = ['digraph CFG {', '  node [shape=box, fontname="monospace"];',
                 '  ENTRY [shape=oval];', '  EXIT [shape=oval];']
        for block in self.blocks:
            label = block.name + '\n' + '\n'.join(
                f'{i.line}: {i.text}' if i.line else i.text for i in block.instructions)
            lines.append(f'  {block.name} [label={quote(label)}];')
        entry = self.blocks[0].name if self.blocks else 'EXIT'
        lines.append(f'  ENTRY -> {entry};')
        for edge in self.edges:
            label = f' [label={quote(edge.kind)}]' if edge.kind in {'true', 'false'} else ''
            lines.append(f'  {edge.source} -> {edge.target}{label};')
        lines.append('}')
        return '\n'.join(lines) + '\n'

    def to_json(self):
        data = asdict(self)
        data['entry'] = self.blocks[0].name if self.blocks else 'EXIT'
        data['exit'] = 'EXIT'
        return json.dumps(data, ensure_ascii=False, indent=2) + '\n'


NAME = r'[A-Za-z][A-Za-z_0-9$]*'
VALUE = rf'(?:-?[0-9]+|{NAME})'
LABEL = re.compile(rf'label\s+({NAME})')
GOTO = re.compile(rf'goto\s+({NAME})')
CONDITIONAL = re.compile(rf'if\s+not\s+({VALUE})\s+goto\s+({NAME})')
NORMAL = re.compile(
    rf'(?:read\s+{NAME}|write\s+{VALUE}|'
    rf'{NAME}\s*:=\s*{VALUE}(?:\s+(?:\+|-|\*|div|=|<>|<=|>=|<|>)\s+{VALUE})?)'
)


def parse_code(code):
    instructions, labels = [], {}
    for line_number, raw in enumerate(code.splitlines(), 1):
        text = raw.strip()
        if not text:
            continue
        match = LABEL.fullmatch(text)
        if match:
            name = match[1]
            if name in labels:
                raise FlowGraphError(f'{line_number}: ラベル {name} が重複しています')
            labels[name] = len(instructions)
            instruction = Instruction(line_number, text, 'label', label=name)
        elif (match := GOTO.fullmatch(text)):
            instruction = Instruction(line_number, text, 'goto', target=match[1])
        elif (match := CONDITIONAL.fullmatch(text)):
            instruction = Instruction(line_number, text, 'conditional', target=match[2])
        elif NORMAL.fullmatch(text):
            instruction = Instruction(line_number, text, 'normal')
        else:
            raise FlowGraphError(f'{line_number}: 未対応または不正な命令: {text}')
        instructions.append(instruction)
    for instruction in instructions:
        if instruction.target and instruction.target not in labels:
            raise FlowGraphError(f'{instruction.line}: 未定義のラベル {instruction.target}')
    return instructions, labels


def build_flow_graph(code):
    instructions, labels = parse_code(code)
    if not instructions:
        return FlowGraph([], [])
    # Leaders: first instruction, jump targets, instructions after jumps.
    leaders = {0}
    for index, instruction in enumerate(instructions):
        if instruction.target:
            leaders.add(labels[instruction.target])
            if index + 1 < len(instructions):
                leaders.add(index + 1)
    starts = sorted(leaders)
    blocks, owner = [], {}
    for i, start in enumerate(starts):
        stop = starts[i + 1] if i + 1 < len(starts) else len(instructions)
        block = BasicBlock(f'B{i + 1}', instructions[start:stop])
        blocks.append(block)
        for index in range(start, stop):
            owner[index] = block.name
    edges = []
    for i, block in enumerate(blocks):
        last = block.instructions[-1]
        following = blocks[i + 1].name if i + 1 < len(blocks) else 'EXIT'
        if last.kind == 'goto':
            edges.append(Edge(block.name, owner[labels[last.target]], 'goto'))
        elif last.kind == 'conditional':
            # "if not t goto L": false goes to L; true falls through.
            edges.append(Edge(block.name, owner[labels[last.target]], 'false'))
            edges.append(Edge(block.name, following, 'true'))
        else:
            edges.append(Edge(block.name, following, 'fallthrough'))
    return FlowGraph(blocks, edges)


IMAGE_FORMATS = {'png', 'svg', 'pdf'}
SUFFIX_FORMATS = {'.txt': 'text', '.dot': 'dot', '.json': 'json',
                  '.png': 'png', '.svg': 'svg', '.pdf': 'pdf'}


def output_format(output, requested=None):
    inferred = SUFFIX_FORMATS.get(Path(output).suffix.lower()) if output else None
    if output and inferred is None and requested is None:
        raise FlowGraphError('出力の拡張子は .png, .svg, .pdf, .txt, .dot, .json を指定してください')
    if inferred and requested and inferred != requested:
        raise FlowGraphError('--format と出力ファイルの拡張子が一致しません')
    return inferred or requested or 'text'


def render_image(graph, image_format):
    if image_format not in IMAGE_FORMATS:
        raise FlowGraphError(f'未対応の画像形式: {image_format}')
    try:
        result = subprocess.run(['dot', f'-T{image_format}'],
                                input=graph.to_dot().encode('utf-8'), capture_output=True)
    except FileNotFoundError as error:
        raise FlowGraphError('画像出力にはGraphvizのdotが必要です') from error
    if result.returncode:
        raise FlowGraphError('Graphvizの画像生成に失敗しました: '
                             + result.stderr.decode('utf-8', errors='replace').strip())
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description='３番地コードから基本ブロックとフローグラフを生成')
    parser.add_argument('input', nargs='?', help='３番地コード（省略時は標準入力）')
    parser.add_argument('--format', choices=['text', 'dot', 'json', 'png', 'svg', 'pdf'])
    parser.add_argument('--dominator-tree', action='store_true', help='フローグラフの代わりに支配木を出力')
    parser.add_argument('-o', '--output', help='出力先。拡張子で形式を判定（png/svg/pdf/txt/dot/json）')
    args = parser.parse_args()
    try:
        fmt = output_format(args.output, args.format)
        if fmt in IMAGE_FORMATS and not args.output:
            raise FlowGraphError('画像出力には -o で出力ファイルを指定してください')
        code = Path(args.input).read_text(encoding='utf-8') if args.input else sys.stdin.read()
        graph = build_flow_graph(code)
        if args.dominator_tree:
            from dominator_tree import build_dominator_tree
            graph = build_dominator_tree(graph)
        if fmt in IMAGE_FORMATS:
            Path(args.output).write_bytes(render_image(graph, fmt))
        elif args.output:
            result = getattr(graph, 'to_' + fmt)()
            Path(args.output).write_text(result, encoding='utf-8')
        else:
            sys.stdout.write(getattr(graph, 'to_' + fmt)())
    except (FlowGraphError, OSError, UnicodeError) as error:
        print(f'エラー: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
