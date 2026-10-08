%token i,t,e,a,b
%start S
%%
S : i E t S S1 | a ;
S1 : e S | %empty ;
E : b ;
%%
