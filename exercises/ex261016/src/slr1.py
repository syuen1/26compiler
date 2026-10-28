#!/usr/bin/env python3
"""Yacc 風文法から SLR(1) 構文解析表を生成する。"""

from __future__ import annotations

import argparse
from importlib import import_module
import sys
from pathlib import Path
from typing import Sequence


# ハイフンを含む共有モジュール名は import_module で読み込む。
_common = import_module("lr-common")
GrammarError = _common.GrammarError
Production = _common.Production
Grammar = _common.Grammar
remove_comments = _common.remove_comments
lex_rules = _common.lex_rules
parse_grammar = _common.parse_grammar
write_graph = _common.write_graph
EPSILON = _common.EPSILON
ENDMARK = _common.ENDMARK
first_sets = _common.first_sets
first_of_sequence = _common.first_of_sequence
Item = _common.LR0Item
lr0_automaton = _common.lr0_automaton
render_table = _common.render_table
latex_escape = _common.latex_escape
latex_table = _common.latex_table
parsing_table_dot = _common.parsing_table_dot
table_listing = _common.table_listing


def follow_sets(grammar: Grammar, first: dict[str, set[str]]) -> dict[str, set[str]]:
    """SLR(1) の還元先を決める FOLLOW 集合を計算する。"""
    nonterminals = set(grammar.nonterminals)
    follow = {symbol: set() for symbol in grammar.nonterminals}
    follow[grammar.start].add(ENDMARK)
    changed = True
    while changed:
        changed = False
        for production in grammar.productions:
            for position, symbol in enumerate(production.rhs):
                if symbol not in nonterminals:
                    continue
                suffix = first_of_sequence(production.rhs[position + 1 :], first, nonterminals)
                values = suffix - {EPSILON}
                if EPSILON in suffix:
                    values |= follow[production.lhs]
                before = len(follow[symbol])
                follow[symbol].update(values)
                changed |= before != len(follow[symbol])
    return follow


def slr_table(
    grammar: Grammar,
    productions: list[Production],
    states: list[frozenset[tuple[int, int]]],
    transitions: dict[tuple[int, str], int],
    follow: dict[str, set[str]],
) -> tuple[dict[tuple[int, str], list[str]], dict[tuple[int, str], int]]:
    """ACTION（複数候補を保持）と GOTO を作る。"""
    action: dict[tuple[int, str], list[str]] = {}
    goto: dict[tuple[int, str], int] = {}
    terminals = set(grammar.terminals)
    nonterminals = set(grammar.nonterminals)

    def add_action(state: int, terminal: str, value: str) -> None:
        cell = action.setdefault((state, terminal), [])
        if value not in cell:
            cell.append(value)

    for (state, symbol), target in transitions.items():
        if symbol in terminals:
            add_action(state, symbol, f"s{target}")
        elif symbol in nonterminals:
            goto[state, symbol] = target
    for state_number, state in enumerate(states):
        for production_index, dot in state:
            production = productions[production_index]
            if dot != len(production.rhs):
                continue
            if production_index == 0:
                add_action(state_number, ENDMARK, "acc")
            else:
                for terminal in follow[production.lhs]:
                    add_action(state_number, terminal, f"r{production.number}")
    return action, goto


def render_set(values: set[str], grammar: Grammar) -> str:
    order = grammar.terminals + [ENDMARK, EPSILON]
    return "{ " + ", ".join(symbol for symbol in order if symbol in values) + " }"


def format_analysis(grammar: Grammar) -> tuple[str, bool]:
    first = first_sets(grammar)
    follow = follow_sets(grammar, first)
    productions, states, transitions = lr0_automaton(grammar)
    action, goto = slr_table(grammar, productions, states, transitions, follow)
    conflicts = [(state, terminal, values) for (state, terminal), values in action.items() if len(values) > 1]

    lines = [f"開始記号: {grammar.start}", "", "生成規則:"]
    lines.extend(f"  [{production.number}] {production.text()}" for production in grammar.productions)
    lines.extend(["", "FIRST:"])
    lines.extend(f"  FIRST({symbol}) = {render_set(first[symbol], grammar)}" for symbol in grammar.nonterminals)
    lines.extend(["", "FOLLOW:"])
    lines.extend(f"  FOLLOW({symbol}) = {render_set(follow[symbol], grammar)}" for symbol in grammar.nonterminals)
    lines.extend(["", "SLR(1) 構文解析表:", "ACTION列: sN = Nへ shift、rN = 規則Nで reduce、acc = accept", render_table(grammar, states, action, goto)])
    if conflicts:
        lines.extend(["", "競合:"])
        lines.extend(f"  ACTION[{state}, {terminal}] = {' / '.join(values)}" for state, terminal, values in conflicts)
        lines.append("この文法は SLR(1) ではありません。")
    else:
        lines.extend(["", "競合はありません。この文法は SLR(1) です。"])
    return "\n".join(lines), bool(conflicts)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("grammar", nargs="?", help="UTF-8 の文法ファイル（省略時は標準入力）")
    parser.add_argument("--tex-table", type=Path, metavar="出力ファイル.tex", help="SLR(1) 構文解析表を LaTeX table 環境として保存")
    parser.add_argument("--eps", type=Path, metavar="出力ファイル", help="SLR(1) 構文解析表を EPS 形式で出力")
    parser.add_argument("--outtab", type=Path, metavar="出力ファイル.tab", help="SLR(1) 構文解析表をリスト形式で保存")
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
        output, has_conflicts = format_analysis(grammar)
        print(output)
        if args.tex_table:
            first = first_sets(grammar)
            follow = follow_sets(grammar, first)
            productions, states, transitions = lr0_automaton(grammar)
            action, goto = slr_table(grammar, productions, states, transitions, follow)
            args.tex_table.write_text(latex_table(grammar, states, action, goto, "SLR(1) parsing table"), encoding="utf-8")
        if args.eps:
            productions, states, transitions = lr0_automaton(grammar)
            action, goto = slr_table(grammar, productions, states, transitions, follow_sets(grammar, first_sets(grammar)))
            write_graph(args.eps, parsing_table_dot(grammar, states, action, goto), "eps")
        if args.outtab:
            first = first_sets(grammar)
            follow = follow_sets(grammar, first)
            productions, states, transitions = lr0_automaton(grammar)
            action, goto = slr_table(grammar, productions, states, transitions, follow)
            args.outtab.write_text(table_listing(grammar, grammar.productions, action, goto, "SLR(1)"), encoding="utf-8")
        return 1 if has_conflicts else 0
    except (GrammarError, OSError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
