#!/usr/bin/env python3
"""Compute FOLLOW sets using supplied FIRST sets (Python 3.9+)."""
import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import sys

EMPTY = '%empty'
END = '#'
IDENT = r'[A-Za-z_][A-Za-z_0-9.]*'
TOKEN = re.compile(
    r'''(?P<space>\s+)|(?P<comment>/\*[\s\S]*?\*/|//[^\n]*)|'''
    r'''(?P<quoted>'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*")|'''
    r'''(?P<word>%[A-Za-z_]+|[A-Za-z_][A-Za-z_0-9.]*)|'''
    r'''(?P<punct>%%|[:,;|\[\]#])'''
)


def lex(text):
    """Keep quoted terminals intact, including punctuation and comment markers."""
    tokens = []
    pos = 0
    while pos < len(text):
        match = TOKEN.match(text, pos)
        if not match:
            line = text.count('\n', 0, pos) + 1
            raise ValueError(f'line {line}: unsupported syntax near {text[pos:pos+24]!r}')
        if match.lastgroup not in ('space', 'comment'):
            tokens.append(match.group())
        pos = match.end()
    return tokens


def is_symbol(value):
    return bool(re.fullmatch(IDENT, value)) or value.startswith(("'", '"'))


@dataclass
class Grammar:
    start: str
    nonterminals: list
    terminals: set
    productions: list


def parse_grammar(text):
    # Section delimiters must occupy their own line (optional trailing comment).
    sections = re.split(r'^\s*%%[ \t]*(?://[^\n]*)?$', text, maxsplit=2, flags=re.M)
    if len(sections) < 2:
        raise ValueError('grammar must contain a %% separator on its own line')
    header = lex(sections[0])
    start = None
    declared = set()
    i = 0
    while i < len(header):
        directive = header[i]
        i += 1
        if directive in ('start', '%start'):
            if start is not None or i == len(header) or not re.fullmatch(IDENT, header[i]):
                raise ValueError('exactly one valid start declaration is required')
            start = header[i]
            i += 1
        elif directive == '%token':
            count = 0
            while i < len(header) and header[i] not in ('start', '%start', '%token'):
                if not is_symbol(header[i]):
                    raise ValueError('only symbol names/literals are supported in %token')
                declared.add(header[i])
                count += 1
                i += 1
            if not count:
                raise ValueError('%token requires at least one terminal')
        else:
            raise ValueError(f'unsupported declaration: {directive}')
    if start is None:
        raise ValueError('declare start S (or %start S) before %%')
    tokens = lex(sections[1])
    productions = []
    names = []
    i = 0
    while i < len(tokens):
        lhs = tokens[i]
        if not re.fullmatch(IDENT, lhs) or i + 1 >= len(tokens) or tokens[i+1] != ':':
            raise ValueError(f'expected nonterminal : near {lhs!r}')
        if lhs not in names:
            names.append(lhs)
        i += 2
        rhs = []
        while True:
            if i >= len(tokens):
                raise ValueError(f'missing ; after production for {lhs}')
            token = tokens[i]
            i += 1
            if token in ('|', ';'):
                if not rhs:
                    raise ValueError(f'{lhs}: write %empty for an empty alternative')
                if EMPTY in rhs and rhs != [EMPTY]:
                    raise ValueError('%empty must be the only symbol in its alternative')
                productions.append((lhs, tuple() if rhs == [EMPTY] else tuple(rhs)))
                rhs = []
                if token == ';':
                    break
            elif is_symbol(token) or token == EMPTY:
                rhs.append(token)
            else:
                raise ValueError(f'unsupported symbol in production: {token}')
    if start not in names:
        raise ValueError(f'start symbol {start} has no production')
    if declared.intersection(names):
        raise ValueError('a %token symbol is also a nonterminal')
    terminals = declared | {s for _, rhs in productions for s in rhs if s not in names}
    return Grammar(start, names, terminals, productions)


def parse_first(text, grammar):
    """Read one N,[a,b,%empty] entry per line; quoted CSV value also accepted."""
    result = {}
    for line_no, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('//'):
            continue
        key, sep, value = line.partition(',')
        key, value = key.strip(), value.strip()
        if value.startswith('"['):
            try:
                row = next(csv.reader([line], strict=True))
            except csv.Error as error:
                raise ValueError(f'FIRST line {line_no}: {error}') from error
            if len(row) != 2:
                raise ValueError(f'FIRST line {line_no}: expected two CSV fields')
            key, value = (part.strip() for part in row)
        if not sep or not (value.startswith('[') and value.endswith(']')):
            raise ValueError(f'FIRST line {line_no}: expected symbol,[x,y,...]')
        if key in result:
            raise ValueError(f'FIRST line {line_no}: duplicate entry {key}')
        if key not in grammar.nonterminals and key not in grammar.terminals:
            raise ValueError(f'FIRST line {line_no}: unknown symbol {key}')
        tokens = lex(value[1:-1])
        values = set()
        for i, token in enumerate(tokens):
            if i % 2:
                if token != ',':
                    raise ValueError(f'FIRST line {line_no}: expected comma')
            else:
                if token != EMPTY and token not in grammar.terminals:
                    raise ValueError(f'FIRST line {line_no}: invalid terminal {token}')
                values.add(token)
        if tokens and len(tokens) % 2 == 0:
            raise ValueError(f'FIRST line {line_no}: trailing comma')
        if key in grammar.terminals and values != {key}:
            raise ValueError(f'FIRST({key}) must be [{key}] for a terminal')
        result[key] = values
    missing = set(grammar.nonterminals) - result.keys()
    if missing:
        raise ValueError('missing FIRST entries: ' + ', '.join(sorted(missing)))
    return result


def first_sequence(sequence, first, nonterminals):
    values = set()
    for symbol in sequence:
        current = first[symbol] if symbol in nonterminals else {symbol}
        values.update(current - {EMPTY})
        if EMPTY not in current:
            return values
    values.add(EMPTY)
    return values


@dataclass
class Step:
    label: str
    detail: str
    sets: dict


def compute_follow(grammar, first, trace=False):
    follow = {n: set() for n in grammar.nonterminals}
    follow[grammar.start].add(END)
    history = []

    def record(label, detail):
        if trace:
            history.append(Step(label, detail, {n: set(v) for n, v in follow.items()}))

    record('0', f'initialize: FOLLOW({grammar.start}) = {{#}}; others = {{}}')
    # FIRST(gamma) does not change during the FOLLOW fixed-point iteration.
    occurrences = []
    for rule_no, (lhs, rhs) in enumerate(grammar.productions, 1):
        for position, symbol in enumerate(rhs):
            if symbol in follow:
                suffix_first = first_sequence(rhs[position+1:], first, follow)
                occurrences.append((rule_no, lhs, rhs, position, symbol, suffix_first))
    round_no = 0
    while True:
        round_no += 1
        changed = False
        for rule_no, lhs, rhs, position, symbol, suffix_first in occurrences:
            contribution = suffix_first - {EMPTY}
            nullable = EMPTY in suffix_first
            if nullable:
                contribution = contribution | follow[lhs]
            added = contribution - follow[symbol]
            follow[symbol].update(added)
            changed = changed or bool(added)
            if trace:
                detail = (f'round {round_no}, rule {rule_no}: {lhs} : {" ".join(rhs)}; '
                          f'B={symbol} at position {position+1}; '
                          f'FIRST(gamma)={format_set(suffix_first)}; '
                          f'nullable={str(nullable).lower()}; add {format_set(added)}')
                record(str(len(history)), detail)
        if not changed:
            break
    return follow, history


def format_set(values):
    return '{' + ','.join(sorted(values)) + '}'


def table_rows(grammar, history):
    yield ['nonterminal'] + [step.label for step in history]
    for name in grammar.nonterminals:
        yield [name] + [format_set(step.sets[name]) for step in history]


def print_table(grammar, history, width=None):
    rows = list(table_rows(grammar, history))
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    width = width or shutil.get_terminal_size((120, 24)).columns
    begin = 1
    while begin < len(widths):
        end = begin
        used = widths[0]
        while end < len(widths) and (end == begin or used + 3 + widths[end] <= width):
            used += 3 + widths[end]
            end += 1
        columns = [0] + list(range(begin, end))
        for row_no, row in enumerate(rows):
            print(' | '.join(row[c].ljust(widths[c]) for c in columns))
            if row_no == 0:
                print('-+-'.join('-' * widths[c] for c in columns))
        begin = end
        if begin < len(widths):
            print()


def read_text(filename):
    return sys.stdin.read() if filename == '-' else Path(filename).read_text(encoding='utf-8-sig')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('grammar', help='yacc-like grammar file (or - for stdin)')
    parser.add_argument('-i', '--first', required=True, help='FIRST file (or - for stdin)')
    parser.add_argument('-v', '--verbose', action='store_true', help='show every calculation step')
    parser.add_argument('-T', '--table', action='store_true', help='show step table')
    parser.add_argument('--csv', metavar='FILE', help='write the full step table to CSV')
    args = parser.parse_args(argv)
    if args.grammar == args.first == '-':
        parser.error('grammar and FIRST cannot both use stdin')
    if args.csv and any(path != '-' and Path(args.csv).resolve() == Path(path).resolve()
                        for path in (args.grammar, args.first)):
        parser.error('CSV output must not overwrite an input file')
    try:
        grammar = parse_grammar(read_text(args.grammar))
        first = parse_first(read_text(args.first), grammar)
        follow, history = compute_follow(grammar, first, args.verbose or args.table or bool(args.csv))
        if args.csv:
            with open(args.csv, 'w', encoding='utf-8', newline='') as output:
                csv.writer(output).writerows(table_rows(grammar, history))
        if args.verbose:
            for step in history:
                print(f'Step {step.label}: {step.detail}')
                print('  ' + '  '.join(f'Follow({n})={format_set(step.sets[n])}'
                                      for n in grammar.nonterminals))
            print('Fixed point reached.\n')
        if args.table:
            print_table(grammar, history)
        else:
            for name in grammar.nonterminals:
                print(f'Follow({name})={format_set(follow[name])}')
    except (OSError, UnicodeError, ValueError) as error:
        parser.exit(2, f'{parser.prog}: error: {error}\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
