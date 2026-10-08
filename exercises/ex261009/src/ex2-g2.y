%token u,v,w,x,y,z
%start S
%%
S : u B D z;
B : B v | w ;
D : E F ;
E : y | %empty;
F : x | %empty;
%%
