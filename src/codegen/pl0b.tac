read n
label l1
t1 := 1 < n
if not t1 goto l2
x := n
t2 := x div 2
m := t2
label l3
t3 := x div m
t4 := t3 * m
t5 := x <> t4
if not t5 goto l4
t6 := m - 1
m := t6
goto l3
label l4
t7 := m = 1
if not t7 goto l5
write x
label l5
t8 := n - 1
n := t8
goto l1
label l2
