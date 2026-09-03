"""
pipeline.py — LangGraph State Machine (v3)
"""
from langgraph.graph import StateGraph, END
from state import AgentState
from agent1_parser       import parse_node
from agent1_5_branch     import branch_detect_node
from agent2_tracer       import trace_node
from agent3_reasoner     import reason_node, confidence_router
from agent4_report       import report_node

def build_pipeline():
    graph = StateGraph(AgentState)
    graph.add_node("agent1_parse",    parse_node)
    graph.add_node("agent1_5_branch", branch_detect_node)
    graph.add_node("agent2_trace",    trace_node)
    graph.add_node("agent3_reason",   reason_node)
    graph.add_node("agent4_report",   report_node)
    graph.add_edge("agent1_parse",    "agent1_5_branch")
    graph.add_edge("agent1_5_branch", "agent2_trace")
    graph.add_edge("agent2_trace",    "agent3_reason")
    graph.add_conditional_edges("agent3_reason", confidence_router,
        {"retry": "agent2_trace", "done": "agent4_report"})
    graph.add_edge("agent4_report", END)
    graph.set_entry_point("agent1_parse")
    return graph

def run(filepath: str, api_key: str = None):
    graph    = build_pipeline()
    compiled = graph.compile()
    initial_state: AgentState = {
        "filepath": filepath, "api_key": api_key,
        "source": "", "assignments": [], "output_nodes": [],
        "raw_tree": None, "call_graph": None,
        "nested_conditions": [], "shadowed_vars": [], "impossible_branches": [],
        "dfg": None, "dead_vars": [], "live_vars": [],
        "verdicts": [], "retry_count": 0, "needs_retry": False,
        "report_html": "", "report_path": "", "error": None,
    }
    print("\n" + "="*55)
    print(" Dead Logic Detector v3 — LangGraph Pipeline")
    print("="*55)
    try:
        final_state = compiled.invoke(initial_state)
    except Exception as e:
        # If Groq fails mid-pipeline, retry with Gemini key
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if gemini_key and api_key != gemini_key:
            print(f"[Pipeline] Primary provider failed ({e}) — retrying with Gemini")
            initial_state["api_key"] = gemini_key
            final_state = compiled.invoke(initial_state)
        else:
            raise
    print("\n" + "="*55)
    print(f" Done. Report → {final_state['report_path']}")
    print("="*55 + "\n")
    return final_state

if __name__ == "__main__":
    import sys, os
    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <file.py> [API_KEY]")
        sys.exit(1)
    
    # Check for API keys in priority order: Groq > Gemini > Anthropic
    api_key = sys.argv[2] if len(sys.argv) > 2 else (
        os.environ.get("GROQ_API_KEY") 
        or os.environ.get("GEMINI_API_KEY") 
        or os.environ.get("ANTHROPIC_API_KEY"))
    
    if api_key:
        if os.environ.get("GROQ_API_KEY"):
            print("[Pipeline] Using Groq API")
        elif os.environ.get("GEMINI_API_KEY"):
            print("[Pipeline] Using Gemini API")
        elif os.environ.get("ANTHROPIC_API_KEY"):
            print("[Pipeline] Using Anthropic API")
    else:
        print("[Pipeline] No API key found — running in heuristic mode")
    
    run(sys.argv[1], api_key)
