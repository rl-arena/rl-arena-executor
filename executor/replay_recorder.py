"""
Replay recording module for match data.
"""

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from executor.config import get_config
from executor.utils import save_json

logger = logging.getLogger(__name__)


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

        # Filter data based on config
        obs_data = observations if self.include_observations else {}
        action_data = actions if self.include_actions else {}

        frame = FrameData(
            frame_number=frame_number,
            timestamp=time.time(),
            observations=obs_data,
            actions=action_data,
            rewards=rewards,
            done=done,
            info=info or {},
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

    def save(self, output_path: Optional[str] = None) -> str:
        """
        Save replay data to file.

        Args:
            output_path: Output file path (optional)

        Returns:
            Path to saved replay file
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

        save_json(replay_data, output_path, indent=2 if not self.config.replay_compress else None)

        logger.info(f"Saved replay to {output_path}")
        return output_path

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
