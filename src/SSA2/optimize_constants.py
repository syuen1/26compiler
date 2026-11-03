"""Clean up a constant-propagated SSA CFG without leaving SSA form."""
import re
from flow_graph import BasicBlock, Edge, FlowGraph, Instruction, FlowGraphError, NAME
from ssa import Operation, parse_operation


def optimize_constant_cfg(graph, executable):
    operations = {b.name: [parse_operation(i) for i in b.instructions] for b in graph.blocks}
    if not operations:
        return FlowGraph([], [])
    root = graph.blocks[0].name
    edges = []
    for e in graph.edges:
        if not executable.get(e.source, False):
            continue
        ops = operations[e.source]
        last = ops[-1] if ops else None
        if last and last.kind == 'conditional' and re.fullmatch(r'-?[0-9]+', last.args[0]):
            if (e.kind == 'true') != bool(int(last.args[0])):
                continue
            edges.append(Edge(e.source, e.target, 'goto'))
        else:
            edges.append(e)
    reachable, pending = set(), [root]
    while pending:
        b = pending.pop()
        if b in reachable or b not in operations:
            continue
        reachable.add(b)
        pending += [e.target for e in edges if e.source == b]
    operations = {b: ops for b, ops in operations.items() if b in reachable}
    edges = [e for e in edges if e.source in reachable and (e.target in reachable or e.target == 'EXIT')]
    for b, ops in operations.items():
        if ops and ops[-1].kind == 'conditional' and len({e.target for e in edges if e.source == b}) == 1:
            ops.pop()
        preds = {e.source for e in edges if e.target == b} | ({'ENTRY'} if b == root else set())
        for op in ops:
            if op.kind == 'phi':
                op.incoming = {p: v for p, v in op.incoming.items() if p in preds}

    def remove_copies_and_dead_code():
        aliases = {}
        for ops in operations.values():
            for op in ops:
                if op.kind == 'phi':
                    values = set(op.incoming.values()) - {op.dest}
                    if len(values) == 1:
                        aliases[op.dest] = next(iter(values))
                elif op.kind == 'assign' and not op.operator and re.fullmatch(NAME, op.args[0]) and op.dest != op.args[0]:
                    aliases[op.dest] = op.args[0]
        def resolve(v):
            seen = set()
            while v in aliases and v not in seen:
                seen.add(v)
                v = aliases[v]
            return v
        for b, ops in list(operations.items()):
            retained = []
            for op in ops:
                if op.dest in aliases and resolve(op.dest) != op.dest:
                    continue
                op.args = [resolve(v) for v in op.args]
                op.incoming = {p: resolve(v) for p, v in op.incoming.items()}
                retained.append(op)
            operations[b] = retained
        definitions = {op.dest: op for ops in operations.values() for op in ops if op.dest}
        needed, work = set(), []
        for ops in operations.values():
            for op in ops:
                # Preserve I/O and potentially trapping divisions.
                trap = op.kind == 'assign' and op.operator == 'div' and (
                    not re.fullmatch(r'-?[0-9]+', op.args[1]) or int(op.args[1]) == 0)
                if op.kind in {'read', 'write', 'conditional'} or trap:
                    if op.dest:
                        needed.add(op.dest)
                    work += op.args
        while work:
            v = work.pop()
            op = definitions.get(v)
            if op is None or v in needed:
                continue
            needed.add(v)
            work += op.args + list(op.incoming.values())
        for b in operations:
            operations[b] = [op for op in operations[b] if not op.dest or op.dest in needed]

    def rewrite_predecessor(old, replacements):
        for ops in operations.values():
            for op in ops:
                if op.kind == 'phi' and old in op.incoming:
                    v = op.incoming.pop(old)
                    for pred in replacements:
                        op.incoming[pred] = v

    while True:
        remove_copies_and_dead_code()
        changed = False
        # Remove empty forwarding blocks and repair phi predecessor names.
        for b, ops in list(operations.items()):
            out = {e.target for e in edges if e.source == b}
            if b == root or any(op.kind not in {'label', 'goto'} for op in ops) or len(out) != 1:
                continue
            target = next(iter(out))
            if target in {b, 'EXIT'}:
                continue
            preds = {e.source for e in edges if e.target == b}
            conflict = any(op.kind == 'phi' and b in op.incoming and any(
                p in op.incoming and op.incoming[p] != op.incoming[b] for p in preds)
                for op in operations.get(target, []))
            if conflict:
                continue
            rewrite_predecessor(b, preds)
            edges = list(dict.fromkeys(Edge(e.source, target if e.target == b else e.target, e.kind)
                                       for e in edges if e.source != b))
            del operations[b]
            changed = True
            break
        if changed:
            continue
        # Merge single-successor / single-predecessor chains.
        for b in list(operations):
            out = {e.target for e in edges if e.source == b}
            if len(out) != 1:
                continue
            target = next(iter(out))
            if target not in operations or target in {root, b}:
                continue
            preds = {e.source for e in edges if e.target == target}
            if preds != {b}:
                continue
            if any(op.kind == 'phi' for op in operations[target]):
                continue
            operations[b] = [op for op in operations[b] if op.kind not in {'goto', 'conditional'}]
            operations[b] += [op for op in operations[target] if op.kind != 'label']
            rewrite_predecessor(target, [b])
            edges = list(dict.fromkeys(Edge(b if e.source == target else e.source,
                                           b if e.target == target else e.target, e.kind)
                        for e in edges if not (e.source == b and e.target == target)))
            del operations[target]
            changed = True
            break
        if not changed:
            break
    # Rebuild branch labels to match the simplified CFG. Explicit goto terminates
    # each single-successor block; the CFG edges carry normal fallthrough semantics.
    reserved = {op.target for ops in operations.values() for op in ops if op.kind == 'label'}
    labels = {}
    for b, ops in operations.items():
        if ops and ops[0].kind == 'label':
            labels[b] = ops[0].target
        else:
            label = 'opt_' + b
            while label in reserved:
                label += '_'
            reserved.add(label)
            labels[b] = label
            ops.insert(0, Operation('label', 0, target=label))
    output, final_edges = [], []
    for b, ops in operations.items():
        out = [e for e in edges if e.source == b]
        targets = {e.target for e in out}
        last = ops[-1] if ops else None
        if last and last.kind in {'goto', 'conditional'}:
            ops.pop()
        if len(targets) == 1:
            target = next(iter(targets))
            if target != 'EXIT':
                ops.append(Operation('goto', 0, target=labels[target]))
            final_edges.append(Edge(b, target, 'fallthrough' if target == 'EXIT' else 'goto'))
        else:
            if last is None or last.kind != 'conditional':
                raise FlowGraphError('最適化後の条件分岐を構成できません')
            chosen = next(e.target for e in out if e.kind == ('false' if last.negated else 'true'))
            if chosen == 'EXIT':
                raise FlowGraphError('分岐先EXITには終了ブロックが必要です')
            ops.append(Operation('conditional', last.line, args=last.args, target=labels[chosen], negated=last.negated))
            final_edges += out
        output.append(BasicBlock(b, [Instruction(op.line, op.text(), op.kind,
            target=op.target if op.kind in {'goto', 'conditional'} else '',
            label=op.target if op.kind == 'label' else '') for op in ops]))
    return FlowGraph(output, final_edges)
