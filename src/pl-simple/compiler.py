"""SLYのreduceアクションで直接目的コードを生成するPL-simpleコンパイラ。"""
import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys

from sly import Lexer, Parser


class CompileError(Exception):
    pass


@dataclass(frozen=True)
class Lexeme:
    text: str
    line: int
    column: int


def column(text, index):
    return index - max(text.rfind("\n", 0, index), text.rfind("\r", 0, index))


KEYWORDS = {word: word.upper() for word in
            "program var if then else while do for to begin end read write div".split()}


class ReduceLexer(Lexer):
    tokens = {"IDENT", "NUMBER", "PROGRAM", "VAR", "IF", "THEN", "ELSE", "WHILE",
              "DO", "FOR", "TO", "BEGIN", "END", "READ", "WRITE", "DIV",
              "ASSIGN", "NE", "LE", "GE"}
    literals = {"=", "<", ">", "+", "-", "*", "(", ")", ";", ",", "."}
    ignore = " \t\f"
    ASSIGN = r":="
    NE = r"<>"
    LE = r"<="
    GE = r">="

    @_(r"[A-Za-z][A-Za-z0-9_]*")
    def IDENT(self, token):
        keyword = KEYWORDS.get(token.value.lower())
        if keyword:
            token.type = keyword
        else:
            token.value = Lexeme(token.value, token.lineno, column(self.text, token.index))
        return token

    @_(r"[+-]?[0-9]+")
    def NUMBER(self, token):
        token.value = Lexeme(token.value, token.lineno, column(self.text, token.index))
        return token

    @_(r"\r\n|\r|\n")
    def ignore_newline(self, token):
        self.lineno += 1

    def error(self, token):
        raise CompileError(f"lexical error: line {token.lineno}, column "
                           f"{column(self.text, token.index)}: illegal character {token.value[0]!r}")


@dataclass(frozen=True)
class WhileContext:
    start: int
    exit_jump: int


@dataclass
class ForContext:
    control: int
    bound: int
    start: int = 0
    exit_jump: int = 0


class ReduceCompiler(Parser):
    tokens = ReduceLexer.tokens
    start = "program"
    precedence = (("nonassoc", "IF_WITHOUT_ELSE"), ("nonassoc", "ELSE"))

    def __init__(self, source="", trace_stream=None):
        self.source = source
        self.trace_stream = trace_stream
        self.code = []
        self.variables = {}
        self.words = 0

    def trace(self, message):
        if self.trace_stream is not None:
            print(message, file=self.trace_stream)

    def emit(self, opcode, operand=0):
        if len(self.code) >= 65536:
            raise CompileError("compile error: program exceeds 65536 instructions")
        address = len(self.code)
        self.code.append([opcode, operand])
        self.trace(f"emit {address}: {opcode},0,0,{operand}")
        return address

    def patch(self, address, operand=None):
        if operand is None:
            operand = len(self.code)
        self.code[address][1] = operand
        self.trace(f"patch {address}: {self.code[address][0]},0,0,{operand}")

    def semantic_error(self, lexeme, message):
        return CompileError(f"compile error: line {lexeme.line}, column {lexeme.column}: {message}")

    def declare(self, lexeme):
        key = lexeme.text.lower()
        if key in self.variables:
            raise self.semantic_error(lexeme, f"duplicate declaration: {lexeme.text}")
        self.variables[key] = self.words
        self.words += 1

    def variable(self, lexeme):
        address = self.variables.get(lexeme.text.lower())
        if address is None:
            raise self.semantic_error(lexeme, f"undeclared identifier: {lexeme.text}")
        return address

    def csv(self):
        return "".join(f"{opcode},0,0,{operand}\n" for opcode, operand in self.code)

    @_('PROGRAM IDENT ";" outblock "."')
    def program(self, p):
        return self.csv()

    @_("var_decl_part reserve_storage statement")
    def outblock(self, p):
        if self.words > 65535:
            raise CompileError("compile error: variable storage too large")
        self.patch(p.reserve_storage, self.words)

    @_("")
    def reserve_storage(self, p):
        # Reduce before the first statement. For-bound slots are discovered later.
        return self.emit("int")

    @_('var_decl_list ";"', '')
    def var_decl_part(self, p):
        pass

    @_('var_decl_list ";" var_decl', 'var_decl')
    def var_decl_list(self, p):
        pass

    @_("VAR id_list")
    def var_decl(self, p):
        pass

    @_('id_list "," IDENT', 'IDENT')
    def id_list(self, p):
        self.declare(p.IDENT)

    @_('statement_list ";" statement', 'statement')
    def statement_list(self, p):
        pass

    @_("assignment_statement", "if_statement", "while_statement", "for_statement",
       "null_statement", "block_statement", "read_statement", "write_statement")
    def statement(self, p):
        pass

    @_("IDENT ASSIGN")
    def assignment_target(self, p):
        return self.variable(p.IDENT)

    @_("assignment_target expression")
    def assignment_statement(self, p):
        self.emit("sto", p.assignment_target)

    @_("IF condition THEN")
    def if_head(self, p):
        return self.emit("jpc")

    @_("if_head statement else_statement")
    def if_statement(self, p):
        # An absent else patches the false jump; a present else patches its end jump.
        self.patch(p.if_head if p.else_statement is None else p.else_statement)

    @_("ELSE else_start statement")
    def else_statement(self, p):
        return p.else_start

    @_("%prec IF_WITHOUT_ELSE")
    def else_statement(self, p):
        return None

    @_("")
    def else_start(self, p):
        # Stack immediately to the left: if_head, statement, ELSE.
        false_jump = p[-3]
        end_jump = self.emit("jmp")
        self.patch(false_jump)
        return end_jump

    @_("")
    def loop_start(self, p):
        return len(self.code)

    @_("WHILE loop_start condition DO")
    def while_head(self, p):
        return WhileContext(p.loop_start, self.emit("jpc"))

    @_("while_head statement")
    def while_statement(self, p):
        context = p.while_head
        self.emit("jmp", context.start)
        self.patch(context.exit_jump)

    @_("FOR IDENT ASSIGN")
    def for_target(self, p):
        control = self.variable(p.IDENT)
        bound = self.words
        self.words += 1
        return ForContext(control, bound)

    @_("for_target expression TO")
    def for_initial(self, p):
        self.emit("sto", p.for_target.control)
        return p.for_target

    @_("for_initial expression DO")
    def for_head(self, p):
        context = p.for_initial
        self.emit("sto", context.bound)
        self.emit("lod", context.control)
        self.emit("lod", context.bound)
        self.emit("opr", 8)
        context.exit_jump = self.emit("jpc")
        context.start = len(self.code)
        return context

    @_("for_head statement")
    def for_statement(self, p):
        context = p.for_head
        self.emit("lod", context.control)
        self.emit("lod", context.bound)
        self.emit("opr", 7)
        done_jump = self.emit("jpc")
        self.emit("lod", context.control)
        self.emit("lit", 1)
        self.emit("opr", 1)
        self.emit("sto", context.control)
        self.emit("jmp", context.start)
        self.patch(context.exit_jump)
        self.patch(done_jump)

    @_("BEGIN statement_list END")
    def block_statement(self, p):
        pass

    @_('READ "(" IDENT ")"')
    def read_statement(self, p):
        address = self.variable(p.IDENT)
        self.emit("get")
        self.emit("sto", address)

    @_('WRITE "(" expression ")"')
    def write_statement(self, p):
        self.emit("put")

    @_("")
    def null_statement(self, p):
        pass

    @_('expression "=" expression', 'expression NE expression',
       'expression "<" expression', 'expression LE expression',
       'expression ">" expression', 'expression GE expression')
    def condition(self, p):
        self.emit("opr", {"=": 5, "<>": 6, "<": 7, "<=": 8, ">": 9, ">=": 10}[p[1]])

    @_("term")
    def expression(self, p):
        pass

    @_('"+" term', '"-" term')
    def expression(self, p):
        if p[0] == "-":
            self.emit("opr", 0)

    @_('expression "+" term', 'expression "-" term')
    def expression(self, p):
        self.emit("opr", 1 if p[1] == "+" else 2)

    @_("factor")
    def term(self, p):
        pass

    @_('term "*" factor', 'term DIV factor')
    def term(self, p):
        self.emit("opr", 3 if p[1] == "*" else 4)

    @_("var_name")
    def factor(self, p):
        pass

    @_("NUMBER")
    def factor(self, p):
        try:
            value = int(p.NUMBER.text)
        except ValueError:
            raise self.semantic_error(p.NUMBER, "integer literal exceeds signed 64-bit range") from None
        if not -(2**63) <= value <= 2**63 - 1:
            raise self.semantic_error(p.NUMBER, "integer literal exceeds signed 64-bit range")
        self.emit("lit", value)

    @_('"(" expression ")"')
    def factor(self, p):
        pass

    @_("IDENT")
    def var_name(self, p):
        self.emit("lod", self.variable(p.IDENT))

    def error(self, token):
        if token is None:
            line = len(re.findall(r"\r\n|\r|\n", self.source)) + 1
            index = len(self.source)
            detail = "unexpected end of input"
        else:
            line, index = token.lineno, token.index
            value = token.value.text if isinstance(token.value, Lexeme) else token.value
            detail = f"unexpected token {value!r}"
        raise CompileError(f"syntax error: line {line}, column {column(self.source, index)}: {detail}")


def compile_source(source, trace_stream=None):
    compiler = ReduceCompiler(source, trace_stream)
    return compiler.parse(ReduceLexer().tokenize(source))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source", help="ソースファイル（-は標準入力）")
    cli.add_argument("-o", "--output", help="CSV保存先（省略時は標準出力）")
    cli.add_argument("--trace-code", action="store_true", help="reduce中の命令生成と補正を表示")
    args = cli.parse_args()
    try:
        source = sys.stdin.read() if args.source == "-" else Path(args.source).read_text(encoding="utf-8")
        output = compile_source(source, sys.stderr if args.trace_code else None)
        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
        else:
            sys.stdout.write(output)
    except (CompileError, OSError, UnicodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
