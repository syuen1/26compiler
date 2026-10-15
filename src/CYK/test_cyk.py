"""元の CFG の固定点認識器と CYK の受理判定を比較する。"""
import itertools
from pathlib import Path
import subprocess
import sys
import unittest

from cyk import cyk, parse_grammar, read_tokens, to_cnf


def recognize_original(grammar, tokens):
    # 空区間を含む各 span について、元の生成規則を直接適用する。
    nts = set(grammar.nonterminals)
    n = len(tokens)
    spans = {symbol: set() for symbol in nts}
    changed = True
    while changed:
        changed = False
        for production in grammar.productions:
            for begin in range(n + 1):
                ends = {begin}
                for symbol in production.rhs:
                    if symbol in nts:
                        ends = {end for position in ends for start, end in spans[symbol] if start == position}
                    else:
                        ends = {position + 1 for position in ends if position < n and tokens[position] == symbol}
                for end in ends:
                    if (begin, end) not in spans[production.lhs]:
                        spans[production.lhs].add((begin, end))
                        changed = True
    return (0, n) in spans[grammar.start]


class CYKTests(unittest.TestCase):
    def test_general_cfg_against_original(self):
        grammars = [
            'S: A B C; A: a | %empty; B: b | %empty; C: c | %empty;',
            'S: A; A: B | a A b; B: A | %empty;',
            'S: S S | a;',
            'S: a S b | %empty;',
            'S: A A A A; A: a | %empty;',
            'S: S | A; A: B; B: A;',
            'S: a b c | a S c;',
            'S: S a | %empty;',
            'S: @CYK0; @CYK0: a;',
        ]
        for rules in grammars:
            grammar = parse_grammar('%%\n' + rules)
            cnf = to_cnf(grammar)
            nts = {lhs for lhs, _ in cnf.rules} | {cnf.start}
            for _, rhs in cnf.rules:
                self.assertTrue((len(rhs) == 1 and rhs[0] not in nts) or
                                (len(rhs) == 2 and all(s in nts for s in rhs)))
            for length in range(5):
                for tokens in itertools.product('abc', repeat=length):
                    with self.subTest(rules=rules, tokens=tokens):
                        result = cyk(cnf, tokens)
                        self.assertEqual(result.accepted, recognize_original(grammar, tokens))
                        if tokens and result.tree:
                            def leaves(node):
                                return [node.symbol] if not node.children else [s for child in node.children for s in leaves(child)]
                            self.assertEqual(leaves(result.tree), list(tokens))

    def test_expression(self):
        root = Path(__file__).parent
        grammar = to_cnf(parse_grammar((root / 'expression.y').read_text()))
        self.assertTrue(cyk(grammar, read_tokens((root / 'input.txt').read_text())).accepted)
        self.assertFalse(cyk(grammar, read_tokens("ID '=' '+' ID")).accepted)

    def test_input(self):
        self.assertEqual(read_tokens("ID '=' ID #"), ['ID', "'='", 'ID'])
        self.assertEqual(read_tokens('#'), [])
        self.assertEqual(read_tokens("'#'"), ["'#'"])
        for text in ['# ID', 'ID # #', "'unclosed"]:
            with self.assertRaises(ValueError):
                read_tokens(text)

    def test_cli(self):
        root = Path(__file__).parent
        command = [sys.executable, str(root / 'cyk.py'), str(root / 'expression.y')]
        good = subprocess.run(command + ['--cnf', '-T', '--tree'], input="ID '=' ID '+' ID '*' ID #", text=True, capture_output=True)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertIn('CYK 表', good.stdout)
        self.assertIn('構文解析木', good.stdout)
        bad = subprocess.run(command, input="ID '=' '+' ID", text=True, capture_output=True)
        self.assertEqual(bad.returncode, 1)
        malformed = subprocess.run(command, input='ID # #', text=True, capture_output=True)
        self.assertEqual(malformed.returncode, 2)


if __name__ == '__main__':
    unittest.main()
