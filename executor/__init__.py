"""
RL Arena Executor

A secure execution environment for running RL agent matches.
"""

__version__ = "0.1.0"
__author__ = "RL Arena Team"

from executor.config import Config
from executor.match_runner import MatchRunner
from executor.sandbox import Sandbox
from executor.validation import AgentValidator

__all__ = [
    "Config",
    "MatchRunner",
    "Sandbox",
    "AgentValidator",
]
