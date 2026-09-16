import unittest

from ll1 import (
    ENDMARK,
    EPSILON,
    GrammarError,
    first_sets,
    follow_sets,
    parse_grammar,
    parsing_table,
)


EXPRESSION_GRAMMAR = r"""
%token ID
%start E
%%
E  : T Ep ;
Ep : '+' T Ep | %empty ;
T  : ID ;
%%
"""


class LL1Tests(unittest.TestCase):
    def test_first_and_follow(self):
        grammar = parse_grammar(EXPRESSION_GRAMMAR)
        first = first_sets(grammar)
        follow = follow_sets(grammar, first)

        self.assertEqual(first["E"], {"ID"})
        self.assertEqual(first["Ep"], {"'+'", EPSILON})
        self.assertEqual(follow["E"], {ENDMARK})
        self.assertEqual(follow["T"], {"'+'", ENDMARK})

    def test_epsilon_entries_use_follow(self):
        grammar = parse_grammar(EXPRESSION_GRAMMAR)
        first = first_sets(grammar)
        follow = follow_sets(grammar, first)
        table = parsing_table(grammar, first, follow)

        self.assertEqual(table[("Ep", ENDMARK)][0].rhs, ())
        self.assertEqual(table[("Ep", "'+'")][0].rhs, ("'+'", "T", "Ep"))

    def test_detects_first_first_conflict(self):
        grammar = parse_grammar("%%\nS: 'a' | 'a' 'b';\n%%")
        first = first_sets(grammar)
        table = parsing_table(grammar, first, follow_sets(grammar, first))
        self.assertEqual(len(table[("S", "'a'")]), 2)

    def test_comments_and_actions_are_ignored(self):
        grammar = parse_grammar(
            r"""
            %{ int helper(void); %}
            %token <text> ID 257
            // declaration comment
            %%
            S : ID { call("}"); { nested(); } } /* rule comment */ ;
            %%
            """
        )
        self.assertEqual(grammar.terminals, ["ID"])
        self.assertEqual(grammar.productions[0].rhs, ("ID",))

    def test_nullable_chain(self):
        grammar = parse_grammar("%%\nS: A B 'c'; A: %empty; B: %empty | 'b';\n%%")
        first = first_sets(grammar)
        follow = follow_sets(grammar, first)
        self.assertEqual(first["S"], {"'b'", "'c'"})
        self.assertEqual(follow["A"], {"'b'", "'c'"})
        self.assertEqual(follow["B"], {"'c'"})

    def test_empty_alternative(self):
        grammar = parse_grammar("%%\nS: 'x' | ;\n%%")
        self.assertEqual(grammar.productions[1].rhs, ())

    def test_prec_requires_token(self):
        with self.assertRaises(GrammarError):
            parse_grammar("%%\nS: 'x' %prec ;\n%%")


if __name__ == "__main__":
    unittest.main()
