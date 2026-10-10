"""Black-box tests for Appendix C, including address evaluation order."""
import pathlib
import sys
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def execute(code, data=""):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv") as f:
        f.write(code)
        f.flush()
        return subprocess.run([sys.executable, str(ROOT / "interpreter.py"), f.name], input=data,
                              text=True, capture_output=True, timeout=5)


class MachineTests(unittest.TestCase):
    def check(self, code, expected, data=""):
        result = execute(code, data)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, expected)

    def test_arithmetic(self):
        for op, x, y, expected in [(1, 7, 3, 10), (2, 7, 3, 4),
                                    (3, -7, 3, -21), (4, -7, 3, -2)]:
            with self.subTest(op=op):
                self.check(f"lit,9,9,{x}\nlit,0,0,{y}\nopr,9,9,{op}\nput,9,9,0\n",
                           f"{expected}\n")
        self.check("lit,0,0,7\nopr,0,0,0\nput,0,0,0\n", "-7\n")

    def test_comparisons(self):
        for x, y in [(2, 3), (3, 3), (4, 3)]:
            expected = [x == y, x != y, x < y, x <= y, x > y, x >= y]
            for op, value in enumerate(expected, 5):
                with self.subTest(op=op, x=x):
                    self.check(f"lit,0,0,{x}\nlit,0,0,{y}\nopr,0,0,{op}\nput,0,0,0\n",
                               f"{int(value)}\n")

    def test_loop(self):
        self.check((ROOT / "examples/sum.csv").read_text(), "55\n")

    def test_input(self):
        self.check("get,9,9,9\nget,0,0,0\nopr,0,0,1\nput,0,0,0\n", "5\n", "-2 7")

    def test_indexed_address_and_load_order(self):
        self.check("int,0,0,5\nlit,0,0,42\nsto,0,0,3\n"
                   "lit,0,0,1\nmvx,0,3,0\nlit,0,0,2\nmvx,0,4,0\n"
                   "lod,3,4,0\nput,0,0,0\n"
                   "lod,2,0,-2\nput,0,0,0\n", "42\n42\n")

    def test_call_return_restore(self):
        # The cal at 4 saves the next PC (5), R3=7, and R4=8.
        self.check("lit,0,0,7\nmvx,0,3,0\nlit,0,0,8\nmvx,0,4,0\n"
                   "cal,9,9,9\nlit,0,0,42\nsto,0,0,15\nlod,3,4,0\njmp,0,0,16\n"
                   "int,0,0,1\nlit,0,0,99\nmvx,0,3,0\nlit,0,0,100\nmvx,0,4,0\n"
                   "rtn,9,9,9\nput,0,0,0\nput,0,0,0\n", "42\n")

    def test_recursive_calls(self):
        # Countdown in global s[0]; each activation retains a local copy.
        self.check("int,0,0,1\nlit,0,0,3\nsto,0,0,0\ncal,0,0,6\n"
                   "jmp,0,0,23\njmp,0,0,23\nint,0,0,1\nlod,0,0,0\nsto,1,0,0\n"
                   "lod,0,0,0\nlit,0,0,0\nopr,0,0,9\njpc,0,0,20\n"
                   "lod,0,0,0\nlit,0,0,1\nopr,0,0,2\nsto,0,0,0\ncal,0,0,6\n"
                   "lod,1,0,0\nput,0,0,0\nrtn,0,0,0\n", "1\n2\n3\n")

    def test_termination(self):
        self.check("jmp,0,0,-1\n", "")
        self.check("", "")

    def test_csv_format(self):
        self.check('\n"lit", 0,0,"42"\r\nput,0,0,0\r\n', "42\n")
        self.check('\ufefflit,0,0,7\nput,0,0,0\n', "7\n")
        for code in ["lit 0 0 42", "lit,0,0", "lit,0,0,42,extra",
                     "OPCODE,b,i,a", '"lit,0,0,42', "lit,0,0,1.5"]:
            with self.subTest(code=code):
                self.assertEqual(execute(code).returncode, 1)

    def test_large_integer_division(self):
        self.check("lit,0,0,9223372036854775807\nlit,0,0,3\nopr,0,0,4\nput,0,0,0\n",
                   "3074457345618258602\n")

    def test_errors(self):
        for code, data in [("put,0,0,0", ""), ("lit,0,0,1\nlit,0,0,0\nopr,0,0,4", ""),
                           ("bad,0,0,0", ""), ("lit,0,0,nope", ""),
                           ("lod,0,0,-1", ""), ("opr,0,0,11", ""),
                           ("get,0,0,0", "abc"), ("get,0,0,0", ""),
                           ("lit,0,0,9223372036854775808", ""),
                           ("lit,0,0,9223372036854775807\nlit,0,0,1\nopr,0,0,1", "")]:
            with self.subTest(code=code):
                result = execute(code, data)
                self.assertEqual(result.returncode, 1)
                self.assertIn("error", result.stderr)


if __name__ == "__main__":
    unittest.main()
