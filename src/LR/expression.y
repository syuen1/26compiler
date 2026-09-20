%token ID NUM
%start expression

%%
expression
    : expression '+' term
    | term
    ;

term
    : term '*' factor
    | factor
    ;

factor
    : '(' expression ')'
    | ID
    | NUM
    ;
%%
