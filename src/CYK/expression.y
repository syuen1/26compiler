%token ID NUM
%start statement
%%
statement : ID '=' expression ;
expression : expression '+' term | term ;
term : term '*' factor | factor ;
factor : '(' expression ')' | ID | NUM ;
%%
