%token ID
%start S
%%
S : E 
  ;
E : 'while' E 'do' E
  : ID ':=' E
  : E '+' E
  : ID
  ;
%%
