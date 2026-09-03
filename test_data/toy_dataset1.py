def unused_variable():
    x = 42  # dead: never used
    y = "hello"
    return y

def shadowed_var():
    a = 1
    a = 2  # first assignment is shadowed
    return a

def dead_branch():
    flag = True
    if flag:
        temp = 10  # dead: flag is always True, but temp not used
    return "done"

def impossible_condition():
    age = 25
    if age > 30:
        if age < 20:  # impossible
            unreachable = "never"
    return age