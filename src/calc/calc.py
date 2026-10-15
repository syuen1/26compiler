from sly import Lexer, Parser

class CalcLexer(Lexer):
    # トークン名のセット
    tokens = {NUMBER}

    # 1文字の演算子・記号（そのままリテラルとして扱う）
    literals = {'+', '-', '*', '/', '(', ')'}

    # 無視する文字（空白とタブ）
    ignore = ' \t'

    # 数値のトークン化規則（整数と小数の両方に対応）
    @_(r'\d+(\.\d+)?')
    def NUMBER(self, t):
        t.value = float(t.value) if '.' in t.value else int(t.value)
        return t

    # 改行処理
    @_(r'\n+')
    def ignore_newline(self, t):
        self.lineno += t.value.count('\n')

    # 字句エラー処理
    def error(self, t):
        print(f"不正な文字です: '{t.value[0]}' (行 {self.lineno})")
        self.index += 1
class CalcParser(Parser):
    # 利用するトークン定義を Lexer から受け取る
    tokens = CalcLexer.tokens

    # 演算子の優先順位と結合性（下ほど優先順位が高い）
    precedence = (
        ('left', '+', '-'),
        ('left', '*', '/'),
        ('right', 'UMINUS'),  # 単項マイナス
    )

    # 文法規則: expr の計算

    @_('expr "+" expr')
    def expr(self, p):
        return p.expr0 + p.expr1

    @_('expr "-" expr')
    def expr(self, p):
        return p.expr0 - p.expr1

    @_('expr "*" expr')
    def expr(self, p):
        return p.expr0 * p.expr1

    @_('expr "/" expr')
    def expr(self, p):
        if p.expr1 == 0:
            print("Error: division by zero")
            return 0
        return p.expr0 / p.expr1

    # 単項マイナス (%prec UMINUS に相当)
    @_('"-" expr %prec UMINUS')
    def expr(self, p):
        return -p.expr

    # 括弧
    @_('"(" expr ")"')
    def expr(self, p):
        return p.expr

    # 数値
    @_('NUMBER')
    def expr(self, p):
        return p.NUMBER

    # 構文エラー処理
    def error(self, p):
        if p:
            print(f"構文エラー: '{p.value}' (位置: {p.index})")
        else:
            print("構文エラー: 式が途中で終わっています")
if __name__ == '__main__':
    lexer = CalcLexer()
    parser = CalcParser()

    print("SLY 電卓プログラム (Ctrl+C または Ctrl+D で終了)")
    while True:
        try:
            text = input('> ')
        except (EOFError, KeyboardInterrupt):
            print("\n終了します。")
            break

        if text.strip():
            result = parser.parse(lexer.tokenize(text))
            if result is not None:
                print(f"= {result}")
