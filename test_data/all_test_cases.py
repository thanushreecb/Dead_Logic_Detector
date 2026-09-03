import random

# ── DEAD VARIABLES ──────────────────────────────────────────────────────────

def process_user(name, age, price, member_level):

    # HIGH: assigned, never read, never returned
    display_name = name.upper()
    internal_tag = "v2.1-beta"
    session_token = "tok_" + name

    # MEDIUM: looks like debug scaffolding
    internal_api_version = "0.0.9"
    trace_id = "trace-abc-123"
    debug_mode = True

    # LOW: assigned but only used in another dead chain
    prefix = "user_"
    full_label = prefix + name       # full_label never used after this

    # HIGH dead chain: a → b → c, none reach return
    a = price * 0.10
    b = a + 5
    c = b * 2                        # c never used

    # Another HIGH dead chain
    tax = price * 0.18
    total_with_tax = price + tax     # total_with_tax never used

    # MEDIUM: intermediate calculation, result dropped
    discount_preview = price * 0.05
    final_preview = discount_preview - 1   # final_preview never used

    # ── SHADOWED ASSIGNMENTS ─────────────────────────────────────────────────

    # HIGH shadow: base_discount set, then immediately overwritten before read
    base_discount = price * 0.05         # line never read before overwrite
    if member_level == "GOLD":
        base_discount = price * 0.20
    else:
        base_discount = price * 0.10

    # HIGH shadow: status set, overwritten before read
    status = "active"                    # wasted — overwritten below
    if age > 65 and age < 18:            # ← IMPOSSIBLE BRANCH too
        status = "out_of_range_error"
    if age > 70:
        status = "senior"

    # MEDIUM shadow: counter reset inside loop before ever being used
    counter = 0
    for i in range(5):
        counter = i * 2                  # previous value always overwritten
    result = counter

    # LOW shadow: flag toggled but only last value matters
    flag = False
    flag = True                          # first assignment wasted
    flag = False                         # second assignment wasted

    # ── IMPOSSIBLE BRANCHES ──────────────────────────────────────────────────

    # HIGH: age > 65 already checked in outer scope, inner age < 18 unreachable
    if age > 65:
        if age < 18:                     # IMPOSSIBLE — HIGH confidence
            print("This never runs")

    # HIGH: x is a constant, condition always false
    x = 100
    if x < 0:                            # always False — HIGH
        print("Negative x never happens")
        extra_dead = x * 99              # dead inside impossible branch

    # MEDIUM: float comparison that can never be exactly true
    ratio = 1 / 3
    if ratio == 0.5:                     # practically impossible — MEDIUM
        print("Unreachable float equality")

    # LOW: redundant else after exhaustive if/elif
    score = random.randint(0, 100)
    if score >= 0 and score <= 100:      # always True for 0-100 range
        grade = "valid"
    else:
        grade = "impossible"             # unreachable else — LOW

    return base_discount, status, result, flag, grade