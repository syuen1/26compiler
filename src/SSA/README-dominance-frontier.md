# 支配境界（dominance frontier）

`dominance_frontier.py`はフローグラフを入力して、到達可能な各基本ブロックの支配境界DFを出力します。Python標準ライブラリだけで動きます。

## 実行

```sh
python3 dominance_frontier.py output/PL0B.cfg.json
python3 dominance_frontier.py output/PL0B.cfg.json -o output/PL0B.df.txt
python3 dominance_frontier.py output/PL0B.cfg.json -o output/PL0B.df.json
python3 dominance_frontier.py --input-format tac output/PL0B.tac
```

入力ファイル省略時は標準入力を使用します。標準入力にも既定でCFGのJSONを指定してください。`--format json`でJSONを標準出力に表示できます。

CFG JSONは`flow_graph.py`の`--format json`で保存した形式です。命令を省略した次の最小形式も受け付けます。

```json
{
  "blocks": ["B1", "B2", "B3", "B4"],
  "entry": "B1",
  "edges": [
    {"source": "B1", "target": "B2"},
    {"source": "B1", "target": "B3"},
    {"source": "B2", "target": "B4"},
    {"source": "B3", "target": "B4"}
  ]
}
```

entryはENTRYが指す基本ブロックです。省略時はblocksの先頭を使います。基本ブロック名の重複・未定義のentry・未定義ブロックを参照する辺はエラーです。EXITへの辺は許容しますが、仮想ENTRY/EXITは分析対象に含めません。到達不能ブロックは支配木と同様に対象から除き、unreachableに別途記録します。

## 定義と計算

```text
DF(x) = { y | yの直前ブロックpが存在し、xがpを支配し、
              xがyを厳密には支配しない }
```

厳密な支配では、自分自身を除きます。ループではDF(x)にx自身が含まれる場合があります。空集合は`{}`と表示します。支配境界を反復して求めるIDFとは異なります。

まず既存の`build_dominator_tree(graph)`で直接支配関係を求めます。到達可能な各辺`p → y`について、pから直接支配ブロックをたどり、`idom(y)`の手前までの各ブロックxにyを追加します。集合で管理するため同じ辺の重複は結果に影響しません。根への戻り辺や根の自己ループも扱います。

Pythonでは次のように使用できます。

```python
from flow_graph import build_flow_graph
from dominance_frontier import compute_dominance_frontiers, load_flow_graph

graph = load_flow_graph(cfg_json_text)  # または build_flow_graph(tac_text)
result = compute_dominance_frontiers(graph)
print(result.to_text())
# result.frontiers: {ブロック名: set(支配境界のブロック名)}
```

## PL0Bの結果

```text
DF(B1) = {}
DF(B2) = {B2}
DF(B3) = {B2}
DF(B4) = {B2, B4}
DF(B5) = {B4}
DF(B6) = {B2}
DF(B7) = {B8}
DF(B8) = {B2}
DF(B9) = {}
```

B7は条件付き出力のブロックです。B7からB8に進めますが、B7を通らずB6から直接B8にも進めるため、B8がB7の支配境界になります。

## テスト

```sh
python3 -m unittest -v test_dominance_frontier
```

PL0A・PL0B、ダイヤモンド型合流、先頭と異なるentry、到達不能ブロック、空入力、不正JSONを検査します。さらに３ブロックの有向グラフ全512通りで、DFの定義から直接計算する結果と照合しています。
