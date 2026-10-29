#!/usr/bin/env python3
"""codegen.pdf: SLY lexer -> LALR parser -> AST -> three-address code."""
import argparse
import re
import sys
from pathlib import Path
from sly import Lexer, Parser


class CompileError(Exception):
    pass


def location(source, index):
    return f'{source.count(chr(10), 0, index) + 1}:{index - source.rfind(chr(10), 0, index)}'


class PLSimpleLexer(Lexer):
    tokens = {IDENT, NUMBER, ASSIGN, NE, LE, GE, PROGRAM, VAR, BEGIN, END,
              IF, THEN, ELSE, WHILE, DO, FOR, TO, READ, WRITE, DIV}
    literals = {';', ',', '.', '(', ')', '+', '-', '*', '=', '<', '>'}
    ignore = ' \t\r\f'
    ASSIGN = r':='
    NE = r'<>'
    LE = r'<='
    GE = r'>='
    NUMBER = r'[0-9]+'
    IDENT = r'[a-zA-Z][a-zA-Z_0-9]*'
    IDENT['program'] = PROGRAM
    IDENT['var'] = VAR
    IDENT['begin'] = BEGIN
    IDENT['end'] = END
    IDENT['if'] = IF
    IDENT['then'] = THEN
    IDENT['else'] = ELSE
    IDENT['while'] = WHILE
    IDENT['do'] = DO
    IDENT['for'] = FOR
    IDENT['to'] = TO
    IDENT['read'] = READ
    IDENT['write'] = WRITE
    IDENT['div'] = DIV

    @_ (r'\n+')
    def ignore_newline(self, t):
        self.lineno += len(t.value)

    def error(self, t):
        raise CompileError(f'{location(self.text, t.index)}: 不正な文字 {t.value[0]!r}')


class PLSimpleParser(Parser):
    tokens = PLSimpleLexer.tokens
    start = 'program'
    # ELSE shifts rather than reducing the shorter if production.
    precedence = (('nonassoc', IF_WITHOUT_ELSE), ('nonassoc', ELSE))

    def __init__(self, source):
        self.source = source

    def name(self, p, index=0):
        return ('var', p[index], p._slice[index].index)

    @_('PROGRAM IDENT ";" declarations statement "."')
    def program(self, p):
        return p.declarations, p.statement

    @_('declarations VAR names ";"')
    def declarations(self, p):
        return p.declarations + p.names

    @_('')
    def declarations(self, p):
        return []

    @_('IDENT')
    def names(self, p):
        return [self.name(p)]

    @_('names "," IDENT')
    def names(self, p):
        return p.names + [self.name(p, 2)]

    @_('IDENT ASSIGN expression')
    def statement(self, p):
        return ('assign', self.name(p), p.expression)

    @_('BEGIN statements END')
    def statement(self, p):
        return ('block', p.statements)

    @_('statement')
    def statements(self, p):
        return [p.statement]

    @_('statements ";" statement')
    def statements(self, p):
        return p.statements + [p.statement]

    @_('')
    def statement(self, p):
        return ('empty',)

    @_('IF condition THEN statement %prec IF_WITHOUT_ELSE')
    def statement(self, p):
        return ('if', p.condition, p.statement, None)

    @_('IF condition THEN statement ELSE statement')
    def statement(self, p):
        return ('if', p.condition, p.statement0, p.statement1)

    @_('WHILE condition DO statement')
    def statement(self, p):
        return ('while', p.condition, p.statement)

    @_('FOR IDENT ASSIGN expression TO expression DO statement')
    def statement(self, p):
        return ('for', self.name(p, 1), p.expression0, p.expression1, p.statement)

    @_('READ "(" IDENT ")"')
    def statement(self, p):
        return ('read', self.name(p, 2))

    @_('WRITE "(" expression ")"')
    def statement(self, p):
        return ('write', p.expression)

    @_('expression relation expression')
    def condition(self, p):
        return ('binary', p.relation, p.expression0, p.expression1)

    @_('"="', 'NE', '"<"', 'LE', '">"', 'GE')
    def relation(self, p):
        return p[0]

    # E -> T | '+' T | '-' T | E '+' T | E '-' T
    @_('term')
    def expression(self, p):
        return p.term

    @_('"+" term', '"-" term')
    def expression(self, p):
        return p.term if p[0] == '+' else ('binary', '-', ('number', '0'), p.term)

    @_('expression "+" term', 'expression "-" term')
    def expression(self, p):
        return ('binary', p[1], p.expression, p.term)

    @_('factor')
    def term(self, p):
        return p.factor

    @_('term "*" factor', 'term DIV factor')
    def term(self, p):
        return ('binary', p[1], p.term, p.factor)

    @_('unsigned_factor')
    def factor(self, p):
        return p.unsigned_factor

    @_('NUMBER')
    def unsigned_factor(self, p):
        return ('number', str(int(p.NUMBER)))

    @_('IDENT')
    def unsigned_factor(self, p):
        return self.name(p)

    @_('"(" expression ")"')
    def unsigned_factor(self, p):
        return p.expression

    def error(self, token):
        index = len(self.source) if token is None else token.index
        value = 'EOF' if token is None else repr(token.value)
        raise CompileError(f'{location(self.source, index)}: 構文エラー (入力: {value})')


class CodeGenerator:
    def __init__(self, source):
        self.source = source
        self.variables = set()
        self.code = []
        self.temp_count = self.label_count = 0

    def newtemp(self):
        self.temp_count += 1
        return f't{self.temp_count}'

    def newlabel(self):
        self.label_count += 1
        return f'l{self.label_count}'

    def emit(self, instruction):
        self.code.append(instruction)

    def variable(self, node):
        _, name, index = node
        if name not in self.variables:
            raise CompileError(f'{location(self.source, index)}: 未宣言の変数 {name}')
        return f'v${name}' if re.fullmatch(r't[0-9]+', name) else name

    def binary(self, left, op, right):
        result = self.newtemp()
        self.emit(f'{result} := {left} {op} {right}')
        return result

    def expression(self, node):
        if node[0] == 'number':
            return node[1]
        if node[0] == 'var':
            return self.variable(node)
        _, op, left, right = node
        return self.binary(self.expression(left), op, self.expression(right))

    def statement(self, node):
        kind = node[0]
        if kind == 'empty':
            return
        if kind == 'block':
            for child in node[1]:
                self.statement(child)
        elif kind == 'assign':
            name = self.variable(node[1])
            value = self.expression(node[2])
            self.emit(f'{name} := {value}')
        elif kind == 'read':
            self.emit(f'read {self.variable(node[1])}')
        elif kind == 'write':
            self.emit(f'write {self.expression(node[1])}')
        elif kind == 'if':
            condition = self.expression(node[1])
            otherwise = self.newlabel()
            self.emit(f'if not {condition} goto {otherwise}')
            self.statement(node[2])
            if node[3] is not None:
                done = self.newlabel()
                self.emit(f'goto {done}')
                self.emit(f'label {otherwise}')
                self.statement(node[3])
                self.emit(f'label {done}')
            else:
                self.emit(f'label {otherwise}')
        elif kind == 'while':
            start = self.newlabel()
            self.emit(f'label {start}')
            condition = self.expression(node[1])
            done = self.newlabel()
            self.emit(f'if not {condition} goto {done}')
            self.statement(node[2])
            self.emit(f'goto {start}')
            self.emit(f'label {done}')
        elif kind == 'for':
            name = self.variable(node[1])
            initial = self.expression(node[2])
            self.emit(f'{name} := {initial}')
            upper = self.expression(node[3])
            bound = self.newtemp()
            self.emit(f'{bound} := {upper}')
            start, done = self.newlabel(), self.newlabel()
            self.emit(f'label {start}')
            condition = self.binary(name, '<=', bound)
            self.emit(f'if not {condition} goto {done}')
            self.statement(node[4])
            value = self.binary(name, '+', '1')
            self.emit(f'{name} := {value}')
            self.emit(f'goto {start}')
            self.emit(f'label {done}')
        else:
            raise ValueError(f'Unknown AST node: {kind}')

    def generate(self, tree):
        declarations, statement = tree
        for _, name, index in declarations:
            if name in self.variables:
                raise CompileError(f'{location(self.source, index)}: 変数の重複宣言 {name}')
            self.variables.add(name)
        self.statement(statement)
        return '\n'.join(self.code) + ('\n' if self.code else '')


def compile_source(source):
    tree = PLSimpleParser(source).parse(PLSimpleLexer().tokenize(source))
    return CodeGenerator(source).generate(tree)


def main(argv=None):
    parser = argparse.ArgumentParser(description='SLY版 codegen.pdf BNF → ３番地コード')
    parser.add_argument('source', nargs='?', help='省略時は標準入力')
    parser.add_argument('-o', '--output', help='省略時は標準出力')
    args = parser.parse_args(argv)
    try:
        source = Path(args.source).read_text(encoding='utf-8') if args.source else sys.stdin.read()
        result = compile_source(source)
        if args.output:
            Path(args.output).write_text(result, encoding='utf-8')
        else:
            sys.stdout.write(result)
    except (CompileError, OSError, UnicodeError) as error:
        print(f'エラー: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
