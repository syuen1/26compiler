#!/usr/bin/env python3
"""Yacc 風文法から正準 LR(1) 項集合族（LR(1) オートマトン）を生成する。"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
import sys
from pathlib import Path
from typing import Iterable, Sequence

from slr import Grammar, GrammarError, Production, parse_grammar, write_graph


EPSILON = "ε"
ENDMARK = "#"
Item = tuple[int, int, str]  # (生成規則の添字, ドット位置, 先読み記号)


def first_sets(grammar: Grammar) -> dict[str, set[str]]:
    """非終端記号ごとの FIRST 集合を計算する。"""
    nonterminals = set(grammar.nonterminals)
    first = {symbol: set() for symbol in grammar.nonterminals}
    changed = True
    while changed:
        changed = False
        for production in grammar.productions:
            values = first_of_sequence(production.rhs, first, nonterminals)
            before = len(first[production.lhs])
            first[production.lhs].update(values)
            changed |= before != len(first[production.lhs])
    return first


def first_of_sequence(symbols: Sequence[str], first: dict[str, set[str]], nonterminals: set[str]) -> set[str]:
    """記号列の FIRST 集合を返す。"""
    if not symbols:
        return {EPSILON}
    result: set[str] = set()
    for symbol in symbols:
        if symbol not in nonterminals:
            result.add(symbol)
            return result
        result.update(first[symbol] - {EPSILON})
        if EPSILON not in first[symbol]:
            return result
    result.add(EPSILON)
    return result


def lr1_automaton(grammar: Grammar) -> tuple[list[Production], list[frozenset[Item]], dict[tuple[int, str], int]]:
    """正準 LR(1) 項集合族と goto 遷移を返す。"""
    augmented = [Production(0, grammar.start + "'", (grammar.start,))] + grammar.productions
    nonterminals = set(grammar.nonterminals) | {augmented[0].lhs}
    first = first_sets(grammar)
    by_lhs: dict[str, list[int]] = defaultdict(list)
    for index, production in enumerate(augmented):
        by_lhs[production.lhs].append(index)

    def closure(seed: Iterable[Item]) -> frozenset[Item]:
        result = set(seed)
        pending = list(result)
        while pending:
            production_index, dot, lookahead = pending.pop()
            production = augmented[production_index]
            if dot >= len(production.rhs) or production.rhs[dot] not in nonterminals:
                continue
            symbol = production.rhs[dot]
            lookaheads = first_of_sequence(production.rhs[dot + 1 :] + (lookahead,), first, nonterminals) - {EPSILON}
            for child in by_lhs[symbol]:
                for child_lookahead in lookaheads:
                    item = (child, 0, child_lookahead)
                    if item not in result:
                        result.add(item)
                        pending.append(item)
        return frozenset(result)

    states = [closure({(0, 0, ENDMARK)})]
    numbers = {states[0]: 0}
    transitions: dict[tuple[int, str], int] = {}
    queue = deque([0])
    while queue:
        state_number = queue.popleft()
        state = states[state_number]
        symbols = sorted({augmented[index].rhs[dot] for index, dot, _ in state if dot < len(augmented[index].rhs)})
        for symbol in symbols:
            target = closure(
                (index, dot + 1, lookahead)
                for index, dot, lookahead in state
                if dot < len(augmented[index].rhs) and augmented[index].rhs[dot] == symbol
            )
            if target not in numbers:
                numbers[target] = len(states)
                states.append(target)
                queue.append(numbers[target])
            transitions[state_number, symbol] = numbers[target]
    return augmented, states, transitions


def format_item(production: Production, dot: int, lookahead: str) -> str:
    return f"[{production.number}] {production.text(dot)}, {lookahead}"


def format_automaton(productions: list[Production], states: list[frozenset[Item]], transitions: dict[tuple[int, str], int]) -> str:
    lines = ["拡張生成規則:"]
    lines.extend(f"  [{production.number}] {production.text()}" for production in productions)
    for state_number, state in enumerate(states):
        lines.extend(["", f"I{state_number}:"])
        lines.extend("  " + format_item(productions[index], dot, lookahead) for index, dot, lookahead in sorted(state))
        outgoing = sorted((symbol, target) for (source, symbol), target in transitions.items() if source == state_number)
        if outgoing:
            lines.append("  goto: " + ", ".join(f"{symbol} -> I{target}" for symbol, target in outgoing))
    return "\n".join(lines)


def format_transition_table(grammar: Grammar, states: list[frozenset[Item]], transitions: dict[tuple[int, str], int]) -> str:
    columns = grammar.terminals + grammar.nonterminals
    rows = [["状態"] + columns]
    for state_number in range(len(states)):
        rows.append([f"I{state_number}"] + [str(transitions.get((state_number, symbol), "·")) for symbol in columns])
    widths = [max(len(row[column]) for row in rows) for column in range(len(columns) + 1)]
    lines: list[str] = []
    for row_number, row in enumerate(rows):
        lines.append(" | ".join(value.ljust(widths[column]) for column, value in enumerate(row)))
        if row_number == 0:
            lines.append("-+-".join("-" * width for width in widths))
    return "\n".join(lines)


def dot_source(
    productions: list[Production],
    states: list[frozenset[Item]],
    transitions: dict[tuple[int, str], int],
    vertical: bool = False,
) -> str:
    """LR(1) 項をノードラベルにした Graphviz DOT ソースを返す。"""
    def escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')
    lines = ["digraph LR1 {", f"  rankdir={'TB' if vertical else 'LR'};", "  node [shape=box fontname=monospace];"]
    for number, state in enumerate(states):
        label = f"I{number}\\l" + "".join(
            escape(format_item(productions[index], dot, lookahead)) + "\\l"
            for index, dot, lookahead in sorted(state)
        )
        lines.append(f'  I{number} [label="{label}"];')
    for (source, symbol), target in sorted(transitions.items()):
        lines.append(f'  I{source} -> I{target} [label="{escape(symbol)}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("grammar", nargs="?", help="UTF-8 の文法ファイル（省略時は標準入力）")
    parser.add_argument("-T", "--table", action="store_true", help="状態遷移表を表示")
    parser.add_argument("--graph", type=Path, metavar="出力ファイル", help="Graphviz で状態遷移図を出力（拡張子で形式を指定）")
    parser.add_argument("--eps", type=Path, metavar="出力ファイル", help="状態遷移図を EPS 形式で出力")
    parser.add_argument("--vertical", action="store_true", help="状態遷移図を上から下へ配置（--graph または --eps と併用）")
    args = parser.parse_args(argv)
    try:
        if args.graph and args.eps:
            raise GrammarError("--graph と --eps は同時に指定できません")
        graph_output = args.graph or args.eps
        if args.vertical and graph_output is None:
            raise GrammarError("--vertical は --graph または --eps と併用してください")
        text = Path(args.grammar).read_text(encoding="utf-8-sig") if args.grammar else sys.stdin.read()
        grammar = parse_grammar(text)
        productions, states, transitions = lr1_automaton(grammar)
        print(format_automaton(productions, states, transitions))
        if args.table:
            print("\n状態遷移表:")
            print(format_transition_table(grammar, states, transitions))
        if graph_output:
            write_graph(graph_output, dot_source(productions, states, transitions, args.vertical), "eps" if args.eps else None)
        return 0
    except (GrammarError, OSError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
