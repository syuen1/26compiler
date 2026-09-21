#!/usr/bin/env python3
"""LR 構文解析表と入力系列から、還元規則番号を出力する pushdown transducer。"""

from __future__ import annotations

import argparse
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from slr import write_graph


ENDMARK = "#"


class TableError(ValueError):
    """.tab 構文解析表の形式または内容が不正である。"""


class ParseError(ValueError):
    """入力系列を構文解析できない。"""


@dataclass(frozen=True)
class Production:
    number: int
    lhs: str
    rhs: tuple[str, ...]


@dataclass
class ParsingTable:
    productions: dict[int, Production]
    action: dict[tuple[int, str], list[str]]
    goto: dict[tuple[int, str], int]


@dataclass(frozen=True)
class TreeNode:
    """構文解析木のノード。terminal は Graphviz の表示形にだけ用いる。"""
    symbol: str
    children: tuple["TreeNode", ...] = ()
    terminal: bool = False
    production_number: int | None = None


def split_symbols(text: str) -> list[str]:
    """空白区切りの記号列を分割し、引用符付き終端記号はそのまま保つ。"""
    lexer = shlex.shlex(text, posix=False)
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def read_table(path: Path) -> ParsingTable:
    section: str | None = None
    productions: dict[int, Production] = {}
    action: dict[tuple[int, str], list[str]] = {}
    goto: dict[tuple[int, str], int] = {}
    production_pattern = re.compile(r"^PRODUCTION\[(\d+)\]\s*=\s*(\S+)\s+->(?:\s+(.*))?$")
    action_pattern = re.compile(r"^ACTION\[(\d+),\s*(.*?)\]\s*=\s*(.+)$")
    goto_pattern = re.compile(r"^GOTO\[(\d+),\s*(.*?)\]\s*=\s*(\d+)$")
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as error:
        raise TableError(str(error)) from error
    for line_number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            if section not in {"PRODUCTIONS", "ACTION", "GOTO"}:
                raise TableError(f"{line_number}行目: 未対応の節 [{section}] です")
            continue
        if section == "PRODUCTIONS":
            match = production_pattern.match(line)
            if not match:
                raise TableError(f"{line_number}行目: PRODUCTION[n] = A -> ... の形式が必要です")
            number, lhs, rhs_text = int(match.group(1)), match.group(2), match.group(3) or "ε"
            if number in productions:
                raise TableError(f"{line_number}行目: 生成規則 {number} が重複しています")
            rhs = () if rhs_text == "ε" else tuple(split_symbols(rhs_text))
            productions[number] = Production(number, lhs, rhs)
        elif section == "ACTION":
            match = action_pattern.match(line)
            if not match:
                raise TableError(f"{line_number}行目: ACTION[状態, 記号] = 動作 の形式が必要です")
            state, symbol, values = int(match.group(1)), match.group(2), match.group(3)
            actions = [value.strip() for value in values.split("/")]
            if not actions or any(not re.fullmatch(r"s\d+|r\d+|acc", value) for value in actions):
                raise TableError(f"{line_number}行目: ACTION の動作が不正です")
            action[state, symbol] = actions
        elif section == "GOTO":
            match = goto_pattern.match(line)
            if not match:
                raise TableError(f"{line_number}行目: GOTO[状態, 非終端記号] = 状態 の形式が必要です")
            goto[int(match.group(1)), match.group(2)] = int(match.group(3))
        else:
            raise TableError(f"{line_number}行目: [PRODUCTIONS]、[ACTION]、[GOTO] のいずれかが必要です")
    if not productions:
        raise TableError("[PRODUCTIONS] に生成規則がありません")
    if not action:
        raise TableError("[ACTION] に動作がありません")
    return ParsingTable(productions, action, goto)


def read_input(path: Path) -> list[str]:
    try:
        symbols = split_symbols(path.read_text(encoding="utf-8-sig"))
    except OSError as error:
        raise ParseError(str(error)) from error
    if ENDMARK in symbols:
        if symbols[-1] != ENDMARK or symbols.count(ENDMARK) != 1:
            raise ParseError(f"入力終端記号 {ENDMARK} は末尾に一度だけ指定してください")
    else:
        symbols.append(ENDMARK)
    return symbols


def format_stack(stack: list[int | str]) -> str:
    return " ".join(str(value) for value in stack) if stack else "(空)"


def format_tape(tape: list[int]) -> str:
    return " ".join(str(number) for number in tape) if tape else "(空)"


def format_input(symbols: list[str]) -> str:
    return " ".join(symbols) if symbols else "(空)"


def reconstruct_tree(table: ParsingTable, tape: Sequence[int]) -> TreeNode:
    """還元規則番号のポストオーダー列から構文解析木を再構成する。"""
    nonterminals = {production.lhs for production in table.productions.values()}
    stack: list[TreeNode] = []
    for number in tape:
        production = table.productions.get(number)
        if production is None:
            raise ParseError(f"出力テープの規則 {number} が表にありません")
        children_reversed: list[TreeNode] = []
        for symbol in reversed(production.rhs):
            if symbol in nonterminals:
                if not stack:
                    raise ParseError(f"規則 {number} の非終端記号 {symbol} に対応する部分木がありません")
                child = stack.pop()
                if child.symbol != symbol:
                    raise ParseError(f"規則 {number} は {symbol} を要求しますが、部分木 {child.symbol} がありました")
                children_reversed.append(child)
            else:
                children_reversed.append(TreeNode(symbol, terminal=True))
        if not production.rhs:
            children_reversed.append(TreeNode("ε", terminal=True))
        stack.append(TreeNode(production.lhs, tuple(reversed(children_reversed)), production_number=number))
    if len(stack) != 1:
        raise ParseError(f"出力テープから構文解析木を一意に復元できません（部分木が {len(stack)} 本残っています）")
    return stack[0]


def format_tree(root: TreeNode) -> str:
    """Unicode の枝記号を使うテキスト形式の構文解析木を返す。"""
    lines = [root.symbol]

    def visit(node: TreeNode, prefix: str) -> None:
        for index, child in enumerate(node.children):
            last = index == len(node.children) - 1
            lines.append(prefix + ("└── " if last else "├── ") + child.symbol)
            visit(child, prefix + ("    " if last else "│   "))

    visit(root, "")
    return "\n".join(lines)


def tree_dot(root: TreeNode) -> str:
    """構文解析木を上から下へ配置する Graphviz DOT ソースを返す。"""
    def escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    lines = ["digraph ParseTree {", "  rankdir=TB;", "  node [fontname=Helvetica];"]
    next_number = 0

    def visit(node: TreeNode) -> int:
        nonlocal next_number
        number = next_number
        next_number += 1
        shape = "ellipse" if node.terminal else "box"
        label = escape(node.symbol)
        if not node.terminal and node.production_number is not None:
            label += f"\\n[{node.production_number}]"
        lines.append(f'  n{number} [label="{label}" shape={shape}];')
        for child in node.children:
            child_number = visit(child)
            lines.append(f"  n{number} -> n{child_number};")
        return number

    visit(root)
    lines.append("}")
    return "\n".join(lines) + "\n"


def run(table: ParsingTable, input_symbols: list[str], verbose: bool = False) -> list[int]:
    """決定的LR表に従い、出力テープ（還元した規則番号列）を返す。"""
    stack: list[int | str] = [0]
    tape: list[int] = []
    position = 0
    step = 0

    def trace(action: str) -> None:
        if verbose:
            print(f"段階 {step}: {action}")
            print(f"  スタック: {format_stack(stack)}")
            print(f"  入力の残り: {format_input(input_symbols[position:])}")
            print(f"  出力テープ: {format_tape(tape)}")

    while True:
        if step >= 1_000_000:
            raise ParseError("動作回数が上限に達しました（表に無限ループの可能性があります）")
        state = stack[-1]
        if not isinstance(state, int):
            raise ParseError("スタックの状態が不正です")
        lookahead = input_symbols[position]
        actions = table.action.get((state, lookahead))
        if not actions:
            raise ParseError(f"状態 {state}、先読み記号 {lookahead} に ACTION がありません")
        if len(actions) != 1:
            raise ParseError(f"ACTION[{state}, {lookahead}] が競合しています: {' / '.join(actions)}")
        action = actions[0]
        step += 1
        if action.startswith("s"):
            target = int(action[1:])
            stack.extend([lookahead, target])
            position += 1
            trace(action)
        elif action.startswith("r"):
            number = int(action[1:])
            production = table.productions.get(number)
            if production is None:
                raise ParseError(f"還元規則 r{number} の生成規則が表にありません")
            count = len(production.rhs)
            if count:
                symbols = tuple(stack[1::2])
                if tuple(symbols[-count:]) != production.rhs:
                    raise ParseError(f"r{number} の右辺とスタック上の記号が一致しません")
                del stack[-2 * count :]
            previous = stack[-1]
            if not isinstance(previous, int):
                raise ParseError("還元後のスタック状態が不正です")
            target = table.goto.get((previous, production.lhs))
            if target is None:
                raise ParseError(f"GOTO[{previous}, {production.lhs}] がありません")
            stack.extend([production.lhs, target])
            tape.append(number)
            trace(action)
        else:  # acc
            augmented = table.productions.get(0)
            if augmented is not None and len(augmented.rhs) == 2 and augmented.rhs[1] == ENDMARK:
                start_symbol = augmented.rhs[0]
                if stack != [0, start_symbol, state] or lookahead != ENDMARK:
                    raise ParseError("acc 時のスタックまたは先読み記号が拡大文法の受理条件と一致しません")
                stack.clear()
                position += 1
                tape.append(0)
            trace(action)
            return tape


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("table", type=Path, help="slr1.py --outtab で出力した .tab ファイル")
    parser.add_argument("input", type=Path, help="空白区切りの入力系列ファイル（末尾の # は省略可）")
    parser.add_argument("-v", "--verbose", action="store_true", help="各 shift/reduce/accept 後のスタック・残り入力・出力テープを表示")
    parser.add_argument("--tree", action="store_true", help="還元規則番号列から再構成した構文解析木をテキストで表示")
    parser.add_argument("--tree-graph", type=Path, metavar="出力ファイル", help="再構成した構文解析木を Graphviz で出力（拡張子で形式を指定）")
    args = parser.parse_args(argv)
    try:
        if args.tree_graph and args.tree_graph.resolve() in {args.table.resolve(), args.input.resolve()}:
            raise ParseError("--tree-graph の出力先には表・入力ファイルと異なるファイルを指定してください")
        table = read_table(args.table)
        tape = run(table, read_input(args.input), args.verbose)
        print(f"出力テープ: {format_tape(tape)}")
        if args.tree or args.tree_graph:
            root = reconstruct_tree(table, tape)
            if args.tree:
                print("\n構文解析木:")
                print(format_tree(root))
            if args.tree_graph:
                write_graph(args.tree_graph, tree_dot(root))
        return 0
    except (TableError, ParseError, OSError, ValueError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
