"""
Replay recording module for match data.

This module records match replays in a format compatible with rl-arena-env,
ensuring that users see the same visualization during training and competition.
"""

import json
import logging
import time
import numpy as np
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import rl_arena
from rl_arena.utils.replay import replay_to_html

from executor.config import get_config
from executor.utils import save_json

logger = logging.getLogger(__name__)


def _make_json_serializable(obj: Any) -> Any:
    """
    Convert numpy arrays and other non-serializable objects to JSON-serializable format.
    
    Args:
        obj: Object to convert
        
    Returns:
        JSON-serializable version of the object
    """
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_make_json_serializable(item) for item in obj]
    elif isinstance(obj, (np.integer, np.floating)):
        return obj.item()
    else:
        return obj


@dataclass
class FrameData:
    """Data for a single frame of the match."""

    frame_number: int
    timestamp: float
    observations: Dict[str, Any]
    actions: Dict[str, Any]
    rewards: Dict[str, float]
    done: bool
    info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchMetadata:
    """Metadata about the match."""

    match_id: str
    environment: str
    agents: List[Dict[str, str]]
    start_time: float
    end_time: Optional[float] = None
    total_steps: int = 0
    winner: Optional[str] = None
    status: str = "running"


class ReplayRecorder:
    """Records match replay data frame by frame."""

    def __init__(self, match_id: str, environment: str, agents: List[Dict[str, str]]) -> None:
        """
        Initialize replay recorder.

        Args:
            match_id: Unique match identifier
            environment: Environment name
            agents: List of agent metadata
        """
        self.config = get_config()
        self.match_id = match_id
        self.environment = environment

        # Initialize metadata
        self.metadata = MatchMetadata(
            match_id=match_id,
            environment=environment,
            agents=agents,
            start_time=time.time(),
        )

        # Frame storage
        self.frames: List[FrameData] = []
        self.max_frames = self.config.max_frames
        self.include_observations = self.config.get("replay.include_observations", True)
        self.include_actions = self.config.get("replay.include_actions", True)

        logger.info(f"Initialized replay recorder for match {match_id}")

    def record_frame(
        self,
        frame_number: int,
        observations: Dict[str, Any],
        actions: Dict[str, Any],
        rewards: Dict[str, float],
        done: bool,
        info: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record a single frame of the match.

        Args:
            frame_number: Frame number (step count)
            observations: Environment observations for each agent
            actions: Actions taken by each agent
            rewards: Rewards received by each agent
            done: Whether the episode is done
            info: Additional info dictionary
        """
        if len(self.frames) >= self.max_frames:
            logger.warning(f"Max frames ({self.max_frames}) reached, skipping frame")
            return

        # Filter data based on config and convert to JSON-serializable format
        obs_data = _make_json_serializable(observations) if self.include_observations else {}
        action_data = _make_json_serializable(actions) if self.include_actions else {}
        rewards_data = _make_json_serializable(rewards)
        info_data = _make_json_serializable(info or {})

        frame = FrameData(
            frame_number=frame_number,
            timestamp=time.time(),
            observations=obs_data,
            actions=action_data,
            rewards=rewards_data,
            done=done,
            info=info_data,
        )

        self.frames.append(frame)

    def finalize(
        self, winner: Optional[str] = None, status: str = "completed"
    ) -> None:
        """
        Finalize the recording with final metadata.

        Args:
            winner: Winner agent ID (None for draw)
            status: Final match status
        """
        self.metadata.end_time = time.time()
        self.metadata.total_steps = len(self.frames)
        self.metadata.winner = winner
        self.metadata.status = status

        logger.info(
            f"Finalized replay for match {self.match_id}: "
            f"{self.metadata.total_steps} frames, winner: {winner}"
        )

    def save(self, output_path: Optional[str] = None, save_html: bool = True) -> Dict[str, str]:
        """
        Save replay data to file(s).

        Args:
            output_path: Output file path for JSON (optional)
            save_html: Whether to also generate and save HTML replay (default: True)

        Returns:
            Dictionary with paths: {"json": "path/to/file.json", "html": "path/to/file.html"}
        """
        if output_path is None:
            replay_dir = Path(self.config.replay_dir)
            replay_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(replay_dir / f"{self.match_id}.json")

        replay_data = {
            "metadata": asdict(self.metadata),
            "frames": [asdict(frame) for frame in self.frames],
            "version": "1.0",
        }

        # Save JSON replay
        save_json(replay_data, output_path, indent=2 if not self.config.replay_compress else None)
        logger.info(f"Saved JSON replay to {output_path}")

        result = {"json": output_path}

        # Save HTML replay (Kaggle-style visualization)
        if save_html:
            html_path = str(Path(output_path).with_suffix(".html"))
            try:
                html_content = self.to_html()
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                result["html"] = html_path
                logger.info(f"Saved HTML replay to {html_path}")
            except Exception as e:
                logger.warning(f"Failed to generate HTML replay: {e}")

        return result

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert replay to dictionary.

        Returns:
            Replay data as dictionary
        """
        return {
            "metadata": asdict(self.metadata),
            "frames": [asdict(frame) for frame in self.frames],
            "version": "1.0",
        }

    def to_html(self) -> str:
        """
        Generate HTML5 replay using rl-arena-env's renderer.

        This ensures that the competition replay visualization matches
        what users see during training with rl-arena-env.

        Returns:
            Complete HTML string with embedded JavaScript animation

        Raises:
            ValueError: If environment is not supported for HTML rendering
        """
        # Convert executor replay format to rl-arena-env format
        recording = self._to_rl_arena_format()

        # Use rl-arena-env's replay_to_html function
        # This guarantees identical visualization between training and competition
        html = replay_to_html(
            recording=recording,
            env_name=self.environment,
            output_path=None,  # Don't save to file, just return HTML
        )

        return html

    def _to_rl_arena_format(self) -> Dict[str, Any]:
        """
        Convert executor replay format to rl-arena-env recording format.

        Executor format:
        {
            "metadata": {...},
            "frames": [
                {
                    "frame_number": 0,
                    "timestamp": 1234.5,
                    "observations": {...},
                    "actions": {...},
                    "rewards": {...},
                    "done": false,
                    "info": {...}
                }
            ]
        }

        rl-arena-env format:
        {
            "metadata": {...},
            "frames": [
                {
                    "step": 0,
                    "state": {...},  # observations
                    "actions": [...],
                    "rewards": [...],
                    "info": {...}
                }
            ],
            "num_frames": 100,
            "duration": 12.5,
            "start_time": "2024-01-01T00:00:00",
            "end_time": "2024-01-01T00:00:12"
        }

        Returns:
            Recording in rl-arena-env format
        """
        # Convert frames
        converted_frames = []
        for frame in self.frames:
            converted_frame = {
                "step": frame.frame_number,
                "state": frame.observations,  # observations → state
            }

            # Add optional fields
            if frame.actions:
                # Convert dict to list for rl-arena-env compatibility
                converted_frame["actions"] = list(frame.actions.values())

            if frame.rewards:
                # Convert dict to list
                converted_frame["rewards"] = list(frame.rewards.values())

            if frame.info:
                converted_frame["info"] = frame.info

            converted_frames.append(converted_frame)

        # Build metadata
        metadata = {
            "environment": self.metadata.environment,
            "match_id": self.metadata.match_id,
            "agents": self.metadata.agents,
        }

        # Calculate duration
        duration = None
        if self.metadata.end_time and self.metadata.start_time:
            duration = self.metadata.end_time - self.metadata.start_time

        return {
            "metadata": metadata,
            "frames": converted_frames,
            "num_frames": len(converted_frames),
            "duration": duration,
            "start_time": time.strftime(
                "%Y-%m-%dT%H:%M:%S", time.localtime(self.metadata.start_time)
            ),
            "end_time": (
                time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.metadata.end_time))
                if self.metadata.end_time
                else None
            ),
        }

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics of the replay.

        Returns:
            Summary dictionary
        """
        if not self.frames:
            return {"total_frames": 0, "duration": 0}

        duration = (
            self.metadata.end_time - self.metadata.start_time
            if self.metadata.end_time
            else time.time() - self.metadata.start_time
        )

        # Calculate agent statistics
        agent_stats = {}
        for agent in self.metadata.agents:
            agent_id = agent["agent_id"]
            total_reward = sum(
                frame.rewards.get(agent_id, 0) for frame in self.frames
            )
            agent_stats[agent_id] = {
                "total_reward": total_reward,
                "avg_reward": total_reward / len(self.frames) if self.frames else 0,
            }

        return {
            "match_id": self.match_id,
            "total_frames": len(self.frames),
            "duration_sec": duration,
            "winner": self.metadata.winner,
            "status": self.metadata.status,
            "agent_stats": agent_stats,
        }


def load_replay(file_path: str) -> Dict[str, Any]:
    """
    Load replay data from file.

    Args:
        file_path: Path to replay file

    Returns:
        Replay data dictionary
    """
    with open(file_path, "r") as f:
        return json.load(f)
