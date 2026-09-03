def dead_computation():
    a = 5 + 3  # dead chain
    b = a * 2
    c = b - 1
    return 10  # c not returned

def always_true():
    x = 5
    if x > 0:  # always true
        dead_inside = "unused"
    return x

def exception_only():
    try:
        raise ValueError()
    except ValueError:
        debug_var = "only in exception"  # looks dead but used in exception
    return "ok"