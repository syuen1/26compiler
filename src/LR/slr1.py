#!/usr/bin/env python3
"""Yacc 風文法から SLR(1) 構文解析表を生成する。"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path
from typing import Sequence

from slr import Grammar, GrammarError, Production, lr0_automaton, parse_grammar, write_graph


EPSILON = "ε"
ENDMARK = "#"


def first_sets(grammar: Grammar) -> dict[str, set[str]]:
    """各非終端記号の FIRST 集合を固定点まで計算する。"""
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


def render_table(grammar: Grammar, states: list[frozenset[tuple[int, int]]], action: dict[tuple[int, str], list[str]], goto: dict[tuple[int, str], int]) -> str:
    terminals = grammar.terminals + [ENDMARK]
    columns = ["状態"] + terminals + grammar.nonterminals
    rows = [columns]
    for state in range(len(states)):
        rows.append(
            [str(state)]
            + [" / ".join(action.get((state, terminal), [])) or "·" for terminal in terminals]
            + [str(goto.get((state, nonterminal), "·")) for nonterminal in grammar.nonterminals]
        )
    widths = [max(len(row[index]) for row in rows) for index in range(len(columns))]
    lines: list[str] = []
    for row_number, row in enumerate(rows):
        lines.append(" | ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
        if row_number == 0:
            lines.append("-+-".join("-" * width for width in widths))
    return "\n".join(lines)


def latex_escape(value: str) -> str:
    """LaTex の通常テキストセルで特別な文字をエスケープする。"""
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
        "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in value)


def latex_table(
    grammar: Grammar,
    states: list[frozenset[tuple[int, int]]],
    action: dict[tuple[int, str], list[str]],
    goto: dict[tuple[int, str], int],
    caption: str = "SLR(1) parsing table",
) -> str:
    """ACTION/GOTO 表をそのまま貼り付けられる LaTeX table 環境にする。"""
    terminals = grammar.terminals + [ENDMARK]
    nonterminals = grammar.nonterminals
    column_spec = "c|" + "c" * len(terminals) + "|" + "c" * len(nonterminals)
    lines = [
        r"\begin{table}[htbp]",
        r"  \centering",
        r"  \small",
        r"  \caption{" + latex_escape(caption) + "}",
        r"  \begin{tabular}{" + column_spec + "}",
        r"    \hline",
        "    & " + rf"\multicolumn{{{len(terminals)}}}{{c|}}{{ACTION}}" + " & "
        + rf"\multicolumn{{{len(nonterminals)}}}{{c}}{{GOTO}}" + r" \\",
        r"    \hline",
        "    State & " + " & ".join(latex_escape(symbol) for symbol in terminals + nonterminals) + r" \\",
        r"    \hline",
    ]
    for state in range(len(states)):
        actions = [" / ".join(action.get((state, terminal), [])) or r"$\cdot$" for terminal in terminals]
        gotos = [str(goto.get((state, nonterminal), r"$\cdot$")) for nonterminal in nonterminals]
        lines.append("    " + " & ".join([str(state)] + actions + gotos) + r" \\")
    lines.extend([r"    \hline", r"  \end{tabular}", r"\end{table}", ""])
    return "\n".join(lines)


def parsing_table_dot(grammar: Grammar, states: list[frozenset[tuple[int, int]]], action: dict[tuple[int, str], list[str]], goto: dict[tuple[int, str], int]) -> str:
    """SLR(1) 構文解析表を Graphviz の HTML テーブルラベルで表現する。"""
    terminals = grammar.terminals + [ENDMARK]
    nonterminals = grammar.nonterminals
    def cell(value: str, **attributes: str) -> str:
        attrs = " ".join(f'{key}="{html.escape(value, quote=True)}"' for key, value in attributes.items())
        return f"<TD {attrs}>{html.escape(value)}</TD>"
    lines = [
        "digraph ParsingTable {",
        "  graph [pad=0.2];",
        "  node [shape=plain fontname=Helvetica];",
        "  parsing_table [label=<",
        '    <TABLE BORDER="1" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">',
        "      <TR>"
        + cell("State", ROWSPAN="2", BGCOLOR="lightgray")
        + cell("ACTION", COLSPAN=str(len(terminals)), BGCOLOR="lightgray")
        + cell("GOTO", COLSPAN=str(len(nonterminals)), BGCOLOR="lightgray")
        + "</TR>",
        "      <TR>" + "".join(cell(symbol, BGCOLOR="lightgray") for symbol in terminals + nonterminals) + "</TR>",
    ]
    for state in range(len(states)):
        actions = [" / ".join(action.get((state, terminal), [])) or "·" for terminal in terminals]
        gotos = [str(goto.get((state, nonterminal), "·")) for nonterminal in nonterminals]
        lines.append("      <TR>" + cell(str(state)) + "".join(cell(value) for value in actions + gotos) + "</TR>")
    lines.extend(["    </TABLE>", "  >];", "}", ""])
    return "\n".join(lines)


def table_listing(
    grammar: Grammar,
    productions: list[Production],
    action: dict[tuple[int, str], list[str]],
    goto: dict[tuple[int, str], int],
    title: str = "SLR(1)",
) -> str:
    """PDTが読み込める、生成規則と非空セルの .tab 形式を作る。"""
    terminal_order = {symbol: index for index, symbol in enumerate(grammar.terminals + [ENDMARK])}
    nonterminal_order = {symbol: index for index, symbol in enumerate(grammar.nonterminals)}
    lines = [
        f"# {title} parsing table",
        "[PRODUCTIONS]",
        f"PRODUCTION[0] = attr-start -> {grammar.start} #",
    ]
    for production in productions:
        rhs = " ".join(production.rhs) if production.rhs else "ε"
        lines.append(f"PRODUCTION[{production.number}] = {production.lhs} -> {rhs}")
    lines.extend(["", "[ACTION]"])
    for (state, terminal), values in sorted(action.items(), key=lambda entry: (entry[0][0], terminal_order[entry[0][1]])):
        lines.append(f"ACTION[{state}, {terminal}] = {' / '.join(values)}")
    lines.extend(["", "[GOTO]"])
    for (state, nonterminal), target in sorted(goto.items(), key=lambda entry: (entry[0][0], nonterminal_order[entry[0][1]])):
        lines.append(f"GOTO[{state}, {nonterminal}] = {target}")
    return "\n".join(lines) + "\n"


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
            args.tex_table.write_text(latex_table(grammar, states, action, goto), encoding="utf-8")
        if args.eps:
            productions, states, transitions = lr0_automaton(grammar)
            action, goto = slr_table(grammar, productions, states, transitions, follow_sets(grammar, first_sets(grammar)))
            write_graph(args.eps, parsing_table_dot(grammar, states, action, goto), "eps")
        if args.outtab:
            first = first_sets(grammar)
            follow = follow_sets(grammar, first)
            productions, states, transitions = lr0_automaton(grammar)
            action, goto = slr_table(grammar, productions, states, transitions, follow)
            args.outtab.write_text(table_listing(grammar, grammar.productions, action, goto), encoding="utf-8")
        return 1 if has_conflicts else 0
    except (GrammarError, OSError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
