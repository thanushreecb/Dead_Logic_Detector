# test_suite_full.py - Comprehensive Test for Dead Logic Detector
# Targets: Dead Variables (H/M/L), Shadowed Assignments, Impossible Branches

import os

# ---------------------------------------------------------
# 1. SCOPE & CLOSURE TRAPS (Tests Tracer & Reasoner)
# ---------------------------------------------------------

def test_closures_and_scopes(x):
    # DEAD HIGH: Completely unused
    unused_config = {"timeout": 30, "retries": 3}
    
    multiplier = 2
    # This variable 'multiplier' IS used in the lambda below.
    # If the tracer misses the lambda scope, it will flag this as dead.
    callback = lambda val: val * multiplier
    
    # SHADOWED: 'result' is assigned but immediately overwritten
    result = 0
    result = callback(x)
    
    return result

def test_exception_usage(data):
    # DEAD MED: Assigned but only "used" in a dead 'finally' branch logic
    temp_state = "initializing"
    
    try:
        # SHADOWED: first_msg is never read because of the immediate error
        first_msg = "Attempting division"
        val = data / 0
        print(first_msg)
    except ZeroDivisionError:
        # DEAD LOW: 'err_log' used only for a print (Low severity)
        err_log = "Caught div by zero"
        print(err_log)
        return -1
    
    return 0

# ---------------------------------------------------------
# 2. IMPOSSIBLE BRANCHES (Tests Agent_Branch & LLM)
# ---------------------------------------------------------

def test_mathematical_contradictions(score, age):
    # IMPOSSIBLE: score cannot be > 100 and < 50 in a nested check
    if score > 100:
        print("High score!")
        if score < 50:
            return "This branch is logically impossible" # DEAD
            
    # IMPOSSIBLE: logic contradiction with 'age'
    if age < 18:
        if age > 21:
            return "Impossible: Minor cannot be over 21" # DEAD
            
    # SHADOWED: 'status' is overwritten in all possible paths
    status = "unknown" 
    if age >= 18:
        status = "adult"
    else:
        status = "minor"
        
    return status

def test_string_logic(mode):
    # IMPOSSIBLE: string can't be two things at once
    if mode == "read":
        if mode == "write":
            return "Hardware Failure? Mode conflict." # DEAD
    
    # SHADOWED: 'buffer' is updated but the first value is never used
    buffer = "Header:"
    buffer = buffer + " Data Content"
    
    return buffer

# ---------------------------------------------------------
# 3. DATA FLOW & SHADOWING (Tests Tracer)
# ---------------------------------------------------------

def test_loop_shadowing(items):
    # SHADOWED: 'idx' is defined here but overwritten by the for-loop
    idx = -1 
    
    total = 0
    for idx in range(len(items)):
        # DEAD MED: 'current_item' is assigned but never read
        current_item = items[idx]
        total += items[idx]
    
    # DEAD LOW: 'final_count' only used for debug printing
    final_count = idx
    print(f"Processed {final_count} items")
    
    return total

def test_nested_conditionals(a, b):
    # DEAD HIGH: 'heavy_calc' is expensive but the result is ignored
    heavy_calc = [i**2 for i in range(1000)]
    
    if a > 0:
        if b > 0:
            res = "Both positive"
        else:
            res = "B is non-positive"
    else:
        # SHADOWED: 'res' assigned 'A is non-positive' then overwritten
        res = "A is non-positive"
        res = "Check A specifically"
        
    return res

# ---------------------------------------------------------
# 4. TRICKY NEGATIVES (Should NOT be flagged)
# ---------------------------------------------------------

def test_not_actually_dead(x):
    # This variable is used to update itself (Not dead)
    count = 10
    count += x
    
    # Used in a conditional (Not dead)
    is_valid = True
    if is_valid:
        return count
        
    return 0

# ---------------------------------------------------------
# 5. REDUNDANT ASSIGNMENTS (Complex Shadowing)
# ---------------------------------------------------------

class DataProcessor:
    def __init__(self, value):
        self.value = value

    def process(self):
        # SHADOWED: 'setting' is overwritten immediately
        setting = "OFF"
        setting = "ON"
        
        # DEAD MED: 'v' is never used
        v = self.value * 10
        
        if self.value > 100:
            # IMPOSSIBLE: if value > 100, it cannot be < 50
            if self.value < 50:
                return "Logic Error" # DEAD
        
        return setting

# ---------------------------------------------------------
# End of Test Suite
# ---------------------------------------------------------

if __name__ == "__main__":
    # Dummy calls to prevent top-level unused function warnings
    test_closures_and_scopes(5)
    test_mathematical_contradictions(120, 25)
    test_loop_shadowing([1, 2, 3])