"""SLYによるPL-0構文解析と付録CのCSVコード生成。"""
import argparse
from dataclasses import dataclass, field
from pathlib import Path
import re
import sys

from sly import Lexer, Parser


class CompileError(Exception):
    pass


@dataclass(frozen=True)
class Node:
    kind: str
    children: tuple = ()
    value: str = None
    line: int = 1
    column: int = 1

    def accept(self, visitor):
        return getattr(visitor, "visit_" + self.kind, visitor.generic_visit)(self)


class Visitor:
    def generic_visit(self, node):
        for child in node.children:
            child.accept(self)


def node(kind, *children, value=None):
    first = children[0] if children else None
    return Node(kind, tuple(children), value,
                first.line if first else 1, first.column if first else 1)


def column(text, index):
    return index - max(text.rfind("\n", 0, index), text.rfind("\r", 0, index))


KEYWORDS = {word: word.upper() for word in
            "program var procedure if then else while do for to begin end read write div".split()}


class PL0Lexer(Lexer):
    tokens = {"IDENT", "NUMBER", "PROGRAM", "VAR", "PROCEDURE", "IF", "THEN",
              "ELSE", "WHILE", "DO", "FOR", "TO", "BEGIN", "END", "READ", "WRITE",
              "DIV", "ASSIGN", "NE", "LE", "GE"}
    literals = {"=", "<", ">", "+", "-", "*", "(", ")", ";", ",", "."}
    ignore = " \t\f"
    ASSIGN = r":="
    NE = r"<>"
    LE = r"<="
    GE = r">="

    @_(r"[a-zA-Z][a-zA-Z0-9_]*")
    def IDENT(self, token):
        keyword = KEYWORDS.get(token.value.lower())
        if keyword:
            token.type = keyword
        else:
            token.value = Node("Identifier", value=token.value, line=token.lineno,
                               column=column(self.text, token.index))
        return token

    @_(r"[0-9]+")
    def NUMBER(self, token):
        token.value = Node("Number", value=token.value, line=token.lineno,
                           column=column(self.text, token.index))
        return token

    @_(r"\r\n|\r|\n")
    def ignore_newline(self, token):
        self.lineno += 1

    def error(self, token):
        raise CompileError(f"lexical error: line {token.lineno}, column "
                           f"{column(self.text, token.index)}: illegal character {token.value[0]!r}")


class PL0Parser(Parser):
    tokens = PL0Lexer.tokens
    start = "program"
    # Empty else reduces only when the next token is not ELSE.
    precedence = (("nonassoc", "IF_WITHOUT_ELSE"), ("nonassoc", "ELSE"))

    def __init__(self, source=""):
        self.source = source

    @_('PROGRAM IDENT ";" outblock "."')
    def program(self, p):
        return node("Program", p.IDENT, p.outblock)

    @_("var_decl_part subprog_decl_part statement")
    def outblock(self, p):
        return node("Outblock", p.var_decl_part, p.subprog_decl_part, p.statement)

    @_('var_decl_list ";"')
    def var_decl_part(self, p):
        return node("VarDeclPart", *p.var_decl_list)

    @_("")
    def var_decl_part(self, p):
        return node("VarDeclPart")

    @_('var_decl_list ";" var_decl')
    def var_decl_list(self, p):
        return p.var_decl_list + (p.var_decl,)

    @_("var_decl")
    def var_decl_list(self, p):
        return (p.var_decl,)

    @_("VAR id_list")
    def var_decl(self, p):
        return node("VarDecl", *p.id_list)

    @_('subprog_decl_list ";"')
    def subprog_decl_part(self, p):
        return node("SubprogDeclPart", *p.subprog_decl_list)

    @_("")
    def subprog_decl_part(self, p):
        return node("SubprogDeclPart")

    @_('subprog_decl_list ";" subprog_decl')
    def subprog_decl_list(self, p):
        return p.subprog_decl_list + (p.subprog_decl,)

    @_("subprog_decl")
    def subprog_decl_list(self, p):
        return (p.subprog_decl,)

    @_("proc_decl")
    def subprog_decl(self, p):
        return p.proc_decl

    @_('PROCEDURE proc_name ";" inblock')
    def proc_decl(self, p):
        return node("ProcDecl", p.proc_name, p.inblock)

    @_("IDENT")
    def proc_name(self, p):
        return p.IDENT

    @_("var_decl_part statement")
    def inblock(self, p):
        return node("Inblock", p.var_decl_part, p.statement)

    @_('statement_list ";" statement')
    def statement_list(self, p):
        return p.statement_list + (p.statement,)

    @_("statement")
    def statement_list(self, p):
        return (p.statement,)

    @_("assignment_statement", "if_statement", "while_statement", "for_statement",
       "proc_call_statement", "null_statement", "block_statement", "read_statement",
       "write_statement")
    def statement(self, p):
        return p[0]

    @_("IDENT ASSIGN expression")
    def assignment_statement(self, p):
        return node("AssignmentStatement", p.IDENT, p.expression)

    @_("IF condition THEN statement else_statement")
    def if_statement(self, p):
        return node("IfStatement", p.condition, p.statement, p.else_statement)

    @_("ELSE statement")
    def else_statement(self, p):
        return node("ElseStatement", p.statement)

    @_("%prec IF_WITHOUT_ELSE")
    def else_statement(self, p):
        return node("ElseStatement")

    @_("WHILE condition DO statement")
    def while_statement(self, p):
        return node("WhileStatement", p.condition, p.statement)

    @_("FOR IDENT ASSIGN expression TO expression DO statement")
    def for_statement(self, p):
        return node("ForStatement", p.IDENT, p.expression0, p.expression1, p.statement)

    @_("proc_call_name")
    def proc_call_statement(self, p):
        return node("ProcCallStatement", p.proc_call_name)

    @_("IDENT")
    def proc_call_name(self, p):
        return p.IDENT

    @_("BEGIN statement_list END")
    def block_statement(self, p):
        return node("BlockStatement", *p.statement_list)

    @_('READ "(" IDENT ")"')
    def read_statement(self, p):
        return node("ReadStatement", p.IDENT)

    @_('WRITE "(" expression ")"')
    def write_statement(self, p):
        return node("WriteStatement", p.expression)

    @_("")
    def null_statement(self, p):
        return node("NullStatement")

    @_('expression "=" expression', 'expression NE expression',
       'expression "<" expression', 'expression LE expression',
       'expression ">" expression', 'expression GE expression')
    def condition(self, p):
        return node("Condition", p.expression0, p.expression1, value=p[1])

    @_("term")
    def expression(self, p):
        return p.term

    @_('"+" term', '"-" term')
    def expression(self, p):
        return node("UnaryPlus" if p[0] == "+" else "Negate", p.term)

    @_('expression "+" term', 'expression "-" term')
    def expression(self, p):
        return node("Add" if p[1] == "+" else "Subtract", p.expression, p.term)

    @_("factor")
    def term(self, p):
        return p.factor

    @_('term "*" factor', 'term DIV factor')
    def term(self, p):
        return node("Multiply" if p[1] == "*" else "Divide", p.term, p.factor)

    @_("var_name", "NUMBER")
    def factor(self, p):
        return p[0]

    @_('"(" expression ")"')
    def factor(self, p):
        return p.expression

    @_("IDENT")
    def var_name(self, p):
        return node("VarName", p.IDENT)

    @_('id_list "," IDENT')
    def id_list(self, p):
        return p.id_list + (p.IDENT,)

    @_("IDENT")
    def id_list(self, p):
        return (p.IDENT,)

    def error(self, token):
        if token is None:
            line = len(re.findall(r"\r\n|\r|\n", self.source)) + 1
            index = len(self.source)
            detail = "unexpected end of input"
        else:
            line, index = token.lineno, token.index
            value = token.value.value if isinstance(token.value, Node) else token.value
            detail = f"unexpected token {value!r}"
        raise CompileError(f"syntax error: line {line}, column {column(self.source, index)}: {detail}")


@dataclass
class Symbol:
    name: str
    b: int = 0
    offset: int = 0
    declaration: Node = None
    order: int = -1
    address: int = -1

    @property
    def procedure(self):
        return self.declaration is not None


@dataclass
class Scope:
    parent: object = None
    names: dict = field(default_factory=dict)
    variable_count: int = 0
    next_temporary: int = 0
    frame_size: int = 0

    @property
    def b(self):
        return 0 if self.parent is None else 1

    def find(self, name):
        symbol = self.names.get(name.lower())
        return self.parent.find(name) if symbol is None and self.parent else symbol


def semantic_error(node, message):
    return CompileError(f"compile error: line {node.line}, column {node.column}: {message}")


class DeclarationVisitor(Visitor):
    def __init__(self, scope, procedures):
        self.scope = scope
        self.procedures = procedures

    def declare(self, identifier, symbol):
        name = symbol.name.lower()
        if name in self.scope.names:
            raise semantic_error(identifier, f"duplicate declaration: {symbol.name}")
        self.scope.names[name] = symbol

    def visit_VarDecl(self, node):
        for identifier in node.children:
            self.declare(identifier, Symbol(identifier.value, self.scope.b, self.scope.variable_count))
            self.scope.variable_count += 1

    def visit_ProcDecl(self, node):
        identifier = node.children[0]
        symbol = Symbol(identifier.value, declaration=node, order=len(self.procedures))
        self.declare(identifier, symbol)
        self.procedures.append(symbol)


class TemporaryCounter(Visitor):
    def __init__(self):
        self.count = 0

    def visit_ForStatement(self, node):
        self.count += 1
        self.generic_visit(node)


class CodeGenerator(Visitor):
    """Use the same memory layout and emission order as the JJTree implementation."""
    def __init__(self):
        self.code = []
        self.procedures = []
        self.scope = None
        self.visible_procedure = float("inf")

    def generate(self, root):
        if self.scope is not None:
            raise ValueError("use a new CodeGenerator per program")
        root.accept(self)
        return "".join(f"{op},{b},{i},{a}\n" for op, b, i, a in self.code)

    def emit(self, opcode, a=0, b=0):
        if len(self.code) >= 65536:
            raise CompileError("compile error: program exceeds 65536 instructions")
        self.code.append([opcode, b, 0, a])
        return len(self.code) - 1

    def patch(self, instruction):
        self.code[instruction][3] = len(self.code)

    def load(self, symbol):
        self.emit("lod", symbol.offset, symbol.b)

    def store(self, symbol):
        self.emit("sto", symbol.offset, symbol.b)

    def variable(self, identifier):
        symbol = self.scope.find(identifier.value)
        if symbol is None:
            raise semantic_error(identifier, f"undeclared identifier: {identifier.value}")
        if symbol.procedure:
            raise semantic_error(identifier, f"variable required: {identifier.value}")
        return symbol

    def prepare_frame(self, body):
        counter = TemporaryCounter()
        body.accept(counter)
        self.scope.next_temporary = self.scope.variable_count
        self.scope.frame_size = self.scope.variable_count + counter.count
        if self.scope.frame_size > 65535:
            raise semantic_error(body, "activation frame too large")

    def visit_Program(self, node):
        self.scope = Scope()
        node.children[1].accept(self)

    def visit_Outblock(self, node):
        variables, procedures, body = node.children
        declarations = DeclarationVisitor(self.scope, self.procedures)
        variables.accept(declarations)
        procedures.accept(declarations)
        self.prepare_frame(body)
        self.emit("int", self.scope.frame_size)
        main_jump = self.emit("jmp")
        for procedure in self.procedures:
            procedure.declaration.accept(self)
        self.visible_procedure = float("inf")
        self.patch(main_jump)
        body.accept(self)

    def visit_ProcDecl(self, node):
        identifier, block = node.children
        global_scope = self.scope
        procedure = global_scope.names[identifier.value.lower()]
        procedure.address = len(self.code)
        self.visible_procedure = procedure.order
        self.scope = Scope(global_scope)
        variables, body = block.children
        variables.accept(DeclarationVisitor(self.scope, self.procedures))
        self.prepare_frame(body)
        self.emit("int", self.scope.frame_size)
        body.accept(self)
        self.emit("rtn")
        self.scope = global_scope

    def visit_AssignmentStatement(self, node):
        identifier, expression = node.children
        symbol = self.variable(identifier)
        expression.accept(self)
        self.store(symbol)

    def visit_ReadStatement(self, node):
        symbol = self.variable(node.children[0])
        self.emit("get")
        self.store(symbol)

    def visit_WriteStatement(self, node):
        self.generic_visit(node)
        self.emit("put")

    def visit_ProcCallStatement(self, node):
        identifier = node.children[0]
        symbol = self.scope.find(identifier.value)
        if symbol is None:
            raise semantic_error(identifier, f"undeclared identifier: {identifier.value}")
        if not symbol.procedure:
            raise semantic_error(identifier, f"procedure required: {identifier.value}")
        if symbol.order > self.visible_procedure:
            raise semantic_error(identifier, f"procedure not yet declared: {identifier.value}")
        self.emit("cal", symbol.address)

    def visit_VarName(self, node):
        self.load(self.variable(node.children[0]))

    def visit_Number(self, node):
        try:
            value = int(node.value)
        except ValueError:
            raise semantic_error(node, "integer literal exceeds signed 64-bit range") from None
        if value > 2**63 - 1:
            raise semantic_error(node, "integer literal exceeds signed 64-bit range")
        self.emit("lit", value)

    def binary(self, node, operation):
        self.generic_visit(node)
        self.emit("opr", operation)

    def visit_Add(self, node):
        self.binary(node, 1)

    def visit_Subtract(self, node):
        self.binary(node, 2)

    def visit_Multiply(self, node):
        self.binary(node, 3)

    def visit_Divide(self, node):
        self.binary(node, 4)

    def visit_Negate(self, node):
        self.generic_visit(node)
        self.emit("opr", 0)

    def visit_Condition(self, node):
        self.binary(node, {"=": 5, "<>": 6, "<": 7, "<=": 8, ">": 9, ">=": 10}[node.value])

    def visit_IfStatement(self, node):
        condition, then, otherwise = node.children
        condition.accept(self)
        false_jump = self.emit("jpc")
        then.accept(self)
        if otherwise.children:
            end_jump = self.emit("jmp")
            self.patch(false_jump)
            otherwise.accept(self)
            self.patch(end_jump)
        else:
            self.patch(false_jump)

    def visit_WhileStatement(self, node):
        condition, body = node.children
        start = len(self.code)
        condition.accept(self)
        exit_jump = self.emit("jpc")
        body.accept(self)
        self.emit("jmp", start)
        self.patch(exit_jump)

    def visit_ForStatement(self, node):
        identifier, initial, upper, body = node.children
        control = self.variable(identifier)
        bound = Symbol("<for-bound>", self.scope.b, self.scope.next_temporary)
        self.scope.next_temporary += 1
        initial.accept(self)
        self.store(control)
        upper.accept(self)
        self.store(bound)
        self.load(control)
        self.load(bound)
        self.emit("opr", 8)
        empty_exit = self.emit("jpc")
        start = len(self.code)
        body.accept(self)
        self.load(control)
        self.load(bound)
        self.emit("opr", 7)
        done_exit = self.emit("jpc")
        self.load(control)
        self.emit("lit", 1)
        self.emit("opr", 1)
        self.store(control)
        self.emit("jmp", start)
        self.patch(empty_exit)
        self.patch(done_exit)


def parse_source(source):
    return PL0Parser(source).parse(PL0Lexer().tokenize(source))


def compile_source(source):
    return CodeGenerator().generate(parse_source(source))


def print_tree(root, indent=""):
    value = f"({root.value})" if root.value is not None else ""
    print(indent + root.kind + value)
    for child in root.children:
        print_tree(child, indent + "  ")


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source", help="PL-0ソースファイル（-は標準入力）")
    cli.add_argument("-o", "--output", help="生成CSVの保存先（省略時は標準出力）")
    modes = cli.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true", help="構文解析のみ")
    modes.add_argument("--tree", action="store_true", help="構文木を表示")
    args = cli.parse_args()
    if args.output and (args.check or args.tree):
        cli.error("-o is available only for code generation")
    try:
        source = sys.stdin.read() if args.source == "-" else Path(args.source).read_text(encoding="utf-8")
        root = parse_source(source)
        if args.check:
            print("OK")
        elif args.tree:
            print_tree(root)
        else:
            csv = CodeGenerator().generate(root)
            if args.output:
                Path(args.output).write_text(csv, encoding="utf-8")
            else:
                sys.stdout.write(csv)
    except (CompileError, OSError, UnicodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
