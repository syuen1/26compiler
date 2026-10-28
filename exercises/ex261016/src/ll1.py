#!/usr/bin/env python3
"""Yacc-like grammar reader and LL(1) parsing-table generator."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


EPSILON = "<epsilon>"
ENDMARK = "$"


class GrammarError(ValueError):
    """Raised when the input is not a supported Yacc-like grammar."""


@dataclass(frozen=True)
class Lexeme:
    value: str
    line: int
    column: int


@dataclass(frozen=True)
class Production:
    number: int
    lhs: str
    rhs: tuple[str, ...]

    def text(self) -> str:
        body = " ".join(self.rhs) if self.rhs else "ε"
        return f"{self.lhs} -> {body}"


@dataclass
class Grammar:
    start: str
    nonterminals: list[str]
    terminals: list[str]
    productions: list[Production]


def _remove_comments(text: str) -> str:
    """Remove comments while retaining newlines for useful locations."""
    out: list[str] = []
    i = 0
    quote: str | None = None
    while i < len(text):
        c = text[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < len(text):
                i += 1
                out.append(text[i])
            elif c == quote:
                quote = None
            i += 1
        elif c in "'\"":
            quote = c
            out.append(c)
            i += 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise GrammarError("閉じられていない /* コメントがあります")
            out.extend("\n" for c2 in text[i : end + 2] if c2 == "\n")
            i = end + 2
        elif text.startswith("//", i):
            end = text.find("\n", i + 2)
            if end < 0:
                break
            out.append("\n")
            i = end + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _split_yacc_sections(text: str) -> tuple[str, str]:
    parts = re.split(r"(?m)^\s*%%\s*$", text)
    if len(parts) < 2:
        raise GrammarError("宣言部と規則部の間に %% が必要です")
    return parts[0], parts[1]


def _untyped_decl_words(value: str) -> list[str]:
    # Remove Yacc semantic types such as <ival>. Numeric token codes are ignored;
    # LL(1) generation only needs symbolic token names and literals.
    value = re.sub(r"<[^>]*>", " ", value)
    words = re.findall(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|[^\s,]+", value)
    return [word for word in words if not word.isdigit()]


def _parse_declarations(text: str) -> tuple[list[str], str | None]:
    terminals: list[str] = []
    start: str | None = None
    in_code_block = False
    for lineno, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if line.startswith("%{"):
            in_code_block = True
        if in_code_block:
            if "%}" in line:
                in_code_block = False
            continue
        match = re.match(r"%(token|left|right|nonassoc)\b(.*)$", line)
        if match:
            for word in _untyped_decl_words(match.group(2)):
                if word not in terminals:
                    terminals.append(word)
            continue
        match = re.match(r"%start\s+(\S+)", line)
        if match:
            if start is not None:
                raise GrammarError(f"{lineno}行目: %start は一度だけ指定できます")
            start = match.group(1)
    return terminals, start


def _rule_lex(text: str) -> list[Lexeme]:
    tokens: list[Lexeme] = []
    i = 0
    line = 1
    column = 1

    def advance(fragment: str) -> None:
        nonlocal line, column
        lines = fragment.split("\n")
        if len(lines) == 1:
            column += len(fragment)
        else:
            line += len(lines) - 1
            column = len(lines[-1]) + 1

    while i < len(text):
        c = text[i]
        if c.isspace():
            advance(c)
            i += 1
            continue
        if c in ":|;":
            tokens.append(Lexeme(c, line, column))
            advance(c)
            i += 1
            continue
        if c in "'\"":
            start_i, start_line, start_column = i, line, column
            quote = c
            i += 1
            advance(c)
            while i < len(text):
                ch = text[i]
                i += 1
                advance(ch)
                if ch == "\\" and i < len(text):
                    advance(text[i])
                    i += 1
                elif ch == quote:
                    break
            else:
                raise GrammarError(f"{start_line}行{start_column}列: 文字列が閉じられていません")
            tokens.append(Lexeme(text[start_i:i], start_line, start_column))
            continue
        if c == "{":
            # Semantic actions do not affect the context-free grammar.
            depth = 1
            start_line, start_column = line, column
            advance(c)
            i += 1
            quote: str | None = None
            while i < len(text) and depth:
                ch = text[i]
                if quote:
                    if ch == "\\" and i + 1 < len(text):
                        advance(text[i : i + 2])
                        i += 2
                        continue
                    if ch == quote:
                        quote = None
                elif ch in "'\"":
                    quote = ch
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                advance(ch)
                i += 1
            if depth:
                raise GrammarError(f"{start_line}行{start_column}列: アクションが閉じられていません")
            continue
        start_i, start_line, start_column = i, line, column
        while i < len(text) and not text[i].isspace() and text[i] not in ":|;{'\"":
            i += 1
        word = text[start_i:i]
        if not word:
            raise GrammarError(f"{line}行{column}列: 解釈できない文字 {c!r} です")
        tokens.append(Lexeme(word, start_line, start_column))
        advance(word)
    return tokens


def parse_grammar(text: str) -> Grammar:
    cleaned = _remove_comments(text)
    declarations, rules = _split_yacc_sections(cleaned)
    declared_terminals, declared_start = _parse_declarations(declarations)
    tokens = _rule_lex(rules)
    if not tokens:
        raise GrammarError("生成規則がありません")

    raw_rules: list[tuple[str, list[str]]] = []
    nonterminals: list[str] = []
    i = 0
    while i < len(tokens):
        lhs_token = tokens[i]
        lhs = lhs_token.value
        if lhs in {":", "|", ";"} or lhs.startswith("%"):
            raise GrammarError(f"{lhs_token.line}行{lhs_token.column}列: 左辺の非終端記号が必要です")
        if lhs not in nonterminals:
            nonterminals.append(lhs)
        i += 1
        if i >= len(tokens) or tokens[i].value != ":":
            raise GrammarError(f"{lhs_token.line}行{lhs_token.column}列: {lhs} の後に : が必要です")
        i += 1
        rhs: list[str] = []
        while True:
            if i >= len(tokens):
                raise GrammarError(f"{lhs_token.line}行目: 規則 {lhs} が ; で閉じられていません")
            token = tokens[i]
            if token.value in {"|", ";"}:
                if "%empty" in rhs and len(rhs) != 1:
                    raise GrammarError(f"{token.line}行目: %empty は単独で指定してください")
                raw_rules.append((lhs, [] if rhs == ["%empty"] else rhs))
                rhs = []
                i += 1
                if token.value == ";":
                    break
                continue
            if token.value == "%prec":
                if i + 1 >= len(tokens) or tokens[i + 1].value in {":", "|", ";"}:
                    raise GrammarError(f"{token.line}行目: %prec の後にトークンが必要です")
                i += 2
                continue
            if token.value.startswith("%") and token.value != "%empty":
                raise GrammarError(f"{token.line}行目: 規則内の {token.value} には対応していません")
            rhs.append(token.value)
            i += 1

    start = declared_start or nonterminals[0]
    if start not in nonterminals:
        raise GrammarError(f"開始記号 {start} に生成規則がありません")

    terminals = list(declared_terminals)
    nonterminal_set = set(nonterminals)
    for _, rhs in raw_rules:
        for symbol in rhs:
            if symbol not in nonterminal_set and symbol not in terminals:
                terminals.append(symbol)
    productions = [Production(n, lhs, tuple(rhs)) for n, (lhs, rhs) in enumerate(raw_rules, 1)]
    return Grammar(start, nonterminals, terminals, productions)


def first_sets(grammar: Grammar) -> dict[str, set[str]]:
    first = {nt: set() for nt in grammar.nonterminals}
    changed = True
    while changed:
        changed = False
        for production in grammar.productions:
            additions = first_of_sequence(production.rhs, first, set(grammar.nonterminals))
            before = len(first[production.lhs])
            first[production.lhs].update(additions)
            changed |= len(first[production.lhs]) != before
    return first


def first_of_sequence(
    symbols: Sequence[str], first: dict[str, set[str]], nonterminals: set[str]
) -> set[str]:
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
    nonterminals = set(grammar.nonterminals)
    follow = {nt: set() for nt in grammar.nonterminals}
    follow[grammar.start].add(ENDMARK)
    changed = True
    while changed:
        changed = False
        for production in grammar.productions:
            for pos, symbol in enumerate(production.rhs):
                if symbol not in nonterminals:
                    continue
                suffix_first = first_of_sequence(production.rhs[pos + 1 :], first, nonterminals)
                additions = suffix_first - {EPSILON}
                if EPSILON in suffix_first:
                    additions |= follow[production.lhs]
                before = len(follow[symbol])
                follow[symbol].update(additions)
                changed |= len(follow[symbol]) != before
    return follow


def parsing_table(
    grammar: Grammar, first: dict[str, set[str]], follow: dict[str, set[str]]
) -> dict[tuple[str, str], list[Production]]:
    table: dict[tuple[str, str], list[Production]] = {}
    nonterminals = set(grammar.nonterminals)
    for production in grammar.productions:
        selection = first_of_sequence(production.rhs, first, nonterminals)
        lookaheads = selection - {EPSILON}
        if EPSILON in selection:
            lookaheads |= follow[production.lhs]
        for terminal in lookaheads:
            table.setdefault((production.lhs, terminal), []).append(production)
    return table


def _ordered_set(items: Iterable[str], order: list[str]) -> str:
    values = set(items)
    display_order = order + [ENDMARK, EPSILON]
    shown = ["ε" if item == EPSILON else item for item in display_order if item in values]
    extras = sorted(values - set(display_order))
    return "{ " + ", ".join(shown + extras) + " }"


def _render_table(grammar: Grammar, table: dict[tuple[str, str], list[Production]]) -> str:
    columns = grammar.terminals + ([ENDMARK] if ENDMARK not in grammar.terminals else [])
    cells: list[list[str]] = [[""] + columns]
    for nt in grammar.nonterminals:
        row = [nt]
        for terminal in columns:
            entries = table.get((nt, terminal), [])
            row.append(" / ".join(f"[{p.number}]" for p in entries) if entries else "·")
        cells.append(row)
    widths = [max(len(row[col]) for row in cells) for col in range(len(cells[0]))]
    lines = []
    for row_number, row in enumerate(cells):
        lines.append(" | ".join(value.ljust(widths[i]) for i, value in enumerate(row)))
        if row_number == 0:
            lines.append("-+-".join("-" * width for width in widths))
    return "\n".join(lines)


def format_analysis(grammar: Grammar) -> tuple[str, bool]:
    first = first_sets(grammar)
    follow = follow_sets(grammar, first)
    table = parsing_table(grammar, first, follow)
    order = grammar.terminals
    lines = [f"開始記号: {grammar.start}", "", "生成規則:"]
    lines.extend(f"  [{p.number}] {p.text()}" for p in grammar.productions)
    lines.extend(["", "FIRST(1):"])
    lines.extend(f"  FIRST({nt}) = {_ordered_set(first[nt], order)}" for nt in grammar.nonterminals)
    lines.extend(["", "FOLLOW(1):"])
    lines.extend(f"  FOLLOW({nt}) = {_ordered_set(follow[nt], order)}" for nt in grammar.nonterminals)
    lines.extend(["", "LL(1) 構文解析表:", _render_table(grammar, table)])

    conflicts = [(key, entries) for key, entries in table.items() if len(entries) > 1]
    if conflicts:
        lines.extend(["", "競合:"])
        for (nt, terminal), entries in conflicts:
            numbers = ", ".join(f"[{p.number}]" for p in entries)
            lines.append(f"  M[{nt}, {terminal}] = {numbers}")
        lines.append("この文法は LL(1) ではありません。")
    else:
        lines.extend(["", "競合はありません。この文法は LL(1) です。"])
    return "\n".join(lines), bool(conflicts)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Yacc風文法から FIRST/FOLLOW と LL(1) 表を生成します")
    parser.add_argument("grammar", nargs="?", help="文法ファイル（省略時は標準入力）")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    try:
        if args.grammar:
            text = Path(args.grammar).read_text(encoding="utf-8")
        else:
            text = sys.stdin.read()
        grammar = parse_grammar(text)
        output, has_conflicts = format_analysis(grammar)
        print(output)
        return 1 if has_conflicts else 0
    except (GrammarError, OSError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
