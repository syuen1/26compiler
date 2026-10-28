"""LR 系生成器で共有する文法、オートマトン、構文解析表の処理。"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence, TypeVar

EPSILON = "ε"
ENDMARK = "#"
LR0Item = tuple[int, int]
LR1Item = tuple[int, int, str]
Item = TypeVar("Item", LR0Item, LR1Item)


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


def lr0_automaton(grammar: Grammar) -> tuple[list[Production], list[frozenset[LR0Item]], dict[tuple[int, str], int]]:
    """正準 LR(0) 項集合族と goto 遷移を返す。"""
    augmented = [Production(0, grammar.start + "'", (grammar.start,))] + grammar.productions
    by_lhs: dict[str, list[int]] = defaultdict(list)
    for index, production in enumerate(augmented):
        by_lhs[production.lhs].append(index)
    nonterminals = set(grammar.nonterminals) | {augmented[0].lhs}

    def closure(seed: Iterable[LR0Item]) -> frozenset[LR0Item]:
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


def first_sets(grammar: Grammar) -> dict[str, set[str]]:
    """非終端記号ごとの FIRST 集合を計算する。"""
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
    """記号列の FIRST 集合を返す。"""
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


def lr1_automaton(grammar: Grammar) -> tuple[list[Production], list[frozenset[LR1Item]], dict[tuple[int, str], int]]:
    """正準 LR(1) 項集合族と goto 遷移を返す。"""
    augmented = [Production(0, grammar.start + "'", (grammar.start,))] + grammar.productions
    nonterminals = set(grammar.nonterminals) | {augmented[0].lhs}
    first = first_sets(grammar)
    by_lhs: dict[str, list[int]] = defaultdict(list)
    for index, production in enumerate(augmented):
        by_lhs[production.lhs].append(index)

    def closure(seed: Iterable[LR1Item]) -> frozenset[LR1Item]:
        result = set(seed)
        pending = list(result)
        while pending:
            production_index, dot, lookahead = pending.pop()
            production = augmented[production_index]
            if dot >= len(production.rhs) or production.rhs[dot] not in nonterminals:
                continue
            symbol = production.rhs[dot]
            lookaheads = first_of_sequence(production.rhs[dot + 1 :] + (lookahead,), first, nonterminals) - {EPSILON}
            for child in by_lhs[symbol]:
                for child_lookahead in lookaheads:
                    item = (child, 0, child_lookahead)
                    if item not in result:
                        result.add(item)
                        pending.append(item)
        return frozenset(result)

    states = [closure({(0, 0, ENDMARK)})]
    numbers = {states[0]: 0}
    transitions: dict[tuple[int, str], int] = {}
    queue = deque([0])
    while queue:
        state_number = queue.popleft()
        state = states[state_number]
        symbols = sorted({augmented[index].rhs[dot] for index, dot, _ in state if dot < len(augmented[index].rhs)})
        for symbol in symbols:
            target = closure(
                (index, dot + 1, lookahead)
                for index, dot, lookahead in state
                if dot < len(augmented[index].rhs) and augmented[index].rhs[dot] == symbol
            )
            if target not in numbers:
                numbers[target] = len(states)
                states.append(target)
                queue.append(numbers[target])
            transitions[state_number, symbol] = numbers[target]
    return augmented, states, transitions


def lalr_automaton(grammar: Grammar) -> tuple[list[Production], list[frozenset[LR1Item]], dict[tuple[int, str], int]]:
    """同一 LR(0) コアの正準 LR(1) 状態を併合して LALR(1) 状態を作る。"""
    productions, canonical_states, canonical_transitions = lr1_automaton(grammar)
    state_for_core: dict[frozenset[tuple[int, int]], int] = {}
    canonical_to_lalr: dict[int, int] = {}
    lookaheads: list[dict[tuple[int, int], set[str]]] = []

    for canonical_number, state in enumerate(canonical_states):
        core = frozenset((production, dot) for production, dot, _ in state)
        if core not in state_for_core:
            state_for_core[core] = len(lookaheads)
            lookaheads.append({})
        lalr_number = state_for_core[core]
        canonical_to_lalr[canonical_number] = lalr_number
        for production, dot, lookahead in state:
            lookaheads[lalr_number].setdefault((production, dot), set()).add(lookahead)

    states = [
        frozenset((production, dot, lookahead) for (production, dot), values in state.items() for lookahead in values)
        for state in lookaheads
    ]
    transitions: dict[tuple[int, str], int] = {}
    for (source, symbol), target in canonical_transitions.items():
        key = canonical_to_lalr[source], symbol
        lalr_target = canonical_to_lalr[target]
        previous = transitions.setdefault(key, lalr_target)
        if previous != lalr_target:
            raise GrammarError("LALR(1) 状態の併合後に一意でない遷移が見つかりました")
    return productions, states, transitions


def format_lr0_automaton(productions: list[Production], states: list[frozenset[LR0Item]], transitions: dict[tuple[int, str], int]) -> str:
    lines = ["拡張生成規則:"]
    lines.extend(f"  [{p.number}] {p.text()}" for p in productions)
    for state_number, state in enumerate(states):
        lines.extend(["", f"I{state_number}:"])
        lines.extend(f"  [{productions[p].number}] {productions[p].text(dot)}" for p, dot in sorted(state))
        outgoing = sorted((symbol, target) for (source, symbol), target in transitions.items() if source == state_number)
        if outgoing:
            lines.append("  goto: " + ", ".join(f"{symbol} -> I{target}" for symbol, target in outgoing))
    return "\n".join(lines)


def format_item(production: Production, dot: int, lookahead: str) -> str:
    return f"[{production.number}] {production.text(dot)}, {lookahead}"


def format_lr1_automaton(productions: list[Production], states: list[frozenset[LR1Item]], transitions: dict[tuple[int, str], int]) -> str:
    lines = ["拡張生成規則:"]
    lines.extend(f"  [{production.number}] {production.text()}" for production in productions)
    for state_number, state in enumerate(states):
        lines.extend(["", f"I{state_number}:"])
        lines.extend("  " + format_item(productions[index], dot, lookahead) for index, dot, lookahead in sorted(state))
        outgoing = sorted((symbol, target) for (source, symbol), target in transitions.items() if source == state_number)
        if outgoing:
            lines.append("  goto: " + ", ".join(f"{symbol} -> I{target}" for symbol, target in outgoing))
    return "\n".join(lines)


def format_transition_table(grammar: Grammar, states: list[frozenset[Item]], transitions: dict[tuple[int, str], int]) -> str:
    columns = grammar.terminals + grammar.nonterminals
    rows = [["状態"] + columns]
    for state_number in range(len(states)):
        rows.append([f"I{state_number}"] + [str(transitions.get((state_number, symbol), "·")) for symbol in columns])
    widths = [max(len(row[column]) for row in rows) for column in range(len(columns) + 1)]
    lines: list[str] = []
    for row_number, row in enumerate(rows):
        lines.append(" | ".join(value.ljust(widths[column]) for column, value in enumerate(row)))
        if row_number == 0:
            lines.append("-+-".join("-" * width for width in widths))
    return "\n".join(lines)


def lr0_dot_source(
    productions: list[Production],
    states: list[frozenset[LR0Item]],
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


def lr1_dot_source(
    productions: list[Production],
    states: list[frozenset[LR1Item]],
    transitions: dict[tuple[int, str], int],
    vertical: bool = False,
) -> str:
    """LR(1) 項をノードラベルにした Graphviz DOT ソースを返す。"""
    def escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')
    lines = ["digraph LR1 {", f"  rankdir={'TB' if vertical else 'LR'};", "  node [shape=box fontname=monospace];"]
    for number, state in enumerate(states):
        label = f"I{number}\\l" + "".join(
            escape(format_item(productions[index], dot, lookahead)) + "\\l"
            for index, dot, lookahead in sorted(state)
        )
        lines.append(f'  I{number} [label="{label}"];')
    for (source, symbol), target in sorted(transitions.items()):
        lines.append(f'  I{source} -> I{target} [label="{escape(symbol)}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"


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


def parsing_table_dot(grammar: Grammar, states: list[frozenset[Item]], action: dict[tuple[int, str], list[str]], goto: dict[tuple[int, str], int]) -> str:
    """構文解析表を Graphviz の HTML テーブルラベルで表現する。"""
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


def lr1_table(
    grammar: Grammar,
    productions: list[Production],
    states: list[frozenset[LR1Item]],
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
