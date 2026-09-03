# Dead Logic Detector

A LangGraph-based agentic pipeline for detecting dead logic in Python code. Finds code that runs but has no real impact, using data flow analysis, symbolic execution, and LLM reasoning.

## Features

- **Data Flow Analysis**: Tracks variable usage and dependencies
- **Symbolic Execution**: Uses Z3 to verify conditions and paths
- **Graph Pruning**: Eliminates unreachable code paths
- **LLM Reasoning**: Groq (primary), with Gemini/Anthropic as fallback, for intelligent verdicts
- **Agentic Workflow**: Looping logic with confidence gates
- **Comprehensive Reporting**: HTML reports with annotations

## Installation

```bash
pip install -r requirements.txt
```

## Setup

Set your API key. Groq is checked first; if unset, the pipeline falls back to Gemini, then Anthropic:
```bash
export GROQ_API_KEY=your_key_here
# or
export GEMINI_API_KEY=your_key_here
# or
export ANTHROPIC_API_KEY=your_key_here
```

## Usage

```python
from pipeline import run

# Run on a file
result = run("your_file.py", api_key="your_key")
print(f"Report: {result['report_path']}")
```

## Pipeline Agents

1. **Parser**: AST parsing with Tree-Sitter
2. **Branch Detector**: Finds impossible conditions
3. **Tracer**: Data flow graph + dead variable detection
4. **Reasoner**: LLM verdicts with retry logic
5. **Reporter**: HTML report generation

## Datasets

All test/dataset files live in `test_data/`:
- `toy_dataset1.py`, `toy_dataset2.py`: Simple test cases
- `negative_tests.py`, `test_hard_negatives.py`: Code that looks dead but isn't
- `sample_target.py`, `large_file.py`, `all_test_cases.py`, `test_1.py`: Complex/aggregate examples

## Benchmarking

Compares results against Pylint and Vulture on a target file:
```bash
python benchmark.py test_data/sample_target.py
```

## Architecture

- **LangGraph**: Orchestrates the agent workflow
- **Tree-Sitter**: AST parsing
- **NetworkX**: Data flow graphs
- **Z3**: Symbolic execution
- **Groq / Google GenAI / Anthropic**: LLM reasoning
