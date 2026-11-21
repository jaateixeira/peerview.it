"""Finds installed plugins through the `peerview.plugins` entry-point group."""

from __future__ import annotations

from importlib.metadata import entry_points

from peerview.application.allocation import AllocationStrategy
from peerview.application.artifacts import ArtifactType
from peerview.application.criteria import CriterionType

GROUP = "peerview.plugins"


def discover_artifact_types() -> list[ArtifactType]:
    """One instance of every installed plugin that implements the ArtifactType API."""
    found: list[ArtifactType] = []
    for entry in sorted(entry_points(group=GROUP), key=lambda e: e.name):
        plugin = entry.load()()
        if isinstance(plugin, ArtifactType):
            found.append(plugin)
    return found


def discover_criterion_types() -> list[CriterionType]:
    """One instance of every installed plugin that implements the CriterionType API."""
    found: list[CriterionType] = []
    for entry in sorted(entry_points(group=GROUP), key=lambda e: e.name):
        plugin = entry.load()()
        if isinstance(plugin, CriterionType):
            found.append(plugin)
    return found


def discover_allocation_strategies() -> list[AllocationStrategy]:
    """One instance of every installed plugin that implements the AllocationStrategy API."""
    found: list[AllocationStrategy] = []
    for entry in sorted(entry_points(group=GROUP), key=lambda e: e.name):
        plugin = entry.load()()
        if isinstance(plugin, AllocationStrategy):
            found.append(plugin)
    return found
