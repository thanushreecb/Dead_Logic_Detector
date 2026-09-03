def process_data_pipeline(items):
    # DEAD HIGH: This variable is never used anywhere.
    config_settings = {"mode": "advanced", "retry": True}
    
    total = 0
    # SHADOWED: 'count' is assigned but immediately overwritten in the loop.
    count = 10 
    
    for count in range(len(items)):
        # DEAD MED: 'val' is assigned here but never used.
        # (The logic uses items[count] directly later, making this redundant).
        val = items[count]
        
        # SHADOWED: 'status' is assigned 'pending', but overwritten 
        # before any branch can read 'pending'.
        status = "pending"
        if items[count] > 0:
            status = "positive"
        else:
            status = "negative"
            
        print(f"Item {count}: {status}")
        total += items[count]
        
    return total

# Note: 'config_settings' (High), the first 'count' (Shadowed), 
# 'val' (Med), and the first 'status' (Shadowed) should be flagged.

def validate_and_score(user_role, score):
    # DEAD LOW: 'internal_flag' is used, but only in a print 
    # that doesn't affect the program's outcome.
    internal_flag = True
    print(f"Debug: {internal_flag}")

    if user_role == "admin":
        # IMPOSSIBLE BRANCH: score cannot be > 100 AND < 0.
        if score > 100:
            if score < 0:
                return "Error: Impossible Score" # Dead
            return "Admin High Score"
            
    elif user_role == "guest":
        # DEAD MED: 'guest_bonus' is defined but never used 
        # in the return or any logic.
        guest_bonus = 5
        return "Guest Access"

    # IMPOSSIBLE BRANCH: If user_role was "admin", it would have returned.
    # Therefore, inside this 'if', user_role cannot be "admin".
    if user_role != "admin":
        if user_role == "admin":
            return "How did I get here?" # Dead
            
    return "Standard Access"

# Note: 'internal_flag' (Low), the 'score < 0' block (Impossible),
# 'guest_bonus' (Med), and the second 'user_role == "admin"' (Impossible) should be flagged.