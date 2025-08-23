"""Test to ensure no print statements in library code."""

import ast
from pathlib import Path

import pytest


def test_no_print_in_library():
    """Ensure no print() statements exist in library code (only logging)."""
    lib_dir = Path(__file__).parent.parent / 'src' / 'swingtrading'
    
    # Files that are allowed to use console output
    exclude_files = ['main.py', 'reporter.py']
    
    violations = []
    
    for py_file in lib_dir.glob('*.py'):
        if py_file.name in exclude_files:
            continue
        
        if not py_file.exists():
            continue
            
        with open(py_file, 'r') as f:
            try:
                content = f.read()
                tree = ast.parse(content)
            except SyntaxError:
                continue
        
        # Walk the AST looking for print calls
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check for print function calls
                if hasattr(node.func, 'id') and node.func.id == 'print':
                    violations.append((py_file.name, node.lineno))
    
    if violations:
        msg = "Found print() statements in library code:\n"
        for filename, lineno in violations:
            msg += f"  - {filename}:{lineno}\n"
        pytest.fail(msg)