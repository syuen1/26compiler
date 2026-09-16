# LL(1) 構文解析表生成器

Yacc 風に記述した文脈自由文法を読み、次の情報を表示する Python プログラムです。

- 生成規則（表中で参照する規則番号つき）
- 各非終端記号の `FIRST(1)`
- 各非終端記号の `FOLLOW(1)`
- LL(1) 構文解析表
- LL(1) 競合の有無と競合セル

外部ライブラリは不要で、Python 3.10 以降で動作します。

## 実行方法

```console
python3 ll1.py examples/expression.y
```

標準入力からも読み込めます。

```console
python3 ll1.py < examples/expression.y
```

競合のない LL(1) 文法なら終了コード `0`、競合があれば `1`、入力エラーなら `2` を返します。

## 入力形式

宣言部と規則部を `%%` で区切ります。2 個目の `%%` より後は読み飛ばします。

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
    : ID
    | NUM
    ;
%%
```

- `%token` で名前つき終端記号を宣言できます。
- `%start` を省略すると、最初の生成規則の左辺が開始記号になります。
- 選択肢は `|`、規則の終わりは `;` です。
- 空語は `%empty`、または空の選択肢（`A : ;` や `A : X | ;`）で表します。
- 文字・文字列リテラルは Yacc と同様に `'+'`、`"if"` のように記述します。
- `/* ... */`、`// ...` コメントと、規則中の `{ ... }` アクションは解析結果に影響しないものとして読み飛ばします。
- `%left`、`%right`、`%nonassoc` に並べた記号も終端記号として扱い、`%prec TOKEN` は読み飛ばします。優先順位による競合解決は行いません。

LL(1) 解析では Yacc の意味値、型、還元アクション、演算子優先順位を使用しません。そのため、本プログラムは `<type>` と数値トークンコードを無視します。

## テスト

```console
python3 -m unittest discover -s tests -v
```
