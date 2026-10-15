"""LALR(1) オートマトン生成器と構文解析表生成器の共通処理。"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable, Sequence

from slr import Grammar, GrammarError, Production


EPSILON = "ε"
ENDMARK = "#"
Item = tuple[int, int, str]  # (生成規則の添字, ドット位置, 先読み記号)


def _first_sets(grammar: Grammar) -> dict[str, set[str]]:
    """非終端記号ごとの FIRST 集合を計算する。"""
    nonterminals = set(grammar.nonterminals)
    first = {symbol: set() for symbol in grammar.nonterminals}
    changed = True
    while changed:
        changed = False
        for production in grammar.productions:
            values = _first_of_sequence(production.rhs, first, nonterminals)
            before = len(first[production.lhs])
            first[production.lhs].update(values)
            changed |= before != len(first[production.lhs])
    return first


def _first_of_sequence(symbols: Sequence[str], first: dict[str, set[str]], nonterminals: set[str]) -> set[str]:
    """記号列の FIRST 集合を返す。"""
    if not symbols:
        return {EPSILON}
    result: set[str] = set()
    for symbol in symbols:
        if symbol not in nonterminals:
            result.add(symbol)
            return result
        result.update(first[symbol] - {EPSILON})
        if EPSILON not in first[symbol]:
            return result
    result.add(EPSILON)
    return result


def _lr1_automaton(grammar: Grammar) -> tuple[list[Production], list[frozenset[Item]], dict[tuple[int, str], int]]:
    """正準 LR(1) 項集合族と goto 遷移を返す。"""
    augmented = [Production(0, grammar.start + "'", (grammar.start,))] + grammar.productions
    nonterminals = set(grammar.nonterminals) | {augmented[0].lhs}
    first = _first_sets(grammar)
    by_lhs: dict[str, list[int]] = defaultdict(list)
    for index, production in enumerate(augmented):
        by_lhs[production.lhs].append(index)

    def closure(seed: Iterable[Item]) -> frozenset[Item]:
        result = set(seed)
        pending = list(result)
        while pending:
            production_index, dot, lookahead = pending.pop()
            production = augmented[production_index]
            if dot >= len(production.rhs) or production.rhs[dot] not in nonterminals:
                continue
            symbol = production.rhs[dot]
            lookaheads = _first_of_sequence(production.rhs[dot + 1 :] + (lookahead,), first, nonterminals) - {EPSILON}
            for child in by_lhs[symbol]:
                for child_lookahead in lookaheads:
                    item = (child, 0, child_lookahead)
                    if item not in result:
                        result.add(item)
                        pending.append(item)
        return frozenset(result)

    states = [closure({(0, 0, ENDMARK)})]
    numbers = {states[0]: 0}
    transitions: dict[tuple[int, str], int] = {}
    queue = deque([0])
    while queue:
        state_number = queue.popleft()
        state = states[state_number]
        symbols = sorted({augmented[index].rhs[dot] for index, dot, _ in state if dot < len(augmented[index].rhs)})
        for symbol in symbols:
            target = closure(
                (index, dot + 1, lookahead)
                for index, dot, lookahead in state
                if dot < len(augmented[index].rhs) and augmented[index].rhs[dot] == symbol
            )
            if target not in numbers:
                numbers[target] = len(states)
                states.append(target)
                queue.append(numbers[target])
            transitions[state_number, symbol] = numbers[target]
    return augmented, states, transitions


def lalr_automaton(grammar: Grammar) -> tuple[list[Production], list[frozenset[Item]], dict[tuple[int, str], int]]:
    """同一 LR(0) コアの正準 LR(1) 状態を併合して LALR(1) 状態を作る。"""
    productions, canonical_states, canonical_transitions = _lr1_automaton(grammar)
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

