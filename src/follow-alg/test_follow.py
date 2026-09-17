import csv
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from follow import compute_follow, parse_first, parse_grammar, table_rows

ROOT = Path(__file__).resolve().parent


class FollowTests(unittest.TestCase):
    def solve(self, grammar_text, first_text):
        grammar = parse_grammar(grammar_text)
        first = parse_first(first_text, grammar)
        follow, history = compute_follow(grammar, first, trace=True)
        for prev, cur in zip(history, history[1:]):
            for symbol in grammar.nonterminals:
                self.assertLessEqual(prev.sets[symbol], cur.sets[symbol])
                self.assertNotIn('%empty', cur.sets[symbol])
        self.assertEqual(history[-1].sets, follow)
        return follow

    def test_expression(self):
        follow = self.solve((ROOT / 'examples/expression.y').read_text(),
                            (ROOT / 'examples/expression.first').read_text())
        self.assertEqual(follow, {'expression': {'#', "')'"}, 'expression_tail': {'#', "')'"},
                                 'term': {'#', "')'", "'+'"}, 'term_tail': {'#', "')'", "'+'"},
                                 'factor': {'#', "')'", "'+'", "'*'"}})

    def test_nullable_suffix_chain(self):
        follow = self.solve('start S\n%%\nS : A B C ; A : a ; B : b | %empty ; C : c | %empty ;',
                            'S,[a]\nA,[a]\nB,[b,%empty]\nC,[c,%empty]')
        self.assertEqual(follow, {'S': {'#'}, 'A': {'b', 'c', '#'},
                                 'B': {'c', '#'}, 'C': {'#'}})

    def test_cycle_reverse_rule_order(self):
        follow = self.solve('%start S\n%%\nC : A | c ; B : C ; A : B ; S : A ;',
                            'S,[c]\nA,[c]\nB,[c]\nC,[c]')
        self.assertTrue(all(v == {'#'} for v in follow.values()))

    def test_left_recursion_multiple_occurrences(self):
        follow = self.solve('start S\n%%\nS : S A A | %empty ; A : a | %empty ;',
                            'S,[a,%empty]\nA,[a,%empty]')
        self.assertEqual(follow, {'S': {'a', '#'}, 'A': {'a', '#'}})

    def test_empty_and_unreachable(self):
        follow = self.solve('start S\n%%\nS : %empty ; U : u ;', 'S,[%empty]\nU,[u]')
        self.assertEqual(follow, {'S': {'#'}, 'U': set()})

    def test_empty_first_is_not_nullable(self):
        follow = self.solve('start S\n%%\nS : A B ; A : a ; B : B ;',
                            'S,[]\nA,[a]\nB,[]')
        self.assertEqual(follow, {'S': {'#'}, 'A': set(), 'B': {'#'}})

    def test_comments_literals_and_epilogue(self):
        follow = self.solve("/* start X */\n%start S\n%%\nS : A ',' '//' ; // note\nA : %empty ;\n%%\nint main() {}",
                            "S,[',']\nA,[%empty]")
        self.assertEqual(follow['A'], {"','"})

    def test_csv_quoted_first(self):
        grammar = parse_grammar('start S\n%%\nS : a | b ;')
        self.assertEqual(parse_first('S,"[a,b]"', grammar), {'S': {'a', 'b'}})

    def test_invalid_grammar(self):
        for text in ('%%\nS : a ;', 'start X\n%%\nS : a ;',
                     'start S\n%%\nS : %empty a ;', 'start S\n%%\nS : ;',
                     'start S\n%%\nS : a', 'start S\n%%\nS : a { action(); } ;'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_grammar(text)

    def test_invalid_first(self):
        grammar = parse_grammar('start S\n%%\nS : a ;')
        for text in ('', 'S,[z]', 'S,[a,]', 'S,[a]\nS,[a]', 'S,[#]', 'S,[a a]'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_first(text, grammar)

    def run_cli(self, *args, input=None):
        return subprocess.run([sys.executable, str(ROOT / 'follow.py'), *map(str, args)],
                              input=input, text=True, capture_output=True)

    def test_cli_stdin_trace_and_csv(self):
        grammar_path = ROOT / 'examples/expression.y'
        first_text = (ROOT / 'examples/expression.first').read_text()
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'result.csv'
            proc = self.run_cli(grammar_path, '-i', '-', '-v', '-T', '--csv', out, input=first_text)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn('Fixed point reached.', proc.stdout)
            self.assertIn('nonterminal', proc.stdout)
            grammar = parse_grammar(grammar_path.read_text())
            _, history = compute_follow(grammar, parse_first(first_text, grammar), trace=True)
            with out.open(newline='') as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(rows, list(table_rows(grammar, history)))
            self.assertGreater(len(rows[0]), 10)

    def test_cli_failures(self):
        proc = self.run_cli('-', '-i', '-')
        self.assertEqual(proc.returncode, 2)
        proc = self.run_cli(ROOT / 'examples/expression.y', '-i', '/nonexistent/first')
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn('Traceback', proc.stderr)
        proc = self.run_cli(ROOT / 'examples/expression.y', '-i', ROOT / 'examples/expression.first',
                            '--csv', ROOT / 'examples/expression.y')
        self.assertEqual(proc.returncode, 2)


if __name__ == '__main__':
    unittest.main()
