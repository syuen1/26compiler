"""有向グラフの支配木を、支配頂点集合の反復計算で構成する。"""

import sys


def dominator_tree(n, edges, root):
    """直接支配頂点のリストを返す。頂点番号は0..n-1、根の親は-1。

    edges は (始点, 終点) の反復可能オブジェクト。
    全頂点が root から到達可能でなければ ValueError を送出する。
    """
    if n <= 0 or not 0 <= root < n:
        raise ValueError("頂点数または根が不正です")
    pred = [[] for _ in range(n)]
    succ = [[] for _ in range(n)]
    for u, v in edges:
        if not (0 <= u < n and 0 <= v < n):
            raise ValueError("辺の頂点番号が不正です")
        pred[v].append(u)
        succ[u].append(v)

    reached = {root}
    stack = [root]
    while stack:
        for v in succ[stack.pop()]:
            if v not in reached:
                reached.add(v)
                stack.append(v)
    if len(reached) != n:
        raise ValueError("根から到達できない頂点があります")

    # 整数の第vビットで、頂点vが集合に含まれるかを表す。
    all_vertices = (1 << n) - 1
    dom = [all_vertices] * n
    dom[root] = 1 << root
    changed = True
    while changed:
        changed = False
        for v in range(n):
            if v == root:
                continue
            common = all_vertices
            for p in pred[v]:
                common &= dom[p]
            updated = common | (1 << v)
            if updated != dom[v]:
                dom[v] = updated
                changed = True

    # 真の支配頂点は一列に並ぶ。支配頂点数が最大のものが直接支配頂点。
    depths = [bits.bit_count() for bits in dom]
    parent = [-1] * n
    for v in range(n):
        if v == root:
            continue
        strict = dom[v] & ~(1 << v)
        while strict:
            bit = strict & -strict
            d = bit.bit_length() - 1
            if parent[v] == -1 or depths[d] > depths[parent[v]]:
                parent[v] = d
            strict ^= bit
    return parent


def main():
    """入力: n m root とm組の辺。出力: 各行に頂点とその親。"""
    try:
        values = list(map(int, sys.stdin.buffer.read().split()))
        if len(values) < 3:
            raise ValueError("先頭に頂点数・辺数・根を指定してください")
        n, m, root = values[:3]
        if m < 0 or len(values) != 3 + 2 * m:
            raise ValueError("辺数と入力データ数が一致しません")
        edges = zip(values[3::2], values[4::2])
        parent = dominator_tree(n, edges, root)
    except ValueError as error:
        print(f"入力エラー: {error}", file=sys.stderr)
        return 1
    for v, p in enumerate(parent):
        print(v, p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
