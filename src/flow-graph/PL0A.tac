n := 10
sum := 0
label l1
t1 := n > 0
if not t1 goto l2
t2 := sum + n
sum := t2
t3 := n - 1
n := t3
goto l1
label l2
write sum
