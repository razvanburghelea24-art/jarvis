"""Adapter package — READ-ONLY surfaces only."""

from .base import ReadOnlyAdapter
from .discord import DiscordAdapter
from .framework import FrameworkAdapter
from .github import GitHubAdapter
from .n8n import N8nAdapter
from .railway import RailwayAdapter

__all__ = [
    "DiscordAdapter",
    "FrameworkAdapter",
    "GitHubAdapter",
    "N8nAdapter",
    "RailwayAdapter",
    "ReadOnlyAdapter",
]
