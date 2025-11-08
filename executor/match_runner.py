"""
Match runner module for executing RL agent matches.
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import rl_arena

from executor.config import get_config
from executor.replay_recorder import ReplayRecorder
from executor.sandbox import Sandbox
from executor.validation import AgentValidator

try:
    from executor.redis_semaphore import RedisSemaphore
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)


class MatchResult:
    """Result of a match execution."""

    def __init__(
        self,
        match_id: str,
        status: str,
        winner_agent_id: Optional[str] = None,
        agent_results: Optional[Dict[str, Dict[str, Any]]] = None,
        replay_url: Optional[str] = None,
        replay_html_url: Optional[str] = None,  # HTML replay URL
        error_message: Optional[str] = None,
        total_steps: int = 0,
        execution_time: float = 0.0,
    ) -> None:
        """Initialize match result."""
        self.match_id = match_id
        self.status = status
        self.winner_agent_id = winner_agent_id
        self.agent_results = agent_results or {}
        self.replay_url = replay_url
        self.replay_html_url = replay_html_url
        self.error_message = error_message
        self.total_steps = total_steps
        self.execution_time = execution_time


class MatchRunner:
    """Manages execution of matches between agents."""

    def __init__(self, redis_url: Optional[str] = None, max_concurrent_matches: int = 10) -> None:
        """
        Initialize match runner.
        
        Args:
            redis_url: Redis URL for distributed semaphore (None = no limit)
            max_concurrent_matches: Maximum concurrent matches (default: 10)
        """
        self.config = get_config()
        self.validator = AgentValidator()
        self.sandbox = Sandbox()
        self.active_matches: Dict[str, bool] = {}
        
        # Redis semaphore for concurrency control
        self.semaphore: Optional[RedisSemaphore] = None
        if redis_url and REDIS_AVAILABLE:
            self.semaphore = RedisSemaphore(
                redis_url=redis_url,
                key="executor:concurrent_matches",
                max_concurrent=max_concurrent_matches,
                timeout_sec=600,  # 10 minutes timeout
            )
            logger.info(
                f"Concurrency control enabled: max {max_concurrent_matches} matches"
            )
        elif redis_url and not REDIS_AVAILABLE:
            logger.warning("Redis URL provided but redis library not available")
        else:
            logger.info("No concurrency limit (Redis not configured)")

    async def run_match(
        self,
        match_id: str,
        environment_name: str,
        agents: List[Dict[str, str]],
        timeout_sec: Optional[int] = None,
        record_replay: bool = True,
    ) -> MatchResult:
        """
        Run a match between agents.

        Args:
            match_id: Unique match identifier
            environment_name: Name of the environment (e.g., "pong")
            agents: List of agent data dicts with keys: agent_id, code_url, version
            timeout_sec: Match timeout in seconds
            record_replay: Whether to record replay data

        Returns:
            MatchResult with match outcome

        Raises:
            ValueError: If invalid parameters
            RuntimeError: If match execution fails
        """
        # Acquire semaphore slot (if enabled)
        semaphore_acquired = False
        if self.semaphore:
            logger.info(f"Waiting for semaphore slot for match {match_id}...")
            semaphore_acquired = await self.semaphore.acquire(timeout_sec=30)
            
            if not semaphore_acquired:
                logger.error(
                    f"Failed to acquire semaphore for match {match_id} "
                    f"(all {self.semaphore.max_concurrent} slots busy)"
                )
                return MatchResult(
                    match_id=match_id,
                    status="queued_timeout",
                    error_message="Failed to acquire execution slot (system busy)",
                    execution_time=0.0,
                )
            
            available = await self.semaphore.get_available_slots()
            logger.info(
                f"Semaphore acquired for match {match_id} "
                f"({available} slots remaining)"
            )

        start_time = time.time()

        if timeout_sec is None:
            timeout_sec = self.config.match_timeout_sec

        logger.info(f"Starting match {match_id} in environment {environment_name}")
        self.active_matches[match_id] = True

        try:
            # Validate inputs
            if len(agents) < 2:
                raise ValueError("At least 2 agents required for a match")

            # Create environment
            try:
                env = rl_arena.make(environment_name)
                logger.info(f"Created environment: {environment_name}")
            except Exception as e:
                raise RuntimeError(f"Failed to create environment: {e}")

            # Initialize replay recorder
            recorder = None
            if record_replay:
                recorder = ReplayRecorder(match_id, environment_name, agents)

            # Prepare agents
            agent_dirs = {}
            for agent in agents:
                agent_id = agent["agent_id"]
                code_url = agent["code_url"]

                # Check if code_url is a Docker image (contains ":" and starts with registry)
                is_docker_image = ":" in code_url and "/" in code_url and not code_url.startswith("/")
                
                if is_docker_image:
                    # Docker image - skip validation and use image directly
                    logger.info(f"Agent {agent_id} uses Docker image: {code_url}")
                    agent_dirs[agent_id] = code_url  # Store Docker image URL
                else:
                    # Local code - validate and prepare
                    logger.info(f"Validating agent {agent_id}")
                    # TODO: Download code from URL if needed
                    # For now, assume code_url is a local path

                    is_valid, errors, warnings = self.validator.validate_code_directory(code_url)
                    if not is_valid:
                        raise ValueError(f"Agent {agent_id} validation failed: {errors}")

                    if warnings:
                        logger.warning(f"Agent {agent_id} warnings: {warnings}")

                    # Prepare agent code
                    agent_dir = self.sandbox.prepare_agent_code(code_url, agent_id)
                    agent_dirs[agent_id] = agent_dir

            # Run match with timeout
            try:
                result = await asyncio.wait_for(
                    self._execute_match(match_id, env, agents, agent_dirs, recorder),
                    timeout=timeout_sec,
                )
            except asyncio.TimeoutError:
                logger.error(f"Match {match_id} timed out after {timeout_sec}s")
                result = MatchResult(
                    match_id=match_id,
                    status="timeout",
                    error_message=f"Match exceeded timeout of {timeout_sec}s",
                    execution_time=time.time() - start_time,
                )

            # Finalize replay
            if recorder and result.status == "success":
                recorder.finalize(winner=result.winner_agent_id, status="completed")
                replay_paths = recorder.save(save_html=True)  # Save both JSON and HTML
                
                # Convert absolute paths to relative paths for Backend storage
                # Backend expects paths relative to storage/ directory (e.g., "replays/match_id.json")
                json_path = replay_paths.get("json")
                html_path = replay_paths.get("html")
                
                if json_path:
                    # Extract just the filename and prepend "replays/"
                    result.replay_url = f"replays/{Path(json_path).name}"
                if html_path:
                    result.replay_html_url = f"replays/{Path(html_path).name}"
                
                logger.info(f"Replay saved: JSON={result.replay_url}, HTML={result.replay_html_url}")

            # Cleanup
            for agent_id in agent_dirs:
                self.sandbox.cleanup_agent(agent_id)

            execution_time = time.time() - start_time
            result.execution_time = execution_time

            logger.info(
                f"Match {match_id} completed: {result.status}, "
                f"winner: {result.winner_agent_id}, time: {execution_time:.2f}s"
            )

            return result

        except Exception as e:
            logger.error(f"Match {match_id} failed: {e}", exc_info=True)
            return MatchResult(
                match_id=match_id,
                status="error",
                error_message=str(e),
                execution_time=time.time() - start_time,
            )

        finally:
            self.active_matches.pop(match_id, None)
            
            # Release semaphore slot
            if semaphore_acquired and self.semaphore:
                await self.semaphore.release()
                available = await self.semaphore.get_available_slots()
                logger.info(
                    f"Semaphore released for match {match_id} "
                    f"({available + 1} slots now available)"
                )

    async def _execute_match(
        self,
        match_id: str,
        env: Any,
        agents: List[Dict[str, str]],
        agent_dirs: Dict[str, str],
        recorder: Optional[ReplayRecorder] = None,
    ) -> MatchResult:
        """
        Execute the actual match loop.

        Args:
            match_id: Match identifier
            env: Environment instance
            agents: Agent metadata
            agent_dirs: Mapping of agent_id to code directory
            recorder: Replay recorder instance

        Returns:
            MatchResult
        """
        import sys
        import importlib.util
        from pathlib import Path
        
        agent_ids = [agent["agent_id"] for agent in agents]

        # Reset environment (returns observations list and info dict)
        observations, reset_info = env.reset()

        # Initialize agent results
        agent_results = {
            agent_id: {"score": 0.0, "errors": 0, "error_message": ""}
            for agent_id in agent_ids
        }

        # Load agent instances
        agent_instances = {}
        for i, agent_id in enumerate(agent_ids):
            agent_dir = agent_dirs[agent_id]
            
            try:
                # Find agent.py or main.py
                agent_path = Path(agent_dir)
                agent_file = None
                
                if (agent_path / "agent.py").exists():
                    agent_file = agent_path / "agent.py"
                elif (agent_path / "main.py").exists():
                    agent_file = agent_path / "main.py"
                else:
                    # Single .py file case
                    py_files = list(agent_path.glob("*.py"))
                    if py_files:
                        agent_file = py_files[0]
                
                if not agent_file:
                    raise FileNotFoundError(f"No Python file found in {agent_dir}")
                
                # Load module dynamically
                spec = importlib.util.spec_from_file_location(f"agent_{agent_id}", agent_file)
                if spec is None or spec.loader is None:
                    raise ImportError(f"Failed to load spec from {agent_file}")
                
                module = importlib.util.module_from_spec(spec)
                sys.modules[f"agent_{agent_id}"] = module
                spec.loader.exec_module(module)
                
                # Try to create agent instance
                if hasattr(module, "create_agent"):
                    agent_instances[agent_id] = module.create_agent(player_id=i)
                    logger.info(f"Loaded agent {agent_id} using create_agent() factory")
                elif hasattr(module, "Agent"):
                    agent_instances[agent_id] = module.Agent(player_id=i)
                    logger.info(f"Loaded agent {agent_id} using Agent class")
                else:
                    raise AttributeError(f"No create_agent() function or Agent class found in {agent_file}")
                
            except Exception as e:
                logger.error(f"Failed to load agent {agent_id}: {e}")
                return MatchResult(
                    match_id=match_id,
                    status="error",
                    error_message=f"Failed to load agent {agent_id}: {e}",
                    total_steps=0,
                )

        done = False
        step_count = 0
        max_steps = self.config.get("resource_limits.max_steps_per_match", 10000)

        while not done and step_count < max_steps:
            # Check if match was cancelled
            if not self.active_matches.get(match_id, False):
                logger.warning(f"Match {match_id} was cancelled")
                break

            # Get actions from agents (as list, not dict)
            actions = []
            for i, agent_id in enumerate(agent_ids):
                try:
                    agent_instance = agent_instances[agent_id]
                    observation = observations[i] if isinstance(observations, list) else observations
                    
                    # Call agent's action method
                    if hasattr(agent_instance, "act"):
                        action = agent_instance.act(observation)
                    elif hasattr(agent_instance, "get_action"):
                        action = agent_instance.get_action(observation)
                    elif hasattr(agent_instance, "predict"):
                        action = agent_instance.predict(observation)
                    else:
                        raise AttributeError(f"Agent has no act(), get_action(), or predict() method")
                    
                    actions.append(action)
                    
                except Exception as e:
                    logger.error(f"Agent {agent_id} failed to produce action: {e}")
                    agent_results[agent_id]["errors"] += 1
                    agent_results[agent_id]["error_message"] = str(e)
                    # Use random action as fallback
                    actions.append(env.action_space.sample())

            # Step environment
            try:
                observations, rewards, terminated, truncated, info = env.step(actions)
                done = terminated or truncated

                # Update scores (rewards is a list, not dict)
                for i, agent_id in enumerate(agent_ids):
                    agent_results[agent_id]["score"] += rewards[i]

                # Record frame
                if recorder:
                    # Convert actions/observations/rewards lists to dicts for recorder
                    actions_dict = {agent_ids[i]: actions[i] for i in range(len(actions))}
                    observations_dict = {agent_ids[i]: observations[i] for i in range(len(observations))}
                    rewards_dict = {agent_ids[i]: rewards[i] for i in range(len(rewards))}
                    
                    recorder.record_frame(
                        frame_number=step_count,
                        observations=observations_dict,
                        actions=actions_dict,
                        rewards=rewards_dict,
                        done=done,
                        info=info,
                    )

                step_count += 1

            except Exception as e:
                logger.error(f"Environment step failed: {e}")
                return MatchResult(
                    match_id=match_id,
                    status="error",
                    error_message=f"Environment error: {e}",
                    total_steps=step_count,
                )

        # Determine winner
        winner_agent_id = max(agent_results.items(), key=lambda x: x[1]["score"])[0]

        # Check for draw
        scores = [result["score"] for result in agent_results.values()]
        if len(set(scores)) == 1:  # All scores are equal
            winner_agent_id = None  # Draw

        return MatchResult(
            match_id=match_id,
            status="success",
            winner_agent_id=winner_agent_id,
            agent_results=agent_results,
            total_steps=step_count,
        )

    def cancel_match(self, match_id: str) -> bool:
        """
        Cancel a running match.

        Args:
            match_id: Match identifier

        Returns:
            True if match was cancelled, False if not found
        """
        if match_id in self.active_matches:
            self.active_matches[match_id] = False
            logger.info(f"Cancelled match {match_id}")
            return True
        return False

    def get_active_matches(self) -> List[str]:
        """
        Get list of active match IDs.

        Returns:
            List of active match IDs
        """
        return [mid for mid, active in self.active_matches.items() if active]
