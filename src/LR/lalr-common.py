"""LALR(1) オートマトン生成器と構文解析表生成器の共通処理。"""

from __future__ import annotations

from lr1 import Item, lr1_automaton
from slr import Grammar, GrammarError, Production


def lalr_automaton(grammar: Grammar) -> tuple[list[Production], list[frozenset[Item]], dict[tuple[int, str], int]]:
    """同一 LR(0) コアの正準 LR(1) 状態を併合して LALR(1) 状態を作る。"""
    productions, canonical_states, canonical_transitions = lr1_automaton(grammar)
    state_for_core: dict[frozenset[tuple[int, int]], int] = {}
    canonical_to_lalr: dict[int, int] = {}
    lookaheads: list[dict[tuple[int, int], set[str]]] = []

    for canonical_number, state in enumerate(canonical_states):
        core = frozenset((production, dot) for production, dot, _ in state)
        if core not in state_for_core:
            state_for_core[core] = len(lookaheads)
            lookaheads.append({})
        lalr_number = state_for_core[core]
        canonical_to_lalr[canonical_number] = lalr_number
        for production, dot, lookahead in state:
            lookaheads[lalr_number].setdefault((production, dot), set()).add(lookahead)

    states = [
        frozenset((production, dot, lookahead) for (production, dot), values in state.items() for lookahead in values)
        for state in lookaheads
    ]
    transitions: dict[tuple[int, str], int] = {}
    for (source, symbol), target in canonical_transitions.items():
        key = canonical_to_lalr[source], symbol
        lalr_target = canonical_to_lalr[target]
        previous = transitions.setdefault(key, lalr_target)
        if previous != lalr_target:
            raise GrammarError("LALR(1) 状態の併合後に一意でない遷移が見つかりました")
    return productions, states, transitions

