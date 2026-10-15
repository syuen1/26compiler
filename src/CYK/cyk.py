#!/usr/bin/env python3
"""Yacc 風の文脈自由文法を標準形へ変換し、CYK 法で入力を解析する。"""
from __future__ import annotations

import argparse
import re
import shlex
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

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


@dataclass(frozen=True)
class Node:
    symbol: str
    children: tuple[Node, ...] = ()


@dataclass
class CNFGrammar:
    start: str
    rules: list[tuple[str, tuple[str, ...]]]
    nullable: bool


@dataclass
class ParseResult:
    accepted: bool
    # chart[i][j] は半開区間 [i, j) を導出する非終端記号と木。
    chart: list[list[dict[str, Node]]]
    tree: Node | None


def to_cnf(grammar: Grammar) -> CNFGrammar:
    """空規則・単位規則を除去し、終端分離と二分化を行う。"""
    nonterminals = set(grammar.nonterminals)
    used = nonterminals | set(grammar.terminals)
    counter = 0

    def fresh() -> str:
        nonlocal counter
        while True:
            symbol = f"@CYK{counter}"
            counter += 1
            if symbol not in used:
                used.add(symbol)
                nonterminals.add(symbol)
                return symbol

    start = fresh()
    original = [(start, (grammar.start,))] + [(p.lhs, p.rhs) for p in grammar.productions]
    nullable: set[str] = set()
    changed = True
    while changed:
        changed = False
        for lhs, rhs in original:
            if lhs not in nullable and all(symbol in nullable for symbol in rhs):
                nullable.add(lhs)
                changed = True

    # nullable な記号を残す場合と取り除く場合を列挙する。
    without_empty: set[tuple[str, tuple[str, ...]]] = set()
    for lhs, rhs in original:
        variants: set[tuple[str, ...]] = {()}
        for symbol in rhs:
            extended = {prefix + (symbol,) for prefix in variants}
            if symbol in nullable:
                extended.update(variants)
            variants = extended
        without_empty.update((lhs, variant) for variant in variants if variant)

    units: dict[str, set[str]] = defaultdict(set)
    bodies: dict[str, set[tuple[str, ...]]] = defaultdict(set)
    for lhs, rhs in without_empty:
        if len(rhs) == 1 and rhs[0] in nonterminals:
            units[lhs].add(rhs[0])
        else:
            bodies[lhs].add(rhs)
    without_units: set[tuple[str, tuple[str, ...]]] = set()
    for lhs in sorted(nonterminals):
        reachable = {lhs}
        pending = [lhs]
        while pending:
            for target in sorted(units[pending.pop()]):
                if target not in reachable:
                    reachable.add(target)
                    pending.append(target)
        for target in reachable:
            without_units.update((lhs, rhs) for rhs in bodies[target])

    rules: set[tuple[str, tuple[str, ...]]] = set()
    terminal_helpers: dict[str, str] = {}
    for lhs, rhs in sorted(without_units):
        if len(rhs) == 1:
            rules.add((lhs, rhs))
            continue
        separated: list[str] = []
        for symbol in rhs:
            if symbol not in nonterminals:
                if symbol not in terminal_helpers:
                    helper = fresh()
                    terminal_helpers[symbol] = helper
                    rules.add((helper, (symbol,)))
                symbol = terminal_helpers[symbol]
            separated.append(symbol)
        current = lhs
        for index in range(len(separated) - 2):
            helper = fresh()
            rules.add((current, (separated[index], helper)))
            current = helper
        rules.add((current, tuple(separated[-2:])))
    return CNFGrammar(start, sorted(rules), grammar.start in nullable)


def cyk(grammar: CNFGrammar, tokens: Sequence[str]) -> ParseResult:
    """長さ1から順に CYK 表を埋め、受理時には標準形の木を一つ返す。"""
    size = len(tokens)
    chart: list[list[dict[str, Node]]] = [[{} for _ in range(size + 1)] for _ in range(size + 1)]
    if size == 0:
        tree = Node(grammar.start, (Node("ε"),)) if grammar.nullable else None
        return ParseResult(grammar.nullable, chart, tree)
    terminal_rules: dict[str, list[str]] = defaultdict(list)
    binary_rules: dict[tuple[str, str], list[str]] = defaultdict(list)
    for lhs, rhs in grammar.rules:
        if len(rhs) == 1:
            terminal_rules[rhs[0]].append(lhs)
        else:
            binary_rules[rhs[0], rhs[1]].append(lhs)
    for i, token in enumerate(tokens):
        for lhs in terminal_rules[token]:
            chart[i][i + 1][lhs] = Node(lhs, (Node(token),))
    for length in range(2, size + 1):
        for i in range(size - length + 1):
            j = i + length
            for split in range(i + 1, j):
                for left, left_tree in chart[i][split].items():
                    for right, right_tree in chart[split][j].items():
                        for lhs in binary_rules.get((left, right), ()):
                            if lhs not in chart[i][j]:
                                chart[i][j][lhs] = Node(lhs, (left_tree, right_tree))
    tree = chart[0][size].get(grammar.start)
    return ParseResult(tree is not None, chart, tree)


def read_tokens(text: str) -> list[str]:
    """引用符を保持する。LR 用の入力と同様に末尾の # は省略可能。"""
    lexer = shlex.shlex(text, posix=False)
    lexer.whitespace_split = True
    lexer.commenters = ""
    tokens = list(lexer)
    if "#" in tokens:
        if tokens[-1] != "#" or tokens.count("#") != 1:
            raise GrammarError("入力終端記号 # は末尾に一度だけ指定してください")
        tokens.pop()
    return tokens


def format_tree(root: Node) -> str:
    lines = [root.symbol]

    def visit(node: Node, prefix: str) -> None:
        for index, child in enumerate(node.children):
            last = index == len(node.children) - 1
            lines.append(prefix + ("└── " if last else "├── ") + child.symbol)
            visit(child, prefix + ("    " if last else "│   "))

    visit(root, "")
    return "\n".join(lines)


def format_chart(result: ParseResult, tokens: Sequence[str]) -> str:
    lines = ["CYK 表（位置は1始まり、両端を含む）:"]
    if not tokens:
        lines.append("  空入力")
    for length in range(1, len(tokens) + 1):
        lines.append(f"  長さ {length}:")
        for i in range(len(tokens) - length + 1):
            values = ", ".join(sorted(result.chart[i][i + length]))
            lines.append(f"    [{i + 1}, {i + length}] = {{{values}}}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("grammar", type=Path, help="Yacc 風の UTF-8 文法ファイル")
    parser.add_argument("input", type=Path, nargs="?", help="空白区切りの入力ファイル（省略時は標準入力）")
    parser.add_argument("-T", "--table", action="store_true", help="CYK 表を表示")
    parser.add_argument("--cnf", action="store_true", help="変換後のチョムスキー標準形を表示")
    parser.add_argument("--tree", action="store_true", help="標準形の構文解析木を一つ表示")
    args = parser.parse_args(argv)
    try:
        original = parse_grammar(args.grammar.read_text(encoding="utf-8-sig"))
        # 非終端と宣言終端の重複は文法の解釈が曖昧になるため拒否する。
        if set(original.nonterminals) & set(original.terminals):
            raise GrammarError("終端記号と非終端記号に同じ名前は指定できません")
        grammar = to_cnf(original)
        text = args.input.read_text(encoding="utf-8-sig") if args.input else sys.stdin.read()
        tokens = read_tokens(text)
        result = cyk(grammar, tokens)
        print(f"開始記号: {original.start}（標準形: {grammar.start}）")
        print("入力: " + (" ".join(tokens) or "ε"))
        if args.cnf:
            print("\nチョムスキー標準形:")
            if grammar.nullable:
                print(f"  {grammar.start} -> ε")
            for lhs, rhs in grammar.rules:
                print(f"  {lhs} -> {' '.join(rhs)}")
        if args.table:
            print("\n" + format_chart(result, tokens))
        print("\n受理しました。" if result.accepted else "\n受理できません。この入力は文法の言語に属しません。")
        if args.tree and result.tree:
            print("\n構文解析木（チョムスキー標準形）:")
            print(format_tree(result.tree))
        return 0 if result.accepted else 1
    except (GrammarError, OSError, ValueError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
