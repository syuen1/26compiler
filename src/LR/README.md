# LR(0) オートマトン生成器

`slr.py` は、Yacc 風に記述した文脈自由文法から LR(0) 項集合族と状態遷移を生成します。入力形式は `../LL-parsing-table/examples/expression.y` と互換です。

```console
python3 slr.py ../LL-parsing-table/examples/expression.y
```

状態遷移表を表示するには `-T` を付けます。

```console
python3 slr.py -T ../LL-parsing-table/examples/expression.y
```

`--graph` には出力ファイルを渡します。拡張子から Graphviz の出力形式を選びます。画像・PDF・SVGの生成には Graphviz の `dot` コマンドが必要です。

```console
python3 slr.py --graph expression-lr0.svg ../LL-parsing-table/examples/expression.y
python3 slr.py --graph expression-lr0.png ../LL-parsing-table/examples/expression.y
```

`.dot` を指定すると、レンダリング前の DOT ソースを保存できます。

状態遷移を上から下へ配置して横幅を抑えるには、`--vertical` を指定します。指定しない場合は左から右への配置です。

```console
python3 slr.py --vertical --graph expression-lr0.svg ../LL-parsing-table/examples/expression.y
```

EPS 形式で出力するには `--eps` を使います。`--vertical` と併用できます。

```console
python3 slr.py --vertical --eps expression-lr0.eps ../LL-parsing-table/examples/expression.y
```

生成規則の先頭には、開始記号を左辺とする拡張生成規則 `S' -> S` を自動で追加します。`%empty` と空の選択肢は空右辺として扱い、規則中の意味アクション、コメント、`%prec` は LR(0) 項に影響しないため読み飛ばします。

## SLR(1) 構文解析表

`slr1.py` は同じ文法入力から SLR(1) の ACTION/GOTO 表を作成します。還元先には FOLLOW 集合を用い、競合があれば該当する ACTION セルを示して終了コード `1` を返します。

入力の終端を表す記号は `#` です。したがって、開始規則の受理動作は ACTION 表の `#` 列に `acc` として現れます。

```console
python3 slr1.py ../LL-parsing-table/examples/expression.y
```

競合がなければ終了コードは `0`、入力エラーは `2` です。標準入力も利用できます。

LaTeX の `table` 環境として ACTION/GOTO 表を保存するには、`--tex-table` を使います。

```console
python3 slr1.py --tex-table expression-slr-table.tex ../LL-parsing-table/examples/expression.y
```

非空の ACTION/GOTO セルをリスト形式で保存するには `--outtab` を使います。各セルは `ACTION[状態, 記号] = 動作` または `GOTO[状態, 非終端記号] = 状態` の形式です。

```console
python3 slr1.py --outtab expression-slr-table.tab ../LL-parsing-table/examples/expression.y
```

この `.tab` には拡大文法の生成規則も含まれ、先頭には `attr-start -> 開始記号 #` を生成規則 `0` として追加します。元の生成規則番号は `1` からのままです。`pdt.py` の入力になります。

## Pushdown transducer

`pdt.py` は `slr1.py --outtab` で出力した構文解析表と、空白区切りの入力系列を読み、還元した生成規則番号を出力テープとして表示します。入力末尾の `#` は省略できます。文法で引用符付き終端記号を使う場合は、入力側も同じ表記にします。

```console
python3 slr1.py --outtab expression.tab expression_tail.y
python3 pdt.py expression.tab input.txt
python3 pdt.py -v expression.tab input.txt
```

`-v` を指定すると、各 shift・reduce・accept 動作後の状態と記号が交互に積まれたスタック、残り入力、出力テープ、実行動作を表示します。拡大文法の規則0（`attr-start -> 開始記号 #`）による受理時は、スタックを空にし、`#` を消費して出力テープへ `0` を追加します。

`--eps` を指定すると、SLR(1) の ACTION/GOTO 構文解析表を EPS 形式でも出力します。

```console
python3 slr1.py --eps expression-slr-table.eps ../LL-parsing-table/examples/expression.y
```

## LR(1) オートマトン

`lr1.py` は同じ入力形式から、先読み記号つきの正準 LR(1) 項集合族と LR(1) オートマトンを生成します。開始項の先読み記号には入力終端記号 `#` を使います。オプションは `slr.py` と同じです。

```console
python3 lr1.py ../LL-parsing-table/examples/expression.y
python3 lr1.py -T ../LL-parsing-table/examples/expression.y
python3 lr1.py --vertical --graph expression-lr1.svg ../LL-parsing-table/examples/expression.y
python3 lr1.py --eps expression-lr1.eps ../LL-parsing-table/examples/expression.y
```

## LR(1) 構文解析表

`lr11.py` は正準 LR(1) 項集合の先読み記号に基づいて ACTION/GOTO 表を作成します。`slr1.py` と同様に競合を表示し、競合があれば終了コード `1` を返します。

```console
python3 lr11.py ../LL-parsing-table/examples/expression.y
python3 lr11.py --tex-table expression-lr1-table.tex ../LL-parsing-table/examples/expression.y
python3 lr11.py --eps expression-lr1-table.eps ../LL-parsing-table/examples/expression.y
python3 lr11.py --outtab expression-lr1-table.tab ../LL-parsing-table/examples/expression.y
```

## LALR(1) オートマトン

`lalr1.py` は正準 LR(1) 項集合を同一の LR(0) コアごとに併合し、LALR(1) 項集合族とオートマトンを生成します。オプションは `lr1.py` と同じです。

```console
python3 lalr1.py expression.y
python3 lalr1.py -T expression.y
python3 lalr1.py --vertical --graph expression-lalr1.svg expression.y
python3 lalr1.py --eps expression-lalr1.eps expression.y
```

## LALR(1) 構文解析表

`lalr11.py` は併合後の LALR(1) 項集合から ACTION/GOTO 表を作成します。`lr11.py` と同様に競合を報告し、LaTeX と EPS の表出力にも対応します。

```console
python3 lalr11.py expression.y
python3 lalr11.py --tex-table expression-lalr1-table.tex expression.y
python3 lalr11.py --eps expression-lalr1-table.eps expression.y
python3 lalr11.py --outtab expression-lalr1-table.tab expression.y
```
