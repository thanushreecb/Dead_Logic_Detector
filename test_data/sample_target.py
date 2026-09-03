# sample_target.py — Complex Dead Logic Test Cases

def calculate_discount(price, member_level="BRONZE"):
    # Case 1: Shadowed Result
    # The 'base_discount' is calculated but completely overwritten 
    # before it is ever read.
    base_discount = price * 0.05
    
    if member_level == "GOLD":
        base_discount = price * 0.20
    else:
        base_discount = price * 0.10
        
    return price - base_discount

def process_user_data(user_id, age):
    # Case 2: Resultless Computation
    # 'display_name' is formatted and stored, but it never leaves 
    # this function and isn't used in the return value.
    display_name = f"User_{user_id}_Age_{age}"
    
    # Case 3: Impossible Logical Branch
    # This block is physically unreachable because age cannot be 
    # both over 65 and under 18 simultaneously.
    status = "active"
    if age > 65:
        if age < 18:
            status = "out_of_range_error"
            print("Logic error detected") 
            
    return {"id": user_id, "status": status}

def maintenance_mode():
    # Case 4: Abandoned Debug Scaffold
    # These variables exist but serve no purpose in the final flow.
    internal_api_version = "v3.4.1"
    trace_id = "0xDEADBEEF"
    
    return True

def chain_reaction(x):
    # Case 5: Dead Data Flow Chain
    # 'a' leads to 'b', and 'b' leads to 'c', but 'c' is never returned.
    # Agent 2 should trace this entire chain as dead.
    a = x + 10
    b = a * 2
    c = b / 5
    
    return x ** 2