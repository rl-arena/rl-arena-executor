"""
Tests for agent validation.
"""

import pytest
import tempfile
from pathlib import Path

from executor.validation import AgentValidator
from executor.config import Config, set_config


@pytest.fixture
def config():
    """Create test configuration."""
    config = Config()
    set_config(config)
    return config


@pytest.fixture
def validator(config):
    """Create validator instance."""
    return AgentValidator()


def test_validator_initialization(validator):
    """Test validator initializes correctly."""
    assert validator is not None
    assert validator.config is not None


def test_validate_nonexistent_directory(validator):
    """Test validation fails for nonexistent directory."""
    is_valid, errors, warnings = validator.validate_code_directory("/nonexistent/path")

    assert is_valid is False
    assert len(errors) > 0
    assert "does not exist" in errors[0].lower()


def test_validate_empty_directory(validator):
    """Test validation fails for directory without Python files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        is_valid, errors, warnings = validator.validate_code_directory(tmpdir)

        assert is_valid is False
        assert any("no python files" in err.lower() for err in errors)


def test_validate_valid_agent_code(validator):
    """Test validation passes for valid agent code."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create valid Python file
        agent_file = Path(tmpdir) / "agent.py"
        agent_file.write_text("""
def act(observation):
    return 0

class Agent:
    def __init__(self):
        pass

    def reset(self):
        pass

    def act(self, obs):
        return 0
""")

        is_valid, errors, warnings = validator.validate_code_directory(tmpdir)

        assert is_valid is True
        assert len(errors) == 0


def test_validate_syntax_error(validator):
    """Test validation fails for Python file with syntax error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create file with syntax error
        agent_file = Path(tmpdir) / "agent.py"
        agent_file.write_text("""
def act(observation)
    return 0
""")

        is_valid, errors, warnings = validator.validate_code_directory(tmpdir)

        assert is_valid is False
        assert any("syntax error" in err.lower() for err in errors)


def test_validate_forbidden_imports(validator):
    """Test validation fails for forbidden imports."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create file with forbidden import
        agent_file = Path(tmpdir) / "agent.py"
        agent_file.write_text("""
import os
os.system("echo hello")

def act(observation):
    return 0
""")

        is_valid, errors, warnings = validator.validate_code_directory(tmpdir)

        # Should have errors or warnings about forbidden imports
        assert is_valid is False or len(warnings) > 0


def test_validate_dangerous_patterns(validator):
    """Test validation warns about dangerous patterns."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create file with dangerous patterns
        agent_file = Path(tmpdir) / "agent.py"
        agent_file.write_text("""
def act(observation):
    result = eval("1 + 1")
    return result
""")

        is_valid, errors, warnings = validator.validate_code_directory(tmpdir)

        # Should have warnings about eval
        assert len(warnings) > 0
        assert any("eval" in warn.lower() for warn in warnings)


def test_validate_dependencies(validator):
    """Test validation of requirements.txt."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create requirements file
        req_file = Path(tmpdir) / "requirements.txt"
        req_file.write_text("""
numpy==1.24.0
pandas>=1.5.0
rl-arena
""")

        # Also need at least one Python file
        agent_file = Path(tmpdir) / "agent.py"
        agent_file.write_text("def act(obs): return 0")

        is_valid, errors, warnings = validator.validate_dependencies(tmpdir)

        assert is_valid is True
        assert len(errors) == 0


def test_validate_no_entry_point(validator):
    """Test validation warns about missing entry point."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create Python file with non-standard name
        random_file = Path(tmpdir) / "utils.py"
        random_file.write_text("def helper(): pass")

        is_valid, errors, warnings = validator.validate_code_directory(tmpdir)

        # Should warn about missing entry point
        assert any("entry point" in warn.lower() for warn in warnings)
