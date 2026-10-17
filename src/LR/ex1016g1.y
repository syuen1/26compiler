%token id
%start S
%%
S : E ;
E : id '(' E ')'
  | id
  | E '+' E
  ;
%%
