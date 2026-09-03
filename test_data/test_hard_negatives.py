# test_hard_negatives.py — Looks dead but ISN'T
# Agent should NOT flag any of these

def used_in_exception(data):
    error_msg = "Something went wrong"  # looks unused
    try:
        return data / 0
    except ZeroDivisionError:
        return error_msg  # actually used here!

def conditional_import_flag():
    DEBUG = False
    if DEBUG:  # looks always False
        print("debug mode")  # but DEBUG could be toggled externally
    return "done"

def used_in_nested_lambda(x):
    multiplier = 3  # looks unused
    fn = lambda v: v * multiplier  # actually captures multiplier
    return fn(x)

def chained_not_dead(x):
    a = x + 1
    b = a * 2  # b uses a
    c = b - 3  # c uses b
    return c   # c IS returned — nothing is dead here


