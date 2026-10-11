"""付録Cの目的コードを実行するスタックマシン（Python 3）。"""
import argparse
import csv
from dataclasses import dataclass
import re
import sys

OPCODES = {"lit", "lod", "sto", "mvx", "opr", "int", "cal", "rtn",
           "jmp", "jpc", "get", "put"}
MIN_INT, MAX_INT = -(2**63), 2**63 - 1


class MachineError(Exception):
    """目的コードまたは実行状態のエラー。"""


def integer(text):
    if not re.fullmatch(r"[+-]?[0-9]+", text):
        raise MachineError(f"invalid integer: {text!r}")
    try:
        return checked(int(text))
    except ValueError as exc:
        raise MachineError("integer too long") from exc


def checked(value):
    if not MIN_INT <= value <= MAX_INT:
        raise MachineError("integer overflow")
    return value


@dataclass(frozen=True)
class Instruction:
    opcode: str
    b: int
    i: int
    a: int


def load_program(stream):
    """ヘッダーなしの4列CSV。空行を除いた命令番号がアドレスになる。"""
    program = []
    reader = csv.reader(stream, skipinitialspace=True, strict=True)
    try:
        for row in reader:
            if not row or (len(row) == 1 and not row[0].strip()):
                continue
            if len(row) != 4:
                raise MachineError(f"line {reader.line_num}: expected OPCODE,b,i,a")
            opcode, b, i, a = (field.strip() for field in row)
            if opcode not in OPCODES:
                raise MachineError(f"line {reader.line_num}: unknown opcode {opcode!r}")
            try:
                program.append(Instruction(opcode, integer(b), integer(i), integer(a)))
            except MachineError as exc:
                raise MachineError(f"line {reader.line_num}: {exc}") from exc
            if len(program) > 65536:
                raise MachineError("program too large")
    except csv.Error as exc:
        raise MachineError(f"line {reader.line_num}: invalid CSV: {exc}") from exc
    return program


class Machine:
    def __init__(self, program, input_stream=None, output_stream=None, trace=False):
        self.program = program
        self.s = [0] * 65536
        self.r = [0, 0, -1, 0, 0]
        self.pc = 0
        self.ir = None
        self.inputs = self.tokens(sys.stdin if input_stream is None else input_stream)
        self.output = sys.stdout if output_stream is None else output_stream
        self.trace = trace

    @staticmethod
    def tokens(stream):
        for line in stream:
            yield from line.split()

    def address(self, value):
        if not 0 <= value < len(self.s):
            raise MachineError(f"invalid stack address: {value}")
        return value

    def need(self, count):
        if not count - 1 <= self.r[2] < len(self.s):
            raise MachineError("stack underflow or invalid stack top")

    def register(self, number):
        if not 0 <= number <= 4:
            raise MachineError(f"invalid register: {number}")
        return self.r[number] if number else 0

    def effective(self, instruction):
        return self.address(self.register(instruction.b) +
                            self.register(instruction.i) + instruction.a)

    def push(self, value):
        top = self.address(self.r[2] + 1)
        self.r[2] = top
        self.s[top] = checked(value)

    def arithmetic(self, operation):
        if not 0 <= operation <= 10:
            raise MachineError("opr requires operation 0..10")
        self.need(1 if operation == 0 else 2)
        if operation == 0:
            self.s[self.r[2]] = checked(-self.s[self.r[2]])
            return
        y = self.s[self.r[2]]
        self.r[2] -= 1
        x = self.s[self.r[2]]
        if operation == 1:
            value = x + y
        elif operation == 2:
            value = x - y
        elif operation == 3:
            value = x * y
        elif operation == 4:
            if y == 0:
                raise MachineError("division by zero")
            # 浮動小数点を使わず、負数でも0方向に切り捨てる。
            value = abs(x) // abs(y)
            if (x < 0) != (y < 0):
                value = -value
        else:
            value = int((x == y, x != y, x < y, x <= y, x > y, x >= y)[operation - 5])
        self.s[self.r[2]] = checked(value)

    def run(self):
        while 0 <= self.pc < len(self.program):
            current_pc = self.pc
            self.ir = t = self.program[self.pc]
            if self.trace:
                print(f"PC={self.pc} {t.opcode},{t.b},{t.i},{t.a} "
                      f"R1={self.r[1]} R2={self.r[2]} R3={self.r[3]} R4={self.r[4]}",
                      file=sys.stderr)
            self.pc += 1
            try:
                self.execute(t)
            except MachineError as exc:
                raise MachineError(f"PC={current_pc}: {exc}") from exc

    def execute(self, t):
        r, s = self.r, self.s
        if t.opcode == "lit":
            self.push(t.a)
        elif t.opcode == "lod":
            # R2を増やしてから実効アドレスを計算する。
            r[2] = self.address(r[2] + 1)
            s[r[2]] = s[self.effective(t)]
        elif t.opcode == "sto":
            self.need(1)
            s[self.effective(t)] = s[r[2]]
            r[2] -= 1
        elif t.opcode == "mvx":
            self.need(1)
            if not 1 <= t.i <= 4:
                raise MachineError("mvx requires register 1..4")
            r[t.i] = s[r[2]]
            r[2] = checked(r[2] - 1)
        elif t.opcode == "opr":
            self.arithmetic(t.a)
        elif t.opcode == "int":
            top = r[2] + t.a
            if not -1 <= top < len(s):
                raise MachineError("invalid stack top")
            r[2] = top
        elif t.opcode == "cal":
            base = r[2]
            self.address(base + 1)
            self.address(base + 4)
            s[base + 1:base + 5] = [r[1], self.pc, r[3], r[4]]
            r[1], r[2], self.pc = base + 5, base + 4, t.a
        elif t.opcode == "rtn":
            base = r[1]
            self.address(base - 4)
            self.address(base - 1)
            r[2] = base - 5
            self.pc = s[base - 3]
            r[3], r[4], r[1] = s[base - 2], s[base - 1], s[base - 4]
        elif t.opcode == "jmp":
            self.pc = t.a
        elif t.opcode == "jpc":
            self.need(1)
            if s[r[2]] == 0:
                self.pc = t.a
            r[2] -= 1
        elif t.opcode == "get":
            try:
                value = integer(next(self.inputs))
            except StopIteration as exc:
                raise MachineError("expected integer input") from exc
            self.push(value)
        elif t.opcode == "put":
            self.need(1)
            print(s[r[2]], file=self.output)
            r[2] -= 1
        else:
            raise MachineError(f"unknown opcode: {t.opcode}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("program", help="ヘッダーなしの4列CSVファイル")
    parser.add_argument("--trace", action="store_true", help="実行状態を表示")
    args = parser.parse_args()
    try:
        with open(args.program, encoding="utf-8-sig", newline="") as stream:
            program = load_program(stream)
        Machine(program, trace=args.trace).run()
    except (MachineError, OSError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
