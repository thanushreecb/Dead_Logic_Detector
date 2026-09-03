def exception_handler():
    try:
        risky = 1 / 0
    except ZeroDivisionError:
        error_msg = "Division by zero"  # used only in exception, not dead
        print(error_msg)
    return "handled"

def conditional_debug():
    DEBUG = True
    if DEBUG:
        debug_info = "Debug mode"  # used conditionally
        print(debug_info)
    return "normal"

def lazy_init():
    result = None
    if some_condition():  # assume defined elsewhere
        result = "computed"
    return result or "default"