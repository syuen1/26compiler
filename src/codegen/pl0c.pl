program PL0C;
var i,r;
begin
  r:=0;
  for i:=1 to 10 do
    r:=r+i*i;
  write(r);
end.
