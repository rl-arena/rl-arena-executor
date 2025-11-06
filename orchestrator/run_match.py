"""
Match orchestrator that runs inside Kubernetes pod.
Loads agents and executes the match.
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

import rl_arena

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class MatchOrchestrator:
    """Orchestrates match execution within a K8s pod."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize orchestrator with match config."""
        self.config = config
        self.match_id = config["match_id"]
        self.environment = config["environment"]
        self.agents = config["agents"]
        self.timeout_sec = config.get("timeout_sec", 300)
        self.record_replay = config.get("record_replay", True)

        # Paths
        self.agent_code_dir = Path("/agent-code")
        self.replay_dir = Path("/replays")

    async def run_match(self) -> Dict[str, Any]:
        """
        Execute the match and return results.

        Returns:
            Match result dictionary
        """
        logger.info(f"Starting match {self.match_id} in environment {self.environment}")

        try:
            # Create environment
            env = rl_arena.make(self.environment)
            logger.info(f"Created environment: {self.environment}")

            # Initialize agents
            agent_modules = []
            for i, agent_data in enumerate(self.agents):
                agent_id = agent_data["agent_id"]
                agent_path = self.agent_code_dir / f"agent-{i+1}"
                
                logger.info(f"Loading agent {agent_id} from {agent_path}")
                
                # Add agent path to sys.path
                sys.path.insert(0, str(agent_path))
                
                try:
                    # Try to import agent module
                    if (agent_path / "agent.py").exists():
                        import agent as agent_module
                    elif (agent_path / "main.py").exists():
                        import main as agent_module
                    else:
                        raise ImportError("No agent.py or main.py found")
                    
                    agent_modules.append(agent_module)
                    logger.info(f"Successfully loaded agent {agent_id}")
                    
                except Exception as e:
                    logger.error(f"Failed to load agent {agent_id}: {e}")
                    return {
                        "match_id": self.match_id,
                        "status": "error",
                        "error_message": f"Failed to load agent {agent_id}: {e}",
                    }

            # Run match
            result = await self._execute_match_loop(env, agent_modules)
            
            logger.info(f"Match {self.match_id} completed: {result['status']}")
            return result

        except Exception as e:
            logger.error(f"Match execution failed: {e}", exc_info=True)
            return {
                "match_id": self.match_id,
                "status": "error",
                "error_message": str(e),
            }

    async def _execute_match_loop(
        self, env: Any, agent_modules: List[Any]
    ) -> Dict[str, Any]:
        """
        Execute the main match loop.

        Args:
            env: RL Arena environment
            agent_modules: Loaded agent modules

        Returns:
            Match result
        """
        observations = env.reset()
        done = False
        step_count = 0
        max_steps = self.timeout_sec * 10  # Approximate max steps

        agent_scores = [0.0, 0.0]
        agent_errors = [0, 0]
        replay_frames = []

        logger.info("Starting match loop")

        try:
            while not done and step_count < max_steps:
                step_count += 1

                # Get actions from both agents
                actions = []
                for i, agent_module in enumerate(agent_modules):
                    try:
                        # Call agent's get_action method
                        if hasattr(agent_module, "get_action"):
                            action = agent_module.get_action(observations[i])
                        elif hasattr(agent_module, "Agent"):
                            # Agent class
                            agent_instance = agent_module.Agent()
                            action = agent_instance.get_action(observations[i])
                        else:
                            raise AttributeError("No get_action method or Agent class")
                        
                        actions.append(action)
                    except Exception as e:
                        logger.error(f"Agent {i+1} action error: {e}")
                        agent_errors[i] += 1
                        # Use random action as fallback
                        actions.append(env.action_space.sample())

                # Environment step
                observations, rewards, done, info = env.step(actions)

                # Update scores
                for i in range(2):
                    agent_scores[i] += rewards[i]

                # Record frame if needed
                if self.record_replay and step_count % 10 == 0:  # Record every 10th frame
                    replay_frames.append({
                        "frame": step_count,
                        "observations": [obs.tolist() if hasattr(obs, "tolist") else obs 
                                       for obs in observations],
                        "actions": actions,
                        "rewards": rewards,
                        "done": done,
                    })

                # Log progress periodically
                if step_count % 100 == 0:
                    logger.info(f"Step {step_count}: Scores = {agent_scores}")

        except Exception as e:
            logger.error(f"Match loop error: {e}", exc_info=True)
            return {
                "match_id": self.match_id,
                "status": "error",
                "error_message": f"Match loop failed: {e}",
            }

        # Determine winner
        winner_agent_id = None
        if agent_scores[0] > agent_scores[1]:
            winner_agent_id = self.agents[0]["agent_id"]
        elif agent_scores[1] > agent_scores[0]:
            winner_agent_id = self.agents[1]["agent_id"]
        # else: draw

        # Save replay
        replay_url = None
        if self.record_replay and replay_frames:
            replay_url = self._save_replay(replay_frames)

        result = {
            "match_id": self.match_id,
            "status": "success",
            "winner_agent_id": winner_agent_id,
            "agent_results": [
                {
                    "agent_id": self.agents[i]["agent_id"],
                    "score": agent_scores[i],
                    "errors": agent_errors[i],
                }
                for i in range(2)
            ],
            "total_steps": step_count,
            "replay_url": replay_url,
        }

        return result

    def _save_replay(self, frames: List[Dict[str, Any]]) -> str:
        """Save replay to file."""
        replay_file = self.replay_dir / f"{self.match_id}.json"
        self.replay_dir.mkdir(parents=True, exist_ok=True)

        replay_data = {
            "match_id": self.match_id,
            "environment": self.environment,
            "agents": self.agents,
            "frames": frames,
        }

        with open(replay_file, "w") as f:
            json.dump(replay_data, f)

        logger.info(f"Saved replay to {replay_file}")
        return str(replay_file)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run RL Arena match")
    parser.add_argument(
        "--config", required=True, help="Path to match config JSON"
    )
    args = parser.parse_args()

    # Load config
    with open(args.config, "r") as f:
        config = json.load(f)

    # Run match
    orchestrator = MatchOrchestrator(config)
    result = asyncio.run(orchestrator.run_match())

    # Print result as JSON (last line for easy parsing)
    print(json.dumps(result))

    # Exit with appropriate code
    if result["status"] == "success":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
