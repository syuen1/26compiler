%token A C D
%start z

%%

z : D
  | x y z
  ;

y : %empty
  | C
  ;

x : y
  | A
  ;

%%
