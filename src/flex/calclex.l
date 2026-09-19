%{
#include <stdio.h>
%}

%%
[a-zA-Z_][a-zA-Z0-9_]*	{printf("type=ID, value=%s\n",yytext);}
[0-9]+			{printf("type=NUMBER, value=%s\n",yytext);}
\+			{printf("type=PLUS, value=%s\n",yytext);}
-			{printf("type=MINUS, value=%s\n",yytext);}
\*			{printf("type=TIMES, value=%s\n",yytext);}
\/			{printf("type=DIVIDE, value=%s\n",yytext);}
=			{printf("type=ASSIGN, value=%s\n",yytext);}
\(			{printf("type=LPAREN, value=%s\n",yytext);}
\)			{printf("type=RPAREN, value=%s\n",yytext);}
%%

int main(void)
{
    const char *data = "x = 3 + 42 * (s - t)";
    YY_BUFFER_STATE buffer = yy_scan_string(data);

    yylex();

    yy_delete_buffer(buffer);
    return 0;
}

int yywrap(void)
{
    return 1;
}
