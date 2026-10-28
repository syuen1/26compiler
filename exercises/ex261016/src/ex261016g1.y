%start S
%%
S : '(' X
  | E ']'
  | F ')'
  ;
X : E ')'
  | F ']'
  ;
E : A
  ;
F : A
  ;
A : %empty
  ;
%%
