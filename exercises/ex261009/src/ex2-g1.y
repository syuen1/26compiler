%token i,t,e,a,b
%start S
%%
S : i E t S | i E t S e S | a ;
E : b ;
%%