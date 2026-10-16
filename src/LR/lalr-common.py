"""LALR 共通処理の互換入口。実装は lr-common.py に置く。"""

from importlib import import_module

lalr_automaton = import_module("lr-common").lalr_automaton
