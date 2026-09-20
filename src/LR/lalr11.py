#!/usr/bin/env python3
"""Yacc 風文法から LALR(1) 構文解析表を生成する。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from lalr1 import lalr_automaton
from lr1 import Item
from lr11 import lr1_table
from slr import Grammar, GrammarError, Production, parse_grammar, write_graph
from slr1 import latex_table, parsing_table_dot, render_table, table_listing


def format_analysis(grammar: Grammar) -> tuple[str, bool, list[Production], list[frozenset[Item]], dict[tuple[int, str], int], dict[tuple[int, str], list[str]], dict[tuple[int, str], int]]:
    productions, states, transitions = lalr_automaton(grammar)
    action, goto = lr1_table(grammar, productions, states, transitions)
    conflicts = [(state, terminal, values) for (state, terminal), values in action.items() if len(values) > 1]
    lines = [f"開始記号: {grammar.start}", "", "生成規則:"]
    lines.extend(f"  [{production.number}] {production.text()}" for production in grammar.productions)
    lines.extend(["", "LALR(1) 構文解析表:", "ACTION列: sN = Nへ shift、rN = 規則Nで reduce、acc = accept", render_table(grammar, states, action, goto)])
    if conflicts:
        lines.extend(["", "競合:"])
        lines.extend(f"  ACTION[{state}, {terminal}] = {' / '.join(values)}" for state, terminal, values in conflicts)
        lines.append("この文法は LALR(1) ではありません。")
    else:
        lines.extend(["", "競合はありません。この文法は LALR(1) です。"])
    return "\n".join(lines), bool(conflicts), productions, states, transitions, action, goto


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("grammar", nargs="?", help="UTF-8 の文法ファイル（省略時は標準入力）")
    parser.add_argument("--tex-table", type=Path, metavar="出力ファイル.tex", help="LALR(1) 構文解析表を LaTeX table 環境として保存")
    parser.add_argument("--eps", type=Path, metavar="出力ファイル", help="LALR(1) 構文解析表を EPS 形式で出力")
    parser.add_argument("--outtab", type=Path, metavar="出力ファイル.tab", help="LALR(1) 構文解析表をリスト形式で保存")
    args = parser.parse_args(argv)
    try:
        if args.tex_table and args.grammar and args.tex_table.resolve() == Path(args.grammar).resolve():
            raise GrammarError("--tex-table の出力先には入力文法と異なるファイルを指定してください")
        if args.eps and args.grammar and args.eps.resolve() == Path(args.grammar).resolve():
            raise GrammarError("--eps の出力先には入力文法と異なるファイルを指定してください")
        if args.outtab and args.grammar and args.outtab.resolve() == Path(args.grammar).resolve():
            raise GrammarError("--outtab の出力先には入力文法と異なるファイルを指定してください")
        text = Path(args.grammar).read_text(encoding="utf-8-sig") if args.grammar else sys.stdin.read()
        grammar = parse_grammar(text)
        output, has_conflicts, productions, states, transitions, action, goto = format_analysis(grammar)
        print(output)
        if args.tex_table:
            args.tex_table.write_text(latex_table(grammar, states, action, goto, "LALR(1) parsing table"), encoding="utf-8")
        if args.eps:
            write_graph(args.eps, parsing_table_dot(grammar, states, action, goto), "eps")
        if args.outtab:
            args.outtab.write_text(table_listing(grammar, grammar.productions, action, goto, "LALR(1)"), encoding="utf-8")
        return 1 if has_conflicts else 0
    except (GrammarError, OSError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
