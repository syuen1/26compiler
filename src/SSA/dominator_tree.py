"""Dominator analysis for the reachable basic blocks of a FlowGraph."""
import json
from dataclasses import dataclass


@dataclass
class DominatorTree:
    root: object
    blocks: list
    dominators: dict
    immediate_dominators: dict
    unreachable: list

    def to_text(self):
        if self.root is None:
            return '(empty dominator tree)\n'
        lines = [f'root: {self.root}', '']
        for block in self.blocks:
            name = block.name
            parent = self.immediate_dominators[name]
            dom = ', '.join(b.name for b in self.blocks if b.name in self.dominators[name])
            lines.append(f'{name}: idom = {parent or "-"}; Dom = {{{dom}}}')
        if self.unreachable:
            lines.append('\nunreachable: ' + ', '.join(self.unreachable))
        return '\n'.join(lines) + '\n'

    def to_dot(self):
        lines = ['digraph DominatorTree {', '  node [shape=box, fontname="monospace"];']
        for block in self.blocks:
            label = block.name + '\n' + '\n'.join(f'{i.line}: {i.text}' for i in block.instructions)
            lines.append(f'  {block.name} [label={json.dumps(label, ensure_ascii=False)}];')
        for name, parent in self.immediate_dominators.items():
            if parent is not None:
                lines.append(f'  {parent} -> {name};')
        lines.append('}')
        return '\n'.join(lines) + '\n'

    def to_json(self):
        data = {'root': self.root, 'dominators': {
            b.name: [d.name for d in self.blocks if d.name in self.dominators[b.name]]
            for b in self.blocks}, 'immediate_dominators': self.immediate_dominators,
            'edges': [{'source': parent, 'target': name}
                      for name, parent in self.immediate_dominators.items() if parent is not None],
            'unreachable': self.unreachable}
        return json.dumps(data, ensure_ascii=False, indent=2) + '\n'


def build_dominator_tree(graph):
    """Root at ENTRY's target; omit virtual ENTRY/EXIT and unreachable blocks.

    Dom(root) = {root}
    Dom(v) = {v} union intersection(Dom(p) for reachable predecessors p).
    Iterate to a fixed point, then connect each node to its immediate dominator.
    """
    if not graph.blocks:
        return DominatorTree(None, [], {}, {}, [])
    names = {b.name for b in graph.blocks}
    root = graph.blocks[0].name
    successors = {name: set() for name in names}
    predecessors = {name: set() for name in names}
    for edge in graph.edges:
        if edge.source in names and edge.target in names:
            successors[edge.source].add(edge.target)
            predecessors[edge.target].add(edge.source)
    reachable, pending = set(), [root]
    while pending:
        name = pending.pop()
        if name not in reachable:
            reachable.add(name)
            pending.extend(successors[name] - reachable)
    blocks = [b for b in graph.blocks if b.name in reachable]
    unreachable = [b.name for b in graph.blocks if b.name not in reachable]
    dom = {b.name: {root} if b.name == root else set(reachable) for b in blocks}
    changed = True
    while changed:
        changed = False
        for block in blocks:
            name = block.name
            if name == root:
                continue
            incoming = predecessors[name] & reachable
            common = set.intersection(*(dom[p] for p in incoming))
            updated = {name} | common
            if updated != dom[name]:
                dom[name] = updated
                changed = True
    parents = {}
    for block in blocks:
        name = block.name
        strict = dom[name] - {name}
        # The immediate dominator is dominated by every other strict dominator.
        parents[name] = next((d for d in strict if strict - {d} <= dom[d]), None)
    return DominatorTree(root, blocks, dom, parents, unreachable)
