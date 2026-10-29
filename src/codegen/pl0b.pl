program PL0B;
var m, n, x;
begin
  read(n);
  while 1 < n do
    begin
      x := n;
      begin
        m := x div 2;
        while x <> (x div m) * m do
          m := m - 1;
        if m = 1 then
          write(x)
      end;
      n := n - 1
    end
end.
