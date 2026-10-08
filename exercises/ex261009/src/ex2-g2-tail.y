%token u,v,w,x,y,z
%start S
%%
S : u B D z;
B : w B_tail;
B_tail : v B_tail | %empty ;
D : E F ;
E : y | %empty;
F : x | %empty;
%%
