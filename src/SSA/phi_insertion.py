#!/usr/bin/env python3
"""Iterated dominance frontiers and unpruned phi placement (before SSA renaming)."""
import argparse
import json
import re
import sys
from collections import deque
from dataclasses import dataclass, field, replace
from pathlib import Path
from dominance_frontier import compute_dominance_frontiers, load_flow_graph
from flow_graph import (BasicBlock, FlowGraph, FlowGraphError, Instruction, NAME,
                        IMAGE_FORMATS, build_flow_graph, output_format, render_image)


@dataclass
class PhiInsertion:
    graph: FlowGraph
    definitions: dict
    placements: dict
    unreachable: list
    trace: dict = field(default_factory=dict)
    verbose: bool = False

    def verbose_report(self):
        def members(values):
            return '{' + ', '.join(values) + '}'
        lines = ['Phi insertion calculation (worklist):']
        for variable, detail in self.trace.items():
            lines += ['', f'variable {variable}:',
                      f'  Def({variable}) = {members(detail["definitions"])}',
                      '  initial worklist = [' + ', '.join(detail['definitions']) + ']']
            for step in detail['steps']:
                lines.append(f'  step {step["step"]}: pop {step["block"]}; '
                             f'DF({step["block"]}) = {members(step["frontier"])}')
                for candidate in step['candidates']:
                    action = 'insert phi' if candidate['inserted'] else 'already inserted; skip'
                    if candidate['inserted']:
                        action += '; enqueue (new definition)' if candidate['enqueued'] else '; already scheduled; no enqueue'
                    lines.append(f'    {candidate["block"]}: {action}')
                lines += ['    inserted = ' + members(step['inserted']),
                          '    worklist = [' + ', '.join(step['worklist_after']) + ']']
            lines.append(f'  fixed point: IDF(Def({variable})) = {members(detail["placements"])}')
        return '\n'.join(lines) + '\n'

    def report(self):
        order = [b.name for b in self.graph.blocks]
        lines = ['Phi placement (iterated dominance frontier):']
        for name, blocks in self.placements.items():
            defs = ', '.join(b for b in order if b in self.definitions[name])
            sites = ', '.join(b for b in order if b in blocks)
            lines.append(f'{name}: Def = {{{defs}}}; IDF = {{{sites}}}')
        if self.unreachable:
            lines.append('unreachable (excluded): ' + ', '.join(self.unreachable))
        return '\n'.join(lines) + '\n'

    def to_text(self):
        trace = self.verbose_report() + '\n' if self.trace else ''
        return self.report() + '\n' + trace + self.display_graph().to_text()

    def display_graph(self):
        """Hide incoming-block annotations without changing the analysis IR."""
        if self.verbose:
            return self.graph
        blocks = [BasicBlock(b.name, [
            replace(i, text=re.sub(rf'@{NAME}', '', i.text)) if i.kind == 'phi' else i
            for i in b.instructions]) for b in self.graph.blocks]
        return FlowGraph(blocks, list(self.graph.edges))

    def to_dot(self):
        return self.display_graph().to_dot()

    def to_json(self):
        data = json.loads(self.graph.to_json())
        order = [b.name for b in self.graph.blocks]
        data['definitions'] = {v: [b for b in order if b in sites] for v, sites in self.definitions.items()}
        data['phi_placements'] = {v: [b for b in order if b in sites] for v, sites in self.placements.items()}
        data['unreachable'] = self.unreachable
        data['stage'] = 'phi-placement-before-ssa-renaming'
        if self.trace:
            data['insertion_trace'] = self.trace
        return json.dumps(data, ensure_ascii=False, indent=2) + '\n'


def insert_phi_functions(graph, verbose=False):
    df = compute_dominance_frontiers(graph)
    reachable = set(df.frontiers)
    definitions = {}
    for block in graph.blocks:
        if block.name not in reachable:
            continue
        for instruction in block.instructions:
            if instruction.kind == 'phi':
                raise FlowGraphError('入力にはφ関数挿入前のフローグラフを指定してください')
            match = re.match(rf'({NAME})\s*:=|read\s+({NAME})\s*$', instruction.text)
            if match:
                variable = match[1] or match[2]
                definitions.setdefault(variable, set()).add(block.name)
    order = [b.name for b in graph.blocks if b.name in reachable]
    def ordered(values):
        return [b for b in order if b in values]
    placements, trace = {}, {}
    for variable, sites in definitions.items():
        placed, visited, pending = set(), set(sites), deque(ordered(sites))
        steps = []
        while pending:
            before = list(pending)
            block = pending.popleft()
            candidates = []
            for frontier in ordered(df.frontiers[block]):
                inserted, enqueued = frontier not in placed, False
                if frontier not in placed:
                    placed.add(frontier)
                    # A newly inserted phi is itself a definition. Propagate it.
                    if frontier not in visited:
                        visited.add(frontier)
                        pending.append(frontier)
                        enqueued = True
                if verbose:
                    candidates.append({'block': frontier, 'inserted': inserted, 'enqueued': enqueued})
            if verbose:
                steps.append({'step': len(steps) + 1, 'block': block,
                              'worklist_before': before, 'frontier': ordered(df.frontiers[block]),
                              'candidates': candidates, 'inserted': ordered(placed),
                              'worklist_after': list(pending)})
        placements[variable] = placed
        if verbose:
            trace[variable] = {'definitions': ordered(sites), 'steps': steps,
                               'placements': ordered(placed)}
    predecessors = {b: set() for b in reachable}
    for edge in graph.edges:
        if edge.source in reachable and edge.target in reachable:
            predecessors[edge.target].add(edge.source)
    order = [b.name for b in graph.blocks if b.name in reachable]
    blocks = []
    for block in graph.blocks:
        if block.name not in reachable:
            continue
        phi = []
        for variable, sites in placements.items():
            if block.name in sites:
                incoming = [p for p in order if p in predecessors[block.name]]
                # ENTRY is an incoming path even when root has a backedge.
                if block.name == df.root:
                    incoming.insert(0, 'ENTRY')
                arguments = ', '.join(f'{variable}@{p}' for p in incoming)
                phi.append(Instruction(0, f'{variable} := φ({arguments})', 'phi'))
        # Keep leading label declarations before phi instructions.
        split = 0
        while split < len(block.instructions) and block.instructions[split].kind == 'label':
            split += 1
        instructions = block.instructions[:split] + phi + block.instructions[split:]
        blocks.append(BasicBlock(block.name, instructions))
    edges = [e for e in graph.edges if e.source in reachable and (e.target in reachable or e.target == 'EXIT')]
    return PhiInsertion(FlowGraph(blocks, edges), definitions, placements, df.unreachable, trace, verbose)


def main():
    parser = argparse.ArgumentParser(description='DFを反復適用し、変数ごとのφ関数をCFGに挿入')
    parser.add_argument('input', nargs='?', help='３番地コードまたはCFG JSON（省略時は標準入力）')
    parser.add_argument('--input-format', choices=['tac', 'json'], help='省略時は入力の.json拡張子で判定')
    parser.add_argument('--format', choices=['text', 'json', 'dot', 'png', 'svg', 'pdf'])
    parser.add_argument('-o', '--output', help='出力形式は拡張子で判定')
    parser.add_argument('-v', '--verbose', action='store_true', help='定義集合・DFの反復・φ挿入の計算過程を表示')
    args = parser.parse_args()
    try:
        fmt = output_format(args.output, args.format)
        if fmt in IMAGE_FORMATS and not args.output:
            raise FlowGraphError('画像出力には-oが必要です')
        text = Path(args.input).read_text(encoding='utf-8') if args.input else sys.stdin.read()
        input_fmt = args.input_format or ('json' if args.input and Path(args.input).suffix.lower() == '.json' else 'tac')
        graph = load_flow_graph(text) if input_fmt == 'json' else build_flow_graph(text)
        result = insert_phi_functions(graph, verbose=args.verbose)
        if args.verbose and fmt in IMAGE_FORMATS | {'dot'}:
            sys.stderr.write(result.verbose_report())
        if fmt in IMAGE_FORMATS:
            Path(args.output).write_bytes(render_image(result, fmt))
        else:
            output = getattr(result, 'to_' + fmt)()
            if args.output:
                Path(args.output).write_text(output, encoding='utf-8')
            else:
                sys.stdout.write(output)
    except (FlowGraphError, OSError, UnicodeError) as error:
        print(f'エラー: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
