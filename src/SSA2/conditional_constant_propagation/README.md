# SSAに対する条件付き定数伝播

`conditional_constant_propagation.py`は、指定された講義資料の初期化・Step 1〜10に従って、ブロックの実行可能性E[B]とSSA変数の値V[x]を固定点まで計算します。

## 使い方

Python 3.9以降。解析に外部Pythonライブラリは不要です。画像出力にはGraphvizのdotが必要です。

```sh
python3 conditional_constant_propagation.py output/PL0A.ssa.json
python3 conditional_constant_propagation.py output/PL0B.ssa.json -o output/PL0B.ccp.json
python3 conditional_constant_propagation.py output/constant_branch.ssa.json -o output/constant_branch.ccp.png
python3 conditional_constant_propagation.py output/constant_branch.ssa.json -o output/constant_branch.ccp.svg
python3 conditional_constant_propagation.py output/constant_branch.ssa.json -o output/constant_branch.ccp.pdf
```

`-o`の拡張子は.txt/.json/.dot/.png/.svg/.pdfに対応します。省略時はテキストを標準出力に表示します。入力省略時は標準入力のJSONを使用します。

## -d / --debug

```sh
python3 conditional_constant_propagation.py output/constant_branch.ssa.json -d
python3 conditional_constant_propagation.py output/PL0A.ssa.json -d -o output/PL0A.ccp.json 2> output/PL0A.ccp.debug.txt
```

初期化、パラメータの設定、入口の実行可能化、各反復の開始・終了、各値とブロックの更新、固定点で、全ブロックの`B -> E[B]`と全変数の`x -> V[x]`を表示します。各更新には対応するStepと命令を付けます。デバッグ情報は標準エラーなのでJSONや画像を壊しません。

## 入力と状態

ssa.pyが生成するJSONを使います。φの引数には内部データの@Bnが必要です。画面表示で@Bnが省略されていても、SSAのJSONは常に流入情報を保持しているので、そのまま入力できます。

- E[B]=false: まだ実行可能と判定されていない。
- E[B]=true: 実行される可能性がある。必ず実行されるという意味ではない。
- V[x]=⊥: 初期化されていない／まだ値を得ていない。
- V[x]=整数: 定数。
- V[x]=⊤: 一つの定数に決まらない。

JSONのV[x]は`{"kind":"bottom"}`、`{"kind":"constant","value":4}`、`{"kind":"top"}`です。Eはブロック名から真偽値への対応です。

定義がない外部変数は引数として⊤にします。ただしSSA JSONのundefinedに指定された変数は⊥で初期化します。引数はJSONのparameters配列または`--parameter x_0`（複数指定可）でも指定できます。定義を持つ変数をparametersに指定することはできません。readの結果は、そのブロックが実行可能になったとき⊤になります。

## 資料との対応

資料のB[n]を実装ではE[B]と呼びます。全ブロックをfalse、全変数を⊥で初期化し、引数を⊤、入口をtrueとします。各反復は次の順です。命令の評価は実行可能ブロックでだけ行います。

1. Step 3: 唯一の後続ブロックを実行可能にする。
2. Step 4/5: 定数同士の四則・比較演算を評価し、引数に⊤があれば結果を⊤にする。
3. Step 6: φの実行可能な流入元に異なる定数があれば結果を⊤にする。
4. Step 7: φのいずれかの引数が⊤なら結果を⊤にする。
5. Step 8: 実行可能な流入元の値がすべて同じ定数で、実行不可能な流入元の値がすべて⊥なら、その定数を伝播する。
6. Step 9/10: 条件が⊤なら両方、定数なら真偽に対応した後続ブロックを実行可能にする。⊥なら未確定として保留する。

資料はブロック単位のアルゴリズムです。実装もそのままE[流入元ブロック]を参照し、実行可能辺を使う別方式のSCCPへは変更していません。特にStep 7では実行不可能な流入元の⊤も調べ、Step 8ではその値が⊥であることまで要求します。このため、実行可能な辺だけでφを評価するSCCPより保守的になる場合があります。

既存コードでは`p := x < y`と`if p goto L`または`if not p goto L`に分かれています。比較は通常命令として評価し、条件分岐ではp自体の真偽とCFGのtrue/false辺を参照します。資料の`if x < y goto Bi else Bj`をこの２命令で実現します。

定数代入とコピー命令も伝播します。値は⊥→定数→⊤の方向にだけ更新し、異なる定数へ再評価された場合も⊤にするため、ループでも単調に収束します。整数divは0方向への切り捨てです。定数のゼロ除算は⊤とし、元の演算を残して実行時の例外を消しません。

## 出力

テキストは反復回数、EとVの最終表、定数伝播済みCFGを表示します。JSONは既存と同じblocks/edgesにE/V/iterations/parametersを追加します。内部のundefined情報は入力から保持します。

既知の結果は`x := 定数`に置き換え、通常命令の使用にも定数を代入します。未確定のφは流入情報を保って残します。残るφはブロックの先頭に並べます。

すべての元ブロックと辺を残し、図ではE=trueを緑、falseを灰色にします。実行不可能ブロックを削除したり、分岐をgotoに置き換えたりする処理は行いません。ブロック単位のEの分析結果と元のCFGを比較できる表示です。

## 例

`examples/constant_branch.pls`ではc=1によりthen側だけが実行可能になり、合流後のxが4、yが8になります。入力SSAと結果はoutput/constant_branch.ssa.json、output/constant_branch.ccp.*にあります。PL0A/PL0Bの結果もoutput/にあります。反復するループ変数やreadの値は一般に⊤になります。

## Python API

```python
from conditional_constant_propagation import propagate_constants

result = propagate_constants(graph, parameters=[], undefined=undefined_names, debug=True)
print(result.executable)  # B -> E[B]
print(result.values)      # x -> Value(kind, value)
print(result.debug_report())
```

## 検証

```sh
python3 -m unittest -v test_conditional_constant_propagation
```

13件で、定数分岐、read、φの同一定数と異なる定数、Step 7/8の流入条件、負数の整数除算、ゼロ除算保持、ループの単調な収束、空入力、非SSAの拒否、デバッグ出力、JSON・画像３形式を検査します。PL0A/PL0Bについて伝播前後の実行結果の一致も確認します。


## 講義資料の正解例との照合

```sh
python3 conditional_constant_propagation.py examples/lecture_ccp.ssa.json -d -o output/lecture_ccp.ccp.json
python3 conditional_constant_propagation.py examples/lecture_ccp.ssa.json -o output/lecture_ccp.ccp.svg
```

７ブロックの正解例をexamples/lecture_ccp.ssa.jsonに用意しました。E[B]はB6のみfalseで、B1,B2,B3,B4,B5,B7はtrueです。i1,j1,j2,j3,j4は1、k1は0、k2,k3,k4は⊤、j5,k5は⊥となり、提示された正解と一致します。条件式を既存の３番地コードで表す補助変数p2とp3は、それぞれ⊤と1です。資料のreturn j2はwrite j2とEXITへの辺で出力先を表現しています。

この結果を回帰テストとして追加し、全表の一致と変換前後の実行結果を検査しています。アルゴリズム本体の変更は不要でした。
