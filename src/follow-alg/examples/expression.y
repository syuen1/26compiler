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
