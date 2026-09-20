%token ID
%start start
%%
start  
   : expression '=' expression
   | ID
   ;
expression  
   : expression '+' term
   | term
   ;
term  
   : ID 
   ;
%%
