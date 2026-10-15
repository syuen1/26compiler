#!/usr/bin/env python3
"""Yacc 風文法から LALR(1) 項集合族（LALR(1) オートマトン）を生成する。"""

from __future__ import annotations

import argparse
from importlib import import_module
import sys
from pathlib import Path
from typing import Sequence

from lr1 import Item, dot_source as lr1_dot_source, format_automaton, format_transition_table
from slr import Grammar, GrammarError, Production, parse_grammar, write_graph


lalr_automaton = import_module("lalr-common").lalr_automaton


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
