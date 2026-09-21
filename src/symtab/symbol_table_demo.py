"""簡単な再帰下降構文解析と記号表の登録例。Python 3、外部ライブラリ不要。

実行: python3 symbol_table_demo.py [ソースファイル] [--out-graph 出力.dot] [--septab]
引数を省略すると SAMPLE を解析する。右辺の式は評価しない。
"""

import re
import argparse
from html import escape
from pathlib import Path
from dataclasses import dataclass


SAMPLE = """int g;

func f(int a, real b) {
    int x;
    x = a + 1;
    g = x;
}

func h() {
    real y;
    y = 2.5;
}
"""


@dataclass
class Symbol:
    name: str
    kind: str
    value: str
    scope: str
    address: str
    type: str
    argc: str = "—"
    argtypes: str = "—"


class Parser:
    def __init__(self, source):
        # 宣言部分は個別のトークン、式部分は consume_expression でまとめて扱う。
        self.tokens = re.findall(r"[A-Za-z_][A-Za-z_0-9]*|\d+(?:\.\d+)?|[^\s]", source)
        self.pos = 0
        self.symbols = []
        self.snapshots = []
        self.scope = "global"
        self.global_offset = 0
        self.local_offset = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self, expected=None):
        token = self.peek()
        if token is None or (expected is not None and token != expected):
            raise SyntaxError(f"トークン位置 {self.pos}: {expected or 'トークン'} が必要（実際: {token!r}）")
        self.pos += 1
        return token

    def identifier(self):
        name = self.take()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name) or name in {"int", "real", "func"}:
            raise SyntaxError(f"識別子が必要: {name!r}")
        return name

    def type_name(self):
        token = self.take()
        if token not in {"int", "real"}:
            raise SyntaxError(f"型が必要: {token!r}")
        return token

    def register(self, symbol):
        if any(s.name == symbol.name and s.scope == symbol.scope for s in self.symbols):
            raise SyntaxError(f"同一スコープでの重複宣言: {symbol.scope}.{symbol.name}")
        self.symbols.append(symbol)

    def variable(self, kind="変数"):
        type_name = self.type_name()
        name = self.identifier()
        if self.scope == "global":
            address = f"G+{self.global_offset}"
            self.global_offset += 8
        else:
            address = f"FP+{self.local_offset}"
            self.local_offset += 8
        self.register(Symbol(name, kind, "呼出し時に決定" if kind == "仮引数" else "未定",
                             self.scope, address, type_name))
        return type_name

    def declaration(self):
        self.variable()
        self.take(";")

    def show(self, title):
        self.snapshots.append((title, [tuple(vars(s).values()) for s in self.symbols]))
        print(f"\n【{title}】")
        print("名前 | 種類 | 値 | スコープ | 番地 | 型 | 引数個数 | 引数型")
        if not self.symbols:
            print("（空）")
        for s in self.symbols:
            print(" | ".join((s.name, s.kind, s.value, s.scope, s.address,
                              s.type, s.argc, s.argtypes)))

    def write_graph(self, path, septab=False):
        """結合形式または表ごとの連番ファイルを保存し、出力先を返す。"""
        path = Path(path)
        if septab:
            paths = []
            for number, snapshot in enumerate(self.snapshots, start=1):
                target = path.with_name(f"{path.stem}-{number}{path.suffix or '.dot'}")
                self._write_graph(target, [snapshot])
                paths.append(target)
            return paths
        self._write_graph(path, self.snapshots)
        return [path]

    def _write_graph(self, path, snapshots):
        """各時点の記号表を HTML 形式の表ラベルを使った DOT に出力する。"""
        headers = ("名前", "種類", "値", "スコープ", "番地", "型", "引数個数", "引数型")
        lines = ['digraph SymbolTables {', '  graph [rankdir=TB];',
                 '  node [shape=plain, fontname="sans-serif"];']
        for index, (title, rows) in enumerate(snapshots):
            lines.append(f'  table{index} [label=<')
            lines.append('    <TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="6">')
            lines.append(f'      <TR><TD COLSPAN="8" BGCOLOR="#dbeafe"><B>{escape(title)}</B></TD></TR>')
            lines.append('      <TR>' + ''.join(f'<TD BGCOLOR="#f1f5f9"><B>{h}</B></TD>' for h in headers) + '</TR>')
            for row in rows:
                lines.append('      <TR>' + ''.join(f'<TD>{escape(str(cell))}</TD>' for cell in row) + '</TR>')
            if not rows:
                lines.append('      <TR><TD COLSPAN="8">（空）</TD></TR>')
            lines.extend(['    </TABLE>', '  >];'])
            if index:
                lines.append(f'  table{index - 1} -> table{index};')
        lines.append('}')
        Path(path).write_text('\n'.join(lines) + '\n', encoding='utf-8')

    def resolve(self, name):
        for scope in (self.scope, "global"):
            for symbol in self.symbols:
                if symbol.scope == scope and symbol.name == name:
                    return symbol
        raise SyntaxError(f"未宣言の名前: {name}")

    def consume_expression(self):
        start = self.pos
        while self.peek() not in {None, ";", "{", "}"}:
            self.take()
        if self.pos == start:
            raise SyntaxError("代入の右辺が空です")
        self.take(";")

    def arguments(self):
        """括弧の深さが0のコンマで式を分割する。式の型・内容は検査しない。"""
        self.take("(")
        count = 0
        if self.peek() != ")":
            while True:
                start = self.pos
                depth = 0
                while True:
                    token = self.peek()
                    if token in {None, ";", "{", "}"}:
                        raise SyntaxError("引数リストを閉じる ')' が必要です")
                    if depth == 0 and token in {",", ")"}:
                        break
                    if token == "(":
                        depth += 1
                    elif token == ")":
                        depth -= 1
                    self.take()
                if self.pos == start:
                    raise SyntaxError("引数の式が空です")
                count += 1
                if self.peek() != ",":
                    break
                self.take(",")
        self.take(")")
        return count

    def statement(self):
        name = self.identifier()
        if self.peek() == "=":
            self.take("=")
            symbol = self.resolve(name)
            if symbol.kind == "関数":
                raise SyntaxError(f"関数には代入できません: {name}")
            self.consume_expression()
        elif self.peek() == "(":
            argc = self.arguments()
            self.take(";")
            symbol = self.resolve(name)
            if symbol.kind != "関数":
                raise SyntaxError(f"関数ではない名前は呼び出せません: {name}")
            if int(symbol.argc) != argc:
                raise SyntaxError(f"引数個数が一致しません: {name}（必要: {symbol.argc}, 実際: {argc}）")
            # 関数本体は実行しない。
        else:
            raise SyntaxError(f"{name} の後には '=' または '(' が必要です（実際: {self.peek()!r}）")

    def function(self):
        self.take("func")
        name = self.identifier()
        function = Symbol(name, "関数", "—", "global", f"L_{name}", "void")
        self.register(function)
        self.scope = "local"
        self.local_offset = 0
        self.show(f"関数 {name} の局所文脈に入るとき（仮引数・局所変数の登録前）")
        self.take("(")
        types = []
        if self.peek() != ")":
            types.append(self.variable("仮引数"))
            while self.peek() == ",":
                self.take(",")
                types.append(self.variable("仮引数"))
        self.take(")")
        function.argc = str(len(types))
        function.argtypes = "(" + ", ".join(types) + ")"
        self.take("{")
        while self.peek() in {"int", "real"}:
            self.declaration()
        while self.peek() != "}":
            self.statement()
        self.take("}")
        self.show(f"関数 {name} の局所文脈を出るとき（局所項目の消去直前）")
        self.symbols = [s for s in self.symbols if s.scope == "global"]
        self.scope = "global"
        self.local_offset = 0

    def parse(self):
        while self.peek() is not None:
            if self.peek() == "func":
                self.function()
            else:
                self.declaration()


def main():
    cli = argparse.ArgumentParser(description="構文解析と記号表の表示")
    cli.add_argument("source", nargs="?", help="入力ソース（省略時は内蔵サンプル）")
    cli.add_argument("--out-graph", metavar="FILE.dot", help="記号表の推移を Graphviz DOT ファイルに保存")
    cli.add_argument("--septab", action="store_true", help="--out-graph の各表を -1, -2, … の連番DOTファイルに分割")
    args = cli.parse_args()
    if args.septab and not args.out_graph:
        cli.error("--septab には --out-graph FILE.dot が必要です")
    try:
        source = Path(args.source).read_text(encoding="utf-8") if args.source else SAMPLE
        print("【入力プログラム】\n" + source)
        parser = Parser(source)
        parser.parse()
        if args.out_graph:
            paths = parser.write_graph(args.out_graph, septab=args.septab)
            for path in paths:
                print(f"\nGraphviz 出力: {path}")
    except SyntaxError as error:
        raise SystemExit(f"解析エラー: {error}") from error
    except OSError as error:
        raise SystemExit(f"ファイル入出力エラー: {error}") from error


if __name__ == "__main__":
    main()
