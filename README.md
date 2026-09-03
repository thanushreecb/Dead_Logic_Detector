# Dead Logic Detector

A LangGraph-based agentic pipeline for detecting dead logic in Python code. Finds code that runs but has no real impact, using data flow analysis, symbolic execution, and LLM reasoning.

## Features

- **Data Flow Analysis**: Tracks variable usage and dependencies
- **Symbolic Execution**: Uses Z3 to verify conditions and paths
- **Graph Pruning**: Eliminates unreachable code paths
- **LLM Reasoning**: Gemini/Claude for intelligent verdicts
- **Agentic Workflow**: Looping logic with confidence gates
- **Comprehensive Reporting**: HTML reports with annotations

## Installation

```bash
pip install -r requirements.txt
```

## Setup

Set your API key:
```bash
export GEMINI_API_KEY=your_key_here
# or
export GEMINI_API_KEY=your_key_here

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

- `toy_dataset*.py`: Simple test cases
- `negative_tests.py`: Code that looks dead but isn't
- `sample_target.py`: Complex examples

## Benchmarking

```bash
python benchmark.py
```

## Architecture

- **LangGraph**: Orchestrates the agent workflow
- **Tree-Sitter**: AST parsing
- **NetworkX**: Data flow graphs
- **Z3**: Symbolic execution
- **Google GenAI/Anthropic**: LLM reasoning
