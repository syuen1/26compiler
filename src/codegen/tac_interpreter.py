#!/usr/bin/env python3
"""Execute generated integer three-address code without eval or exec."""
import argparse
import re
import sys
from collections import deque
from pathlib import Path
from dataclasses import dataclass


class InterpreterError(ValueError):
    pass


@dataclass(frozen=True)
class Instruction:
    line: int
    text: str
    kind: str
    target: str = ''
    label: str = ''


NAME = r'[A-Za-z][A-Za-z_0-9$]*'
VALUE = rf'(?:-?[0-9]+|{NAME})'
LABEL = re.compile(rf'label\s+({NAME})')
GOTO = re.compile(rf'goto\s+({NAME})')
CONDITIONAL = re.compile(rf'if\s+not\s+({VALUE})\s+goto\s+({NAME})')
NORMAL = re.compile(
    rf'(?:read\s+{NAME}|write\s+{VALUE}|'
    rf'{NAME}\s*:=\s*{VALUE}(?:\s+(?:\+|-|\*|div|=|<>|<=|>=|<|>)\s+{VALUE})?)'
)


def parse_code(code):
    instructions, labels = [], {}
    for line_number, raw in enumerate(code.splitlines(), 1):
        text = raw.strip()
        if not text:
            continue
        match = LABEL.fullmatch(text)
        if match:
            name = match[1]
            if name in labels:
                raise InterpreterError(f'{line_number}: ラベル {name} が重複しています')
            labels[name] = len(instructions)
            instruction = Instruction(line_number, text, 'label', label=name)
        elif (match := GOTO.fullmatch(text)):
            instruction = Instruction(line_number, text, 'goto', target=match[1])
        elif (match := CONDITIONAL.fullmatch(text)):
            instruction = Instruction(line_number, text, 'conditional', target=match[2])
        elif NORMAL.fullmatch(text):
            instruction = Instruction(line_number, text, 'normal')
        else:
            raise InterpreterError(f'{line_number}: 未対応または不正な命令: {text}')
        instructions.append(instruction)
    for instruction in instructions:
        if instruction.target and instruction.target not in labels:
            raise InterpreterError(f'{instruction.line}: 未定義のラベル {instruction.target}')
    return instructions, labels



ASSIGN = re.compile(rf'({NAME})\s*:=\s*({VALUE})(?:\s+(\+|-|\*|div|=|<>|<=|>=|<|>)\s+({VALUE}))?')
INTEGER = re.compile(r'[+-]?[0-9]+')


def execute(code, inputs=(), *, read=None, write=None, max_steps=1_000_000):
    """Return (variable dictionary, output list). read()/write(int) allow live I/O.

    All code is validated before execution. Each call starts with fresh state.
    Labels count as steps; max_steps must be a positive integer.
    """
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps <= 0:
        raise InterpreterError('実行命令数の上限は正の整数にしてください')
    instructions, labels = parse_code(code)
    iterator = iter(inputs)
    values, output = {}, []
    pc = steps = 0

    def fail(instruction, message):
        raise InterpreterError(f'{instruction.line}: {message} (命令: {instruction.text})')

    def value(operand, instruction):
        if INTEGER.fullmatch(operand):
            return int(operand)
        if operand not in values:
            fail(instruction, f'未初期化の変数 {operand}')
        return values[operand]

    while pc < len(instructions):
        instruction = instructions[pc]
        if steps >= max_steps:
            fail(instruction, f'実行命令数の上限 {max_steps} を超えました')
        steps += 1
        pc += 1
        if instruction.kind == 'label':
            continue
        if instruction.kind == 'goto':
            pc = labels[instruction.target]
            continue
        if instruction.kind == 'conditional':
            operand = instruction.text.split()[2]
            if value(operand, instruction) == 0:
                pc = labels[instruction.target]
            continue
        text = instruction.text
        if text.split()[0] == 'read':
            target = text.split()[1]
            try:
                raw = read() if read is not None else next(iterator)
            except (StopIteration, EOFError):
                fail(instruction, 'read の入力が不足しています')
            if not INTEGER.fullmatch(str(raw).strip()):
                fail(instruction, f'整数でない入力 {raw!r}')
            values[target] = int(str(raw).strip())
        elif text.split()[0] == 'write':
            result = value(text.split()[1], instruction)
            output.append(result)
            if write is not None:
                write(result)
        else:
            target, left, op, right = ASSIGN.fullmatch(text).groups()
            a = value(left, instruction)
            if op is None:
                values[target] = a
                continue
            b = value(right, instruction)
            if op == 'div':
                if b == 0:
                    fail(instruction, 'ゼロ除算')
                result = (abs(a) // abs(b)) * (-1 if (a < 0) != (b < 0) else 1)
            elif op == '+':
                result = a + b
            elif op == '-':
                result = a - b
            elif op == '*':
                result = a * b
            else:
                result = {'=': a == b, '<>': a != b, '<': a < b,
                          '<=': a <= b, '>': a > b, '>=': a >= b}[op]
            values[target] = int(result)
    return values, output


def main(argv=None):
    parser = argparse.ArgumentParser(description='３番地コードの整数インタプリター')
    parser.add_argument('code', help='３番地コードのファイル')
    parser.add_argument('--max-steps', type=int, default=1_000_000,
                        help='実行命令数の上限（既定: 1000000）')
    args = parser.parse_args(argv)
    pending = deque()

    def read_integer():
        while not pending:
            line = sys.stdin.readline()
            if not line:
                raise EOFError
            pending.extend(line.split())
        return pending.popleft()

    try:
        code = Path(args.code).read_text(encoding='utf-8')
        execute(code, read=read_integer, write=print, max_steps=args.max_steps)
    except (InterpreterError, OSError, UnicodeError) as error:
        print(f'エラー: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
