"""
Agent code validation module.
"""

import ast
import logging
import os
from pathlib import Path
from typing import List, Tuple

from executor.config import get_config
from executor.utils import get_dir_size, format_bytes

logger = logging.getLogger(__name__)


class AgentValidator:
    """Validator for agent code before execution."""

    def __init__(self) -> None:
        """Initialize validator with configuration."""
        self.config = get_config()

    def validate_code_directory(self, code_dir: str) -> Tuple[bool, List[str], List[str]]:
        """
        Validate agent code directory or single file.

        Args:
            code_dir: Path to agent code directory or single Python file

        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        errors: List[str] = []
        warnings: List[str] = []

        code_path = Path(code_dir)

        # Check if path exists
        if not code_path.exists():
            errors.append(f"Code path does not exist: {code_dir}")
            return False, errors, warnings

        # If it's a single file, validate only that file
        if code_path.is_file():
            if not str(code_path).endswith('.py'):
                errors.append(f"File is not a Python file: {code_dir}")
                return False, errors, warnings
            
            file_errors, file_warnings = self._validate_python_file(str(code_path))
            errors.extend(file_errors)
            warnings.extend(file_warnings)
            
            is_valid = len(errors) == 0
            return is_valid, errors, warnings

        # If it's a directory, validate all Python files in it
        # Check directory size
        dir_size = get_dir_size(code_dir)
        max_size_bytes = self.config.max_code_size_mb * 1024 * 1024

        if dir_size > max_size_bytes:
            errors.append(
                f"Code directory too large: {format_bytes(dir_size)} "
                f"(max: {format_bytes(max_size_bytes)})"
            )

        # Find Python files
        py_files = list(code_path.rglob("*.py"))

        if not py_files:
            errors.append("No Python files found in code directory")
            return False, errors, warnings

        # Validate each Python file
        for py_file in py_files:
            file_errors, file_warnings = self._validate_python_file(str(py_file))
            errors.extend(file_errors)
            warnings.extend(file_warnings)

        # Check for entry point (agent.py or main.py)
        entry_points = ["agent.py", "main.py", "__init__.py"]
        has_entry = any((code_path / ep).exists() for ep in entry_points)

        if not has_entry:
            warnings.append(
                f"No standard entry point found. Expected one of: {', '.join(entry_points)}"
            )

        is_valid = len(errors) == 0
        return is_valid, errors, warnings

    def _validate_python_file(self, file_path: str) -> Tuple[List[str], List[str]]:
        """
        Validate a single Python file.

        Args:
            file_path: Path to Python file

        Returns:
            Tuple of (errors, warnings)
        """
        errors: List[str] = []
        warnings: List[str] = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Check file size
            if len(content.splitlines()) > self.config.get("validation.max_lines", 5000):
                warnings.append(f"File {file_path} has too many lines")

            # Check for syntax errors
            try:
                tree = ast.parse(content)
            except SyntaxError as e:
                errors.append(f"Syntax error in {file_path}: {e}")
                return errors, warnings

            # Check for forbidden imports and function calls using AST
            forbidden = self.config.forbidden_imports
            if forbidden:
                for node in ast.walk(tree):
                    # Check for function calls like eval(), exec(), etc.
                    if isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Name):
                            func_name = node.func.id
                            if func_name in forbidden:
                                errors.append(
                                    f"Forbidden function call '{func_name}()' found in {file_path}"
                                )
                    
                    # Check for imports like 'import os.system', 'from os import system'
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            if any(f in alias.name for f in forbidden):
                                errors.append(
                                    f"Forbidden import '{alias.name}' found in {file_path}"
                                )
                    
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and any(f in node.module for f in forbidden):
                            errors.append(
                                f"Forbidden import 'from {node.module}' found in {file_path}"
                            )
                        for alias in node.names:
                            if alias.name in forbidden:
                                errors.append(
                                    f"Forbidden import '{alias.name}' from {node.module} found in {file_path}"
                                )

            # Check for potentially dangerous patterns
            dangerous_patterns = [
                ("eval(", "Use of eval() is not recommended"),
                ("exec(", "Use of exec() is not recommended"),
                ("__import__", "Dynamic imports are not recommended"),
                ("open(", "File operations should be carefully reviewed"),
            ]

            for pattern, message in dangerous_patterns:
                if pattern in content:
                    warnings.append(f"{message} in {file_path}")

        except Exception as e:
            errors.append(f"Failed to read file {file_path}: {e}")

        return errors, warnings

    def validate_agent_interface(self, code_dir: str, environment: str) -> Tuple[bool, List[str]]:
        """
        Validate that agent implements required interface.

        Args:
            code_dir: Path to agent code directory
            environment: Target environment name

        Returns:
            Tuple of (is_valid, errors)

        TODO: Implement interface checking by importing agent class
        and verifying it has required methods (act, reset, etc.)
        """
        errors: List[str] = []

        # Basic check: ensure main file exists
        code_path = Path(code_dir)
        main_files = ["agent.py", "main.py"]

        has_main = any((code_path / f).exists() for f in main_files)
        if not has_main:
            errors.append(f"No main agent file found. Expected one of: {', '.join(main_files)}")
            return False, errors

        # TODO: More sophisticated interface validation
        # - Import the agent class
        # - Check for required methods
        # - Validate method signatures
        # - Test basic instantiation

        return len(errors) == 0, errors

    def validate_dependencies(self, code_dir: str) -> Tuple[bool, List[str], List[str]]:
        """
        Validate agent dependencies (requirements.txt).

        Args:
            code_dir: Path to agent code directory

        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        errors: List[str] = []
        warnings: List[str] = []

        code_path = Path(code_dir)
        requirements_file = code_path / "requirements.txt"

        if not requirements_file.exists():
            warnings.append("No requirements.txt found")
            return True, errors, warnings

        try:
            with open(requirements_file, "r") as f:
                requirements = f.read().splitlines()

            # Check for dangerous packages
            dangerous_packages = ["os", "sys", "subprocess"]

            for req in requirements:
                req = req.strip().lower()
                if not req or req.startswith("#"):
                    continue

                # Extract package name
                package_name = req.split("==")[0].split(">=")[0].split("<=")[0].strip()

                if package_name in dangerous_packages:
                    warnings.append(f"Potentially dangerous package: {package_name}")

        except Exception as e:
            errors.append(f"Failed to read requirements.txt: {e}")

        return len(errors) == 0, errors, warnings
