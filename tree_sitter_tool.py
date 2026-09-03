"""
tree_sitter_tool.py — Tree-Sitter Tool Wrapper
Provides enhanced AST parsing utilities for the Dead Logic Detector.
"""

import tree_sitter_python as tsp
from tree_sitter import Language, Parser
from typing import Dict, List, Any

PY_LANGUAGE = Language(tsp.language())
_parser = Parser(PY_LANGUAGE)

class TreeSitterTool:
    def __init__(self):
        self.parser = _parser
    
    def parse_code(self, code: str) -> Dict[str, Any]:
        """Parse code and return enhanced AST info."""
        tree = self.parser.parse(code.encode('utf-8'))
        root = tree.root_node
        
        return {
            'tree': tree,
            'root': root,
            'functions': self._extract_functions(root, code),
            'variables': self._extract_variables(root, code),
            'conditions': self._extract_conditions(root, code)
        }
    
    def _extract_functions(self, root, code: str) -> List[Dict]:
        functions = []
        for node in self._walk(root):
            if node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = code[name_node.start_byte:name_node.end_byte].decode('utf-8')
                    functions.append({
                        'name': name,
                        'line': node.start_point[0] + 1,
                        'body': code[node.start_byte:node.end_byte].decode('utf-8')
                    })
        return functions
    
    def _extract_variables(self, root, code: str) -> List[Dict]:
        variables = []
        for node in self._walk(root):
            if node.type in ("assignment", "augmented_assignment"):
                left = node.child_by_field_name("left")
                right = node.child_by_field_name("right")
                if left and right:
                    var_name = code[left.start_byte:left.end_byte].decode('utf-8')
                    value = code[right.start_byte:right.end_byte].decode('utf-8')
                    variables.append({
                        'name': var_name,
                        'value': value,
                        'line': node.start_point[0] + 1
                    })
        return variables
    
    def _extract_conditions(self, root, code: str) -> List[Dict]:
        conditions = []
        for node in self._walk(root):
            if node.type == "if_statement":
                cond = node.child_by_field_name("condition")
                if cond:
                    cond_text = code[cond.start_byte:cond.end_byte].decode('utf-8')
                    conditions.append({
                        'condition': cond_text,
                        'line': node.start_point[0] + 1
                    })
        return conditions
    
    def _walk(self, node):
        yield node
        for child in node.children:
            yield from self._walk(child)