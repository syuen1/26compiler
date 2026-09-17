# FOLLOW 集合計算

Python 3.9 以降。外部パッケージ不要。
添付の follow-algorithm.txt の反復アルゴリズムを実装しています。

## 実行

このフォルダを `~/github/26compiler/src/follow-alg` に配置し、そこで実行します。

```sh
python3 follow.py examples/expression.y -i examples/expression.first
python3 follow.py examples/expression.y -i examples/expression.first -v
python3 follow.py examples/expression.y -i examples/expression.first -T
python3 follow.py examples/expression.y -i examples/expression.first -T --csv follow.csv
cat examples/expression.first | python3 follow.py examples/expression.y -i -
python3 -m unittest -v
```

文法ファイルは位置引数、FIRST ファイルは必須の `-i` 引数です。
文法にも `-` を指定できますが、文法と FIRST の両方を標準入力にはできません。
エラーは標準エラー出力に表示し、終了コード 2 を返します。

## 文法形式

`examples/expression.y` は添付された文法そのものです。左辺と `:` を別の行に置けます。

```yacc
%token ID NUM
%start expression

%%

expression
    : term expression_tail
    ;

expression_tail
    : '+' term expression_tail
    | %empty
    ;

term
    : factor term_tail
    ;

term_tail
    : '*' factor term_tail
    | %empty
    ;

factor
    : '(' expression ')'
    | ID
    | NUM
    ;

%%
```

- 開始記号は最初の `%%` より前に `start S` または `%start S` で宣言します。
- `%%` は単独行に置きます。2 番目の `%%` とその後の内容は省略できます。後続内容は読みません。
- 規則の左辺に登場する記号が非終端記号、それ以外の右辺記号が終端記号です。
- `%token` 宣言は省略可能です。宣言には記号名・引用されたリテラルを列挙できます。
- 識別子は `[A-Za-z_][A-Za-z_0-9.]*`。`'+'`、`'('` などの引用リテラルにも対応します。
- 記号の引用符は名前の一部として保持します。文法と FIRST ファイルで同じ表記を使ってください。
  例えば `'a'` と `a` は別の記号です。
- 規則は `:`、`|`、`;` で記述します。空列は必ず `%empty` と明記します。
- 文法内では `/* ... */`、`// ...` コメントが使えます。
- yacc 全体を処理するパーサではありません。意味アクション、型指定、トークン番号、
  別名、`%prec`、`%left`、`%{ ... %}` などは未対応で、エラーにします。
- `#` は入力終端専用です。通常の終端として使う場合は引用した `'#'` を使います。

## FIRST 形式

一行につき `非終端記号,[値,値,...]` を指定します。

```text
expression,['(',ID,NUM]
expression_tail,['+',%empty]
term,['(',ID,NUM]
term_tail,['*',%empty]
factor,['(',ID,NUM]
```

すべての非終端記号について指定してください。集合が空なら `A,[]` とします。
空行および `//` で始まる行を無視します。
通常の CSV の引用形式 `S,"[a,b,%empty]"` も受け付けます。
終端記号の FIRST は自動的にその記号自身の単集合とします。
終端記号の行も入力可能ですが、自身の単集合である必要があります。

入力された FIRST 集合を前提として計算します。未知の記号、重複した行、必須行の欠落は
検査しますが、FIRST 集合が文法と数学的に一致するかの再計算・検証は行いません。

## アルゴリズムとステップ

1. 開始記号の FOLLOW を `{#}`、その他を空集合に初期化します（列 0）。
2. 規則を入力順、右辺の非終端記号を左から右の順に処理します。
3. `A : β B γ` に対して `FIRST(γ) - {%empty}` を `FOLLOW(B)` に追加します。
   γ が nullable なら、現在の `FOLLOW(A)` も追加します。
4. 一巡してどの集合にも追加がなければ終了します。

`FIRST(γ)` は左から順に計算し、nullable な記号を越えて続けます。
空の接尾辞の FIRST は `{%empty}` です。
更新はその場で反映するため、同じ巡回の後続処理にも利用されます。

- 通常出力: 各非終端記号について `Follow(A)={...}`。
- `-v`: 初期状態および各処理の規則、右辺位置、FIRST(γ)、nullable 判定、追加要素、全 FOLLOW。
- `-T`: 横軸はステップ番号、縦軸は非終端記号。列 0 の後は非終端記号の出現を
  一つ処理するごとに列を追加します。変更なしの処理と、収束を確認した最後の巡回も含みます。
  横幅が端末に収まらない場合は、非終端記号列を繰り返して複数の表に分けます。
- `--csv FILE`: 同じ表を折り返さず、一つの CSV に出力します。`-T` なしでも指定可能です。
  CSV は画像形式ではなく、表計算ソフトで開けるデータです。
- `-v` と `-T` は併用可能です。`-T` を指定しなければ最後に通常出力も表示します。

出力の記号は文字列の辞書順、行は規則の左辺の初出順です。
入力は UTF-8（BOM 付きも可）、CSV 出力は UTF-8 です。
履歴表示を指定しない場合、各ステップの集合のコピーは保存しません。
履歴表示時はステップ数と文法サイズに応じたメモリを使用します。

## サンプルの期待結果

```text
Follow(expression)={#,')'}
Follow(expression_tail)={#,')'}
Follow(term)={#,')','+'}
Follow(term_tail)={#,')','+'}
Follow(factor)={#,')','*','+'}
```
