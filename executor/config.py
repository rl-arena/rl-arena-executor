"""
Configuration management for the executor service.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class Config:
    """Configuration manager for executor service."""

    def __init__(self, config_path: Optional[str] = None) -> None:
        """
        Initialize configuration.

        Args:
            config_path: Path to config file. If None, uses default config/limits.yaml
        """
        if config_path is None:
            config_path = self._find_config_file()

        self.config_path = config_path
        self.config_data = self._load_config()

    def _find_config_file(self) -> str:
        """Find the default config file."""
        # Try multiple locations
        possible_paths = [
            Path(__file__).parent.parent / "config" / "limits.yaml",
            Path.cwd() / "config" / "limits.yaml",
            Path("/app/config/limits.yaml"),
        ]

        for path in possible_paths:
            if path.exists():
                return str(path)

        raise FileNotFoundError("Could not find config/limits.yaml")

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to load config from {self.config_path}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key.

        Args:
            key: Configuration key (supports dot notation, e.g., "resource_limits.cpu_count")
            default: Default value if key not found

        Returns:
            Configuration value
        """
        keys = key.split(".")
        value = self.config_data

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    # Resource limits
    @property
    def cpu_count(self) -> int:
        """Get CPU count limit."""
        return self.get("resource_limits.cpu_count", 1)

    @property
    def memory_limit(self) -> str:
        """Get memory limit."""
        return self.get("resource_limits.memory_limit", "512m")

    @property
    def step_timeout_sec(self) -> int:
        """Get step timeout in seconds."""
        return self.get("resource_limits.step_timeout_sec", 5)

    @property
    def match_timeout_sec(self) -> int:
        """Get match timeout in seconds."""
        return self.get("resource_limits.match_timeout_sec", 300)

    @property
    def init_timeout_sec(self) -> int:
        """Get initialization timeout in seconds."""
        return self.get("resource_limits.init_timeout_sec", 30)

    # Sandbox settings
    @property
    def use_docker(self) -> bool:
        """Whether to use Docker for sandboxing."""
        return self.get("sandbox.use_docker", True)

    @property
    def docker_image(self) -> str:
        """Get Docker image for sandbox."""
        return self.get("sandbox.docker_image", "python:3.10-slim")

    @property
    def tmp_dir(self) -> str:
        """Get temporary directory path."""
        return self.get("sandbox.tmp_dir", "/tmp/agent_code")

    @property
    def replay_dir(self) -> str:
        """Get replay directory path."""
        return self.get("sandbox.replay_dir", "/tmp/replays")

    # Validation settings
    @property
    def max_code_size_mb(self) -> int:
        """Get maximum code size in MB."""
        return self.get("sandbox.max_code_size_mb", 50)

    @property
    def allowed_extensions(self) -> list[str]:
        """Get allowed file extensions."""
        return self.get("validation.allowed_extensions", [".py"])

    @property
    def forbidden_imports(self) -> list[str]:
        """Get forbidden import statements."""
        return self.get("validation.forbidden_imports", [])

    # Replay settings
    @property
    def replay_format(self) -> str:
        """Get replay format (json or html)."""
        return self.get("replay.format", "json")

    @property
    def replay_compress(self) -> bool:
        """Whether to compress replay files."""
        return self.get("replay.compress", True)

    @property
    def max_frames(self) -> int:
        """Get maximum frames to record."""
        return self.get("replay.max_frames", 10000)

    # Logging
    @property
    def log_level(self) -> str:
        """Get logging level."""
        return self.get("logging.level", "INFO")

    @property
    def log_format(self) -> str:
        """Get logging format."""
        return self.get("logging.format", "json")


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get global config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def set_config(config: Config) -> None:
    """Set global config instance."""
    global _config
    _config = config
