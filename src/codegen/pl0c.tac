i := 1
t1 := 10
label l1
t2 := i <= t1
if not t2 goto l2
t3 := i * i
t4 := r + t3
r := t4
t5 := i + 1
i := t5
goto l1
label l2
write r
