"""
Sandbox execution module for running agent code in isolated environments.
"""

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import docker
from docker.errors import DockerException

from executor.config import get_config
from executor.utils import extract_zip, safe_remove_dir

logger = logging.getLogger(__name__)


class Sandbox:
    """Secure sandbox for executing agent code."""

    def __init__(self) -> None:
        """Initialize sandbox with configuration."""
        self.config = get_config()
        self.docker_client: Optional[docker.DockerClient] = None

        if self.config.use_docker:
            try:
                self.docker_client = docker.from_env()
                logger.info("Docker client initialized successfully")
            except DockerException as e:
                logger.error(f"Failed to initialize Docker client: {e}")
                logger.warning("Falling back to local execution")

    def prepare_agent_code(
        self, code_source: str, agent_id: str, is_zip: bool = False
    ) -> str:
        """
        Prepare agent code for execution.

        Args:
            code_source: Path to code directory or zip file bytes
            agent_id: Agent identifier
            is_zip: Whether code_source is a zip file

        Returns:
            Path to prepared code directory

        Raises:
            RuntimeError: If preparation fails
        """
        # Create agent-specific directory
        agent_dir = os.path.join(self.config.tmp_dir, agent_id)
        os.makedirs(agent_dir, exist_ok=True)

        try:
            if is_zip:
                # Extract zip to agent directory
                extract_zip(code_source, agent_dir)
            else:
                # Copy directory contents
                if os.path.isdir(code_source):
                    shutil.copytree(code_source, agent_dir, dirs_exist_ok=True)
                else:
                    raise ValueError(f"Invalid code source: {code_source}")

            logger.info(f"Prepared agent code for {agent_id} at {agent_dir}")
            return agent_dir

        except Exception as e:
            safe_remove_dir(agent_dir)
            raise RuntimeError(f"Failed to prepare agent code: {e}")

    async def run_agent_action(
        self,
        agent_dir: str,
        agent_id: str,
        observation: Any,
        timeout: Optional[int] = None,
    ) -> Any:
        """
        Run agent to get action for observation.

        Args:
            agent_dir: Path to agent code directory
            agent_id: Agent identifier
            observation: Environment observation
            timeout: Execution timeout in seconds

        Returns:
            Action from agent

        Raises:
            TimeoutError: If execution times out
            RuntimeError: If execution fails
        """
        if timeout is None:
            timeout = self.config.step_timeout_sec

        try:
            if self.docker_client and self.config.use_docker:
                return await self._run_in_docker(agent_dir, agent_id, observation, timeout)
            else:
                return await self._run_locally(agent_dir, agent_id, observation, timeout)

        except asyncio.TimeoutError:
            raise TimeoutError(f"Agent {agent_id} execution timed out after {timeout}s")
        except Exception as e:
            raise RuntimeError(f"Agent {agent_id} execution failed: {e}")

    async def _run_in_docker(
        self, agent_dir: str, agent_id: str, observation: Any, timeout: int
    ) -> Any:
        """
        Run agent in Docker container.

        Args:
            agent_dir: Path to agent code directory
            agent_id: Agent identifier
            observation: Environment observation
            timeout: Execution timeout

        Returns:
            Action from agent

        TODO: Implement Docker container execution with proper resource limits
        """
        if not self.docker_client:
            raise RuntimeError("Docker client not available")

        # TODO: Implement Docker execution
        # 1. Create container with resource limits
        # 2. Mount agent code as volume
        # 3. Pass observation via stdin or temp file
        # 4. Execute agent script
        # 5. Capture output (action)
        # 6. Clean up container

        logger.warning("Docker execution not fully implemented, falling back to local")
        return await self._run_locally(agent_dir, agent_id, observation, timeout)

    async def _run_locally(
        self, agent_dir: str, agent_id: str, observation: Any, timeout: int
    ) -> Any:
        """
        Run agent locally (without Docker).

        Args:
            agent_dir: Path to agent code directory
            agent_id: Agent identifier
            observation: Environment observation
            timeout: Execution timeout

        Returns:
            Action from agent

        Note: This is less secure than Docker execution
        """
        # TODO: Implement local execution with process isolation
        # 1. Create subprocess with resource limits
        # 2. Set up IPC (stdin/stdout or socket)
        # 3. Send observation
        # 4. Receive action
        # 5. Handle timeout

        # Placeholder implementation
        logger.warning("Local execution not fully implemented")
        raise NotImplementedError("Local agent execution not yet implemented")

    def cleanup_agent(self, agent_id: str) -> None:
        """
        Clean up agent resources.

        Args:
            agent_id: Agent identifier
        """
        agent_dir = os.path.join(self.config.tmp_dir, agent_id)
        safe_remove_dir(agent_dir)
        logger.debug(f"Cleaned up agent {agent_id}")

    def __enter__(self) -> "Sandbox":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        if self.docker_client:
            self.docker_client.close()


class AgentProcess:
    """
    Manages a persistent agent process for multiple action queries.

    This allows keeping the agent loaded in memory across multiple steps,
    which is more efficient than creating a new process for each action.
    """

    def __init__(self, agent_dir: str, agent_id: str, sandbox: Sandbox) -> None:
        """
        Initialize agent process.

        Args:
            agent_dir: Path to agent code directory
            agent_id: Agent identifier
            sandbox: Sandbox instance
        """
        self.agent_dir = agent_dir
        self.agent_id = agent_id
        self.sandbox = sandbox
        self.process: Optional[subprocess.Popen] = None

    async def start(self) -> None:
        """
        Start the agent process.

        TODO: Implement process startup with proper IPC setup
        """
        logger.info(f"Starting agent process for {self.agent_id}")
        # TODO: Start subprocess and set up communication channel
        raise NotImplementedError("AgentProcess.start() not yet implemented")

    async def get_action(self, observation: Any, timeout: int) -> Any:
        """
        Get action from agent for given observation.

        Args:
            observation: Environment observation
            timeout: Timeout in seconds

        Returns:
            Action from agent
        """
        if not self.process:
            raise RuntimeError("Agent process not started")

        # TODO: Send observation and receive action via IPC
        raise NotImplementedError("AgentProcess.get_action() not yet implemented")

    async def reset(self) -> None:
        """Reset agent state."""
        # TODO: Send reset signal to agent
        pass

    async def stop(self) -> None:
        """Stop the agent process."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            logger.info(f"Stopped agent process for {self.agent_id}")
