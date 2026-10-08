#!/usr/bin/env python3
"""yacc風の生成規則を読み、非終端記号と右辺の全接尾語のFIRSTを求める。"""

import argparse
import csv
from contextlib import nullcontext, redirect_stdout
import re
import shutil
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path


EPSILON = "%empty"


@dataclass(frozen=True)
class Token:
    value: str
    line: int


def tokenize(text):
    # 引用符付き終端記号は引用符を含めたまま保存する。
    pattern = re.compile(
        r"(?P<space>\s+)|(?P<comment>//[^\n]*|/\*[\s\S]*?\*/)"
        r"|(?P<quoted>'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\")"
        r"|(?P<directive>%%|%[A-Za-z_][A-Za-z_0-9]*)|(?P<name>[^\s:;|'\"/{}%]+)|(?P<punct>[:;|])"
    )
    result = []
    pos, line = 0, 1
    separators = 0
    while pos < len(text):
        match = pattern.match(text, pos)
        if match is None:
            raise ValueError(f"{line}行目: 読み取れない文字 {text[pos]!r}")
        value = match.group()
        if match.lastgroup not in ("space", "comment"):
            result.append(Token(value, line))
        if match.lastgroup == "directive" and value == "%%":
            separators += 1
            if separators == 2:
                break  # 第2区切り以降の補助コードはFIRST計算に不要
        line += value.count("\n")
        pos = match.end()
    return result


def read_grammar(text):
    tokens = tokenize(text)
    declared_terminals = set()
    start_symbol = None
    boundaries = [i for i, token in enumerate(tokens) if token.value == "%%"]
    if boundaries:
        declarations = tokens[:boundaries[0]]
        index = 0
        while index < len(declarations):
            directive = declarations[index]
            if directive.value not in ("%token", "%start"):
                raise ValueError(f"{directive.line}行目: 未対応の宣言 {directive.value}")
            index += 1
            symbols = []
            while index < len(declarations) and not declarations[index].value.startswith("%"):
                symbol = declarations[index]
                if symbol.value in (":", ";", "|") or symbol.value.isdecimal() or symbol.value.startswith("<"):
                    raise ValueError(f"{symbol.line}行目: 宣言には記号名を指定してください（型・番号指定は未対応）")
                symbols.append(symbol.value)
                index += 1
            if not symbols:
                raise ValueError(f"{directive.line}行目: {directive.value} に記号が必要です")
            if directive.value == "%token":
                declared_terminals.update(symbols)
            else:
                if len(symbols) != 1 or start_symbol is not None:
                    raise ValueError(f"{directive.line}行目: %start は1つの記号を1回だけ指定してください")
                start_symbol = symbols[0]
        end = boundaries[1] if len(boundaries) > 1 else len(tokens)
        tokens = tokens[boundaries[0] + 1:end]
    for token in tokens:
        if token.value.startswith("%") and token.value != EPSILON:
            raise ValueError(f"{token.line}行目: 未対応の指定 {token.value}（宣言部の後には %% が必要です）")
    productions = []
    nonterminals = set()
    index = 0
    while index < len(tokens):
        lhs = tokens[index]
        if lhs.value in (":", ";", "|", EPSILON) or lhs.value.startswith(("'", '"')):
            raise ValueError(f"{lhs.line}行目: 左辺には非終端記号が必要です")
        index += 1
        if index >= len(tokens) or tokens[index].value != ":":
            raise ValueError(f"{lhs.line}行目: {lhs.value} の後に ':' が必要です")
        index += 1
        nonterminals.add(lhs.value)
        rhs = []
        while True:
            if index >= len(tokens):
                raise ValueError(f"{lhs.line}行目: {lhs.value} の規則を閉じる ';' が必要です")
            token = tokens[index]
            index += 1
            if token.value in ("|", ";"):
                if EPSILON in rhs and rhs != [EPSILON]:
                    raise ValueError(f"{token.line}行目: %empty は選択肢の単独要素にしてください")
                productions.append((lhs.value, () if rhs == [EPSILON] else tuple(rhs)))
                rhs = []
                if token.value == ";":
                    break
            elif token.value == ":":
                raise ValueError(f"{token.line}行目: 右辺に ':' は書けません（終端記号なら引用符で囲んでください）")
            else:
                rhs.append(token.value)
    if not productions:
        raise ValueError("生成規則がありません")
    if declared_terminals & nonterminals:
        raise ValueError("%tokenで宣言した記号が生成規則の左辺にあります: " + ", ".join(sorted(declared_terminals & nonterminals)))
    if start_symbol is not None and start_symbol not in nonterminals:
        raise ValueError(f"%start の記号 {start_symbol} に生成規則がありません")
    terminals = ({s for _, rhs in productions for s in rhs} - nonterminals) | declared_terminals
    return nonterminals, terminals, productions


def compute_first(nonterminals, terminals, productions, verbose=False, history=None):
    # 記号列はtupleで表す。非終端記号Aは長さ1の列(A,)と同一視する。
    # PO_p: 各右辺の全接尾語（空列を含む）。X = N ∪ PO_p。
    suffixes = {rhs[i:] for _, rhs in productions for i in range(len(rhs) + 1)}
    domain = suffixes | {(symbol,) for symbol in nonterminals}
    first = {}
    def snapshot(label):
        if history is not None:
            history.append((label, {alpha: values.copy() for alpha, values in first.items()}))

    def log(message):
        if verbose:
            print(message)

    if verbose:
        print(f"FIRSTの定義域 X = N ∪ PO_p（{len(domain)}要素）:")
        for alpha in sorted(domain, key=lambda a: (len(a), a)):
            print(f"  - {format_sequence(alpha)}")
        print()

    def initial_step(alpha):
        return 1 if not alpha else 2 if alpha[0] in terminals else 3

    for step in (1, 2, 3):
        for alpha in sorted(domain, key=lambda a: (len(a), a)):
            if initial_step(alpha) != step:
                continue
            if step == 1:
                first[alpha] = {EPSILON}
            elif step == 2:
                first[alpha] = {alpha[0]}
            else:
                first[alpha] = set()
            log(f"[{step}] FIRST({format_sequence(alpha)}) = {format_set(first[alpha])}")
        snapshot(f"{step}: init")

    def add(alpha, values, step, reason):
        before = first[alpha].copy()
        added = values - before
        first[alpha].update(values)
        log(f"[{step}] {reason}")
        log(f"  FIRST({format_sequence(alpha)}): {format_set(before)} → {format_set(first[alpha])}"
            f" （追加: {format_set(added)}{'、変化なし' if not added else ''}）")
        return bool(added)

    changed = True
    iteration = 0
    while changed:                            # 手順4: 単調に追加し、固定点まで反復
        iteration += 1
        log(f"\n反復 {iteration}")
        changed = False
        for alpha in sorted(suffixes):        # 手順4(a)
            if alpha and alpha[0] in nonterminals:
                head = first[(alpha[0],)]
                values = head - {EPSILON}
                if EPSILON in head:
                    values = values | first[alpha[1:]]
                    reason = (f"%empty ∈ FIRST({alpha[0]}): "
                              f"(FIRST({alpha[0]}) - {{%empty}}) ∪ FIRST({format_sequence(alpha[1:])})")
                else:
                    reason = f"%empty ∉ FIRST({alpha[0]}): FIRST({alpha[0]}) を追加"
                changed = add(alpha, values, "4(a)", reason) or changed
        snapshot(f"{2 * iteration + 2}: 4(a)")
        for lhs, rhs in productions:          # 手順4(b)
            reason = f"{lhs} → {format_sequence(rhs)}: FIRST({format_sequence(rhs)}) を追加"
            changed = add((lhs,), first[rhs], "4(b)", reason) or changed
        snapshot(f"{2 * iteration + 3}: 4(b)")
        if not changed:
            log("全体を通して追加がなかったため終了。\n")
    return first, suffixes


def format_sequence(alpha):
    return " ".join(alpha) if alpha else EPSILON


def format_set(values):
    return "{" + ", ".join(sorted(values)) + "}"


def table_data(history, undefined="—"):
    """表示とCSVで共用する表。初期化を含む変更セルに ! を付ける。"""
    arguments = sorted(history[-1][1], key=lambda a: (len(a), a))
    headers = ["FIRST(arg)"] + [label for label, _ in history]
    rows = []
    for alpha in arguments:
        row = [format_sequence(alpha)]
        previous = None
        for _, state in history:
            current = state.get(alpha)
            cell = undefined if current is None else format_set(current)
            if current is not None and current != previous:
                cell += " !"
            row.append(cell)
            previous = current
        rows.append(row)
    return headers, rows


def write_csv(path, history):
    headers, rows = table_data(history, undefined="--")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)


def write_first(path, first):
    """FOLLOW計算への入力として、全引数の最終的なFIRSTを保存する。"""
    destination = nullcontext(sys.stdout) if path == Path("-") else path.open("w", encoding="utf-8", newline="\n")
    with destination as stream:
        for alpha in sorted(first, key=lambda a: (len(a), a)):
            values = ",".join(sorted(first[alpha]))
            stream.write(f"{format_sequence(alpha)},[{values}]\n")


def print_table(history):
    """全引数の各段階の集合を、端末幅に応じて列を分割して表示する。"""
    def width(text):
        return sum(0 if unicodedata.combining(c) else
                   2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
                   for c in text)

    def pad(text, size):
        return text + " " * (size - width(text))

    headers, rows = table_data(history)
    sizes = [max(width(row[i]) for row in [headers] + rows) for i in range(len(headers))]
    terminal_width = shutil.get_terminal_size(fallback=(120, 24)).columns
    print("1・2・3 = 各初期化手順の直後。以後、4(a)全体・4(b)全体ごとに1ステップ。")
    print("各セルはその時点のFIRST集合（— は未初期化、{} は空集合）。最後の2列は変化なしを確認した反復です。")
    print("! は前のステップから変化したセル（初期化を含む）を示します。")
    start = 1
    while start < len(headers):
        columns = [0]
        used = sizes[0] + 4
        end = start
        while end < len(headers):
            needed = sizes[end] + 3
            if len(columns) > 1 and used + needed > terminal_width:
                break
            columns.append(end)
            used += needed
            end += 1
        border = "+" + "+".join("-" * (sizes[i] + 2) for i in columns) + "+"
        print()
        print(border)
        print("| " + " | ".join(pad(headers[i], sizes[i]) for i in columns) + " |")
        print(border)
        for row in rows:
            print("| " + " | ".join(pad(row[i], sizes[i]) for i in columns) + " |")
        print(border)
        start = end


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="UTF-8の文法ファイル")
    parser.add_argument("--all", action="store_true", help="右辺の全接尾語のFIRSTも表示")
    parser.add_argument("-v", "--verbose", action="store_true", help="手順1・2・3・4(a)・4(b)の計算過程を表示")
    parser.add_argument("-T", "--table", action="store_true", help="横軸を計算ステップ、縦軸をFIRSTの全引数とした表を表示")
    parser.add_argument("--csv", type=Path, metavar="出力ファイル", help="全ステップを分割しないCSV表として保存（-Tと併用可）")
    parser.add_argument("-o", type=Path, metavar="出力ファイル", help="FOLLOW用に全引数の最終結果を X,[a,b,...] 形式で保存（- は標準出力）")
    args = parser.parse_args()
    stdout_first = args.o == Path("-")
    try:
        n, t, productions = read_grammar(args.input.read_text(encoding="utf-8-sig"))
        if args.csv and args.csv.resolve() == args.input.resolve():
            raise ValueError("CSV出力先には入力ファイルと異なるファイルを指定してください")
        if args.o and not stdout_first and args.o.resolve() == args.input.resolve():
            raise ValueError("-oの出力先には入力ファイルと異なるファイルを指定してください")
        if args.o and not stdout_first and args.csv and args.o.resolve() == args.csv.resolve():
            raise ValueError("-oと--csvには異なる出力ファイルを指定してください")
        history = [] if args.table or args.csv else None
        with redirect_stdout(sys.stderr) if stdout_first else nullcontext():
            first, suffixes = compute_first(n, t, productions, verbose=args.verbose, history=history)
        if args.csv:
            write_csv(args.csv, history)
        if args.o:
            write_first(args.o, first)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    if args.table:
        with redirect_stdout(sys.stderr) if stdout_first else nullcontext():
            print_table(history)
        return 0
    if stdout_first:
        return 0
    if args.verbose:
        print("計算結果:")
    for symbol in sorted(n):
        print(f"FIRST({symbol}) = {format_set(first[(symbol,)])}")
    if args.all:
        print("\n右辺の接尾語:")
        for alpha in sorted(suffixes, key=lambda x: (len(x), x)):
            label = " ".join(alpha) if alpha else EPSILON
            print(f"FIRST({label}) = {format_set(first[alpha])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
