  %{
  #include <stdio.h>
  #include <stdlib.h>

  int yylex(void);
  void yyerror(const char *s);
  %}

  /* トークン定義 */
  %token NUMBER

  /* 演算子の優先順位と結合性 */
  %left '+' '-'
  %left '*' '/'
  %nonassoc UMINUS

  %%

  /* 構文規則 */
  input:
  /* 空入力を許容 */
  | input line
  ;
  line:
  '\n'            { printf("> "); }
  | expr '\n'       { printf("= %d\n> ", $1); }
  | error '\n'      { yyerrok; printf("> "); }
  ;

  expr:
  NUMBER          { $$ = $1; }
  | expr '+' expr   { $$ = $1 + $3; }
  | expr '-' expr   { $$ = $1 - $3; }
  | expr '*' expr   { $$ = $1 * $3; }
  | expr '/' expr   {
      if ($3 == 0) {
          yyerror("division by zero");
          $$ = 0;
        } else {
          $$ = $1 / $3;
        }
    }
  | '-' expr %prec UMINUS { $$ = -$2; }
  | '(' expr ')'    { $$ = $2; }
  ;

  %%

  void yyerror(const char *s) {
      fprintf(stderr, "Error: %s\n", s);
    }

  int main(void) {
      setvbuf(stdout, NULL, _IONBF, 0);

      printf("電卓プログラム (Ctrl+D または Ctrl+C で終了)\n> ");
      return yyparse();
    }
