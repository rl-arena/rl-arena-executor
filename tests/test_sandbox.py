"""
Tests for sandbox execution.
"""

import pytest
import tempfile
import os
from pathlib import Path

from executor.sandbox import Sandbox
from executor.config import Config, set_config


@pytest.fixture
def config():
    """Create test configuration."""
    config = Config()
    set_config(config)
    return config


@pytest.fixture
def sandbox(config):
    """Create sandbox instance."""
    return Sandbox()


def test_sandbox_initialization(sandbox):
    """Test sandbox initializes correctly."""
    assert sandbox is not None
    assert sandbox.config is not None


def test_prepare_agent_code_directory(sandbox):
    """Test preparing agent code from directory."""
    # Create temporary directory with test code
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "agent.py"
        test_file.write_text("def act(obs): return 0")

        # Prepare agent code
        agent_dir = sandbox.prepare_agent_code(tmpdir, "test_agent")

        # Verify agent directory was created
        assert os.path.exists(agent_dir)
        assert os.path.isdir(agent_dir)

        # Verify files were copied
        copied_file = Path(agent_dir) / "agent.py"
        assert copied_file.exists()

        # Cleanup
        sandbox.cleanup_agent("test_agent")
        assert not os.path.exists(agent_dir)


def test_prepare_agent_code_invalid_source(sandbox):
    """Test preparing agent code fails with invalid source."""
    with pytest.raises(RuntimeError):
        sandbox.prepare_agent_code("/nonexistent/path", "test_agent")


def test_cleanup_agent(sandbox):
    """Test agent cleanup."""
    # Create temporary agent directory
    agent_id = "test_agent_cleanup"
    agent_dir = os.path.join(sandbox.config.tmp_dir, agent_id)
    os.makedirs(agent_dir, exist_ok=True)

    # Create a test file
    test_file = Path(agent_dir) / "test.txt"
    test_file.write_text("test")

    # Verify directory exists
    assert os.path.exists(agent_dir)

    # Cleanup
    sandbox.cleanup_agent(agent_id)

    # Verify directory was removed
    assert not os.path.exists(agent_dir)


def test_sandbox_context_manager(config):
    """Test sandbox can be used as context manager."""
    with Sandbox() as sandbox:
        assert sandbox is not None
        assert sandbox.config is not None


@pytest.mark.asyncio
async def test_run_agent_action_not_implemented(sandbox):
    """Test that run_agent_action raises NotImplementedError."""
    with pytest.raises(NotImplementedError):
        await sandbox.run_agent_action(
            agent_dir="/tmp/test",
            agent_id="test_agent",
            observation={"state": [0, 0]},
            timeout=5,
        )
