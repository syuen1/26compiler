i := 1
j := 1
k := 0
label l1
t1 := k < 100
if not t1 goto l2
t2 := j < 20
if not t2 goto l3
j := i
t3 := k + 1
k := t3
goto l4
label l3
j := k
t4 := k + 2
k := t4
label l4
t5 := i + 1
i := t5
goto l1
label l2
return := j
