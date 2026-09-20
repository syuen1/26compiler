#!/usr/bin/env python3
"""Yacc 風文法から LR(0) 項集合族（LR(0) オートマトン）を生成する。"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


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


Item = tuple[int, int]  # (拡張文法を含む生成規則の添字, ドット位置)


def lr0_automaton(grammar: Grammar) -> tuple[list[Production], list[frozenset[Item]], dict[tuple[int, str], int]]:
    """正準 LR(0) 項集合族と goto 遷移を返す。"""
    augmented = [Production(0, grammar.start + "'", (grammar.start,))] + grammar.productions
    by_lhs: dict[str, list[int]] = defaultdict(list)
    for index, production in enumerate(augmented):
        by_lhs[production.lhs].append(index)
    nonterminals = set(grammar.nonterminals) | {augmented[0].lhs}

    def closure(seed: Iterable[Item]) -> frozenset[Item]:
        result = set(seed)
        pending = list(result)
        while pending:
            production_index, dot = pending.pop()
            production = augmented[production_index]
            if dot < len(production.rhs) and production.rhs[dot] in nonterminals:
                for child in by_lhs[production.rhs[dot]]:
                    item = (child, 0)
                    if item not in result:
                        result.add(item)
                        pending.append(item)
        return frozenset(result)

    states = [closure({(0, 0)})]
    numbers = {states[0]: 0}
    transitions: dict[tuple[int, str], int] = {}
    queue = deque([0])
    while queue:
        state_number = queue.popleft()
        state = states[state_number]
        symbols = sorted({augmented[p].rhs[d] for p, d in state if d < len(augmented[p].rhs)})
        for symbol in symbols:
            target = closure((p, d + 1) for p, d in state if d < len(augmented[p].rhs) and augmented[p].rhs[d] == symbol)
            if target not in numbers:
                numbers[target] = len(states)
                states.append(target)
                queue.append(numbers[target])
            transitions[state_number, symbol] = numbers[target]
    return augmented, states, transitions


def format_automaton(productions: list[Production], states: list[frozenset[Item]], transitions: dict[tuple[int, str], int]) -> str:
    lines = ["拡張生成規則:"]
    lines.extend(f"  [{p.number}] {p.text()}" for p in productions)
    for state_number, state in enumerate(states):
        lines.extend(["", f"I{state_number}:"])
        lines.extend(f"  [{productions[p].number}] {productions[p].text(dot)}" for p, dot in sorted(state))
        outgoing = sorted((symbol, target) for (source, symbol), target in transitions.items() if source == state_number)
        if outgoing:
            lines.append("  goto: " + ", ".join(f"{symbol} -> I{target}" for symbol, target in outgoing))
    return "\n".join(lines)


def format_transition_table(grammar: Grammar, states: list[frozenset[Item]], transitions: dict[tuple[int, str], int]) -> str:
    columns = grammar.terminals + grammar.nonterminals
    rows = [["状態"] + columns]
    for state_number in range(len(states)):
        rows.append([f"I{state_number}"] + [str(transitions.get((state_number, symbol), "·")) for symbol in columns])
    widths = [max(len(row[col]) for row in rows) for col in range(len(columns) + 1)]
    return "\n".join(
        " | ".join(value.ljust(widths[i]) for i, value in enumerate(row)) +
        ("\n" + "-+-".join("-" * width for width in widths) if number == 0 else "")
        for number, row in enumerate(rows)
    )


def dot_source(
    productions: list[Production],
    states: list[frozenset[Item]],
    transitions: dict[tuple[int, str], int],
    vertical: bool = False,
) -> str:
    def escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')
    lines = ["digraph LR0 {", f"  rankdir={'TB' if vertical else 'LR'};"]
    lines.append("  node [shape=box fontname=monospace];")
    for number, state in enumerate(states):
        # \l は Graphviz の左寄せ改行。項の本文だけをエスケープする。
        label = f"I{number}\\l" + "".join(
            f"[{productions[p].number}] {escape(productions[p].text(dot))}\\l"
            for p, dot in sorted(state)
        )
        lines.append(f'  I{number} [label="{label}"];')
    for (source, symbol), target in sorted(transitions.items()):
        lines.append(f'  I{source} -> I{target} [label="{escape(symbol)}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"


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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("grammar", nargs="?", help="UTF-8 の文法ファイル（省略時は標準入力）")
    parser.add_argument("-T", "--table", action="store_true", help="状態遷移表を表示")
    parser.add_argument("--graph", type=Path, metavar="出力ファイル", help="Graphviz で状態遷移図を出力（拡張子で形式を指定）")
    parser.add_argument("--eps", type=Path, metavar="出力ファイル", help="状態遷移図を EPS 形式で出力")
    parser.add_argument("--vertical", action="store_true", help="状態遷移図を上から下へ配置（--graph と併用）")
    args = parser.parse_args(argv)
    try:
        if args.graph and args.eps:
            raise GrammarError("--graph と --eps は同時に指定できません")
        graph_output = args.graph or args.eps
        if args.vertical and graph_output is None:
            raise GrammarError("--vertical は --graph または --eps と併用してください")
        text = Path(args.grammar).read_text(encoding="utf-8-sig") if args.grammar else sys.stdin.read()
        grammar = parse_grammar(text)
        productions, states, transitions = lr0_automaton(grammar)
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
