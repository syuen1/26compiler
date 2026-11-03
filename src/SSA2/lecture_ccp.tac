i := 1
j := 1
k := 0
label l1
t1 := k < 100
if not t1 goto l4
t2 := j < 20
if not t2 goto l2
j := i
k := k + 1
goto l3
label l2
j := k
k := k + 2
label l3
goto l1
label l4
write j
