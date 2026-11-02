"""Offline Trackmania 2020 research SDK. Not a complete game physics engine."""
from .geometry import PartialCollisionWorld
from .replays import ReplayTrajectory, MapLayout, ReplayCorpus
__all__ = ["PartialCollisionWorld","ReplayTrajectory","MapLayout","ReplayCorpus"]
