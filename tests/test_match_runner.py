"""
Tests for match runner.
"""

import pytest
import asyncio

from executor.match_runner import MatchRunner, MatchResult
from executor.config import Config, set_config


@pytest.fixture
def config():
    """Create test configuration."""
    config = Config()
    set_config(config)
    return config


@pytest.fixture
def match_runner(config):
    """Create match runner instance."""
    return MatchRunner()


@pytest.mark.asyncio
async def test_match_runner_initialization(match_runner):
    """Test match runner initializes correctly."""
    assert match_runner is not None
    assert match_runner.config is not None
    assert match_runner.validator is not None
    assert match_runner.sandbox is not None


@pytest.mark.asyncio
async def test_run_match_invalid_agents(match_runner):
    """Test match fails with invalid number of agents."""
    result = await match_runner.run_match(
        match_id="test_match_1",
        environment_name="pong",
        agents=[{"agent_id": "agent1", "code_url": "/tmp/agent1", "version": "1.0"}],
        timeout_sec=10,
        record_replay=False,
    )

    assert result.status == "error"
    assert "at least 2 agents" in result.error_message.lower()


@pytest.mark.asyncio
async def test_run_match_invalid_environment(match_runner):
    """Test match fails with invalid environment."""
    result = await match_runner.run_match(
        match_id="test_match_2",
        environment_name="nonexistent_env",
        agents=[
            {"agent_id": "agent1", "code_url": "/tmp/agent1", "version": "1.0"},
            {"agent_id": "agent2", "code_url": "/tmp/agent2", "version": "1.0"},
        ],
        timeout_sec=10,
        record_replay=False,
    )

    assert result.status == "error"
    assert "environment" in result.error_message.lower()


def test_cancel_match(match_runner):
    """Test match cancellation."""
    match_id = "test_match_3"

    # Add match to active matches
    match_runner.active_matches[match_id] = True

    # Cancel match
    cancelled = match_runner.cancel_match(match_id)
    assert cancelled is True
    assert match_runner.active_matches[match_id] is False

    # Try to cancel non-existent match
    cancelled = match_runner.cancel_match("nonexistent_match")
    assert cancelled is False


def test_get_active_matches(match_runner):
    """Test getting active matches."""
    match_runner.active_matches["match1"] = True
    match_runner.active_matches["match2"] = True
    match_runner.active_matches["match3"] = False

    active = match_runner.get_active_matches()
    assert len(active) == 2
    assert "match1" in active
    assert "match2" in active
    assert "match3" not in active


@pytest.mark.asyncio
async def test_match_result():
    """Test MatchResult creation."""
    result = MatchResult(
        match_id="test_match",
        status="success",
        winner_agent_id="agent1",
        total_steps=100,
        execution_time=5.5,
    )

    assert result.match_id == "test_match"
    assert result.status == "success"
    assert result.winner_agent_id == "agent1"
    assert result.total_steps == 100
    assert result.execution_time == 5.5
