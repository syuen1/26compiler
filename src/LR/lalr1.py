#!/usr/bin/env python3
"""Yacc 風文法から LALR(1) 項集合族（LALR(1) オートマトン）を生成する。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from lr1 import Item, dot_source as lr1_dot_source, format_automaton, format_transition_table, lr1_automaton
from slr import Grammar, GrammarError, Production, parse_grammar, write_graph


def lalr_automaton(grammar: Grammar) -> tuple[list[Production], list[frozenset[Item]], dict[tuple[int, str], int]]:
    """同一 LR(0) コアの正準 LR(1) 状態を併合して LALR(1) 状態を作る。"""
    productions, canonical_states, canonical_transitions = lr1_automaton(grammar)
    state_for_core: dict[frozenset[tuple[int, int]], int] = {}
    canonical_to_lalr: dict[int, int] = {}
    lookaheads: list[dict[tuple[int, int], set[str]]] = []

    for canonical_number, state in enumerate(canonical_states):
        core = frozenset((production, dot) for production, dot, _ in state)
        if core not in state_for_core:
            state_for_core[core] = len(lookaheads)
            lookaheads.append({})
        lalr_number = state_for_core[core]
        canonical_to_lalr[canonical_number] = lalr_number
        for production, dot, lookahead in state:
            lookaheads[lalr_number].setdefault((production, dot), set()).add(lookahead)

    states = [
        frozenset((production, dot, lookahead) for (production, dot), values in state.items() for lookahead in values)
        for state in lookaheads
    ]
    transitions: dict[tuple[int, str], int] = {}
    for (source, symbol), target in canonical_transitions.items():
        key = canonical_to_lalr[source], symbol
        lalr_target = canonical_to_lalr[target]
        previous = transitions.setdefault(key, lalr_target)
        if previous != lalr_target:
            raise GrammarError("LALR(1) 状態の併合後に一意でない遷移が見つかりました")
    return productions, states, transitions


def dot_source(
    productions: list[Production], states: list[frozenset[Item]], transitions: dict[tuple[int, str], int], vertical: bool = False
) -> str:
    """LALR(1) の名称を付けた Graphviz DOT ソースを返す。"""
    return lr1_dot_source(productions, states, transitions, vertical).replace("digraph LR1 {", "digraph LALR1 {", 1)


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
        productions, states, transitions = lalr_automaton(grammar)
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
