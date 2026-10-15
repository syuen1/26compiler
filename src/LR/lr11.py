#!/usr/bin/env python3
"""Yacc 風文法から正準 LR(1) 構文解析表を生成する。"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
from dataclasses import dataclass
import sys
from pathlib import Path
from typing import Sequence

from lr1 import ENDMARK, Item, lr1_automaton
class GrammarError(ValueError):
    """入力がサポート対象の Yacc 風文法ではない。"""


@dataclass(frozen=True)
class Production:
    number: int
    lhs: str
    rhs: tuple[str, ...]

    def text(self, dot: int | None = None) -> str:
        body = list(self.rhs)
        if dot is not None:
            body.insert(dot, "·")
        return f"{self.lhs} -> {' '.join(body) if body else '·'}"


@dataclass
class Grammar:
    start: str
    nonterminals: list[str]
    terminals: list[str]
    productions: list[Production]


def remove_comments(text: str) -> str:
    """コメントを除去する（引用符中のコメント記号は保持する）。"""
    out: list[str] = []
    i = 0
    quote: str | None = None
    while i < len(text):
        char = text[i]
        if quote:
            out.append(char)
            if char == "\\" and i + 1 < len(text):
                i += 1
                out.append(text[i])
            elif char == quote:
                quote = None
            i += 1
        elif char in "'\"":
            quote = char
            out.append(char)
            i += 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise GrammarError("閉じられていない /* コメントがあります")
            out.extend("\n" for c in text[i : end + 2] if c == "\n")
            i = end + 2
        elif text.startswith("//", i):
            end = text.find("\n", i + 2)
            if end < 0:
                break
            out.append("\n")
            i = end + 1
        else:
            out.append(char)
            i += 1
    return "".join(out)


def lex_rules(text: str) -> list[str]:
    """規則部をトークン化し、Yacc の意味アクションは読み飛ばす。"""
    tokens: list[str] = []
    i = 0
    while i < len(text):
        if text[i].isspace():
            i += 1
        elif text[i] in ":|;":
            tokens.append(text[i])
            i += 1
        elif text[i] in "'\"":
            start, quote = i, text[i]
            i += 1
            while i < len(text):
                if text[i] == "\\" and i + 1 < len(text):
                    i += 2
                elif text[i] == quote:
                    i += 1
                    break
                else:
                    i += 1
            else:
                raise GrammarError("文字列リテラルが閉じられていません")
            tokens.append(text[start:i])
        elif text[i] == "{":
            # C 風の意味アクション。文字列中の波括弧には対応しない。
            depth = 1
            i += 1
            while i < len(text) and depth:
                depth += (text[i] == "{") - (text[i] == "}")
                i += 1
            if depth:
                raise GrammarError("意味アクションが閉じられていません")
        else:
            start = i
            while i < len(text) and not text[i].isspace() and text[i] not in ":|;{'\"":
                i += 1
            if start == i:
                raise GrammarError(f"解釈できない文字 {text[i]!r} です")
            tokens.append(text[start:i])
    return tokens


def parse_grammar(text: str) -> Grammar:
    sections = re.split(r"(?m)^\s*%%\s*$", remove_comments(text))
    if len(sections) < 2:
        raise GrammarError("宣言部と規則部の間に %% が必要です")
    declared_terminals: list[str] = []
    start: str | None = None
    for line in sections[0].splitlines():
        match = re.match(r"\s*%(token|left|right|nonassoc)\b(.*)$", line)
        if match:
            words = re.findall(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|[^\s,]+", re.sub(r"<[^>]*>", " ", match.group(2)))
            for word in words:
                if not word.isdigit() and word not in declared_terminals:
                    declared_terminals.append(word)
            continue
        match = re.match(r"\s*%start\s+(\S+)\s*$", line)
        if match:
            if start is not None:
                raise GrammarError("%start は一度だけ指定できます")
            start = match.group(1)

    tokens = lex_rules(sections[1])
    raw: list[tuple[str, tuple[str, ...]]] = []
    nonterminals: list[str] = []
    i = 0
    while i < len(tokens):
        lhs = tokens[i]
        if lhs in {":", "|", ";"} or lhs.startswith("%"):
            raise GrammarError("左辺の非終端記号が必要です")
        if lhs not in nonterminals:
            nonterminals.append(lhs)
        i += 1
        if i >= len(tokens) or tokens[i] != ":":
            raise GrammarError(f"{lhs} の後に : が必要です")
        i += 1
        rhs: list[str] = []
        while True:
            if i >= len(tokens):
                raise GrammarError(f"規則 {lhs} が ; で閉じられていません")
            token = tokens[i]
            i += 1
            if token in {"|", ";"}:
                if "%empty" in rhs and rhs != ["%empty"]:
                    raise GrammarError("%empty は選択肢の単独要素にしてください")
                raw.append((lhs, () if rhs == ["%empty"] else tuple(rhs)))
                rhs = []
                if token == ";":
                    break
            elif token == "%prec":
                if i >= len(tokens):
                    raise GrammarError("%prec の後にトークンが必要です")
                i += 1
            elif token.startswith("%") and token != "%empty":
                raise GrammarError(f"規則内の {token} には対応していません")
            else:
                rhs.append(token)
    if not raw:
        raise GrammarError("生成規則がありません")
    start = start or nonterminals[0]
    if start not in nonterminals:
        raise GrammarError(f"開始記号 {start} に生成規則がありません")
    terminals = list(declared_terminals)
    nts = set(nonterminals)
    for _, rhs in raw:
        for symbol in rhs:
            if symbol not in nts and symbol not in terminals:
                terminals.append(symbol)
    return Grammar(start, nonterminals, terminals, [Production(i + 1, lhs, rhs) for i, (lhs, rhs) in enumerate(raw)])


def write_graph(path: Path, source: str, output_format: str | None = None) -> None:
    suffix = output_format or path.suffix.lower().lstrip(".")
    if not suffix:
        raise GrammarError("--graph の出力ファイル名には .png、.svg、.pdf、.dot などの拡張子が必要です")
    if suffix == "dot":
        path.write_text(source, encoding="utf-8")
        return
    dot = shutil.which("dot")
    if dot is None:
        raise GrammarError("Graphviz の dot コマンドが見つかりません（.dot 出力は利用できます）")
    try:
        subprocess.run([dot, f"-T{suffix}", "-o", str(path)], input=source, text=True, check=True, capture_output=True)
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or "dot の実行に失敗しました"
        raise GrammarError(detail) from error


def render_table(grammar: Grammar, states: list[frozenset[Item]], action: dict[tuple[int, str], list[str]], goto: dict[tuple[int, str], int]) -> str:
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
    states: list[frozenset[Item]],
    action: dict[tuple[int, str], list[str]],
    goto: dict[tuple[int, str], int],
    caption: str = "LR(1) parsing table",
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


def parsing_table_dot(grammar: Grammar, states: list[frozenset[Item]], action: dict[tuple[int, str], list[str]], goto: dict[tuple[int, str], int]) -> str:
    """LR(1) 構文解析表を Graphviz の HTML テーブルラベルで表現する。"""
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
    title: str = "LR(1)",
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


def lr1_table(
    grammar: Grammar,
    productions: list[Production],
    states: list[frozenset[Item]],
    transitions: dict[tuple[int, str], int],
) -> tuple[dict[tuple[int, str], list[str]], dict[tuple[int, str], int]]:
    """正準 LR(1) 項の先読み記号を使って ACTION/GOTO を構築する。"""
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
        for production_index, dot, lookahead in state:
            production = productions[production_index]
            if dot != len(production.rhs):
                continue
            if production_index == 0:
                add_action(state_number, ENDMARK, "acc")
            else:
                add_action(state_number, lookahead, f"r{production.number}")
    return action, goto


def format_analysis(grammar: Grammar) -> tuple[str, bool, list[Production], list[frozenset[Item]], dict[tuple[int, str], int], dict[tuple[int, str], list[str]], dict[tuple[int, str], int]]:
    productions, states, transitions = lr1_automaton(grammar)
    action, goto = lr1_table(grammar, productions, states, transitions)
    conflicts = [(state, terminal, values) for (state, terminal), values in action.items() if len(values) > 1]
    lines = [f"開始記号: {grammar.start}", "", "生成規則:"]
    lines.extend(f"  [{production.number}] {production.text()}" for production in grammar.productions)
    lines.extend(["", "正準 LR(1) 構文解析表:", "ACTION列: sN = Nへ shift、rN = 規則Nで reduce、acc = accept", render_table(grammar, states, action, goto)])
    if conflicts:
        lines.extend(["", "競合:"])
        lines.extend(f"  ACTION[{state}, {terminal}] = {' / '.join(values)}" for state, terminal, values in conflicts)
        lines.append("この文法は LR(1) ではありません。")
    else:
        lines.extend(["", "競合はありません。この文法は LR(1) です。"])
    return "\n".join(lines), bool(conflicts), productions, states, transitions, action, goto


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("grammar", nargs="?", help="UTF-8 の文法ファイル（省略時は標準入力）")
    parser.add_argument("--tex-table", type=Path, metavar="出力ファイル.tex", help="LR(1) 構文解析表を LaTeX table 環境として保存")
    parser.add_argument("--eps", type=Path, metavar="出力ファイル", help="LR(1) 構文解析表を EPS 形式で出力")
    parser.add_argument("--outtab", type=Path, metavar="出力ファイル.tab", help="LR(1) 構文解析表をリスト形式で保存")
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
            args.tex_table.write_text(latex_table(grammar, states, action, goto, "LR(1) parsing table"), encoding="utf-8")
        if args.eps:
            write_graph(args.eps, parsing_table_dot(grammar, states, action, goto), "eps")
        if args.outtab:
            args.outtab.write_text(table_listing(grammar, grammar.productions, action, goto, "LR(1)"), encoding="utf-8")
        return 1 if has_conflicts else 0
    except (GrammarError, OSError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
