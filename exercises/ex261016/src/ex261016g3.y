%start S
%%
S : X
  ;
X : M 'a'
  | 'b' M 'c'
  | 'd' 'c'
  | 'b' 'd' 'a'
  ;
M : 'd'
  ;
%%
